from __future__ import annotations

import asyncio
import csv
import json
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


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
    kata_rank_id: int | None = None
    kata_rank_name: str = ""
    awarded_score: int = 0


@dataclass(frozen=True)
class SheetUser:
    flow: str
    name: str
    username: str


@dataclass(frozen=True)
class KataMetadata:
    kata_id: str
    kata_slug: str
    kata_rank_id: int | None
    kata_rank_name: str


@dataclass(frozen=True)
class ScoringRule:
    rank_id: int
    rank_name: str
    awarded_score: int


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
CODE_CHALLENGE_URL = "https://www.codewars.com/api/v1/code-challenges/{challenge}"
UKRAINE_TIMEZONE = ZoneInfo("Europe/Kyiv")
UKRAINIAN_WEEK_BOUNDARY_WEEKDAY = 4
UKRAINIAN_WEEK_BOUNDARY_TIME = dt_time(17, 0)


def load_scoring_rules(path: Path) -> dict[int, ScoringRule]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required_fields = {"rank_id", "rank_name", "awarded_score"}
        if reader.fieldnames is None or not required_fields.issubset(reader.fieldnames):
            raise ValueError(
                f"{path} must contain columns: rank_id, rank_name, awarded_score."
            )

        rules: dict[int, ScoringRule] = {}
        for line_number, row in enumerate(reader, start=2):
            try:
                rank_id = int(row["rank_id"])
                awarded_score = int(row["awarded_score"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{path}:{line_number} contains an invalid rank score row.") from exc

            rules[rank_id] = ScoringRule(
                rank_id=rank_id,
                rank_name=(row.get("rank_name") or "").strip(),
                awarded_score=awarded_score,
            )
    return rules


def load_kata_cache(path: Path) -> dict[str, KataMetadata]:
    if not path.exists():
        return {}

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required_fields = {"kata_id", "kata_slug", "kata_rank_id", "kata_rank_name"}
        if reader.fieldnames is None or not required_fields.issubset(reader.fieldnames):
            raise ValueError(
                f"{path} must contain columns: kata_id, kata_slug, kata_rank_id, kata_rank_name."
            )

        cache: dict[str, KataMetadata] = {}
        for line_number, row in enumerate(reader, start=2):
            kata_id = (row.get("kata_id") or "").strip()
            kata_slug = (row.get("kata_slug") or "").strip()
            if not kata_id and not kata_slug:
                print(f"Skipping cache row {line_number}: empty kata_id and kata_slug.", file=sys.stderr)
                continue

            rank_id_value = (row.get("kata_rank_id") or "").strip()
            try:
                rank_id = int(rank_id_value) if rank_id_value else None
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number} contains an invalid kata_rank_id.") from exc

            metadata = KataMetadata(
                kata_id=kata_id,
                kata_slug=kata_slug,
                kata_rank_id=rank_id,
                kata_rank_name=(row.get("kata_rank_name") or "").strip(),
            )
            if kata_id:
                cache[kata_id] = metadata
            if kata_slug:
                cache[kata_slug] = metadata
    return cache


def write_kata_cache(path: Path, cache: dict[str, KataMetadata]) -> None:
    by_id_or_slug: dict[str, KataMetadata] = {}
    for metadata in cache.values():
        key = metadata.kata_id or metadata.kata_slug
        if key:
            by_id_or_slug[key] = metadata

    rows = sorted(
        by_id_or_slug.values(),
        key=lambda metadata: (
            metadata.kata_rank_id is None,
            metadata.kata_rank_id or 0,
            metadata.kata_slug,
            metadata.kata_id,
        ),
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["kata_id", "kata_slug", "kata_rank_id", "kata_rank_name"],
        )
        writer.writeheader()
        for metadata in rows:
            writer.writerow(
                {
                    "kata_id": metadata.kata_id,
                    "kata_slug": metadata.kata_slug,
                    "kata_rank_id": "" if metadata.kata_rank_id is None else str(metadata.kata_rank_id),
                    "kata_rank_name": metadata.kata_rank_name,
                }
            )


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


def fetch_code_challenge_metadata(
    challenge: str,
    *,
    timeout_seconds: int,
) -> KataMetadata:
    url = CODE_CHALLENGE_URL.format(challenge=quote(challenge))
    request = Request(url, headers={"User-Agent": "katas-evaluator/1.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"{challenge}: Codewars returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError(f"{challenge}: could not reach Codewars ({exc.reason}).") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"{challenge}: unexpected Codewars challenge response format.")

    rank_payload = payload.get("rank", {})
    rank_id: int | None = None
    rank_name = ""
    if isinstance(rank_payload, dict):
        raw_rank_id = rank_payload.get("id")
        raw_rank_name = rank_payload.get("name")
        if isinstance(raw_rank_id, int):
            rank_id = raw_rank_id
        if isinstance(raw_rank_name, str):
            rank_name = raw_rank_name

    return KataMetadata(
        kata_id=str(payload.get("id") or ""),
        kata_slug=str(payload.get("slug") or ""),
        kata_rank_id=rank_id,
        kata_rank_name=rank_name,
    )


async def resolve_kata_metadata(
    completed_katas: Iterable[CompletedKata],
    *,
    cache: dict[str, KataMetadata],
    timeout_seconds: int,
) -> dict[str, KataMetadata]:
    metadata_by_kata_id: dict[str, KataMetadata] = {}
    missing_challenges: dict[str, str] = {}

    for kata in completed_katas:
        cached_metadata = cache.get(kata.kata_id) or cache.get(kata.kata_slug)
        if cached_metadata:
            metadata_by_kata_id[kata.kata_id] = cached_metadata
            continue

        challenge = kata.kata_id or kata.kata_slug
        if challenge:
            missing_challenges[challenge] = challenge

    async def fetch_missing(challenge: str) -> tuple[str, KataMetadata | None]:
        try:
            metadata = await asyncio.to_thread(
                fetch_code_challenge_metadata,
                challenge,
                timeout_seconds=timeout_seconds,
            )
        except RuntimeError as exc:
            print(f"Warning: {exc}", file=sys.stderr)
            return challenge, None
        return challenge, metadata

    if missing_challenges:
        tasks = [asyncio.create_task(fetch_missing(challenge)) for challenge in missing_challenges]
        for challenge, metadata in await asyncio.gather(*tasks):
            if metadata is None:
                continue
            cache[challenge] = metadata
            if metadata.kata_id:
                cache[metadata.kata_id] = metadata
            if metadata.kata_slug:
                cache[metadata.kata_slug] = metadata
            metadata_by_kata_id[metadata.kata_id or challenge] = metadata

    for kata in completed_katas:
        if kata.kata_id not in metadata_by_kata_id:
            cached_metadata = cache.get(kata.kata_id) or cache.get(kata.kata_slug)
            if cached_metadata:
                metadata_by_kata_id[kata.kata_id] = cached_metadata

    return metadata_by_kata_id


def apply_kata_scores(
    completed_katas: Iterable[CompletedKata],
    *,
    metadata_by_kata_id: dict[str, KataMetadata],
    scoring_rules: dict[int, ScoringRule],
) -> list[CompletedKata]:
    scored_katas: list[CompletedKata] = []
    for kata in completed_katas:
        metadata = metadata_by_kata_id.get(kata.kata_id)
        rank_id = metadata.kata_rank_id if metadata else None
        rank_name = metadata.kata_rank_name if metadata else ""
        awarded_score = scoring_rules[rank_id].awarded_score if rank_id in scoring_rules else 0
        scored_katas.append(
            CompletedKata(
                flow=kata.flow,
                name=kata.name,
                username=kata.username,
                kata_id=kata.kata_id,
                kata_name=kata.kata_name,
                kata_slug=kata.kata_slug,
                completed_at=kata.completed_at,
                completed_languages=kata.completed_languages,
                kata_rank_id=rank_id,
                kata_rank_name=rank_name,
                awarded_score=awarded_score,
            )
        )
    return scored_katas


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


def resolve_ukrainian_last_week(now: datetime) -> tuple[datetime, datetime]:
    now_ukraine = now.astimezone(UKRAINE_TIMEZONE)
    days_since_friday = (now_ukraine.weekday() - UKRAINIAN_WEEK_BOUNDARY_WEEKDAY) % 7
    boundary_date = (now_ukraine - timedelta(days=days_since_friday)).date()
    end_local = datetime.combine(
        boundary_date,
        UKRAINIAN_WEEK_BOUNDARY_TIME,
        tzinfo=UKRAINE_TIMEZONE,
    )
    if end_local > now_ukraine:
        end_local -= timedelta(days=7)

    start_local = end_local - timedelta(days=7)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def resolve_date_range(
    *,
    from_date: str | None,
    to_date: str | None,
    period: str | None,
    from_last: str | None = None,
    ukrainian_last_week: bool = False,
    now: datetime | None = None,
) -> tuple[datetime | None, datetime | None]:
    if period and (from_date or to_date or from_last or ukrainian_last_week):
        raise ValueError(
            "--period cannot be combined with --from-date, --to-date, --from-last, "
            "or --ukrainian-last-week."
        )

    if from_last and (from_date or to_date or ukrainian_last_week):
        raise ValueError(
            "--from-last cannot be combined with --from-date, --to-date, "
            "or --ukrainian-last-week."
        )

    if ukrainian_last_week and (from_date or to_date):
        raise ValueError("--ukrainian-last-week cannot be combined with --from-date or --to-date.")

    if now is None:
        now = datetime.now(timezone.utc)

    if ukrainian_last_week:
        return resolve_ukrainian_last_week(now)

    if period:
        period_days = {
            "week": 7,
            "month": 30,
            "year": 365,
        }
        if period not in period_days:
            raise ValueError(f"Unsupported period: {period}.")
        return now - timedelta(days=period_days[period]), now

    if from_last:
        weekdays = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        target_weekday = weekdays.get(from_last)
        if target_weekday is None:
            raise ValueError(f"Unsupported weekday: {from_last}.")

        days_since_target = (now.weekday() - target_weekday) % 7
        start_date = (now - timedelta(days=days_since_target)).date()
        start_at = datetime.combine(start_date, dt_time.min, tzinfo=timezone.utc)
        return start_at, now

    start_at = parse_date_arg(from_date)
    end_before = parse_date_arg(to_date, inclusive_end=True)
    if start_at and end_before and start_at >= end_before:
        raise ValueError("--from-date must be earlier than or equal to --to-date.")
    return start_at, end_before
