#!/usr/bin/env python3
"""Build Codewars completion reports from a spreadsheet export."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from cli_args import parse_args
from formatting import (
    build_user_counts,
    format_detail_rows,
    format_summary_rows,
    format_summary_table,
    write_csv,
)
from google_auth import resolve_google_access_token
from input_source import load_sheet_users_from_source
from retrieval import resolve_date_range, retrieve_completed_katas


def main() -> int:
    args = parse_args()
    google_access_token = resolve_google_access_token(
        explicit_access_token=os.getenv(args.google_access_token_env),
        credentials_file=args.google_credentials_file,
        token_cache_file=args.google_token_cache_file,
        timeout_seconds=args.timeout_seconds,
    )
    users = load_sheet_users_from_source(
        args.sheet_source,
        timeout_seconds=args.timeout_seconds,
        google_access_token=google_access_token,
    )
    start_at, end_before = resolve_date_range(
        from_date=args.from_date,
        to_date=args.to_date,
        period=args.period,
        from_last=args.from_last,
        ukrainian_last_week=args.ukrainian_last_week,
    )

    completed_katas = asyncio.run(
        retrieve_completed_katas(
            users,
            start_at=start_at,
            end_before=end_before,
            language=args.language,
            timeout_seconds=args.timeout_seconds,
            pause_seconds=args.pause_seconds,
        )
    )
    detail_rows = format_detail_rows(completed_katas)
    summary_rows = format_summary_rows(build_user_counts(users, completed_katas))

    write_csv(
        Path(args.details_out),
        [
            "flow",
            "name",
            "username",
            "kata_id",
            "kata_name",
            "kata_slug",
            "completed_at",
            "completed_languages",
        ],
        detail_rows,
    )
    write_csv(
        Path(args.summary_out),
        ["name", "username", "solved_count"],
        summary_rows,
    )

    print(format_summary_table(summary_rows))
    print(f"\nWrote {len(detail_rows)} completion rows to {args.details_out}.", file=sys.stderr)
    print(f"Wrote {len(summary_rows)} summary rows to {args.summary_out}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
