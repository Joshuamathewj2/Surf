BLOCKED = ["delete", "format", "shutdown", "remove all"]

def is_safe(command: str):
    cmd = command.lower()
    return not any(word in cmd for word in BLOCKED)
