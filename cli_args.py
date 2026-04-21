from __future__ import annotations

import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read a local CSV or a Google Drive/Sheets source with Flow,name,username columns, "
            "fetch Codewars completions, and generate a detailed report plus a per-user summary."
        )
    )
    parser.add_argument(
        "sheet_source",
        help="Local CSV path or Google Sheets/Drive URL for the source spreadsheet.",
    )
    parser.add_argument(
        "--from-date",
        dest="from_date",
        help="Inclusive start date in UTC, format YYYY-MM-DD.",
    )
    parser.add_argument(
        "--to-date",
        dest="to_date",
        help="Inclusive end date in UTC, format YYYY-MM-DD.",
    )
    parser.add_argument(
        "--period",
        choices=("week", "month", "year"),
        help="Rolling UTC window ending now: week=7 days, month=30 days, year=365 days.",
    )
    parser.add_argument(
        "--language",
        help="Optional language filter, for example python.",
    )
    parser.add_argument(
        "--details-out",
        default="completed_katas.csv",
        help="Output CSV for individual completed kata rows.",
    )
    parser.add_argument(
        "--summary-out",
        default="summary.csv",
        help="Output CSV for per-user solved counts.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="HTTP timeout per request.",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.0,
        help="Optional pause between paginated requests for the same user.",
    )
    parser.add_argument(
        "--google-access-token-env",
        default="GOOGLE_ACCESS_TOKEN",
        help="Env var name containing a Google OAuth bearer token for Google sources.",
    )
    parser.add_argument(
        "--google-credentials-file",
        help="Path to Google OAuth credentials.json or authorized_user token JSON.",
    )
    return parser.parse_args()
