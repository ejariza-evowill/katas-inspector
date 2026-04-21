from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class CompletedKata:
    flow: str
    name: str
    username: str
    kata_id: str
    kata_name: str
    kata_slug: str
    completed_at: str
    completed_languages: tuple[str, ...]


@dataclass(frozen=True)
class SheetUser:
    flow: str
    name: str
    username: str


def build_completed_kata(user: SheetUser, challenge: dict[str, object]) -> CompletedKata:
    return CompletedKata(
        flow=user.flow,
        name=user.name,
        username=user.username,
        kata_id=str(challenge.get("id", "")),
        kata_name=str(challenge.get("name", "")),
        kata_slug=str(challenge.get("slug", "")),
        completed_at=str(challenge.get("completedAt", "")),
        completed_languages=tuple(str(item) for item in challenge.get("completedLanguages", [])),
    )


def parse_completed_at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def challenge_matches(
    challenge: CompletedKata,
    start_at: datetime | None,
    end_before: datetime | None,
    language: str | None,
) -> bool:
    completed_at = parse_completed_at(challenge.completed_at)
    if start_at and completed_at < start_at:
        return False
    if end_before and completed_at >= end_before:
        return False

    if language:
        languages = [item.lower() for item in challenge.completed_languages]
        if language.lower() not in languages:
            return False

    return True


API_URL = "https://www.codewars.com/api/v1/users/{username}/code-challenges/completed?page={page}"


def fetch_completed_challenges(
    username: str,
    *,
    timeout_seconds: int,
    pause_seconds: float,
) -> list[dict[str, object]]:
    page = 0
    collected: list[dict[str, object]] = []

    while True:
        url = API_URL.format(username=quote(username), page=page)
        request = Request(url, headers={"User-Agent": "katas-evaluator/1.0"})
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                payload = json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"{username}: Codewars returned HTTP {exc.code}.") from exc
        except URLError as exc:
            raise RuntimeError(f"{username}: could not reach Codewars ({exc.reason}).") from exc

        page_data = payload.get("data", [])
        if not isinstance(page_data, list):
            raise RuntimeError(f"{username}: unexpected Codewars response format.")

        collected.extend(page_data)
        total_pages = int(payload.get("totalPages", page + 1))
        page += 1
        if page >= total_pages:
            break

        if pause_seconds > 0:
            time.sleep(pause_seconds)

    return collected


async def retrieve_completed_katas_for_user(
    user: SheetUser,
    *,
    start_at: datetime | None,
    end_before: datetime | None,
    language: str | None,
    timeout_seconds: int,
    pause_seconds: float,
) -> list[CompletedKata]:
    print(f"Fetching Codewars completions for {user.username}...", file=sys.stderr)
    try:
        challenges = await asyncio.to_thread(
            fetch_completed_challenges,
            user.username,
            timeout_seconds=timeout_seconds,
            pause_seconds=pause_seconds,
        )
    except RuntimeError as exc:
        print(f"Warning: {exc}", file=sys.stderr)
        return []

    completed_katas: list[CompletedKata] = []
    for challenge in challenges:
        completed_kata = build_completed_kata(user, challenge)
        if not challenge_matches(completed_kata, start_at, end_before, language):
            continue

        completed_katas.append(completed_kata)
    return completed_katas


async def retrieve_completed_katas(
    users: Iterable[SheetUser],
    *,
    start_at: datetime | None,
    end_before: datetime | None,
    language: str | None,
    timeout_seconds: int,
    pause_seconds: float,
) -> list[CompletedKata]:
    tasks = [
        asyncio.create_task(
            retrieve_completed_katas_for_user(
                user,
                start_at=start_at,
                end_before=end_before,
                language=language,
                timeout_seconds=timeout_seconds,
                pause_seconds=pause_seconds,
            )
        )
        for user in users
    ]
    results = await asyncio.gather(*tasks)
    return [kata for user_katas in results for kata in user_katas]


def parse_date_arg(value: str | None, *, inclusive_end: bool = False) -> datetime | None:
    if value is None:
        return None
    parsed_date = date.fromisoformat(value)
    boundary = datetime.combine(parsed_date, dt_time.min, tzinfo=timezone.utc)
    if inclusive_end:
        return boundary + timedelta(days=1)
    return boundary


def resolve_date_range(
    *,
    from_date: str | None,
    to_date: str | None,
    period: str | None,
    now: datetime | None = None,
) -> tuple[datetime | None, datetime | None]:
    if period and (from_date or to_date):
        raise ValueError("--period cannot be combined with --from-date or --to-date.")

    if period:
        if now is None:
            now = datetime.now(timezone.utc)

        period_days = {
            "week": 7,
            "month": 30,
            "year": 365,
        }
        if period not in period_days:
            raise ValueError(f"Unsupported period: {period}.")
        return now - timedelta(days=period_days[period]), now

    start_at = parse_date_arg(from_date)
    end_before = parse_date_arg(to_date, inclusive_end=True)
    if start_at and end_before and start_at >= end_before:
        raise ValueError("--from-date must be earlier than or equal to --to-date.")
    return start_at, end_before
