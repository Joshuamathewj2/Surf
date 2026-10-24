"""
skills/web_skill.py
Live answers from the web: weather, news headlines, and Wikipedia facts.

These are the only skills that go online, and only when you ask for them (set SURF_OFFLINE=1
to turn them off). No API keys: Open-Meteo for weather, Google News RSS for headlines, and
the Wikipedia REST API for facts. Your location for the weather comes from SURF_CITY, or
from your IP address when that isn't set.
"""
import re
import urllib.parse
import xml.etree.ElementTree as ET
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

import requests

from core import config
from core.logger import get_logger
from skills.base import BaseSkill

logger = get_logger("skills.web")

HEADERS = {"User-Agent": "Surf-voice-assistant/3 (local desktop assistant)"}

# WMO weather codes (Open-Meteo) -> words that sound natural in a sentence.
WMO = {
    0: "clear skies", 1: "mostly clear skies", 2: "partly cloudy skies", 3: "overcast skies",
    45: "fog", 48: "freezing fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow",
    77: "snow grains", 80: "light showers", 81: "showers", 82: "heavy showers", 85: "snow showers",
    86: "heavy snow showers", 95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail",
}
RAINY = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}


class Offline(Exception):
    pass


def _get(url: str, **params) -> requests.Response:
    if not config.ONLINE:
        raise Offline()
    r = requests.get(url, params=params or None, headers=HEADERS, timeout=config.HTTP_TIMEOUT)
    r.raise_for_status()
    return r


# ---------------------------------------------------------------------------- location


@lru_cache(maxsize=32)
def geocode(place: str) -> Optional[dict]:
    """'london' -> {'name': 'London', 'lat': .., 'lon': .., 'country_code': 'GB'}"""
    data = _get("https://geocoding-api.open-meteo.com/v1/search", name=place, count=1, language="en").json()
    hits = data.get("results") or []
    if not hits:
        return None
    h = hits[0]
    return {"name": h["name"], "lat": h["latitude"], "lon": h["longitude"], "country_code": h.get("country_code", "")}


@lru_cache(maxsize=1)
def home_location() -> Optional[dict]:
    if config.HOME_CITY:
        return geocode(config.HOME_CITY)
    for url in ("https://ipapi.co/json/", "http://ip-api.com/json/"):
        try:
            d = _get(url).json()
            lat, lon = d.get("latitude", d.get("lat")), d.get("longitude", d.get("lon"))
            if lat is not None and lon is not None:
                return {"name": d.get("city") or "your area", "lat": lat, "lon": lon,
                        "country_code": d.get("country_code") or d.get("countryCode") or ""}
        except (requests.RequestException, ValueError) as e:
            logger.debug(f"IP location via {url} failed: {e}")
    return None


# ---------------------------------------------------------------------------- weather


def forecast(loc: dict) -> dict:
    return _get(
        "https://api.open-meteo.com/v1/forecast",
        latitude=loc["lat"], longitude=loc["lon"], timezone="auto", forecast_days=3,
        current="temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
        daily="weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    ).json()


def describe_weather(data: dict, place: str, day: int = 0, rain_question: bool = False) -> str:
    """Spoken weather summary. day 0 = today (with current conditions), 1 = tomorrow."""
    daily = data["daily"]
    code = daily["weather_code"][day]
    hi, lo = round(daily["temperature_2m_max"][day]), round(daily["temperature_2m_min"][day])
    rain = daily.get("precipitation_probability_max", [None] * 3)[day]
    rain_part = f", with a {rain} percent chance of rain" if rain is not None else ""
    when = "today" if day == 0 else "tomorrow"
    if rain_question:
        likely = (rain or 0) >= 50 or code in RAINY
        lead = "Yes, rain is likely" if likely else ("There's a small chance of rain" if (rain or 0) >= 20 else "No rain expected")
        return f"{lead} in {place} {when}" + (f", about {rain} percent" if rain is not None else "") + f". Expect {WMO.get(code, 'mixed weather')}."
    if day == 0:
        cur = data["current"]
        temp, feels = round(cur["temperature_2m"]), round(cur["apparent_temperature"])
        now_desc = WMO.get(cur["weather_code"], "mixed weather")
        feels_part = f", feels like {feels}" if abs(feels - temp) >= 3 else ""
        return f"It's {temp} degrees with {now_desc} in {place}{feels_part}. Today's high is {hi} and the low is {lo}{rain_part}."
    return f"Tomorrow in {place}: {WMO.get(code, 'mixed weather')}, a high of {hi} and a low of {lo}{rain_part}."


# ---------------------------------------------------------------------------- news


def headlines(topic: str = "", country: str = "", limit: int = 3) -> list[str]:
    cc = (country or "US").upper()
    edition = {"hl": f"en-{cc}", "gl": cc, "ceid": f"{cc}:en"}
    if topic:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": topic, **edition})
    else:
        url = "https://news.google.com/rss?" + urllib.parse.urlencode(edition)
    root = ET.fromstring(_get(url).content)
    titles = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        title = re.sub(r"\s+-\s+[^-]+$", "", title)  # drop the " - Publisher" suffix
        if title and title not in titles:
            titles.append(title)
        if len(titles) >= limit:
            break
    return titles


# ---------------------------------------------------------------------------- Wikipedia


@lru_cache(maxsize=64)
def wiki_summary(topic: str) -> Optional[str]:
    """Lead paragraph of the best-matching Wikipedia article, or None."""
    try:
        hits = _get("https://en.wikipedia.org/w/api.php", action="query", list="search", srsearch=topic,
                    srlimit=1, format="json").json()["query"]["search"]
        if not hits:
            return None
        title = hits[0]["title"]
        page = _get("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_"))).json()
        if page.get("type") == "disambiguation":
            return None
        return page.get("extract") or None
    except (Offline, requests.RequestException, ValueError, KeyError) as e:
        logger.debug(f"Wikipedia lookup for {topic!r} failed: {e}")
        return None


def first_sentences(text: str, n: int = 2) -> str:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())
    return " ".join(parts[:n])


# ---------------------------------------------------------------------------- YouTube


def first_youtube_video(query: str) -> Optional[str]:
    """Video id of the top search result, so "play X on YouTube" actually plays X."""
    try:
        html = _get("https://www.youtube.com/results", search_query=query).text
    except (Offline, requests.RequestException) as e:
        logger.debug(f"YouTube lookup failed: {e}")
        return None
    m = re.search(r'"videoRenderer":\{"videoId":"([\w-]{11})"', html) or re.search(r"/watch\?v=([\w-]{11})", html)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------- skill


class WebSkill(BaseSkill):
    name = "web"

    HANDLED_INTENTS = {"weather", "news"}

    def can_handle(self, intent: str, slots: Dict[str, Any]) -> bool:
        return intent in self.HANDLED_INTENTS

    def execute(self, slots: Dict[str, Any]) -> Tuple[bool, str]:
        intent = slots.get("intent", "")
        try:
            if intent == "weather":
                return self._weather(slots.get("place", ""), int(slots.get("day", 0)), bool(slots.get("rain")))
            if intent == "news":
                return self._news(slots.get("topic", ""))
        except Offline:
            return False, "I'm in offline mode, so I can't check that."
        except requests.RequestException as e:
            logger.error(f"{intent} lookup failed: {e}")
            return False, "I couldn't reach the internet to check that."
        return False, f"Unknown web action: {intent}"

    def _weather(self, place: str, day: int, rain: bool) -> Tuple[bool, str]:
        loc = geocode(place) if place else home_location()
        if loc is None:
            if place:
                return False, f"I couldn't find a place called {place}."
            return False, "I don't know where you are. Set SURF_CITY to your city, or ask about a place."
        return True, describe_weather(forecast(loc), loc["name"], min(max(day, 0), 2), rain)

    def _news(self, topic: str) -> Tuple[bool, str]:
        country = ""
        try:
            loc = home_location()
            country = (loc or {}).get("country_code", "")
        except requests.RequestException:
            pass
        titles = headlines(topic, country)
        if not titles:
            return False, f"I couldn't find any news{' about ' + topic if topic else ''}."
        intro = f"Here's the latest on {topic}" if topic else "Here are the top headlines"
        return True, intro + ". " + " ... ".join(f"{t}." if not t.endswith((".", "?", "!")) else t for t in titles)
