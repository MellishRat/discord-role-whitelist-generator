"""Read member exports without silently repairing malformed rows or headers."""
import csv
from collections import Counter
import pandas as pd


def load_members_csv(path):
    try:
        with open(path, encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, strict=True)
            headers = next(reader, None)
            if not headers:
                raise ValueError("CSV is empty; expected a header row.")
            if any(not header.strip() for header in headers):
                raise ValueError("CSV has a blank column heading. Give each column a name.")
            duplicates = [name for name, count in Counter(headers).items() if count > 1]
            if duplicates:
                raise ValueError("Duplicate CSV headings: " + ", ".join(duplicates))
            rows = []
            for row in reader:
                if not row:  # Match the previous reader's treatment of blank lines.
                    continue
                if len(row) != len(headers):
                    raise ValueError(f"CSV line {reader.line_num}: expected {len(headers)} fields, found {len(row)}. Check delimiters and quoted commas.")
                if any("\n" in cell or "\r" in cell for cell in row):
                    raise ValueError(f"CSV line {reader.line_num}: multiline cells cannot be written safely to one-name-per-line whitelists.")
                rows.append(row)
            if not rows:
                raise ValueError("CSV contains headings but no members.")
            return pd.DataFrame(rows, columns=headers)
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must use UTF-8 encoding. Export or save it as UTF-8 CSV.") from exc
    except csv.Error as exc:
        raise ValueError(f"Malformed CSV near line {reader.line_num}: {exc}") from exc
