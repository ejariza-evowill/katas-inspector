from __future__ import annotations

import csv
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

from retrieval import SheetUser

GOOGLE_SHEETS_MIME_TYPE = "application/vnd.google-apps.spreadsheet"
GOOGLE_DRIVE_METADATA_URL = (
    "https://www.googleapis.com/drive/v3/files/{file_id}"
    "?fields=id,name,mimeType&supportsAllDrives=true"
)
GOOGLE_DRIVE_DOWNLOAD_URL = (
    "https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&supportsAllDrives=true"
)
GOOGLE_SHEETS_METADATA_URL = (
    "https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
    "?fields=sheets.properties(sheetId,title,index)"
)
GOOGLE_SHEETS_VALUES_URL = (
    "https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{sheet_range}"
    "?majorDimension=ROWS"
)


@dataclass(frozen=True)
class GoogleSource:
    kind: str
    file_id: str
    gid: str | None = None


def normalize_header(value: str) -> str:
    return "".join(char for char in value.strip().lower() if char.isalnum())


def load_sheet_users_from_rows(rows: list[list[str]], *, source_name: str) -> list[SheetUser]:
    if not rows:
        raise ValueError(f"{source_name} did not contain any rows.")

    fieldnames = rows[0]
    header_map = {normalize_header(field): field for field in fieldnames}
    missing = [name for name in ("flow", "name", "username") if name not in header_map]
    if missing:
        raise ValueError(
            f"{source_name} is missing required columns: {', '.join(missing)}. "
            "Expected headers like Flow, name, username."
        )

    users: list[SheetUser] = []
    for line_number, raw_row in enumerate(rows[1:], start=2):
        row = {
            fieldnames[index]: raw_row[index] if index < len(raw_row) else ""
            for index in range(len(fieldnames))
        }
        username = (row.get(header_map["username"]) or "").strip()
        if not username:
            print(f"Skipping row {line_number}: empty username.", file=sys.stderr)
            continue

        users.append(
            SheetUser(
                flow=(row.get(header_map["flow"]) or "").strip(),
                name=(row.get(header_map["name"]) or "").strip(),
                username=username,
            )
        )

    if not users:
        raise ValueError(f"{source_name} did not contain any usable usernames.")
    return users


def load_sheet_users(path: Path) -> list[SheetUser]:
    text = path.read_text(encoding="utf-8-sig")
    return load_sheet_users_from_csv_text(text, source_name=str(path))


def load_sheet_users_from_csv_text(text: str, *, source_name: str) -> list[SheetUser]:
    with io.StringIO(text) as handle:
        rows = [row for row in csv.reader(handle)]
    return load_sheet_users_from_rows(rows, source_name=source_name)


def parse_google_source(source: str) -> GoogleSource | None:
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"}:
        return None

    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)
    fragment = parse_qs(parsed.fragment)
    gid = query.get("gid", [None])[0] or fragment.get("gid", [None])[0]

    if host == "docs.google.com" and len(path_parts) >= 3 and path_parts[:2] == ["spreadsheets", "d"]:
        return GoogleSource(kind="spreadsheet", file_id=path_parts[2], gid=gid)

    if host == "drive.google.com":
        if len(path_parts) >= 3 and path_parts[:2] == ["file", "d"]:
            return GoogleSource(kind="drive_file", file_id=path_parts[2], gid=gid)
        if "id" in query:
            return GoogleSource(kind="drive_file", file_id=query["id"][0], gid=gid)

    return None


def load_sheet_users_from_source(
    source: str,
    *,
    timeout_seconds: int,
    google_access_token: str | None,
) -> list[SheetUser]:
    google_source = parse_google_source(source)
    if google_source is None:
        return load_sheet_users(Path(source))

    if not google_access_token:
        raise ValueError(
            "Google Drive and Google Sheets sources require Google OAuth credentials. "
            "Provide a bearer token or a Google credentials file and try again."
        )

    if google_source.kind == "spreadsheet":
        rows = fetch_google_sheet_rows(
            google_source.file_id,
            gid=google_source.gid,
            access_token=google_access_token,
            timeout_seconds=timeout_seconds,
        )
        return load_sheet_users_from_rows(rows, source_name=source)

    csv_text = fetch_google_drive_csv_text(
        google_source.file_id,
        access_token=google_access_token,
        timeout_seconds=timeout_seconds,
        gid=google_source.gid,
    )
    return load_sheet_users_from_csv_text(csv_text, source_name=source)


def fetch_google_sheet_rows(
    spreadsheet_id: str,
    *,
    gid: str | None,
    access_token: str,
    timeout_seconds: int,
) -> list[list[str]]:
    sheet_title = fetch_google_sheet_title(
        spreadsheet_id,
        gid=gid,
        access_token=access_token,
        timeout_seconds=timeout_seconds,
    )
    range_name = quote_a1_sheet_name(sheet_title)
    url = GOOGLE_SHEETS_VALUES_URL.format(
        spreadsheet_id=quote(spreadsheet_id),
        sheet_range=quote(range_name, safe=""),
    )
    payload = fetch_google_json(url, access_token=access_token, timeout_seconds=timeout_seconds)
    values = payload.get("values", [])
    if not isinstance(values, list):
        raise RuntimeError("Google Sheets returned an unexpected values payload.")
    return [[str(cell) for cell in row] for row in values]


def fetch_google_sheet_title(
    spreadsheet_id: str,
    *,
    gid: str | None,
    access_token: str,
    timeout_seconds: int,
) -> str:
    url = GOOGLE_SHEETS_METADATA_URL.format(spreadsheet_id=quote(spreadsheet_id))
    payload = fetch_google_json(url, access_token=access_token, timeout_seconds=timeout_seconds)
    sheets = payload.get("sheets", [])
    if not isinstance(sheets, list) or not sheets:
        raise RuntimeError("Google Sheets metadata did not include any sheets.")

    selected_title: str | None = None
    selected_index: int | None = None
    for sheet in sheets:
        properties = sheet.get("properties", {}) if isinstance(sheet, dict) else {}
        sheet_id = properties.get("sheetId")
        title = properties.get("title")
        index = properties.get("index", 0)
        if not isinstance(title, str):
            continue
        if gid is not None and str(sheet_id) == gid:
            return title
        if selected_title is None or int(index) < (selected_index or 0):
            selected_title = title
            selected_index = int(index)

    if gid is not None:
        raise ValueError(f"Could not find a Google Sheet tab with gid={gid}.")
    if selected_title is None:
        raise RuntimeError("Google Sheets metadata did not include a usable sheet title.")
    return selected_title


def fetch_google_drive_csv_text(
    file_id: str,
    *,
    access_token: str,
    timeout_seconds: int,
    gid: str | None,
) -> str:
    metadata_url = GOOGLE_DRIVE_METADATA_URL.format(file_id=quote(file_id))
    metadata = fetch_google_json(
        metadata_url,
        access_token=access_token,
        timeout_seconds=timeout_seconds,
    )
    mime_type = metadata.get("mimeType")
    if mime_type == GOOGLE_SHEETS_MIME_TYPE:
        rows = fetch_google_sheet_rows(
            file_id,
            gid=gid,
            access_token=access_token,
            timeout_seconds=timeout_seconds,
        )
        with io.StringIO(newline="") as handle:
            writer = csv.writer(handle)
            writer.writerows(rows)
            return handle.getvalue()

    download_url = GOOGLE_DRIVE_DOWNLOAD_URL.format(file_id=quote(file_id))
    content = fetch_google_bytes(
        download_url,
        access_token=access_token,
        timeout_seconds=timeout_seconds,
    )
    return content.decode("utf-8-sig")


def quote_a1_sheet_name(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


def fetch_google_json(url: str, *, access_token: str, timeout_seconds: int) -> dict[str, object]:
    content = fetch_google_bytes(url, access_token=access_token, timeout_seconds=timeout_seconds)
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise RuntimeError("Google API returned an unexpected JSON payload.")
    return payload


def fetch_google_bytes(url: str, *, access_token: str, timeout_seconds: int) -> bytes:
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "katas-evaluator/1.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return response.read()
    except HTTPError as exc:
        raise RuntimeError(f"Google API returned HTTP {exc.code} for {url}.") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach Google API ({exc.reason}).") from exc
