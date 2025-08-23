from __future__ import annotations
import argparse
from .tidesync import TideSync

def build_cli() -> argparse.ArgumentParser:
    """Define the CLI for syncing or clearing tide events."""
    p = argparse.ArgumentParser(description="Sync WillyWeather tides to Google Calendar")
    p.add_argument("command", choices=["sync", "clear", "delete-range"], default="sync", help="Action to run")
    p.add_argument("--config", dest="config", default=None,
                   help="Path to config.json (default: project root)")
    p.add_argument("--start", dest="start", default=None,
                   help="YYYY-MM-DD start date (default: today)")
    p.add_argument("--days", dest="days", type=int, default=365, help="Window length in days (default: config WW_DAYS)")

    return p


def main():
    parser = build_cli()
    args = parser.parse_args()

    ts = TideSync(config_path=args.config)

    if args.command == "sync":
        count = ts.upsert(start_date=args.start)
        print(f"Inserted {count} tide events into calendar {ts.calendar_id}")
    elif args.command == "clear":
        ts.clear()
        print(f"Cleared all events from calendar {ts.calendar_id}")
    elif args.command == "delete-range":
        ts.delete_range(start_date=args.start, days=args.days)


if __name__ == "__main__":
    main()