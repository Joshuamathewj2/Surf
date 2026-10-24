"""
agent/intents.py
Deterministic parsing for the Siri-style intents: timers, alarms, reminders, weather, news,
maths, media, device settings, memory, clipboard and small fun requests.

siri_intent() takes an utterance already cleaned by router.clean_utterance() and returns a
route dict ({"type": "direct", "action": ..., slots...}) or None to let the router carry on.
"""
import datetime
import re
from typing import Any, Dict, Optional

from agent.spoken import parse_clock, parse_duration, to_expression, words_to_digits

Route = Optional[Dict[str, Any]]


def _direct(action: str, **slots: Any) -> Dict[str, Any]:
    return {"type": "direct", "action": action, **slots}


# ---------------------------------------------------------------------------- timers & co.

_CANCEL = r"\b(?:cancel|stop|delete|remove|clear|turn off|dismiss)\b"


def _kind(norm: str) -> str:
    for kind in ("timer", "alarm", "reminder"):
        if re.search(rf"\b{kind}s?\b", norm):
            return kind
    return ""


def _timers(norm: str, now: datetime.datetime) -> Route:
    kind = _kind(norm)
    if kind:
        if re.search(_CANCEL, norm):
            return _direct("cancel_timer", kind=kind)
        if re.search(r"\b(?:how (?:much|long)|time left|remaining|left on)\b", norm) and kind == "timer":
            return _direct("timer_status")
        if re.search(r"\b(?:what|which|list|show|any|do i have|my)\b", norm) and not re.search(r"\b(?:set|start|create|add|make)\b", norm):
            return _direct("list_reminders", kind=kind)
    if kind == "timer" or re.match(r"^(?:start a |set a )?countdown\b", norm):
        seconds = parse_duration(norm)
        label = ""
        m = re.search(r"\btimer (?:for|called|named) (?!\d|an? (?:hour|minute|second)|half)([a-z][a-z ]*?)$", norm)
        if m and not parse_duration(m.group(1)):
            label = m.group(1).strip()
        return _direct("set_timer", seconds=seconds or 0, label=label)

    if kind == "alarm" or re.match(r"^wake me(?: up)?\b", norm):
        clock_text = re.sub(r"\bfor (?=\d|noon|midnight)", "at ", norm)
        if not re.search(r"\bat\b", clock_text):
            clock_text = re.sub(r"\b(alarm|wake me(?: up)?)\s+(?=\d)", r"\1 at ", clock_text)
        when = parse_clock(clock_text, now)
        if when is None:
            secs = parse_duration(norm) if re.search(r"\bin\b", norm) else None
            when = now + datetime.timedelta(seconds=secs) if secs else None
        if when is not None and "tomorrow" in norm and when.date() == now.date():
            when += datetime.timedelta(days=1)
        return _direct("set_alarm", due=when.timestamp() if when else 0)

    m = re.match(r"^remind me\b\s*(.*)$", norm)
    if m:
        rest = m.group(1)
        due = None
        # "in 10 minutes" / "in an hour"
        dm = re.search(r"\bin ((?:an?|half an?|\d+|[a-z-]+)(?: and a half)? (?:hours?|minutes?|mins?|seconds?|secs?)(?: and \d+ (?:minutes?|seconds?))?)\b", words_to_digits(rest))
        rest_digits = words_to_digits(rest)
        if dm:
            secs = parse_duration(dm.group(1))
            if secs:
                due = now + datetime.timedelta(seconds=secs)
                rest_digits = rest_digits.replace(dm.group(0), " ")
        else:
            cm = re.search(r"\b(?:at|by) (?:\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm|a m|p m)?(?: in the (?:morning|afternoon|evening))?|noon|midnight)", rest_digits)
            if cm:
                due = parse_clock(cm.group(0).replace("by ", "at "), now)
                rest_digits = rest_digits.replace(cm.group(0), " ")
        if re.search(r"\btomorrow\b", rest_digits) and due is not None and due.date() == now.date():
            due += datetime.timedelta(days=1)
        rest_digits = re.sub(r"\btomorrow\b|\btonight\b", " ", rest_digits)
        task = re.sub(r"^(?:to|that|about)\s+", "", re.sub(r"\s+", " ", rest_digits).strip())
        task = re.sub(r"\s+(?:to|that)$", "", task)
        return _direct("set_reminder", task=task, due=due.timestamp() if due else 0)
    return None


# ---------------------------------------------------------------------------- weather & news

_WEATHER = re.compile(
    r"\b(?:weather|forecast|temperature|umbrella|raining|rain|snowing|snow|sunny|humid|"
    r"(?:hot|cold|warm|chilly) (?:is it )?(?:outside|out there|today|tomorrow))\b"
)


def _weather(norm: str) -> Route:
    if not _WEATHER.search(norm) or re.match(r"^(?:play|search|google|open|look up|find)\b", norm):
        return None
    if not re.search(r"\b(?:what|what's|how|is|will|does|do|weather|forecast|tell|temperature|going to|gonna)\b", norm):
        return None
    day = 2 if "day after tomorrow" in norm else 1 if "tomorrow" in norm else 0
    rain = bool(re.search(r"\b(?:rain|raining|umbrella|snow|snowing)\b", norm)) and "weather" not in norm
    t = re.sub(r"\b(?:the )?day after tomorrow\b|\btomorrow\b|\btoday\b|\bright now\b|\bnow\b|\bthis (?:week|morning|afternoon|evening)\b|\btonight\b", "", norm)
    t = re.sub(r"\s+", " ", t).strip(" ?")
    place = ""
    m = re.search(r"\b(?:in|at|for) ([a-z][a-z .'-]*?)$", t)
    if m and m.group(1) not in ("the morning", "the evening", "the afternoon", "outside", "here", "my area"):
        place = m.group(1).strip()
    return _direct("weather", place=place, day=day, rain=rain)


def _news(norm: str) -> Route:
    if not re.search(r"\b(?:news|headlines)\b", norm) or re.match(r"^(?:play|open)\b", norm):
        return None
    topic = ""
    m = re.search(r"\b(?:news|headlines) (?:about|on|regarding|for|from) (.+)$", norm) or re.search(
        r"^(?:what's the |what is the |tell me the |give me the |read me the |read the )?(?:latest |top )?([a-z0-9 ]+?) news$", norm)
    if m and m.group(1) not in ("the", "latest", "top", "today's", "todays", "the latest", "some", "any"):
        topic = m.group(1).strip()
    return _direct("news", topic=topic)


# ---------------------------------------------------------------------------- device & media


def _device(norm: str) -> Route:
    t = words_to_digits(norm)
    m = re.search(r"\b(?:set |change |turn )?(?:the )?volume (?:to |at )?(\d{1,3})(?: ?(?:percent|%))?$", t) or \
        re.search(r"^(?:set|turn) (?:the )?volume (?:up |down )?to (\d{1,3})", t)
    if m:
        return _direct("set_volume", level=min(100, int(m.group(1))))

    if re.fullmatch(r"(?:pause|resume|play|unpause|continue)(?: (?:the |my )?(?:music|song|video|track|playback|it|podcast))?|"
                    r"(?:stop|pause) (?:the |my )?(?:music|song|video|playback)", norm):
        return _direct("media_play_pause")
    if re.fullmatch(r"(?:next|skip)(?: (?:this |the )?(?:song|track|video))?|play (?:the )?next (?:song|track|video)|skip", norm):
        return _direct("media_next")
    if re.fullmatch(r"(?:previous|last|go back a)(?: (?:song|track|video))|play (?:the )?previous (?:song|track|video)", norm):
        return _direct("media_previous")

    if re.search(r"\bbattery\b", norm) and not re.search(r"\bsettings?\b", norm):
        return _direct("battery")
    if re.fullmatch(r"lock (?:the |my |this )?(?:pc|computer|screen|laptop|device|windows)|lock (?:it|up)|lock", norm):
        return _direct("lock_screen")

    if re.search(r"\bbrightness\b|\bscreen (?:brighter|dimmer|darker)\b|\bdim (?:the )?screen\b", t):
        m = re.search(r"(\d{1,3})", t)
        if m:
            return _direct("brightness", level=int(m.group(1)))
        down = re.search(r"\b(?:down|lower|decrease|reduce|dim|dimmer|darker|less)\b", t)
        if re.search(r"\b(?:max|maximum|full)\b", t):
            return _direct("brightness", level=100)
        return _direct("brightness", step=-20 if down else 20)

    m = re.fullmatch(r"(?:turn on|enable|switch to|use|activate) (?:the )?(dark|light) (?:mode|theme)|"
                     r"(dark|light) (?:mode|theme)(?: on)?", norm)
    if m:
        return _direct("dark_mode", on=(m.group(1) or m.group(2)) == "dark")
    m = re.fullmatch(r"(?:turn off|disable) (?:the )?(dark|light) (?:mode|theme)", norm)
    if m:
        return _direct("dark_mode", on=m.group(1) == "light")

    m = re.fullmatch(r"(?:open|show|go to|launch)(?: the| my)? ([a-z -]*?) ?settings(?: page)?|(?:open |show )?(?:the )?settings", norm)
    if m:
        return _direct("open_settings", page=(m.group(1) or "").strip())
    m = re.fullmatch(r"(?:open|show|go to)(?: the| my)? (downloads|documents|desktop|pictures|photos|music|videos)(?: folder)?", norm)
    if m and not (m.group(1) == "desktop" and not norm.startswith("open") and "folder" not in norm):  # "show desktop" = Win+D
        folder = {"photos": "pictures"}.get(m.group(1), m.group(1))
        return _direct("open_folder", folder=folder)
    return None


# ---------------------------------------------------------------------------- memory


def _memory(norm: str, cmd: str) -> Route:
    m = re.fullmatch(r"(?:my name is|call me|i am|i'm) ([a-z][a-z' -]{0,30})", norm)
    if m and not (norm.startswith(("i am ", "i'm ")) and len(m.group(1).split()) > 2):
        if not re.search(r"\b(?:going|not|so|very|tired|hungry|fine|good|ok|okay|back|done|here|sad|happy|bored)\b", m.group(1)):
            return _direct("set_name", name=m.group(1))
    if re.fullmatch(r"what(?:'s| is) my name|who am i|do you know my name|do you know who i am", norm):
        return _direct("get_name")
    m = re.match(r"^(?:remember|don't forget|note) (?:that )?(.+)$", norm)
    if m and not norm.startswith("remember me"):
        fact = m.group(1)
        # keep the speaker's casing for names, codes, places
        orig = re.search(r"\b(?:remember|don't forget|note)\s+(?:that\s+)?", cmd, flags=re.IGNORECASE)
        if orig:
            fact = cmd[orig.end():].strip(" .!?")
        return _direct("remember", fact=fact)
    if re.fullmatch(r"what do you (?:remember|know)(?: about me)?|what have i told you|what did i ask you to remember", norm):
        return _direct("recall")
    if re.fullmatch(r"forget (?:everything|all of it|all that|it all)(?: (?:about me|i told you))?", norm):
        return _direct("forget", about="")
    m = re.match(r"^forget (?:that |about )?(.+)$", norm)
    if m:
        return _direct("forget", about=m.group(1))
    return None


# ---------------------------------------------------------------------------- clipboard


def _clipboard(norm: str) -> Route:
    copied = r"(?:this|that|it|what i (?:just )?copied|(?:my |the )?clipboard|the copied text|the text i copied)"
    if re.fullmatch(rf"(?:read|what's on|what is on|show)(?: me)? {copied}|read (?:it|this) (?:out|aloud|to me)", norm):
        return _direct("read_clipboard")
    m = re.fullmatch(rf"(summari[sz]e|explain|simplify|proofread|translate) {copied}(?: (?:in|to|into) ([a-z ]+))?", norm)
    if m:
        verb, lang = m.group(1), m.group(2)
        instruction = {
            "summarise": "Summarise this in two or three sentences.",
            "summarize": "Summarise this in two or three sentences.",
            "explain": "Explain this simply.",
            "simplify": "Rewrite this in simpler words.",
            "proofread": "Point out any spelling or grammar mistakes, briefly.",
            "translate": f"Translate this into {lang or 'English'}.",
        }[verb]
        return _direct("clipboard_ai", instruction=instruction)
    return None


# ---------------------------------------------------------------------------- fun & misc


def _misc(norm: str) -> Route:
    if re.fullmatch(r"(?:stop|stop talking|be quiet|quiet|shut up|shush|silence|enough|stop it)", norm):
        return _direct("stop_speaking")
    if re.fullmatch(r"(?:never ?mind|nothing|cancel|forget it|no thanks|nope)", norm):
        return _direct("dismiss")
    if re.search(r"\b(?:tell me|say|know|got) (?:a |another |any )?(?:funny )?jokes?\b|\bmake me laugh\b|\bsay something funny\b", norm) or norm in ("joke", "another one", "another joke"):
        return _direct("joke")
    if re.search(r"\b(?:flip|toss) a coin\b|\bheads or tails\b", norm):
        return _direct("flip_coin")
    if re.search(r"\broll (?:a |the )?(?:die|dice)\b", norm):
        return _direct("roll_dice")
    m = re.search(r"\b(?:pick|choose|give me|generate) a (?:random )?number(?: (?:between|from) (\d+) (?:and|to) (\d+))?", words_to_digits(norm))
    if m:
        return _direct("random_number", low=int(m.group(1) or 1), high=int(m.group(2) or 100))
    if re.fullmatch(r"(?:repeat(?: that| it)?|say (?:that|it) again|what did you (?:just )?say|come again|pardon)", norm):
        return _direct("repeat")
    return None


def siri_intent(norm: str, cmd: str = "", now: Optional[datetime.datetime] = None) -> Route:
    now = now or datetime.datetime.now()
    for parse in (_misc, _timers, _memory, _clipboard, _device, _weather, _news):
        route = parse(norm, now) if parse is _timers else parse(norm, cmd or norm) if parse is _memory else parse(norm)
        if route:
            return route
    expr = to_expression(norm)
    if expr:
        return _direct("calculate", expression=expr)
    return None
