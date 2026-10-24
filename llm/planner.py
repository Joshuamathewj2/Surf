"""
llm/planner.py
Local LLM (Ollama) features:
  - plan_actions(): natural language -> validated list of desktop actions
  - ask():          short spoken answer, aware of the conversation so far
  - transform():    summarise / translate / explain a piece of text
  - compose():      text to type (emails, notes, poems...)
  - warm_up():      load the model in the background so the first request isn't slow

Planner output is validated against an allowlist. The model can never run shell
commands: an LLM that mishears "list files" must not be able to execute anything.
"""
import datetime
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
    "set_timer": {"seconds": (int, float)},
    "media": {"command": str},
    "weather": {},
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
{"action":"set_timer","seconds":300}
{"action":"media","command":"play_pause|next|previous"}
{"action":"weather"}
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


def _chat(messages: list[dict], *, max_tokens: int, temperature: float) -> str | None:
    """Multi-turn generation (used for answers, so follow-up questions have context)."""
    if not _ollama_is_running():
        logger.error("Ollama is not running. Start it with: ollama serve")
        return None
    payload: dict[str, Any] = {
        "model": config.MODEL_NAME,
        "messages": messages,
        "stream": False,
        "keep_alive": config.LLM_KEEP_ALIVE,
        "options": {"num_predict": max_tokens, "temperature": temperature},
    }
    try:
        r = requests.post(f"{config.OLLAMA_HOST}/api/chat", json=payload, timeout=config.LLM_TIMEOUT)
        if r.status_code == 404:
            logger.error(f"Model '{config.MODEL_NAME}' not found. Run: ollama pull {config.MODEL_NAME}")
            return None
        r.raise_for_status()
        return (r.json().get("message") or {}).get("content", "").strip()
    except requests.Timeout:
        logger.error(f"Ollama took longer than {config.LLM_TIMEOUT:.0f}s.")
    except requests.RequestException as e:
        logger.error(f"Ollama request failed: {e}")
    return None


def _answer_system(personal: str = "", reference: str = "") -> str:
    now = datetime.datetime.now()
    lines = [
        "You are Surf, a friendly, concise voice assistant on the user's Windows PC (like Siri).",
        "Answer in at most two or three short sentences of plain spoken English: no markdown, lists, "
        "emojis or URLs. Be warm but get to the point. Use the earlier conversation to resolve follow-ups "
        "like 'he', 'it' or 'what about tomorrow'.",
        f"Right now it is {now.strftime('%A, %d %B %Y, %I:%M %p')}.",
    ]
    if config.HOME_CITY:
        lines.append(f"The user lives in {config.HOME_CITY}.")
    if personal:
        lines.append(personal)
    if reference:
        lines.append(
            "Reference text from Wikipedia, which may help (prefer it over your own memory for facts, "
            f"ignore it if it is about something else):\n{reference}"
        )
    else:
        lines.append("If the question needs live data you don't have (prices, scores, today's news), say so briefly.")
    return "\n".join(lines)


def ask(question: str, history: list[dict] | None = None, personal: str = "", reference: str = "") -> str | None:
    """Short spoken answer. `history` = earlier chat turns, `personal` = what Surf remembers
    about the user, `reference` = text fetched from the web to ground the answer."""
    messages = [{"role": "system", "content": _answer_system(personal, reference)}]
    messages += (history or [])[-12:]
    messages.append({"role": "user", "content": question})
    answer = _chat(messages, max_tokens=160, temperature=0.4)
    return _plain(answer) if answer else None


def transform(instruction: str, text: str) -> str | None:
    """Do something to a piece of text: summarise it, translate it, explain it..."""
    out = _generate(
        f"{instruction}\n\nText:\n{text[:6000]}",
        "You help with text the user copied. Reply in plain spoken English (no markdown), at most "
        "four sentences, unless the instruction asks for a translation, which should be complete.",
        json_mode=False,
        max_tokens=300,
        temperature=0.3,
    )
    return _plain(out) if out else None


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
