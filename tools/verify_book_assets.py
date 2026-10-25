#!/usr/bin/env python3
"""Check reader-facing local links and the four generated workbench images."""

from pathlib import Path
import re
import struct
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = (
    "01-ontology-workbench.png", "02-action-console.png",
    "03-audit-trace.png", "04-evaluation-dashboard.png",
)


def check() -> list[str]:
    errors = []
    documents = list(ROOT.glob("*.md")) + list((ROOT / "docs").rglob("*.md"))
    for document in documents:
        text = document.read_text(encoding="utf-8")
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        for target in re.findall(r"\]\(([^\s)]+)(?:\s+[^)]*)?\)", text):
            parts = urlsplit(target.strip("<>"))
            if parts.scheme or parts.netloc or not parts.path:
                continue
            path = (document.parent / unquote(parts.path)).resolve()
            if not path.is_relative_to(ROOT):
                errors.append(f"Link leaves repository: {document.relative_to(ROOT)} -> {target}")
            elif not path.exists():
                errors.append(f"Missing link: {document.relative_to(ROOT)} -> {target}")
    for name in SCREENSHOTS:
        path = ROOT / "docs" / "assets" / "screenshots" / name
        if not path.is_file():
            errors.append(f"Missing workbench screenshot: {name}")
            continue
        header = path.read_bytes()[:24]
        if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
            errors.append(f"Invalid PNG: {name}")
        elif min(struct.unpack(">II", header[16:24])) < 800:
            errors.append(f"Screenshot is too small for reading: {name}")
    return errors


def main() -> int:
    errors = check()
    for error in errors:
        print(error)
    if errors:
        return 1
    print("PASS: reader links and four Chinese workbench screenshots.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
