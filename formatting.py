from __future__ import annotations

import csv
import unicodedata
from pathlib import Path
from typing import Iterable

from retrieval import CompletedKata, SheetUser

ANSI_RESET = "\033[0m"
ANSI_BOLD_BRIGHT_GREEN = "\033[1;92m"
ANSI_GREEN = "\033[32m"
ANSI_DIM_GREEN = "\033[2;32m"
ANSI_BRIGHT_CYAN = "\033[1;96m"
ANSI_BRIGHT_YELLOW = "\033[1;93m"
ANSI_BRIGHT_WHITE = "\033[1;97m"
ANSI_CYAN = "\033[96m"
ANSI_BRONZE = "\033[38;5;208m"


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
    summary_rows.sort(key=lambda row: row[0].username.lower())
    summary_rows.sort(key=lambda row: row[0].name.lower())
    summary_rows.sort(key=lambda row: row[0].flow.lower(), reverse=True)
    summary_rows.sort(key=lambda row: row[1], reverse=True)
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


def colorize(text: str, color: str) -> str:
    return f"{color}{text}{ANSI_RESET}"


def visible_width(text: str) -> int:
    width = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        if char in {"\u200d", "\ufe0f"}:
            continue
        if unicodedata.category(char)[0] == "C":
            continue
        width += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
    return width


def pad_visible(text: str, width: int, *, align: str = "left") -> str:
    padding = max(0, width - visible_width(text))
    if align == "right":
        return (" " * padding) + text
    if align == "center":
        left_padding = padding // 2
        right_padding = padding - left_padding
        return (" " * left_padding) + text + (" " * right_padding)
    return text + (" " * padding)


def format_summary_table(summary_rows: Iterable[dict[str, str]]) -> str:
    rows = list(summary_rows)
    headers = ["name", "username", "solved_count"]
    medal_styles = [
        ("🥇", ANSI_BRIGHT_YELLOW),
        ("🥈", ANSI_BRIGHT_WHITE),
        ("🥉", ANSI_BRONZE),
    ]
    display_rows: list[dict[str, str | None]] = []
    for index, row in enumerate(rows):
        medal_label: str | None = None
        medal_color: str | None = None
        display_name = row["name"]
        if index < len(medal_styles):
            medal_label, medal_color = medal_styles[index]
            display_name = f"{medal_label} {row['name']}"
        display_rows.append(
            {
                **row,
                "display_name": display_name,
                "medal_label": medal_label,
                "medal_color": medal_color,
            }
        )

    widths = {
        "name": max(visible_width("name"), *(visible_width(str(row["display_name"])) for row in display_rows))
        if display_rows
        else visible_width("name"),
        "username": max(visible_width("username"), *(visible_width(str(row["username"])) for row in display_rows))
        if display_rows
        else visible_width("username"),
        "solved_count": max(
            visible_width("solved_count"),
            *(visible_width(str(row["solved_count"])) for row in display_rows),
        )
        if display_rows
        else visible_width("solved_count"),
    }
    total_width = 1 + sum(widths[header] + 3 for header in headers)
    total_width += len(headers)

    def border_line() -> str:
        segments = ["-" * (widths[header] + 2) for header in headers]
        return colorize("+" + "+".join(segments) + "+", ANSI_DIM_GREEN)

    def build_row(values: dict[str, str] | None = None, *, header: bool = False) -> str:
        cells: list[str] = []
        for column in headers:
            if header:
                header_text = pad_visible(
                    column,
                    widths[column],
                    align="right" if column == "solved_count" else "left",
                )
                content = colorize(header_text, ANSI_BRIGHT_CYAN)
            else:
                if column == "name":
                    value = pad_visible(str(values["display_name"]), widths[column]) if values else (" " * widths[column])
                    medal_color = values.get("medal_color") if values else None
                    if isinstance(medal_color, str):
                        content = colorize(value, medal_color)
                    else:
                        content = colorize(value, ANSI_CYAN)
                else:
                    value = (
                        pad_visible(str(values[column]), widths[column], align="right")
                        if column == "solved_count"
                        else pad_visible(str(values[column]), widths[column])
                    ) if values else (" " * widths[column])
                    content = colorize(value, ANSI_BRIGHT_YELLOW if column == "solved_count" else ANSI_CYAN)
            cells.append(f" {content} ")
        return colorize("|", ANSI_GREEN) + colorize("|", ANSI_GREEN).join(cells) + colorize("|", ANSI_GREEN)


    art_line = pad_visible(".:: ꧁⎝ 𓆩༺   KATAS   RANKING   ༻𓆪 ⎠꧂::.", total_width, align="center")
    separator_line = "=" * total_width

    lines = [
        colorize(separator_line, ANSI_DIM_GREEN),
        "",
        colorize(art_line, ANSI_BRIGHT_CYAN),
        "",
        colorize(separator_line, ANSI_DIM_GREEN),
        border_line(),
        build_row(header=True),
        border_line(),
    ]
    for row in display_rows:
        lines.append(build_row(row))
    lines.append(border_line())
    return "\n".join(lines)
