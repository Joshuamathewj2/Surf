"""
agent/router.py
Robust Intent-Based Router with synonym canonicalization,
entity slot extraction, and multi-command parsing.
"""
import re
from typing import Dict, Any, List
from core.logger import get_logger

logger = get_logger("router")

# Synonym sets for command normalization
VERB_OPEN = {"open", "launch", "start", "bring up", "run", "switch to"}
VERB_CLOSE = {"close", "quit", "exit", "shut"}
VERB_PLAY = {"play", "listen to", "put on", "stream"}
VERB_SEARCH = {"search", "find", "look up", "google"}

def split_compound_command(command: str) -> List[str]:
    """
    Splits multi-step commands on conjunctions:
    e.g. 'open chrome and search lofi on youtube' -> ['open chrome', 'search lofi on youtube']
    """
    cmd = command.strip()
    # Normalize common joiners
    parts = re.split(r'\s+(?:and then|and|then)\s+', cmd, flags=re.IGNORECASE)
    cleaned = [p.strip() for p in parts if p.strip()]
    return cleaned if cleaned else [cmd]

def _parse_single_intent(cmd: str) -> Dict[str, Any]:
    norm = cmd.lower().strip()
    norm = re.sub(r'^[,\.\?!]+|[,\.\?!]+$', '', norm) # Trim punctuation

    # 1. Vision Click
    if norm.startswith("click "):
        target = norm[6:].strip().strip('"\'')
        return {"type": "direct", "action": "click_text", "target": target}

    # 2. Screenshot
    if any(k in norm for k in ["take screenshot", "screenshot", "screen shot", "capture screen"]):
        return {"type": "direct", "action": "take_screenshot"}

    # 3. Volume Controls
    if any(k in norm for k in ["volume up", "increase volume", "louder", "turn up volume", "raise volume"]):
        return {"type": "direct", "action": "volume_up"}
    if any(k in norm for k in ["volume down", "decrease volume", "lower volume", "quieter", "turn down volume"]):
        return {"type": "direct", "action": "volume_down"}
    if any(k in norm for k in ["mute audio", "unmute", "mute"]):
        return {"type": "direct", "action": "mute_audio"}

    # 4. Tab Controls
    if any(k in norm for k in ["new tab", "open a new tab", "open new tab"]):
        return {"type": "direct", "action": "new_tab"}
    if any(k in norm for k in ["close tab", "close this tab", "shut tab"]):
        return {"type": "direct", "action": "close_tab"}

    # 5. YouTube Queries
    # E.g. "search youtube for lofi", "play jazz on youtube", "search lofi on youtube", "open youtube"
    if "youtube" in norm:
        # Check if simply opening youtube
        if any(norm.startswith(f"{v} youtube") for v in VERB_OPEN) or norm == "open youtube":
            return {"type": "direct", "action": "open_youtube", "query": ""}
        
        # Extract query patterns
        m = re.search(r'(?:search youtube for|youtube search for|search (?:for )?|play )\s*(.+?)(?:\s+(?:on|in) youtube)?$', norm)
        if m:
            query = m.group(1).replace("on youtube", "").replace("in youtube", "").strip()
            if query:
                return {"type": "direct", "action": "youtube_search", "query": query}
        
        m2 = re.search(r'youtube\s+(?:search\s+)?(.+)', norm)
        if m2:
            query = m2.group(1).strip()
            return {"type": "direct", "action": "youtube_search", "query": query}

    # 6. Spotify Queries
    # E.g. "play bohemian rhapsody on spotify", "spotify play jazz"
    if "spotify" in norm:
        m = re.search(r'(?:play|listen to)\s+(.+?)(?:\s+on spotify|\s+in spotify)?$', norm)
        if m:
            query = m.group(1).replace("on spotify", "").replace("in spotify", "").strip()
            return {"type": "direct", "action": "play_spotify", "query": query}
        m2 = re.search(r'spotify\s+(?:play\s+)?(.+)', norm)
        if m2:
            query = m2.group(1).strip()
            return {"type": "direct", "action": "play_spotify", "query": query}
        if any(norm.startswith(f"{v} spotify") for v in VERB_OPEN):
            return {"type": "direct", "action": "play_spotify", "query": ""}

    # 7. Chrome Application Open/Close
    if "chrome" in norm:
        if any(norm.startswith(f"{v} chrome") for v in VERB_CLOSE):
            return {"type": "direct", "action": "close_chrome"}
        if any(norm.startswith(f"{v} chrome") for v in VERB_OPEN) or norm == "chrome":
            return {"type": "direct", "action": "open_chrome"}

    # 8. Notepad Open / Quick Notes
    if "notepad" in norm or "notes" in norm:
        if any(norm.startswith(f"{v} notepad") for v in VERB_OPEN) or norm == "notepad":
            return {"type": "direct", "action": "open_notepad"}
    
    # 9. Typing / Note creation
    if norm.startswith("type ") or norm.startswith("write "):
        content = re.sub(r'^(?:type|write)\s+', '', norm).strip()
        return {"type": "direct", "action": "type_text", "text": content}

    # 10. Google Web Search
    if "google" in norm and not any(norm.startswith(f"{v} google") for v in VERB_OPEN):
        m = re.search(r'(?:google search for|search google for|search for|google)\s+(.+)', norm)
        if m:
            query = m.group(1).strip()
            return {"type": "direct", "action": "google_search", "query": query}

    # 11. Generic URL Open
    if norm.startswith("open http://") or norm.startswith("open https://") or norm.startswith("open www."):
        url = norm.replace("open ", "", 1).strip()
        return {"type": "direct", "action": "open_url", "url": url}

    # 12. General App Launching (with synonym support)
    # E.g. "launch calculator", "start whiteboard", "open vscode"
    for verb in VERB_OPEN:
        if norm.startswith(f"{verb} "):
            target_app = norm[len(verb)+1:].strip()
            # If target app is notepad
            if target_app in ("notepad", "notes"):
                return {"type": "direct", "action": "open_notepad"}
            return {"type": "direct", "action": "open_app", "app": target_app}

    # 13. Fallback: LLM Planner
    return {"type": "llm"}

def route_command(command: str) -> Dict[str, Any]:
    """
    Routes command with multi-step conjunction support.
    """
    sub_commands = split_compound_command(command)

    if len(sub_commands) > 1:
        actions = []
        for sub_cmd in sub_commands:
            parsed = _parse_single_intent(sub_cmd)
            actions.append(parsed)
        return {
            "type": "multi",
            "actions": actions,
            "raw": command
        }
    
    return _parse_single_intent(sub_commands[0])
