"""
agent/router.py
Routes user commands to either a direct action (fast, no LLM)
or the LLM planner (for complex/unknown commands).
"""

import re

# ── Known application shortcuts (keyword → app name for open_app) ──────────
APP_KEYWORDS = {
    "spotify": "spotify",
    "notepad": "notepad",
    "calculator": "calc",
    "excel": "excel",
    "word": "winword",
    "powerpoint": "powerpnt",
    "vlc": "vlc",
    "vs code": "code",
    "vscode": "code",
    "file explorer": "explorer",
    "explorer": "explorer",
    "cmd": "cmd",
    "terminal": "cmd",
    "paint": "mspaint",
    "task manager": "taskmgr",
    "whiteboard": "Microsoft Whiteboard"
}

def extract_query(command: str, trigger_phrases: list) -> str:
    cmd = command.lower()
    # Try regex match if it contains regex capture group
    for pattern in trigger_phrases:
        if "(" in pattern:
            m = re.search(pattern, cmd)
            if m:
                return m.group(1).strip()
        else:
            if cmd.startswith(pattern):
                return cmd.replace(pattern, "", 1).strip()
            elif pattern in cmd:
                return cmd.split(pattern)[-1].strip()
    return ""

def extract_vision_click(command: str) -> str:
    cmd = command.lower()
    if "click " in cmd:
        parts = cmd.split("click ", 1)
        if len(parts) > 1:
            return parts[1].strip().strip('"').strip("'")
    return ""

def route_command(command: str) -> dict:
    cmd = command.lower()

    # ── Vision Click ──────────────────────────────────────────────────────
    if cmd.startswith("click "):
        target = cmd.replace("click ", "").strip()
        return {"type": "direct", "action": "click_text", "target": target}
    if ("hey surf" in cmd or "hey sir" in cmd) and "click" in cmd:
        target = extract_vision_click(cmd)
        if target:
            return {"type": "direct", "action": "click_text", "target": target}

    # ── Screenshot ────────────────────────────────────────────────────────
    if "screenshot" in cmd or "screen shot" in cmd:
        return {"type": "direct", "action": "take_screenshot"}

    # ── System Controls ───────────────────────────────────────────────────
    if "volume up" in cmd:
        return {"type": "direct", "action": "volume_up"}
    if "volume down" in cmd:
        return {"type": "direct", "action": "volume_down"}
    if "mute" in cmd:
        return {"type": "direct", "action": "mute_audio"}

    # ── Google search ─────────────────────────────────────────────────────
    if "google" in cmd and not cmd.startswith("open"):
        query = extract_query(cmd, ["search google for ", "google "])
        if query:
            return {"type": "direct", "action": "google_search", "query": query}

    # ── YouTube search ────────────────────────────────────────────────────
    if "youtube" in cmd and any(k in cmd for k in ["search", "play", "find"]):
        query = extract_query(cmd, [r"search youtube for (.+)", r"youtube search (?:for )?(.+)", r"play (.+) on youtube", "search youtube"])
        return {"type": "direct", "action": "youtube_search", "query": query}

    # ── Browser Control ───────────────────────────────────────────────────
    if "open youtube" in cmd:
        return {"type": "direct", "action": "open_url", "url": "https://youtube.com"}
    if "open new tab" in cmd:
        return {"type": "direct", "action": "new_browser_tab"}
    if "close tab" in cmd:
        return {"type": "direct", "action": "close_browser_tab"}

    # ── Spotify play ──────────────────────────────────────────────────────
    if "spotify" in cmd and "play" in cmd:
        query = extract_query(cmd, [r"play (.+) on spotify", r"play (.+) in spotify", r"spotify play (.+)", r"open spotify and play (.+)"])
        query = query.replace('"', '').replace('song', '').strip()
        if query:
            return {"type": "direct", "action": "play_spotify", "query": query}

    # ── App Launching ─────────────────────────────────────────────────────
    if "open" in cmd:
        if "notepad" in cmd:
            return {"type": "direct", "action": "open_app", "app": "notepad"}
        if "vscode" in cmd or "vs code" in cmd:
            return {"type": "direct", "action": "open_app", "app": "code"}
        if "whiteboard" in cmd:
            return {"type": "direct", "action": "open_app", "app": "Microsoft Whiteboard"}
        if "file explorer" in cmd or "explorer" in cmd:
            return {"type": "direct", "action": "open_app", "app": "explorer"}
        if "calculator" in cmd:
            return {"type": "direct", "action": "open_app", "app": "calc"}
        if "chrome" in cmd and "spotify" not in cmd:
            return {"type": "direct", "action": "open_chrome"}

        # Catch-all for app launching via app_index
        if cmd.startswith("open "):
            target = cmd.replace("open ", "").strip()
            return {"type": "direct", "action": "open_app", "app": target}

    # ── Web/n8n Tasks ─────────────────────────────────────────────────────
    n8n_keywords = ["notify me", "send message", "message", "create notion"]
    if any(k in cmd for k in n8n_keywords):
        return {"type": "direct", "action": "trigger_n8n", "workflow": "surf_default", "payload": {"command": command}}

    # ── Close Chrome ──────────────────────────────────────────────────────
    if "close" in cmd and "chrome" in cmd:
        return {"type": "direct", "action": "close_chrome"}

    # Fall through: let the LLM planner handle everything else
    return {"type": "llm"}
