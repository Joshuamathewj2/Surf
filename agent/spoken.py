"""
agent/spoken.py
Turn spoken phrasing into numbers, durations, clock times and arithmetic.

Whisper writes most numbers as digits, but not all of them ("set a timer for five minutes",
"half an hour"), so everything here accepts both. Pure functions, no I/O: easy to test.
"""
import ast
import datetime
import math
import operator
import re
from typing import Optional

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000}
_NUMBER_WORD = "|".join(list(_UNITS) + list(_TENS) + list(_SCALES))
_NUMBER_RUN = re.compile(rf"\b(?:{_NUMBER_WORD})(?:[\s-]+(?:and[\s-]+)?(?:{_NUMBER_WORD}))*\b")


def _run_value(words: list[str]) -> int:
    total, current = 0, 0
    for w in words:
        if w in _UNITS:
            current += _UNITS[w]
        elif w in _TENS:
            current += _TENS[w]
        elif w == "hundred":
            current = max(current, 1) * 100
        elif w in _SCALES:
            total += max(current, 1) * _SCALES[w]
            current = 0
    return total + current


def words_to_digits(text: str) -> str:
    """'twenty five minutes' -> '25 minutes', 'one hundred and five' -> '105'."""

    def repl(m: re.Match) -> str:
        words = [w for w in re.split(r"[\s-]+", m.group(0)) if w and w != "and"]
        return str(_run_value(words))

    return _NUMBER_RUN.sub(repl, text.lower())


# ---------------------------------------------------------------------------- durations

_DURATION_UNITS = {
    "second": 1, "sec": 1, "s": 1,
    "minute": 60, "min": 60, "m": 60,
    "hour": 3600, "hr": 3600, "h": 3600,
}
_DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|[smh])\b")


def parse_duration(text: str) -> Optional[int]:
    """Seconds in phrases like '5 minutes', 'an hour and a half', '1 hour 20 minutes', '90 sec'."""
    t = words_to_digits(text)
    t = re.sub(r"\b(?:an?|one)\s+(hour|minute|second)\b", r"1 \1", t)
    t = re.sub(r"\bhalf an? hour\b", "30 minutes", t)
    t = re.sub(r"\bhalf a minute\b", "30 seconds", t)
    t = re.sub(r"\ba quarter of an hour\b|\bquarter (?:of an )?hour\b", "15 minutes", t)
    total = 0.0
    found = False
    for value, unit in _DURATION_PART.findall(t):
        unit = unit.rstrip("s") if len(unit) > 1 else unit
        total += float(value) * _DURATION_UNITS.get(unit, _DURATION_UNITS.get(unit[:3], 0))
        found = True
    if not found:
        return None
    # "an hour and a half", "2 minutes and a half"
    m = re.search(r"(\d+(?:\.\d+)?)\s*(hours?|minutes?)\s+and a half\b", t)
    if m:
        total += 0.5 * (3600 if m.group(2).startswith("hour") else 60)
    return int(round(total)) if total > 0 else None


def parse_clock(text: str, now: datetime.datetime) -> Optional[datetime.datetime]:
    """The next occurrence of 'at 6 pm', 'at 18:30', 'at 7:15 in the morning', 'at noon'."""
    t = re.sub(r"(\d)\.(\d{2})\b", r"\1:\2", words_to_digits(text)).replace(".", "")  # 7.30 -> 7:30
    if re.search(r"\bat (?:12 )?noon\b|\bat midday\b", t):
        hour, minute, meridiem = 12, 0, None
    elif re.search(r"\bat midnight\b", t):
        hour, minute, meridiem = 0, 0, None
    else:
        m = re.search(r"\bat (\d{1,2})(?:[: ](\d{2}))?\s*(am|pm|a m|p m)?(?:\s+(?:in the|this) (morning|afternoon|evening|night))?", t)
        if not m:
            return None
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        meridiem = (m.group(3) or "").replace(" ", "") or None
        part = m.group(4)
        if meridiem is None and part:
            meridiem = "am" if part == "morning" else "pm"
        if hour > 23 or minute > 59:
            return None
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # "at 7" with no am/pm: the next 7 o'clock, morning or evening, whichever comes first
    if target <= now and meridiem is None and hour < 12:
        target = target.replace(hour=hour + 12)
    if target <= now:
        target += datetime.timedelta(days=1)
    return target


def spoken_duration(seconds: int) -> str:
    """3725 -> '1 hour, 2 minutes and 5 seconds'."""
    seconds = int(round(seconds))
    parts = []
    for name, size in (("hour", 3600), ("minute", 60), ("second", 1)):
        n, seconds = divmod(seconds, size)
        if n:
            parts.append(f"{n} {name}{'s' if n != 1 else ''}")
    if not parts:
        return "0 seconds"
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


# ---------------------------------------------------------------------------- arithmetic

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}
_SPOKEN_OPS = [
    (r"\bsquare root of (\d+(?:\.\d+)?)", r"sqrt(\1)"),
    (r"\bcube root of (\d+(?:\.\d+)?)", r"cbrt(\1)"),
    (r"(\d+(?:\.\d+)?)\s*(?:percent|%)\s+of\b", r"\1 / 100 *"),
    (r"(\d+(?:\.\d+)?)\s+squared\b", r"\1 ** 2"),
    (r"(\d+(?:\.\d+)?)\s+cubed\b", r"\1 ** 3"),
    (r"\b(?:to the power of|raised to(?: the power of)?|to the)\b", "**"),
    (r"\b(?:multiplied by|times|into)\b|(?<=\d)\s*[x×]\s*(?=\d)", "*"),
    (r"\b(?:divided by|over)\b|÷", "/"),
    (r"\bplus\b", "+"),
    (r"\bminus\b", "-"),
    (r"\bmod(?:ulo)?\b", "%"),
]
_MATH_PREFIX = re.compile(
    r"^(?:what(?:'s| is)|whats|calculate|compute|how much is|tell me|solve|evaluate)\s+", re.IGNORECASE
)


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("exponent too large")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and len(node.args) == 1:
        fn = {"sqrt": math.sqrt, "cbrt": lambda v: math.copysign(abs(v) ** (1 / 3), v)}.get(node.func.id)
        if fn:
            return fn(_eval(node.args[0]))
    raise ValueError("unsupported expression")


def to_expression(text: str) -> Optional[str]:
    """'what's 15 percent of 240' -> '15 / 100 * 240'. None unless it is clearly arithmetic."""
    t = _MATH_PREFIX.sub("", words_to_digits(text).strip(" ?.!"))
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)  # 1,250 -> 1250
    for pattern, repl in _SPOKEN_OPS:
        t = re.sub(pattern, repl, t)
    t = t.strip()
    if not t or not re.fullmatch(r"[\d\s.+\-*/%()]+", re.sub(r"(?:sqrt|cbrt)\(", "(", t)):
        return None
    if not re.search(r"\d", t) or not re.search(r"[+\-*/%]|sqrt|cbrt", t):
        return None
    return t


def evaluate(expression: str) -> float:
    return _eval(ast.parse(expression, mode="eval"))


def spoken_number(value: float) -> str:
    """Readable number for TTS: no trailing .0, at most 4 decimals, thousands separators."""
    if isinstance(value, float) and (math.isinf(value) or math.isnan(value)):
        return "undefined"
    rounded = round(value, 4)
    if rounded == int(rounded):
        return f"{int(rounded):,}"
    return f"{rounded:,.4f}".rstrip("0").rstrip(".")
