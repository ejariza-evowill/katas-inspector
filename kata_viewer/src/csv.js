export function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let insideQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const nextChar = text[index + 1];

    if (insideQuotes) {
      if (char === '"' && nextChar === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') {
        insideQuotes = false;
      } else {
        field += char;
      }
      continue;
    }

    if (char === '"') {
      insideQuotes = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (char !== "\r") {
      field += char;
    }
  }

  if (field || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  return rows.filter((csvRow) => csvRow.some((value) => value.trim() !== ""));
}

export function parseCsvObjects(text) {
  const rows = parseCsv(text);
  const headers = rows[0] ?? [];
  return rows.slice(1).map((row) =>
    Object.fromEntries(headers.map((header, index) => [header, row[index] ?? ""])),
  );
}

export async function fetchCsvObjects(fileName) {
  const buildId = import.meta.env.VITE_BUILD_ID || "dev";
  const url = `${import.meta.env.BASE_URL}data/${fileName}?v=${encodeURIComponent(buildId)}`;
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Could not load ${fileName}: HTTP ${response.status}`);
  }
  return parseCsvObjects(await response.text());
}

export async function fetchJson(fileName, { optional = false } = {}) {
  const buildId = import.meta.env.VITE_BUILD_ID || "dev";
  const url = `${import.meta.env.BASE_URL}data/${fileName}?v=${encodeURIComponent(buildId)}`;
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    if (optional && response.status === 404) {
      return null;
    }
    throw new Error(`Could not load ${fileName}: HTTP ${response.status}`);
  }
  return response.json();
}
