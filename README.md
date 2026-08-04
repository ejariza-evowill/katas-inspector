# Katas Evaluator

CLI tool to read users from a local CSV or Google Sheets/Drive, fetch solved Codewars katas, and produce a detailed CSV plus a per-user count summary.

## Input

The source must contain these columns:

- `Flow`
- `name`
- `username`

The source can be:

- A local CSV path
- A Google Sheets URL
- A Google Drive file URL

## Basic Usage

Run with a local CSV:

```bash
.venv/bin/python codewars_report.py users.csv
```

Run with Google Sheets:

```bash
.venv/bin/python codewars_report.py \
  "https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit#gid=0" \
  --google-credentials-file ~/.config/gcloud/application_default_credentials.json
```

## Date Filters

Use explicit UTC dates:

```bash
.venv/bin/python codewars_report.py users.csv \
  --from-date 2026-04-01 \
  --to-date 2026-04-21
```

Use a rolling period ending now:

```bash
.venv/bin/python codewars_report.py users.csv --period week
.venv/bin/python codewars_report.py users.csv --period month
.venv/bin/python codewars_report.py users.csv --period year
```

Use the most recent named weekday, including that day:

```bash
.venv/bin/python codewars_report.py users.csv --from-last saturday
```

`--from-last saturday` means “from the latest Saturday at `00:00 UTC` through now.” If today is Saturday, it counts only today.

Use the last completed Ukrainian weekly window:

```bash
.venv/bin/python codewars_report.py users.csv --ukrainian-last-week
```

`--ukrainian-last-week` means “from the previous Friday at `17:00 Europe/Kyiv` through the last Friday at `17:00 Europe/Kyiv`.” The end boundary is exclusive. For example, if it is Friday at 20:00 in Ukraine, it reports the window from the previous Friday at 17:00 through today at 17:00.

`--period` cannot be combined with `--from-date`, `--to-date`, `--from-last`, or `--ukrainian-last-week`. `--from-last` cannot be combined with `--from-date`, `--to-date`, or `--ukrainian-last-week`. `--ukrainian-last-week` cannot be combined with `--from-date` or `--to-date`.

## Other Filters

Filter by language:

```bash
.venv/bin/python codewars_report.py users.csv --language python
```

Customize outputs:

```bash
.venv/bin/python codewars_report.py users.csv \
  --details-out my_completed_katas.csv \
  --summary-out my_summary.csv
```

## Google Authentication

You can authenticate with either:

- `--google-access-token-env GOOGLE_ACCESS_TOKEN`
- `--google-credentials-file /path/to/credentials.json`

If you pass a Desktop app OAuth client JSON, the tool can reuse a cached login with:

```bash
--google-token-cache-file ./credentials.token.json
```

Without an explicit cache path, it uses `<credentials-stem>.token.json`.

## Outputs

- `completed_katas.csv`: one row per completed kata
- `summary.csv`: one row per user with `name`, `username`, and `solved_count`, sorted by solved count descending
