"""Whitelist matching and output naming, independent of the GUI."""
from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd

INVALID_FILENAME_CHARS = '<>:"/\\|?*'

@dataclass
class OutputRule:
    file_name: str
    must_have_roles: list[str] = field(default_factory=list)
    any_of_roles: list[str] = field(default_factory=list)
    must_not_have_roles: list[str] = field(default_factory=list)


def normalize_output_filename(raw_name: str) -> str:
    """Clean user input and always force a .txt file extension."""
    name = raw_name.strip()
    for ch in INVALID_FILENAME_CHARS:
        name = name.replace(ch, " ")
    name = " ".join(name.split()).strip(" .")
    stem = Path(name).stem.strip(" .") if name else ""
    if not stem:
        stem = "Whitelist"
    return f"{stem}.txt"


def member_has_role(row: pd.Series, role: str) -> bool:
    return role in row.index and str(row[role]).strip() != ""

def build_lists(df, output_rules, name_column, dedupe_names=True, sort_names=True) -> dict[str, list[str]]:
    if df is None:
        raise ValueError("Load a CSV first.")
    if not output_rules:
        raise ValueError("Add at least one output rule.")
    name_col = name_column
    if name_col not in df.columns:
        raise ValueError(f"Name column '{name_col}' was not found in the CSV.")

    normalized_rule_names = [normalize_output_filename(rule.file_name).casefold() for rule in output_rules]
    if len(normalized_rule_names) != len(set(normalized_rule_names)):
        raise ValueError("Two or more output rules have the same file name. Rename one of them before generating lists.")

    output = {}
    for rule in output_rules:
        names = []
        for _, row in df.iterrows():
            name = str(row[name_col]).strip()
            if not name:
                continue
            if any(not member_has_role(row, role) for role in rule.must_have_roles):
                continue
            if rule.any_of_roles and not any(member_has_role(row, role) for role in rule.any_of_roles):
                continue
            if any(member_has_role(row, role) for role in rule.must_not_have_roles):
                continue
            names.append(name)
        if dedupe_names:
            names = list(dict.fromkeys(names))
        if sort_names:
            names = sorted(names, key=str.casefold)
        output[normalize_output_filename(rule.file_name)] = names
    return output

