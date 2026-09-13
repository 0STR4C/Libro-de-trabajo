"""Lectura estructurada del registro de versiones del proyecto."""
from __future__ import annotations

import re
from pathlib import Path


CHANGELOG_PATH = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
RELEASE_HEADING = re.compile(
    r"^##\s+(?P<version>\d+\.\d+\.\d+)\s+[—-]\s+(?P<label>.+?)\s*$"
)
RELEASE_DATE = re.compile(
    r"^(?P<day>\d{1,2}) de (?P<month>[a-záéíóú]+) de (?P<year>\d{4})"
    r"(?:\s+\((?P<title>.+)\))?$",
    re.IGNORECASE,
)
MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def _release_date(label: str) -> tuple[str, str, str]:
    match = RELEASE_DATE.fullmatch(label.strip())
    if not match:
        return label.strip(), label.strip(), ""
    day = int(match.group("day"))
    month_name = match.group("month").lower()
    month = MONTHS.get(month_name)
    if month is None:
        return label.strip(), label.strip(), match.group("title") or ""
    year = int(match.group("year"))
    released_label = f"{day} de {month_name} de {year}"
    return f"{year:04d}-{month:02d}-{day:02d}", released_label, match.group("title") or ""


def parse_release_history(markdown: str) -> list[dict]:
    """Convierte las secciones ``## versión — fecha`` del changelog en registros."""
    releases: list[dict] = []
    current: dict | None = None
    for raw_line in markdown.splitlines():
        heading = RELEASE_HEADING.match(raw_line.strip())
        if heading:
            if current is not None:
                releases.append(current)
            released, released_label, title = _release_date(heading.group("label"))
            current = {
                "version": heading.group("version"),
                "released": released,
                "released_label": released_label,
                "title": title,
                "notes": [],
            }
            continue
        if current is not None and raw_line.startswith("- "):
            note = raw_line[2:].strip()
            if note:
                current["notes"].append(note)
    if current is not None:
        releases.append(current)
    return releases


def release_history(changelog_path: Path = CHANGELOG_PATH) -> list[dict]:
    try:
        markdown = changelog_path.read_text(encoding="utf-8")
    except OSError:
        return []
    return parse_release_history(markdown)


def release_payload(
    app_version: str,
    fallback_release: str,
    fallback_notes: list[str],
    changelog_path: Path = CHANGELOG_PATH,
) -> dict:
    releases = release_history(changelog_path)
    current = next((item for item in releases if item["version"] == app_version), None)
    if current is None:
        current = {
            "version": app_version,
            "released": fallback_release,
            "released_label": fallback_release,
            "title": "",
            "notes": list(fallback_notes),
        }
        releases.insert(0, current)
    return {
        "version": app_version,
        "released": current["released"],
        "released_label": current["released_label"],
        "notes": current["notes"],
        "releases": releases,
    }
