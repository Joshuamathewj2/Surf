import json
import re
import requests
import config

def plan_actions(command: str) -> list:
    """
    Calls the local Ollama API to convert a natural language command
    into a list of desktop automation actions.
    """
    prompt = f"""You are a Windows desktop automation assistant. Convert the user's command into a JSON array of actions.

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

    try:
        response = requests.post(
            config.OLLAMA_URL,
            json={
                "model": config.MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 300,
                    "temperature": 0.1   # Low temp = more deterministic / less hallucination
                }
            }
        )
        response.raise_for_status()
        result = response.json()
        output_text = result.get('response', '').strip()

        # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
        output_text = re.sub(r'^```(?:json)?\s*', '', output_text, flags=re.IGNORECASE)
        output_text = re.sub(r'\s*```$', '', output_text)
        output_text = output_text.strip()

        # Remove single-line // comments (invalid in JSON)
        output_text = re.sub(r'//[^\n]*', '', output_text)

        # Remove trailing commas before ] or } (common LLM mistake)
        output_text = re.sub(r',\s*([\]\}])', r'\1', output_text)

        # Extract first JSON array from text
        json_match = re.search(r'\[.*\]', output_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = output_text

        actions = json.loads(json_str)

        if isinstance(actions, list):
            return actions
        elif isinstance(actions, dict):
            for key in ("actions", "steps", "plan"):
                if key in actions and isinstance(actions[key], list):
                    return actions[key]

        print("Error: Could not extract a valid JSON array from LLM response.")
        return []

    except json.JSONDecodeError as je:
        print(f"Failed to parse JSON from LLM output: {je}")
        print(f"Raw Output:\n{output_text}")
        return []
    except requests.RequestException as e:
        if getattr(e.response, "status_code", None) == 404:
            print(f"Error: Model '{config.MODEL_NAME}' not found in Ollama. Run 'ollama pull {config.MODEL_NAME}' first.")
        else:
            print(f"Error communicating with Ollama: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error in planner: {e}")
        return []
