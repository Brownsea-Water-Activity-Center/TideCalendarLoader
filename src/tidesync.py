# src/tide_sync.py
from __future__ import annotations
from datetime import date ,datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo   # Python 3.9+

from .config_loader import load_config, load_text_secret, ConfigError
from .willyweatherclient import fetch_tide_data, flatten_tide_entries
from .googlecalendarclient import GCalClient, event_body_from_tide


class TideSync:
    """
    Orchestrates: load config -> fetch WillyWeather tides -> build event bodies
    -> upsert into Google Calendar (10-minute events, colored by tide type).
    Uses a stable per-event key: extendedProperties.private.syncKey = "tide:<dateTime>".
    """

    def __init__(self, config_path: str | None = None):
        # Load config + secrets
        self.cfg = load_config(config_path)
        self.api_key = load_text_secret(self.cfg["WW_KEY_PATH"])
        self.calendar_id = self.cfg["CALENDAR_ID"]
        self.sa_json = self.cfg["SA_JSON_PATH"]

        # Required WW location
        self.ww_location_id = self.cfg.get("WW_LOCATION_ID")
        if not self.ww_location_id:
            raise ConfigError("WW_LOCATION_ID must be set in config.json")
        
        # Load timezone from config (fallback UTC if missing)
        tz_name = self.cfg.get("TIMEZONE", "UTC")
        try:
            self.tz = ZoneInfo(tz_name)
        except Exception as e:
            raise ConfigError(f"Invalid TIMEZONE in config: {tz_name}") from e

        self.client = GCalClient(self.sa_json, self.calendar_id)


        # Optional window length
        self.days = int(self.cfg.get("WW_DAYS", 7))

        # Calendar client
        self.client = GCalClient(self.sa_json, self.calendar_id)

    # -------- Data fetch / transform --------

    def fetch_entries(self, start_date: str | None = None) -> List[Dict[str, Any]]:
        """
        Fetch and flatten tide entries from WillyWeather.
        Returns a list of dicts with keys: date, dateTime, height, type.
        """
        sd = start_date or date.today().isoformat()  # YYYY-MM-DD
        data = fetch_tide_data(self.api_key, int(self.ww_location_id), sd, self.days)
        return flatten_tide_entries(data)

    def make_event_bodies(self, entries: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert entries to Google Calendar event bodies:
        - 10-minute duration
        - color by tide type (high/low)
        - extendedProperties.private.syncKey = "tide:<entry['dateTime']>"
        """

        tz_name = self.cfg.get("TIMEZONE", "UTC")

        return [event_body_from_tide(
                    e,
                    timezone_str=tz_name,
                    high_color=self.cfg.get("HighTideColor"),
                    low_color=self.cfg.get("LowTideColor"),
                    high_label=self.cfg.get("HighTideLabel", "High Tide"),
                    low_label=self.cfg.get("LowTideLabel", "Low Tide"),
                )
                for e in entries]

    # -------- Sync actions --------

    def upsert(self, start_date: str | None = None) -> int:
        # Compute window
        sd_str = start_date or date.today().isoformat()         # YYYY-MM-DD
        sd_start = datetime.fromisoformat(sd_str).replace(tzinfo=self.tz)
        ed_exclusive = sd_start + timedelta(days=self.days)      # [start, end)

        # Build bodies only for this feed (already constrained by WW days/start)
        entries = self.fetch_entries(sd_str)
        bodies = self.make_event_bodies(entries)

        # Upsert considering ONLY events in this window
        inserted, updated = self.client.upsert(
            bodies,
            time_min=sd_start,
            time_max=ed_exclusive
        )
        print(f"Upsert complete: {inserted} inserted, {updated} updated")
        return inserted + updated

    def clear(self):
        """
        Clear ALL events from the target calendar (works on secondary calendars).
        """
        #self.client.clear()
        print("Calendar cleared.")

    def delete_range(self, start_date: str | None = None, *, days: int | None = None, only_tides: bool = True) -> int:
        """
        Delete events in [start, start+days). If days is None, uses self.days.
        By default, only deletes tide events (syncKey starts with 'tide:').
        """
        days = int(days or self.days)

        # Build window in configured timezone
        sd_str = start_date or date.today().isoformat()      # "YYYY-MM-DD"
        # midnight at tz
        sd_start = datetime.fromisoformat(sd_str).replace(tzinfo=self.tz)
        ed_exclusive = sd_start + timedelta(days=days)

        #Hack prefix = "tide:" if only_tides else None
        prefix =  None
        deleted = self.client.delete_range(sd_start, ed_exclusive, filter_sync_prefix=prefix)

        print(f"Deleted {deleted} event(s) from {sd_start.isoformat()} to {ed_exclusive.isoformat()} "
            f"{'(tide-only)' if only_tides else '(all)'}")
        return deleted

