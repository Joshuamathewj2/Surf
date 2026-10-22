"""
llm/planner.py
Local LLM (Ollama) features:
  - plan_actions(): natural language -> validated list of desktop actions
  - ask():          short spoken answer to a question
  - compose():      text to type (emails, notes, poems...)
  - warm_up():      load the model in the background so the first request isn't slow

Planner output is validated against an allowlist. The model can never run shell
commands: an LLM that mishears "list files" must not be able to execute anything.
"""
import json
import re
import threading
from typing import Any

import requests

from core import config
from core.logger import get_logger

logger = get_logger("planner")

# action -> required fields and their types
ALLOWED_ACTIONS: dict[str, dict[str, type | tuple[type, ...]]] = {
    "open_app": {"name": str},
    "open_url": {"url": str},
    "youtube_search": {"query": str},
    "google_search": {"query": str},
    "type": {"text": str},
    "press": {"key": str},
    "hotkey": {"keys": list},
    "wait": {"seconds": (int, float)},
    "scroll": {"direction": str},
    "focus_window": {"title": str},
    "take_screenshot": {},
    "open_start_menu": {},
}
MAX_WAIT_SEC = 10
MAX_STEPS = 12

_SYSTEM = """You turn a user's spoken request into Windows desktop actions.
Reply with JSON only: {"actions": [ ... ]}. Use ONLY these actions:
{"action":"open_app","name":"<app>"}
{"action":"open_url","url":"https://..."}
{"action":"youtube_search","query":"<text>"}
{"action":"google_search","query":"<text>"}
{"action":"type","text":"<text to type>"}
{"action":"press","key":"enter|esc|tab|backspace|up|down|left|right|space"}
{"action":"hotkey","keys":["ctrl","s"]}
{"action":"wait","seconds":1.5}
{"action":"scroll","direction":"up|down"}
{"action":"focus_window","title":"<part of window title>"}
{"action":"take_screenshot"}
Rules: real values only, no placeholders. After open_app add a wait of 1.5-3 seconds before typing.
If the request cannot be done with these actions, reply {"actions": []}."""

_EXAMPLES = """Request: open notepad and type hello
{"actions":[{"action":"open_app","name":"notepad"},{"action":"wait","seconds":1.5},{"action":"type","text":"hello"}]}
Request: save this file
{"actions":[{"action":"hotkey","keys":["ctrl","s"]}]}
Request: play lofi beats on youtube
{"actions":[{"action":"youtube_search","query":"lofi beats"}]}"""


def _ollama_is_running() -> bool:
    """False only if nothing is listening. A slow reply means Ollama is busy, not down."""
    try:
        return requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=3).status_code == 200
    except requests.Timeout:
        return True
    except requests.RequestException:
        return False


def _generate(prompt: str, system: str, *, json_mode: bool, max_tokens: int, temperature: float) -> str | None:
    if not _ollama_is_running():
        logger.error("Ollama is not running. Start it with: ollama serve")
        return None
    payload: dict[str, Any] = {
        "model": config.MODEL_NAME,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "keep_alive": config.LLM_KEEP_ALIVE,
        "options": {"num_predict": max_tokens, "temperature": temperature},
    }
    if json_mode:
        payload["format"] = "json"
    try:
        r = requests.post(config.OLLAMA_URL, json=payload, timeout=config.LLM_TIMEOUT)
        if r.status_code == 404:
            logger.error(f"Model '{config.MODEL_NAME}' not found. Run: ollama pull {config.MODEL_NAME}")
            return None
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except requests.Timeout:
        logger.error(f"Ollama took longer than {config.LLM_TIMEOUT:.0f}s.")
    except requests.RequestException as e:
        logger.error(f"Ollama request failed: {e}")
    return None


def warm_up() -> None:
    """Load the model into memory in the background (first real request is then fast)."""

    def _run() -> None:
        if _generate("hi", "Reply with one word.", json_mode=False, max_tokens=1, temperature=0) is not None:
            logger.info(f"LLM '{config.MODEL_NAME}' is warm.")

    threading.Thread(target=_run, daemon=True, name="LLMWarmUp").start()


def validate_actions(raw: Any) -> list[dict[str, Any]]:
    """Keep only well-formed, allowlisted actions. Unknown or malformed steps are dropped."""
    if isinstance(raw, dict):
        raw = next((raw[k] for k in ("actions", "steps", "plan") if isinstance(raw.get(k), list)), [])
    if not isinstance(raw, list):
        return []
    valid: list[dict[str, Any]] = []
    for step in raw[:MAX_STEPS]:
        if not isinstance(step, dict):
            continue
        name = step.get("action")
        fields = ALLOWED_ACTIONS.get(name)
        if fields is None:
            logger.warning(f"Dropping non-allowlisted action from plan: {name!r}")
            continue
        ok = True
        if name == "wait" and isinstance(step.get("seconds"), str):
            try:  # small models often write "2" instead of 2
                step = {**step, "seconds": float(step["seconds"])}
            except ValueError:
                pass
        for field, kind in fields.items():
            value = step.get(field)
            if not isinstance(value, kind) or (isinstance(value, str) and (not value.strip() or re.fullmatch(r"<.*>", value.strip()))):
                ok = False
                break
        if not ok:
            logger.warning(f"Dropping malformed step: {step}")
            continue
        if name == "wait":
            step = {**step, "seconds": max(0.0, min(float(step["seconds"]), MAX_WAIT_SEC))}
        if name == "hotkey" and not all(isinstance(k, str) for k in step["keys"]):
            continue
        valid.append(step)
    return valid


def plan_actions(command: str) -> list[dict[str, Any]]:
    """Natural-language command -> validated action list ([] if Ollama is unavailable)."""
    text = _generate(
        f"{_EXAMPLES}\nRequest: {command}\n",
        _SYSTEM,
        json_mode=True,
        max_tokens=250,
        temperature=0.1,
    )
    if not text:
        return []
    try:
        return validate_actions(json.loads(text))
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}|\[.*\]", text, re.DOTALL)
        if match:
            try:
                return validate_actions(json.loads(match.group(0)))
            except json.JSONDecodeError:
                pass
        logger.error(f"Planner returned invalid JSON: {text[:200]}")
        return []


def ask(question: str) -> str | None:
    """Short answer suitable for speaking aloud."""
    answer = _generate(
        question,
        "You are Surf, a concise voice assistant. Answer in at most two short sentences of plain "
        "spoken English: no markdown, lists, or emojis. If you don't know or it needs live data "
        "(news, weather, prices), say so briefly.",
        json_mode=False,
        max_tokens=120,
        temperature=0.4,
    )
    return _plain(answer) if answer else None


def compose(request: str) -> str | None:
    """Text to type for requests like 'a short email to my manager saying I'll be late'."""
    text = _generate(
        f"Write {request}.",
        "Write exactly what was asked, ready to paste. No preamble, no title line unless asked, "
        "no markdown. Keep it short unless a length is given.",
        json_mode=False,
        max_tokens=350,
        temperature=0.7,
    )
    return text.strip().strip('"') if text else None


def _plain(text: str) -> str:
    text = re.sub(r"[*_#`>]+", "", text)
    return re.sub(r"\s+", " ", text).strip()
