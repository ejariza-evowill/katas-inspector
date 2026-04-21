from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from retrieval import CompletedKata, SheetUser


def build_user_counts(
    users: Iterable[SheetUser],
    completed_katas: Iterable[CompletedKata],
) -> list[tuple[SheetUser, int]]:
    counts: dict[tuple[str, str, str], int] = {}
    for user in users:
        counts[(user.flow, user.name, user.username)] = 0

    for kata in completed_katas:
        key = (kata.flow, kata.name, kata.username)
        counts[key] = counts.get(key, 0) + 1

    summary_rows = [
        (
            SheetUser(flow=flow, name=name, username=username),
            count,
        )
        for (flow, name, username), count in counts.items()
    ]
    summary_rows.sort(
        key=lambda row: (
            -row[1],
            row[0].flow.lower(),
            row[0].name.lower(),
            row[0].username.lower(),
        )
    )
    return summary_rows


def format_detail_rows(completed_katas: Iterable[CompletedKata]) -> list[dict[str, str]]:
    return [
        {
            "flow": kata.flow,
            "name": kata.name,
            "username": kata.username,
            "kata_id": kata.kata_id,
            "kata_name": kata.kata_name,
            "kata_slug": kata.kata_slug,
            "completed_at": kata.completed_at,
            "completed_languages": ",".join(kata.completed_languages),
        }
        for kata in completed_katas
    ]


def format_summary_rows(summary_counts: Iterable[tuple[SheetUser, int]]) -> list[dict[str, str]]:
    return [
        {
            "flow": user.flow,
            "name": user.name,
            "username": user.username,
            "solved_count": str(count),
        }
        for user, count in summary_counts
    ]


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def format_summary_table(summary_rows: Iterable[dict[str, str]]) -> str:
    rows = list(summary_rows)
    headers = ["solved_count", "flow", "name", "username"]
    widths = {
        header: max(len(header), *(len(row[header]) for row in rows)) if rows else len(header)
        for header in headers
    }
    lines = [
        "  ".join(header.ljust(widths[header]) for header in headers),
        "  ".join("-" * widths[header] for header in headers),
    ]
    for row in rows:
        lines.append("  ".join(row[header].ljust(widths[header]) for header in headers))
    return "\n".join(lines)
