"""
agent/router.py
Fast, deterministic intent router. Handles the common commands in microseconds;
anything it can't map is sent to the LLM planner as a whole (type "llm").
"""
import re
from typing import Any, Dict, List

from core.logger import get_logger

logger = get_logger("router")

VERB_OPEN = ("open", "launch", "start", "bring up", "run", "switch to", "go to")
VERB_CLOSE = ("close", "quit", "exit", "shut")

# Words that may start a new sub-command after "and"/"then". Splitting only on these keeps
# queries like "play rock and roll on youtube" in one piece.
ACTION_STARTERS = (
    "open", "launch", "start", "run", "close", "quit", "search", "google", "look up", "find",
    "play", "type", "write", "take", "capture", "mute", "unmute", "volume", "turn", "increase",
    "decrease", "lower", "raise", "click", "new tab", "close tab", "go to", "switch to", "tell me",
    "what", "show", "save", "undo", "redo", "copy", "paste", "cut", "select", "refresh", "reload",
    "go back", "scroll", "zoom", "minimize", "minimise", "maximize", "maximise", "press", "print",
)

# Whole-utterance phrases for everyday keyboard actions (see skills/shortcut_skill.py).
SHORTCUT_PHRASES = [
    (r"save(?: (?:this|the|my) (?:file|document|work|page))?", "save"),
    (r"undo(?: that)?", "undo"),
    (r"redo(?: that)?", "redo"),
    (r"copy(?: (?:this|that|it|the selection))?", "copy"),
    (r"paste(?: (?:it|that|this))?", "paste"),
    (r"cut(?: (?:this|that|it))?", "cut"),
    (r"select (?:all|everything)", "select_all"),
    (r"find (?:on|in) (?:this |the )?page", "find"),
    (r"print(?: (?:this|the) (?:page|document))?", "print"),
    (r"(?:go |navigate )?back(?: a page)?|go to (?:the )?previous page|previous page", "go_back"),
    (r"(?:go )?forward(?: a page)?|next page", "go_forward"),
    (r"(?:refresh|reload)(?: (?:the|this) page)?", "refresh"),
    (r"(?:go to |switch to )?(?:the )?next tab", "next_tab"),
    (r"(?:go to |switch to )?(?:the )?previous tab", "previous_tab"),
    (r"switch (?:windows?|apps?)|(?:go to )?(?:the )?other window", "switch_window"),
    (r"minimi[sz]e(?: (?:this|the|it)(?: window)?)?", "minimize_window"),
    (r"maximi[sz]e(?: (?:this|the|it)(?: window)?)?", "maximize_window"),
    (r"show (?:the |my )?desktop", "show_desktop"),
    (r"close (?:this|the) (?:window|app)", "close_window"),
    (r"zoom in", "zoom_in"),
    (r"zoom out", "zoom_out"),
    (r"reset (?:the )?zoom", "reset_zoom"),
    (r"snap (?:this |the )?(?:window )?(?:to the )?left", "snap_left"),
    (r"snap (?:this |the )?(?:window )?(?:to the )?right", "snap_right"),
    (r"scroll up", "scroll_up"),
    (r"scroll down", "scroll_down"),
    (r"(?:press|hit) enter", "press_enter"),
    (r"(?:press|hit) escape", "press_escape"),
]
_SHORTCUTS = [(re.compile(rf"^(?:{p})$"), intent) for p, intent in SHORTCUT_PHRASES]

WAKE_PREFIXES = ("hey jarvis", "ok jarvis", "okay jarvis", "jarvis", "hey surf", "surf")
FILLER_PREFIXES = (
    "please", "can you", "could you", "would you", "will you", "i want you to", "i'd like you to",
    "i need you to", "go ahead and", "um", "uh", "okay", "ok", "so", "just", "now",
)

QUESTION_START = re.compile(
    r"^(?:what|who|whom|whose|why|how|when|where|which|is|are|was|were|do|does|did|can|could|"
    r"should|tell me|explain|define|describe|give me)\b"
)
COMPOSE_OBJECTS = (
    "poem", "email", "mail", "note", "story", "letter", "summary", "list", "paragraph", "essay",
    "message", "joke", "tweet", "haiku", "reply", "caption", "bio", "description",
)


def clean_utterance(text: str) -> str:
    """Lower-case, trim punctuation, and drop wake words and polite filler at the start."""
    norm = re.sub(r"\s+", " ", text.lower()).strip()
    norm = norm.strip(" ,.!?;:\"'")
    changed = True
    while changed and norm:
        changed = False
        for prefix in WAKE_PREFIXES + FILLER_PREFIXES:
            if norm == prefix:
                return ""
            if norm.startswith(prefix + " ") or norm.startswith(prefix + ","):
                norm = norm[len(prefix):].lstrip(" ,")
                changed = True
                break
    norm = re.sub(r"\s+(?:please|for me)$", "", norm)
    return norm.strip(" ,.!?;:")


def split_compound_command(command: str) -> List[str]:
    """
    'open chrome and search lofi on youtube' -> ['open chrome', 'search lofi on youtube'],
    but 'play rock and roll on youtube' stays whole (no action verb after "and").
    """
    starters = "|".join(re.escape(s) for s in ACTION_STARTERS)
    # "and then" / "then" / "after that" always mark a new step; a bare "and" only does
    # when an action verb follows it.
    pattern = rf"[,.]?\s+(?:and then|then|after that)\s+|[,.]?\s+and\s+(?=(?:{starters})\b)"
    parts = [p.strip(" ,.") for p in re.split(pattern, command.strip(), flags=re.IGNORECASE)]
    return [p for p in parts if p] or [command.strip()]


def _compose_request(norm: str) -> str | None:
    """'write a poem about rain' -> the thing to compose; None if it's literal text to type."""
    m = re.match(r"^(?:write|compose|draft|create)\s+(.+)$", norm)
    if not m:
        return None
    body = m.group(1)
    if re.match(r"^(?:a|an|me a|me an|something|some)\b", body) or any(
        re.search(rf"\b{obj}s?\b", body) for obj in COMPOSE_OBJECTS
    ):
        return body
    return None


def _parse_single_intent(cmd: str) -> Dict[str, Any]:
    norm = clean_utterance(cmd)
    if not norm:
        return {"type": "empty"}

    # Click by on-screen text
    if norm.startswith("click "):
        return {"type": "direct", "action": "click_text", "target": norm[6:].strip().strip("\"'")}

    # Time and date
    if re.search(r"\b(?:what(?:'s| is) the time|what time is it|tell me the time|current time)\b", norm):
        return {"type": "direct", "action": "tell_time"}
    if re.search(r"\b(?:what(?:'s| is) (?:the |today's )?date|what day is (?:it|today)|today's date)\b", norm):
        return {"type": "direct", "action": "tell_date"}

    # Everyday keyboard actions
    for pattern, intent in _SHORTCUTS:
        if pattern.match(norm):
            return {"type": "direct", "action": intent}

    # Screenshot
    if re.search(r"\b(?:take (?:a )?screenshot|screenshot|screen shot|capture (?:the )?screen)\b", norm):
        return {"type": "direct", "action": "take_screenshot"}

    # Volume
    if re.search(r"\b(?:volume up|increase (?:the )?volume|louder|turn (?:it |the volume )?up|raise (?:the )?volume)\b", norm):
        return {"type": "direct", "action": "volume_up"}
    if re.search(r"\b(?:volume down|decrease (?:the )?volume|lower (?:the )?volume|quieter|turn (?:it |the volume )?down)\b", norm):
        return {"type": "direct", "action": "volume_down"}
    if re.search(r"\b(?:unmute|mute)\b", norm):
        return {"type": "direct", "action": "mute_audio"}

    # Browser tabs
    if re.search(r"\b(?:open )?(?:a )?new tab\b", norm):
        return {"type": "direct", "action": "new_tab"}
    if re.search(r"\b(?:close|shut) (?:this |the )?tab\b", norm):
        return {"type": "direct", "action": "close_tab"}

    # YouTube
    if "youtube" in norm:
        if re.fullmatch(rf"(?:{'|'.join(VERB_OPEN)}) youtube", norm) or norm == "youtube":
            return {"type": "direct", "action": "open_youtube", "query": ""}
        m = re.search(
            r"(?:search youtube for|youtube search for|search (?:for )?|play |find |look up )\s*(.+?)(?:\s+(?:on|in) youtube)?$",
            norm,
        )
        if m and m.group(1).strip() not in ("youtube", ""):
            return {"type": "direct", "action": "youtube_search", "query": m.group(1).strip()}
        m = re.search(r"youtube\s+(?:search\s+(?:for\s+)?)?(.+)", norm)
        if m:
            return {"type": "direct", "action": "youtube_search", "query": m.group(1).strip()}

    # Spotify
    if "spotify" in norm:
        if re.fullmatch(rf"(?:{'|'.join(VERB_OPEN)}) spotify", norm):
            return {"type": "direct", "action": "play_spotify", "query": ""}
        m = re.search(r"(?:play|listen to|put on)\s+(.+?)(?:\s+(?:on|in) spotify)?$", norm)
        if m:
            return {"type": "direct", "action": "play_spotify", "query": m.group(1).strip()}
        m = re.search(r"spotify\s+(?:play\s+)?(.+)", norm)
        if m:
            return {"type": "direct", "action": "play_spotify", "query": m.group(1).strip()}

    # Chrome
    if re.search(r"\bchrome\b", norm):
        if any(norm.startswith(f"{v} chrome") for v in VERB_CLOSE):
            return {"type": "direct", "action": "close_chrome"}
        if any(norm.startswith(f"{v} chrome") for v in VERB_OPEN) or norm == "chrome":
            return {"type": "direct", "action": "open_chrome"}

    # Notepad
    if re.fullmatch(rf"(?:{'|'.join(VERB_OPEN)}) (?:notepad|notes)", norm) or norm == "notepad":
        return {"type": "direct", "action": "open_notepad"}

    # Writing: compose with the LLM ("write a poem about rain") or type literally ("type hello")
    compose = _compose_request(norm)
    if compose:
        return {"type": "direct", "action": "compose", "prompt": compose}
    m = re.match(r"^(?:type|write|enter)\s+(.+)$", norm)
    if m:
        # Keep the speaker's original casing for literal text.
        verb = re.search(r"\b(?:type|write|enter)\s+", cmd, flags=re.IGNORECASE)
        original = cmd[verb.end():] if verb else m.group(1)
        return {"type": "direct", "action": "type_text", "text": original.strip(" \"'.") or m.group(1)}

    # Google
    m = re.search(r"^(?:google(?: search)?(?: for)?|search google for|search (?:the web )?for|look up|search)\s+(.+)$", norm)
    if m:
        return {"type": "direct", "action": "google_search", "query": m.group(1).strip()}

    # URLs
    m = re.match(r"^(?:open|go to|visit)\s+((?:https?://|www\.)\S+|\S+\.(?:com|org|net|io|in|dev|ai)\S*)$", norm)
    if m:
        return {"type": "direct", "action": "open_url", "url": m.group(1)}

    # Generic app launch
    for verb in sorted(VERB_OPEN, key=len, reverse=True):
        if norm.startswith(f"{verb} "):
            target = norm[len(verb) + 1:].strip()
            if target in ("notepad", "notes"):
                return {"type": "direct", "action": "open_notepad"}
            if re.search(r"\b(?:and|then|with|to)\b", target) or len(target.split()) > 4:
                break  # "open notepad and fix my files" is not an app name; let the planner read it
            return {"type": "direct", "action": "open_app", "app": target}

    # Questions go to the LLM for a spoken answer (Siri-style)
    if QUESTION_START.match(norm) or norm.endswith("?"):
        return {"type": "direct", "action": "ask", "question": cmd.strip()}

    return {"type": "llm"}


def route_command(command: str) -> Dict[str, Any]:
    """Route a whole utterance. Compound commands only stay deterministic if every part maps
    to a known intent; otherwise the full utterance goes to the planner, which sees the context."""
    sub_commands = split_compound_command(command)
    if len(sub_commands) > 1:
        actions = [_parse_single_intent(c) for c in sub_commands]
        actions = [a for a in actions if a["type"] != "empty"]
        if any(a["type"] != "direct" for a in actions):
            return {"type": "llm", "raw": command}
        if len(actions) > 1:
            return {"type": "multi", "actions": actions, "raw": command}
        if actions:
            return actions[0]
        return {"type": "empty"}
    return _parse_single_intent(sub_commands[0])
