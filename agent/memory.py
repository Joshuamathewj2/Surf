"""
agent/memory.py
Context memory. Stores last 10 commands and results in JSON.
"""
import json
import os

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.json")
MAX_HISTORY = 10

def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return []

def save_memory(history):
    with open(MEMORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

def add_to_memory(command: str, result: str):
    history = load_memory()
    history.append({"command": command, "result": result})
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    save_memory(history)

def get_context_string() -> str:
    history = load_memory()
    if not history:
        return ""
    ctx = "\nRecent history context:\n"
    for item in history:
        ctx += f"- User: {item['command']} -> Result: {item['result']}\n"
    return ctx
