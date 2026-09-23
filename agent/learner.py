"""
agent/learner.py
Command learning module. Builds personal shortcuts over time based on successes.
"""
import json
import os

LEARNING_FILE = os.path.join(os.path.dirname(__file__), "learned.json")

def _load():
    if os.path.exists(LEARNING_FILE):
        try:
            with open(LEARNING_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {}

def learn_command(trigger: str, action_sequence: list):
    data = _load()
    data[trigger] = action_sequence
    with open(LEARNING_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[Learner] Learned route: {trigger}")

def get_learned_route(command: str):
    data = _load()
    return data.get(command)
