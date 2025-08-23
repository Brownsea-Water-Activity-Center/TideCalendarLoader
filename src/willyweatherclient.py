from __future__ import annotations

from datetime import date as _date
from typing import Any, Dict, List, Optional

import requests


class WillyWeatherError(RuntimeError):
    """Raised when the WillyWeather API call fails or returns unexpected data."""
    pass


def build_tide_url(api_key: str, location_id: int | str, start_date: str, days: int) -> str:
    """
    Build the WillyWeather tides endpoint URL.

    Args:
        api_key: Your WillyWeather API key.
        location_id: Numeric location ID (e.g., Brisbane Bar).
        start_date: YYYY-MM-DD (local date for the location).
        days: Number of days forward to fetch.

    Returns:
        Fully composed request URL.
    """
    return (
        f"https://api.willyweather.com.au/v2/{api_key}/locations/{location_id}/weather.json"
        f"?forecasts=tides&startDate={start_date}&days={days}"
    )


def fetch_tide_data(
    api_key: str,
    location_id: int | str,
    start_date: str | _date,
    days: int,
    *,
    timeout: int = 30,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """
    Call WillyWeather and return the parsed JSON.

    Args:
        api_key: WillyWeather API key.
        location_id: Numeric location ID.
        start_date: YYYY-MM-DD string or datetime.date.
        days: Number of days to fetch.
        timeout: HTTP timeout seconds.
        session: Optional requests.Session for reuse.

    Returns:
        Parsed JSON dict.

    Raises:
        WillyWeatherError on HTTP/parse errors.
    """
    if isinstance(start_date, _date):
        sd_str = start_date.isoformat()
    else:
        sd_str = start_date

    url = build_tide_url(api_key, location_id, sd_str, days)

    sess = session or requests.Session()
    try:
        resp = sess.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as e:
        text = getattr(e.response, "text", "")
        raise WillyWeatherError(f"HTTP {e.response.status_code} from WillyWeather: {text}") from e
    except requests.RequestException as e:
        raise WillyWeatherError(f"Request error calling WillyWeather: {e}") from e
    except ValueError as e:
        raise WillyWeatherError(f"Invalid JSON from WillyWeather: {e}") from e
    finally:
        if session is None:
            sess.close()

    # Basic shape check
    if not isinstance(data, dict) or "forecasts" not in data:
        raise WillyWeatherError("Unexpected JSON structure from WillyWeather (no 'forecasts').")

    return data


def flatten_tide_entries(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Flatten the WillyWeather JSON into a list of simple tide entry dicts.

    Expected input (simplified):
    {
      "forecasts": {
        "tides": {
          "days": [
            { "date": "YYYY-MM-DD", "entries": [
                { "dateTime": "YYYY-MM-DDTHH:MM:SS+zz:zz", "height": 1.23, "type": "high" | "low" },
                ...
            ]},
            ...
          ]
        }
      }
    }

    Returns:
        [
          {"date": "YYYY-MM-DD", "dateTime": "...+10:00", "height": 1.23, "type": "high"},
          ...
        ]
    """
    entries: List[Dict[str, Any]] = []
    days = data.get("forecasts", {}).get("tides", {}).get("days", [])
    if not isinstance(days, list):
        # Handle unexpected shapes gracefully
        return entries

    for d in days:
        day_date = d.get("date")
        for e in d.get("entries", []) or []:
            entries.append(
                {
                    "date": day_date,                             # YYYY-MM-DD
                    "dateTime": e.get("dateTime"),               # ISO-8601 with offset (local)
                    "height": e.get("height"),
                    "type": (e.get("type") or "").lower(),       # normalize to 'high' / 'low'
                }
            )
    return entries
