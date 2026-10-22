"""
agent/autocorrect.py
Context-aware phonetic and typing autocorrect.
Normalizes common speech-to-text glitches without corrupting search queries or arguments.
"""
from rapidfuzz import process, fuzz
import re

PHRASE_FIXES = {
    "not bad": "notepad",
    "not pad": "notepad",
    "noted pad": "notepad",
    "note pad": "notepad",
    "crome": "chrome",
    "chorme": "chrome",
    "yutube": "youtube",
    "you tube": "youtube",
    "serch": "search",
    "goggle": "google",
    "screenshoot": "screenshot",
    "screen shoot": "screenshot",
    "volumne": "volume",
    "notepadd": "notepad",
    "expolrer": "explorer",
    "vs code": "vscode",
    "visual studio code": "vscode"
}

# Verbs and targets eligible for fuzzy correction
TARGET_KEYWORDS = [
    "chrome", "youtube", "search", "open", "close", "launch",
    "google", "screenshot", "volume", "mute", "notepad",
    "explorer", "calculator", "whiteboard", "vscode", "click", "spotify"
]

def correct_command(text: str) -> str:
    """
    Cleans up speech recognition artifacts while preserving search query entities.
    """
    if not text:
        return ""

    lowered = text.lower().strip()

    # 1. Apply multi-word phrase corrections first (whole words only, so "this is not bad"
    #    isn't rewritten unless it's the app name being asked for)
    for wrong, right in PHRASE_FIXES.items():
        if wrong in ("not bad", "not pad"):
            if lowered == wrong:
                lowered = right
            lowered = re.sub(rf"\b(open|launch|start|close)\s+{wrong}\b", rf"\1 {right}", lowered)
        else:
            lowered = re.sub(rf"\b{re.escape(wrong)}\b", right, lowered)

    # 2. Check if first word (the verb) is close to an action verb
    words = lowered.split()
    if not words:
        return lowered

    # Only correct the first 1-2 words (verb/intent context), leaving the rest (arguments) alone
    for idx in range(min(2, len(words))):
        w = words[idx]
        match = process.extractOne(w, TARGET_KEYWORDS, scorer=fuzz.ratio)
        if match and match[1] >= 88: # High confidence threshold
            words[idx] = match[0]

    return " ".join(words)
