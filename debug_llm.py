"""Quick script to see exactly what Mistral returns — writes to file."""
import requests, json

resp = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "mistral",
        "prompt": (
            'You are a desktop automation assistant. '
            'Convert the user command into a JSON array of actions.\n'
            'Supported actions:\n'
            '- {"action": "open_start_menu"}\n'
            '- {"action": "type", "text": "<text>"}\n'
            '- {"action": "press", "key": "<key>"}\n'
            '- {"action": "wait", "seconds": <int>}\n'
            '- {"action": "click", "x": <int>, "y": <int>}\n\n'
            'User command: "open notepad"\n\n'
            'Output ONLY a valid JSON array of action objects.'
        ),
        "stream": False,
        "format": "json",
    },
)
data = resp.json()
raw = data.get("response", "")

with open("debug_output.txt", "w") as f:
    f.write("=== RAW RESPONSE ===\n")
    f.write(raw + "\n\n")
    parsed = json.loads(raw)
    f.write(f"=== TYPE: {type(parsed).__name__} ===\n")
    f.write(json.dumps(parsed, indent=2) + "\n")

print("Saved to debug_output.txt")
