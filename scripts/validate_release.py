#!/usr/bin/env python3
"""Validate comic page files and QA artifacts against the project layout."""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PAGE_RE = re.compile(r"^page-(\d+)\.png$")


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != PNG_MAGIC or header[12:16] != b"IHDR":
        raise ValueError("not a valid PNG with IHDR")
    return struct.unpack(">II", header[16:24])


def load_audit(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{path.name}: invalid JSON: {exc}"]
    if data.get("result") != "PASS":
        errors.append(f"{path.name}: result is not PASS")
    if data.get("expected") != data.get("audited"):
        errors.append(f"{path.name}: expected/audited mismatch")
    collection = data.get("balloons", data.get("items", []))
    failed = [item.get("id", "unknown") for item in collection if item.get("status") != "PASS"]
    if failed:
        errors.append(f"{path.name}: failed items: {', '.join(failed)}")
    if "balloons" in data:
        incomplete = [
            item.get("id", "unknown")
            for item in collection
            if item.get("shape") not in {"ellipse", "rect"}
            or not isinstance(item.get("textBounds"), list)
            or len(item.get("textBounds", [])) != 4
        ]
        if incomplete:
            errors.append(
                f"{path.name}: missing shape-aware rendered-glyph evidence: {', '.join(incomplete)}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--max-mib", type=float)
    parser.add_argument("--allow-missing-audits", action="store_true")
    args = parser.parse_args()

    root = args.release_dir.expanduser().resolve()
    errors: list[str] = []
    if not root.is_dir():
        print(f"ERROR: release directory not found: {root}", file=sys.stderr)
        return 2

    layout: dict = {}
    layout_path = root / "comic-layout.json"
    if not layout_path.is_file():
        errors.append("missing comic-layout.json")
    else:
        try:
            layout = json.loads(layout_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"comic-layout.json: invalid JSON: {exc}")

    expected_width = args.width or layout.get("width")
    expected_height = args.height or layout.get("height")
    if not isinstance(expected_width, int) or expected_width < 1:
        errors.append("output width is missing or invalid")
    if not isinstance(expected_height, int) or expected_height < 1:
        errors.append("output height is missing or invalid")

    delivery = layout.get("delivery", {}) if isinstance(layout.get("delivery", {}), dict) else {}
    max_mib = args.max_mib
    if max_mib is None:
        candidate = delivery.get("max_mib_per_page")
        if isinstance(candidate, (int, float)) and candidate > 0:
            max_mib = float(candidate)

    pages = []
    for path in root.glob("page-*.png"):
        match = PAGE_RE.match(path.name)
        if match:
            pages.append((int(match.group(1)), path))
    pages.sort(key=lambda item: item[0])
    if not pages:
        errors.append("no page-NN.png files found")
    numbers = [number for number, _ in pages]
    expected_numbers = list(range(1, len(pages) + 1))
    if numbers != expected_numbers:
        errors.append(f"page sequence is not contiguous: {numbers}")

    for _, page in pages:
        try:
            dimensions = png_dimensions(page)
            if expected_width and expected_height and dimensions != (expected_width, expected_height):
                errors.append(
                    f"{page.name}: {dimensions[0]}x{dimensions[1]}, "
                    f"expected {expected_width}x{expected_height}"
                )
        except ValueError as exc:
            errors.append(f"{page.name}: {exc}")
        if max_mib is not None and page.stat().st_size > int(max_mib * 1024 * 1024):
            errors.append(f"{page.name}: larger than {max_mib:g} MiB")

    layout_pages = layout.get("pages", []) if isinstance(layout, dict) else []
    if len(layout_pages) != len(pages):
        errors.append(f"layout/final page count mismatch: {len(layout_pages)} vs {len(pages)}")
    for item in layout_pages:
        source_value = item.get("source", "") if isinstance(item, dict) else ""
        source = root / source_value
        if not source_value or not source.is_file():
            errors.append(f"layout source missing: {source_value}")

    qa = root / "qa"
    required = [qa / "review-contact-sheet.jpg", qa / "visual-review.md"]
    for item in required:
        if not item.is_file():
            errors.append(f"missing QA artifact: {item.relative_to(root)}")

    visual_review = qa / "visual-review.md"
    review_text = ""
    if visual_review.is_file():
        review_text = visual_review.read_text(encoding="utf-8")
        if "PASS" not in review_text:
            errors.append("visual-review.md does not contain a PASS status")

    previews_dir = qa / "review-preview-pages"
    previews = sorted(previews_dir.glob("page-*.jpg")) if previews_dir.is_dir() else []
    if len(previews) != len(pages):
        errors.append(f"review preview count mismatch: {len(previews)} vs {len(pages)}")

    audit_paths = [qa / "bubble-layout-audit.json", qa / "framed-text-layout-audit.json"]
    found_audit = False
    balloon_count = 0
    for audit in audit_paths:
        if audit.is_file():
            found_audit = True
            errors.extend(load_audit(audit))
            if audit.name == "bubble-layout-audit.json":
                try:
                    balloon_count = int(json.loads(audit.read_text(encoding="utf-8")).get("audited", 0))
                except Exception:
                    pass
    if not found_audit and not args.allow_missing_audits:
        errors.append("no layout audit JSON found; final delivery requires layout audits")
    if balloon_count > 0:
        if not (qa / "bubble-contact-sheet.jpg").is_file():
            errors.append("missing QA artifact: qa/bubble-contact-sheet.jpg")
        if not re.search(r"(?:气泡|bubble)[^\n]{0,30}PASS", review_text, re.IGNORECASE):
            errors.append("visual-review.md does not record a PASS for the bubble contact sheet")

    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    total_mib = sum(page.stat().st_size for _, page in pages) / (1024 * 1024)
    limit_text = f", max {max_mib:g} MiB/page" if max_mib is not None else ""
    print(
        f"PASS: {len(pages)} pages, {expected_width}x{expected_height}, "
        f"{total_mib:.2f} MiB total{limit_text}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
