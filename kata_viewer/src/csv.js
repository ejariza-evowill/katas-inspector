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
  const response = await fetch(`${import.meta.env.BASE_URL}data/${fileName}`);
  if (!response.ok) {
    throw new Error(`Could not load ${fileName}: HTTP ${response.status}`);
  }
  return parseCsvObjects(await response.text());
}
