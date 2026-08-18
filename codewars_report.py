#!/usr/bin/env python3
"""Build Codewars completion reports from a spreadsheet export."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from cli_args import parse_args
from formatting import (
    build_user_totals,
    format_detail_rows,
    format_summary_rows,
    format_summary_table,
    write_csv,
)
from google_auth import resolve_google_access_token
from input_source import load_sheet_users_from_source
from retrieval import (
    KataMetadata,
    apply_kata_scores,
    load_kata_cache,
    load_scoring_rules,
    resolve_date_range,
    resolve_kata_metadata,
    retrieve_completed_katas,
    write_kata_cache,
)


def count_unique_kata_cache_records(kata_cache: dict[str, KataMetadata]) -> int:
    return len(
        {
            (metadata.kata_id, metadata.kata_slug)
            for metadata in kata_cache.values()
        }
    )


def format_metadata_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def write_report_metadata(
    path: Path,
    *,
    start_at: datetime | None,
    end_before: datetime | None,
) -> bool:
    if start_at is None and end_before is None:
        return False

    payload = {
        "date_range": {
            "start_at": format_metadata_datetime(start_at),
            "end_before": format_metadata_datetime(end_before),
        }
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


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

    scoring_rules = load_scoring_rules(Path(args.scoring_rules_file))
    kata_cache_path = Path(args.kata_cache_file)
    kata_cache = load_kata_cache(kata_cache_path)

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
    kata_metadata = asyncio.run(
        resolve_kata_metadata(
            completed_katas,
            cache=kata_cache,
            timeout_seconds=args.timeout_seconds,
        )
    )
    completed_katas = apply_kata_scores(
        completed_katas,
        metadata_by_kata_id=kata_metadata,
        scoring_rules=scoring_rules,
    )
    write_kata_cache(kata_cache_path, kata_cache)

    detail_rows = format_detail_rows(completed_katas)
    summary_rows = format_summary_rows(build_user_totals(users, completed_katas))

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
            "kata_rank_id",
            "kata_rank_name",
            "awarded_score",
        ],
        detail_rows,
    )
    write_csv(
        Path(args.summary_out),
        ["flow", "name", "username", "solved_count", "total_score"],
        summary_rows,
    )
    wrote_metadata = write_report_metadata(
        Path(args.metadata_out),
        start_at=start_at,
        end_before=end_before,
    )

    print(format_summary_table(summary_rows))
    print(f"\nWrote {len(detail_rows)} completion rows to {args.details_out}.", file=sys.stderr)
    print(f"Wrote {len(summary_rows)} summary rows to {args.summary_out}.", file=sys.stderr)
    if wrote_metadata:
        print(f"Wrote report metadata to {args.metadata_out}.", file=sys.stderr)
    print(
        f"Wrote {count_unique_kata_cache_records(kata_cache)} kata cache records to {kata_cache_path}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
