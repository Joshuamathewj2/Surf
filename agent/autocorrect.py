from rapidfuzz import process

COMMON_FIXES = {
    "crome": "chrome", "chorme": "chrome",
    "yutube": "youtube", "you tube": "youtube",
    "serch": "search", "goggle": "google",
    "screenshoot": "screenshot", "volumne": "volume",
    "notepadd": "notepad", "expolrer": "explorer"
}

VOCAB = [
    "chrome", "youtube", "search", "open", "close",
    "google", "screenshot", "volume", "mute", "notepad",
    "explorer", "calculator", "whiteboard", "vscode", "click"
]

def correct_command(text: str):
    text = text.lower()

    for wrong, correct in COMMON_FIXES.items():
        text = text.replace(wrong, correct)

    words = text.split()
    corrected = []

    for w in words:
        match = process.extractOne(w, VOCAB)
        if match and match[1] > 90:
            corrected.append(match[0])
        else:
            corrected.append(w)

    return " ".join(corrected)
