"""
llm/planner.py
Calls the local Ollama API to convert natural-language commands into
desktop-automation action lists.

If Ollama is not running, the function returns an empty list and prints a
clear, actionable message instead of a cryptic WinError 10061.
"""
import json
import re
import requests
# Use core.config (the rebuilt version) — NOT the legacy root config.py
from core import config
from core.logger import get_logger

logger = get_logger("planner")

# ── Ollama health-check ───────────────────────────────────────────────────────
def _ollama_is_running() -> bool:
    """
    Pings Ollama's tags endpoint to verify the daemon is up.
    Returns True if reachable, False otherwise.
    This runs in < 200ms and prevents the 10-second hang that WinError 10061 causes.
    """
    try:
        resp = requests.get(
            "http://localhost:11434/api/tags",
            timeout=1.5         # 1.5s — fail fast
        )
        return resp.status_code == 200
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────────────────────

_PROMPT_TEMPLATE = """You are a Windows desktop automation assistant. Convert the user's command into a JSON array of actions.

SUPPORTED ACTIONS (use ONLY these, no other keys or comments):
- {{"action": "open_app", "name": "<app name>"}}           — Open any app via Start menu
- {{"action": "run_command", "cmd": "<shell cmd>"}}        — Run a Windows shell command
- {{"action": "open_url", "url": "<full url>"}}            — Open a URL in browser
- {{"action": "open_start_menu"}}                          — Press the Windows key
- {{"action": "type", "text": "<text to type>"}}           — Type text
- {{"action": "press", "key": "<key>"}}                    — Press a key (enter, esc, tab, win, etc.)
- {{"action": "hotkey", "keys": ["ctrl", "l"]}}            — Press a keyboard shortcut
- {{"action": "wait", "seconds": <number>}}                — Wait N seconds
- {{"action": "click", "x": <int>, "y": <int>}}           — Click at screen coordinates
- {{"action": "scroll", "direction": "down", "amount": 3}} — Scroll up or down
- {{"action": "focus_window", "title": "<window title>"}}  — Bring a window to front
- {{"action": "take_screenshot"}}                          — Capture the screen
- {{"action": "youtube_search", "query": "<search term>"}} — Search YouTube in browser

RULES:
1. Output ONLY a valid JSON array. No markdown, no code fences, no comments, no explanation.
2. Do NOT use placeholder values like <X coordinate>. Use real numbers or omit the action.
3. For opening apps like Spotify, Notepad, Chrome — use "open_app" with the app name.
4. For playing music on Spotify, open it first then use the search hotkey and type the song.
5. Every value must be a concrete string or number. Never leave angle-bracket placeholders.

EXAMPLES:

Command: "open notepad and type hello"
[
  {{"action": "open_app", "name": "notepad"}},
  {{"action": "wait", "seconds": 1.5}},
  {{"action": "type", "text": "hello"}}
]

Command: "open spotify and play shape of you"
[
  {{"action": "open_app", "name": "spotify"}},
  {{"action": "wait", "seconds": 3}},
  {{"action": "hotkey", "keys": ["ctrl", "l"]}},
  {{"action": "wait", "seconds": 0.5}},
  {{"action": "type", "text": "shape of you"}},
  {{"action": "press", "key": "enter"}}
]

Command: "search youtube for lo-fi music"
[
  {{"action": "youtube_search", "query": "lo-fi music"}}
]

Command: "take a screenshot"
[
  {{"action": "take_screenshot"}}
]

Now convert this command:
"{command}"

Output ONLY the JSON array, nothing else:"""


def plan_actions(command: str) -> list:
    """
    Converts a natural-language command into a list of desktop automation actions
    by querying the local Ollama LLM.

    Returns [] if Ollama is down, the model is missing, or parsing fails.
    """
    # ── Fast pre-flight check ───────────────────────────────────────────────
    if not _ollama_is_running():
        logger.error(
            "Ollama is NOT running on localhost:11434.\n"
            "  ► To start it, open a terminal and run:  ollama serve\n"
            "  ► If ollama is not installed: https://ollama.ai\n"
            "  ► After starting, pull the model:  ollama pull phi3:mini"
        )
        print(
            "\n[Planner] ❌ Ollama is not running.\n"
            "  Fix: open a new terminal and run →  ollama serve\n"
            "  Then retry your command.\n"
        )
        return []

    prompt = _PROMPT_TEMPLATE.format(command=command)

    try:
        response = requests.post(
            config.OLLAMA_URL,
            json={
                "model": config.MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 300,
                    "temperature": 0.1   # Low temp = deterministic, fewer hallucinations
                }
            },
            timeout=config.LLM_TIMEOUT  # 6s default — prevents blocking the voice loop
        )
        response.raise_for_status()
        result = response.json()
        output_text = result.get('response', '').strip()

        # Strip markdown code fences if the model wrapped the output anyway
        output_text = re.sub(r'^```(?:json)?\s*', '', output_text, flags=re.IGNORECASE)
        output_text = re.sub(r'\s*```$', '', output_text)
        output_text = output_text.strip()

        # Remove single-line // comments (invalid in JSON but common LLM output)
        output_text = re.sub(r'//[^\n]*', '', output_text)

        # Remove trailing commas before ] or } (common LLM mistake)
        output_text = re.sub(r',\s*([\]\}])', r'\1', output_text)

        # Extract first JSON array from text
        json_match = re.search(r'\[.*\]', output_text, re.DOTALL)
        json_str = json_match.group(0) if json_match else output_text

        actions = json.loads(json_str)

        if isinstance(actions, list):
            return actions
        elif isinstance(actions, dict):
            for key in ("actions", "steps", "plan"):
                if key in actions and isinstance(actions[key], list):
                    return actions[key]

        logger.error("Could not extract a valid JSON array from LLM response.")
        return []

    except json.JSONDecodeError as je:
        logger.error(f"Failed to parse JSON from LLM output: {je}\nRaw: {output_text}")
        return []

    except requests.exceptions.Timeout:
        logger.error(f"Ollama request timed out after {config.LLM_TIMEOUT}s.")
        print(f"\n[Planner] ⏱ Ollama took too long (>{config.LLM_TIMEOUT}s). Try a simpler command or increase SURF_LLM_TIMEOUT.\n")
        return []

    except requests.RequestException as e:
        if getattr(getattr(e, 'response', None), 'status_code', None) == 404:
            logger.error(f"Model '{config.MODEL_NAME}' not found. Run: ollama pull {config.MODEL_NAME}")
            print(f"\n[Planner] ❌ Model '{config.MODEL_NAME}' not found in Ollama.\n  Fix: ollama pull {config.MODEL_NAME}\n")
        else:
            logger.error(f"Ollama request error: {e}")
        return []

    except Exception as e:
        logger.error(f"Unexpected planner error: {e}", exc_info=True)
        return []


