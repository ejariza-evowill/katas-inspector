import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import codewars_report
import formatting
import google_auth
import input_source
import retrieval


class LoadSheetUsersTests(unittest.TestCase):
    def test_load_sheet_users_accepts_case_insensitive_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "users.csv"
            csv_path.write_text(
                "Flow,Name,User Name\n"
                "Flow A,Alice,alice\n"
                "Flow B,Bob,\n",
                encoding="utf-8",
            )

            users = input_source.load_sheet_users(csv_path)

        self.assertEqual(
            users,
            [retrieval.SheetUser(flow="Flow A", name="Alice", username="alice")],
        )


class GoogleInputSourceTests(unittest.TestCase):
    def test_parse_google_source_extracts_spreadsheet_id_and_gid(self) -> None:
        source = input_source.parse_google_source(
            "https://docs.google.com/spreadsheets/d/abc123/edit#gid=456"
        )

        self.assertEqual(
            source,
            input_source.GoogleSource(kind="spreadsheet", file_id="abc123", gid="456"),
        )

    def test_load_sheet_users_from_source_uses_google_sheet_rows(self) -> None:
        with mock.patch(
            "input_source.fetch_google_sheet_rows",
            return_value=[
                ["Flow", "name", "username"],
                ["Flow A", "Alice", "alice"],
            ],
        ) as fetch_google_sheet_rows:
            users = input_source.load_sheet_users_from_source(
                "https://docs.google.com/spreadsheets/d/abc123/edit#gid=456",
                timeout_seconds=30,
                google_access_token="token",
            )

        fetch_google_sheet_rows.assert_called_once_with(
            "abc123",
            gid="456",
            access_token="token",
            timeout_seconds=30,
        )
        self.assertEqual(
            users,
            [retrieval.SheetUser(flow="Flow A", name="Alice", username="alice")],
        )


class GoogleAuthTests(unittest.TestCase):
    def test_resolve_google_access_token_prefers_explicit_token(self) -> None:
        token = google_auth.resolve_google_access_token(
            explicit_access_token="explicit-token",
            credentials_file=None,
            token_cache_file=None,
            timeout_seconds=30,
        )

        self.assertEqual(token, "explicit-token")

    def test_get_google_access_token_refreshes_authorized_user(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            credentials_path = Path(temp_dir) / "authorized-user.json"
            credentials_path.write_text(
                (
                    '{"type":"authorized_user","client_id":"client-id",'
                    '"client_secret":"client-secret","refresh_token":"refresh-me",'
                    '"token_uri":"https://oauth2.googleapis.com/token"}'
                ),
                encoding="utf-8",
            )

            with mock.patch(
                "google_auth.refresh_authorized_user",
                return_value=(
                    "fresh-access-token",
                    {
                        "type": "authorized_user",
                        "client_id": "client-id",
                        "client_secret": "client-secret",
                        "refresh_token": "refresh-me",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    },
                ),
            ) as refresh_authorized_user:
                token = google_auth.get_google_access_token(
                    credentials_path,
                    token_cache_path=Path(temp_dir) / "unused.token.json",
                    timeout_seconds=30,
                )

        refresh_authorized_user.assert_called_once()
        self.assertEqual(token, "fresh-access-token")

    def test_get_google_access_token_uses_cached_authorized_user_for_desktop_client(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            credentials_path = Path(temp_dir) / "credentials.json"
            cache_path = Path(temp_dir) / "credentials.token.json"
            credentials_path.write_text(
                '{"installed":{"client_id":"client-id","client_secret":"client-secret"}}',
                encoding="utf-8",
            )
            cache_path.write_text(
                (
                    '{"type":"authorized_user","client_id":"client-id",'
                    '"client_secret":"client-secret","refresh_token":"refresh-me",'
                    '"token_uri":"https://oauth2.googleapis.com/token"}'
                ),
                encoding="utf-8",
            )

            with mock.patch(
                "google_auth.refresh_authorized_user",
                return_value=(
                    "fresh-access-token",
                    {
                        "type": "authorized_user",
                        "client_id": "client-id",
                        "client_secret": "client-secret",
                        "refresh_token": "refresh-me",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    },
                ),
            ) as refresh_authorized_user:
                token = google_auth.get_google_access_token(
                    credentials_path,
                    token_cache_path=cache_path,
                    timeout_seconds=30,
                )

        refresh_authorized_user.assert_called_once()
        self.assertEqual(token, "fresh-access-token")

    def test_parse_google_oauth_client_rejects_web_client(self) -> None:
        with self.assertRaisesRegex(ValueError, "Desktop app OAuth client"):
            google_auth.parse_google_oauth_client(
                {
                    "web": {
                        "client_id": "client-id",
                        "client_secret": "client-secret",
                    }
                }
            )


class ChallengeFilterTests(unittest.TestCase):
    def test_challenge_matches_applies_date_and_language_filters(self) -> None:
        challenge = retrieval.CompletedKata(
            flow="Flow A",
            name="Alice",
            username="alice",
            kata_id="kata-1",
            kata_name="Example Kata",
            kata_slug="example-kata",
            completed_at="2026-04-10T15:30:00Z",
            completed_languages=("python", "javascript"),
        )

        self.assertTrue(
            retrieval.challenge_matches(
                challenge,
                retrieval.parse_date_arg("2026-04-01"),
                retrieval.parse_date_arg("2026-04-30", inclusive_end=True),
                "python",
            )
        )
        self.assertFalse(
            retrieval.challenge_matches(
                challenge,
                retrieval.parse_date_arg("2026-04-11"),
                None,
                "python",
            )
        )
        self.assertFalse(
            retrieval.challenge_matches(
                challenge,
                None,
                None,
                "ruby",
            )
        )

    def test_resolve_date_range_uses_relative_period(self) -> None:
        now = retrieval.datetime(2026, 4, 20, 12, 0, tzinfo=retrieval.timezone.utc)

        start_at, end_before = retrieval.resolve_date_range(
            from_date=None,
            to_date=None,
            period="week",
            now=now,
        )

        self.assertEqual(start_at, retrieval.datetime(2026, 4, 13, 12, 0, tzinfo=retrieval.timezone.utc))
        self.assertEqual(end_before, now)

    def test_resolve_date_range_rejects_mixing_period_and_explicit_dates(self) -> None:
        with self.assertRaisesRegex(ValueError, "--period cannot be combined"):
            retrieval.resolve_date_range(
                from_date="2026-04-01",
                to_date=None,
                period="month",
            )

    def test_resolve_date_range_uses_latest_named_weekday(self) -> None:
        now = retrieval.datetime(2026, 4, 21, 15, 45, tzinfo=retrieval.timezone.utc)

        start_at, end_before = retrieval.resolve_date_range(
            from_date=None,
            to_date=None,
            period=None,
            from_last="saturday",
            now=now,
        )

        self.assertEqual(start_at, retrieval.datetime(2026, 4, 18, 0, 0, tzinfo=retrieval.timezone.utc))
        self.assertEqual(end_before, now)

    def test_resolve_date_range_from_last_same_weekday_counts_today_only(self) -> None:
        now = retrieval.datetime(2026, 4, 18, 15, 45, tzinfo=retrieval.timezone.utc)

        start_at, end_before = retrieval.resolve_date_range(
            from_date=None,
            to_date=None,
            period=None,
            from_last="saturday",
            now=now,
        )

        self.assertEqual(start_at, retrieval.datetime(2026, 4, 18, 0, 0, tzinfo=retrieval.timezone.utc))
        self.assertEqual(end_before, now)

    def test_resolve_date_range_uses_ukrainian_last_week_after_friday_boundary(self) -> None:
        now = retrieval.datetime(2026, 8, 7, 17, 0, tzinfo=retrieval.timezone.utc)

        start_at, end_before = retrieval.resolve_date_range(
            from_date=None,
            to_date=None,
            period=None,
            ukrainian_last_week=True,
            now=now,
        )

        self.assertEqual(start_at, retrieval.datetime(2026, 7, 31, 14, 0, tzinfo=retrieval.timezone.utc))
        self.assertEqual(end_before, retrieval.datetime(2026, 8, 7, 14, 0, tzinfo=retrieval.timezone.utc))

    def test_resolve_date_range_uses_previous_ukrainian_week_before_friday_boundary(self) -> None:
        now = retrieval.datetime(2026, 8, 7, 10, 0, tzinfo=retrieval.timezone.utc)

        start_at, end_before = retrieval.resolve_date_range(
            from_date=None,
            to_date=None,
            period=None,
            ukrainian_last_week=True,
            now=now,
        )

        self.assertEqual(start_at, retrieval.datetime(2026, 7, 24, 14, 0, tzinfo=retrieval.timezone.utc))
        self.assertEqual(end_before, retrieval.datetime(2026, 7, 31, 14, 0, tzinfo=retrieval.timezone.utc))

    def test_resolve_date_range_rejects_mixing_ukrainian_last_week_and_explicit_dates(self) -> None:
        with self.assertRaisesRegex(ValueError, "--ukrainian-last-week cannot be combined"):
            retrieval.resolve_date_range(
                from_date="2026-04-01",
                to_date=None,
                period=None,
                ukrainian_last_week=True,
            )

    def test_resolve_date_range_rejects_mixing_from_last_and_explicit_dates(self) -> None:
        with self.assertRaisesRegex(ValueError, "--from-last cannot be combined"):
            retrieval.resolve_date_range(
                from_date=None,
                to_date="2026-04-20",
                period=None,
                from_last="saturday",
            )


class SummaryFormattingTests(unittest.TestCase):
    def test_format_summary_rows_sorts_by_solved_count_desc_then_flow_desc(self) -> None:
        users = [
            retrieval.SheetUser(flow="Flow A", name="Alice", username="alice"),
            retrieval.SheetUser(flow="Flow B", name="Bob", username="bob"),
            retrieval.SheetUser(flow="Flow C", name="Carol", username="carol"),
        ]
        completed_katas = [
            retrieval.CompletedKata(
                flow="Flow B",
                name="Bob",
                username="bob",
                kata_id="1",
                kata_name="One",
                kata_slug="one",
                completed_at="2026-04-01T00:00:00Z",
                completed_languages=("python",),
            ),
            retrieval.CompletedKata(
                flow="Flow B",
                name="Bob",
                username="bob",
                kata_id="2",
                kata_name="Two",
                kata_slug="two",
                completed_at="2026-04-02T00:00:00Z",
                completed_languages=("python",),
            ),
            retrieval.CompletedKata(
                flow="Flow A",
                name="Alice",
                username="alice",
                kata_id="3",
                kata_name="Three",
                kata_slug="three",
                completed_at="2026-04-03T00:00:00Z",
                completed_languages=("python",),
            ),
            retrieval.CompletedKata(
                flow="Flow C",
                name="Carol",
                username="carol",
                kata_id="4",
                kata_name="Four",
                kata_slug="four",
                completed_at="2026-04-04T00:00:00Z",
                completed_languages=("python",),
            ),
        ]

        summary_rows = formatting.format_summary_rows(
            formatting.build_user_counts(users, completed_katas)
        )

        self.assertEqual(
            summary_rows,
            [
                {
                    "name": "Bob",
                    "username": "bob",
                    "solved_count": "2",
                },
                {
                    "name": "Carol",
                    "username": "carol",
                    "solved_count": "1",
                },
                {
                    "name": "Alice",
                    "username": "alice",
                    "solved_count": "1",
                },
            ],
        )

    def test_format_summary_table_returns_printable_table(self) -> None:
        summary_rows = [
            {
                "name": "Alice",
                "username": "alice",
                "solved_count": "3",
            }
        ]

        table = formatting.format_summary_table(summary_rows)

        self.assertIn("KATAS RANKING", table)
        self.assertIn("\033[", table)
        self.assertIn("🥇 Alice", table)
        self.assertIn("solved_count", table)
        self.assertIn("Alice", table)
        self.assertIn("alice", table)
        self.assertNotIn("Flow A", table)

    def test_format_summary_table_uses_cyan_for_non_top_three_names(self) -> None:
        summary_rows = [
            {"name": "Alice", "username": "alice", "solved_count": "4"},
            {"name": "Bob", "username": "bob", "solved_count": "3"},
            {"name": "Carol", "username": "carol", "solved_count": "2"},
            {"name": "Dave", "username": "dave", "solved_count": "1"},
        ]

        table = formatting.format_summary_table(summary_rows)

        self.assertIn(f"{formatting.ANSI_CYAN}Dave", table)

    def test_visible_width_treats_medal_emoji_as_double_width(self) -> None:
        self.assertEqual(formatting.visible_width("🥇 Alice"), len(" Alice") + 2)


class AsyncRetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_retrieve_completed_katas_fetches_users_concurrently(self) -> None:
        users = [
            retrieval.SheetUser(flow="Flow A", name="Alice", username="alice"),
            retrieval.SheetUser(flow="Flow B", name="Bob", username="bob"),
        ]

        async def fake_to_thread(func, username, **kwargs):
            self.assertIs(func, retrieval.fetch_completed_challenges)
            await asyncio.sleep(0)
            return [
                {
                    "id": f"{username}-1",
                    "name": f"{username} kata",
                    "slug": f"{username}-kata",
                    "completedAt": "2026-04-10T15:30:00Z",
                    "completedLanguages": ["python"],
                }
            ]

        with mock.patch("retrieval.asyncio.to_thread", side_effect=fake_to_thread):
            completed_katas = await retrieval.retrieve_completed_katas(
                users,
                start_at=retrieval.parse_date_arg("2026-04-01"),
                end_before=retrieval.parse_date_arg("2026-04-30", inclusive_end=True),
                language="python",
                timeout_seconds=30,
                pause_seconds=0.0,
            )

        self.assertEqual(
            completed_katas,
            [
                retrieval.CompletedKata(
                    flow="Flow A",
                    name="Alice",
                    username="alice",
                    kata_id="alice-1",
                    kata_name="alice kata",
                    kata_slug="alice-kata",
                    completed_at="2026-04-10T15:30:00Z",
                    completed_languages=("python",),
                ),
                retrieval.CompletedKata(
                    flow="Flow B",
                    name="Bob",
                    username="bob",
                    kata_id="bob-1",
                    kata_name="bob kata",
                    kata_slug="bob-kata",
                    completed_at="2026-04-10T15:30:00Z",
                    completed_languages=("python",),
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
