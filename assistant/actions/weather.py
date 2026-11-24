"""Live weather from OpenWeatherMap (free tier, current-weather endpoint)."""
from __future__ import annotations

from typing import Optional

import requests

API_URL = "https://api.openweathermap.org/data/2.5/weather"


class WeatherError(Exception):
    """Raised with a message that is safe to read out loud."""


def fetch_weather(city: str, api_key: str, units: str = "metric",
                  session=None, timeout: float = 8) -> str:
    if not api_key:
        raise WeatherError("I need an OpenWeatherMap API key first. Add it to the dot env file.")
    session = session or requests
    try:
        resp = session.get(API_URL, params={"q": city, "appid": api_key, "units": units},
                           timeout=timeout)
    except requests.RequestException:
        raise WeatherError("I couldn't reach the weather service. Please check your connection.")
    if resp.status_code == 401:
        raise WeatherError("The weather API key was rejected. New keys can take a couple of hours to activate.")
    if resp.status_code == 404:
        raise WeatherError(f"I couldn't find a place called {city}.")
    if resp.status_code != 200:
        raise WeatherError("The weather service returned an error. Please try again later.")
    return format_weather(resp.json(), units)


def format_weather(data: dict, units: str = "metric") -> str:
    unit_name = "degrees Celsius" if units == "metric" else "degrees Fahrenheit"
    desc = data["weather"][0]["description"]
    main = data["weather"][0].get("main", "")
    temp = round(data["main"]["temp"])
    feels = round(data["main"].get("feels_like", temp))
    humidity = data["main"].get("humidity")
    text = f"Right now in {data.get('name', 'your area')} it's {temp} {unit_name} with {desc}."
    if feels != temp:
        text += f" It feels like {feels}."
    if humidity is not None:
        text += f" Humidity is {humidity} percent."
    if main in ("Rain", "Drizzle", "Thunderstorm"):
        text += " You might want an umbrella."
    return text
