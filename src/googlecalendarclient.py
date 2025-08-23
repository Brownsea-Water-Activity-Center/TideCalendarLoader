from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Pick distinct Google Calendar colors (1–11). Examples:
# 11=red, 7=turquoise, 9=blue, 2=sage, 5=banana, 6=tangerine
COLOR_MAP = {
    "high": "9",  # blue for high
    "low":  "5",  # banana for low
}


class GCalClient:
    def __init__(self, sa_json_path: str, calendar_id: str):
        creds = Credentials.from_service_account_file(sa_json_path, scopes=SCOPES)
        self.service = build("calendar", "v3", credentials=creds)
        self.calendar_id = calendar_id

    # -------------------------
    # Low-level helpers
    # -------------------------

    def list_all_events(
        self,
        *,
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,   # NEW
        show_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        page_token = None

        if time_min is None:
            time_min = datetime(1970, 1, 1, tzinfo=timezone.utc)

        while True:
            res = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat() if time_max else None,  # NEW
                maxResults=2500,
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
                showDeleted=show_deleted,
            ).execute()
            items.extend(res.get("items", []))
            page_token = res.get("nextPageToken")
            if not page_token:
                break
        return items

    def safe_delete(self, event_id: str):
        """Delete an event, ignore if already deleted."""
        try:
            self.service.events().delete(
                calendarId=self.calendar_id, eventId=event_id
            ).execute()
        except HttpError as e:
            if getattr(e, "resp", None) and e.resp.status == 404:
                return
            raise

    def clear(self):
        """Clear *all* events (only works on secondary calendars)."""
        print(f"Clearing Events")
        self.service.calendars().clear(calendarId=self.calendar_id).execute()

    # -------------------------
    # Upsert
    # -------------------------

    def upsert(
        self,
        event_bodies: Iterable[Dict[str, Any]],
        *,
        time_min: Optional[datetime] = None,   # NEW
        time_max: Optional[datetime] = None    # NEW
    ) -> Tuple[int, int]:
        existing = self.list_all_events(show_deleted=False, time_min=time_min, time_max=time_max)  # UPDATED

        existing_map: Dict[str, Dict[str, Any]] = {}
        for ev in existing:
            key = ev.get("extendedProperties", {}).get("private", {}).get("syncKey")
            if key:
                existing_map[key] = ev

        inserted = updated = 0
        for body in event_bodies:
            key = body.get("extendedProperties", {}).get("private", {}).get("syncKey")
            if not key:
                self.service.events().insert(calendarId=self.calendar_id, body=body).execute()
                inserted += 1
                continue

            if key in existing_map:
                ev_id = existing_map[key]["id"]
                print(f"Updating {key}")
                self.service.events().update(
                    calendarId=self.calendar_id, eventId=ev_id, body=body
                ).execute()
                updated += 1
            else:
                print(f"Inserting {key}")
                self.service.events().insert(calendarId=self.calendar_id, body=body).execute()
                inserted += 1

        return inserted, updated
    
    def delete_range(
        self,
        start_dt: datetime,
        end_dt: datetime,
        *,
        filter_sync_prefix: Optional[str] = None,  # e.g. "tide:" to delete only tide events
    ) -> int:
        """
        Delete events whose start falls in [start_dt, end_dt).
        If filter_sync_prefix is set, only delete events whose
        extendedProperties.private.syncKey startswith that prefix.
        Returns count deleted.
        """
        to_delete = self.list_all_events(time_min=start_dt, time_max=end_dt, show_deleted=False)

        deleted = 0
        for ev in to_delete:
            if filter_sync_prefix:
                key = ev.get("extendedProperties", {}).get("private", {}).get("syncKey", "")
                if not isinstance(key, str) or not key.startswith(filter_sync_prefix):
                    continue  # skip non-matching events

            try:
                ev_id = ev["id"]
                start = ev["start"]
                print(f"Deleting {start}")
                self.service.events().delete(calendarId=self.calendar_id, eventId=ev_id).execute()
                deleted += 1
            except HttpError as e:
                # ignore "already gone"
                if not (getattr(e, "resp", None) and e.resp.status == 404):
                    raise
        return deleted


# -------------------------
# Event body builder (tides)
# -------------------------

def event_body_from_tide(entry: Dict[str, Any], duration_minutes: int = 10, timezone_str="Australia/Brisbane") -> Dict[str, Any]:
    """Create a Google Calendar event body from a WillyWeather tide entry."""
    start_dt = datetime.fromisoformat(entry["dateTime"])
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    tide_type = (entry.get("type") or "").lower()
    height = entry.get("height")

    emoji = "🌊" if tide_type == "high" else "🏝️"

    return {
        "summary": f"{emoji} {tide_type.title()} tide {height} m",
        "description": f"Tide: {tide_type}\nHeight: {height} m\nSource: WillyWeather\n",
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": timezone_str,        
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": timezone_str,        
        },
        "colorId": COLOR_MAP.get(tide_type, "9"),
        "extendedProperties": {
            "private": {
                "syncKey": f"tide:{entry['dateTime']}"  # 👈 simple unique key
            }
        }
    }

