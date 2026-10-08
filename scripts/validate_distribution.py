#!/usr/bin/env python3
"""Validate an ark-story-comic distribution ZIP without extracting it."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
import zipfile
from pathlib import PurePosixPath


REQUIRED_FILES = {
    "SKILL.md",
    "README.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "agents/openai.yaml",
    "package.json",
    "package-lock.json",
    "scripts/smoke_test.py",
    "scripts/validate_distribution.py",
    "assets/storyboard-library/catalog.json",
    "assets/storyboard-library/LICENSE.handraw-style",
}
TEXT_SUFFIXES = {".md", ".py", ".cjs", ".json", ".yaml", ".yml", ".txt"}
FORBIDDEN_SEGMENTS = {"__MACOSX", "__pycache__", "node_modules", ".git"}
FORBIDDEN_NAMES = {".DS_Store", ".env", "credentials.json"}
MACHINE_PATHS = (
    re.compile("/" + "Users/" + r"[^/\s]+/"),
    re.compile("/" + "home/" + r"[^/\s]+/"),
    re.compile(r"[A-Za-z]:\\" + "Users" + r"\\[^\\\s]+\\"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_path")
    return parser.parse_args()


def normalized_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsafe archive path: {name}")
    if any(part in FORBIDDEN_SEGMENTS for part in path.parts):
        raise ValueError(f"forbidden archive segment: {name}")
    if any(part.startswith(".") for part in path.parts) or path.name in FORBIDDEN_NAMES:
        raise ValueError(f"hidden or sensitive archive member: {name}")
    return path


def strip_single_root(paths: list[PurePosixPath]) -> tuple[str, dict[str, PurePosixPath]]:
    roots = {path.parts[0] for path in paths}
    if roots != {"ark-story-comic"}:
        raise ValueError(f"archive must contain exactly one ark-story-comic root, got {sorted(roots)}")
    stripped = {
        PurePosixPath(*path.parts[1:]).as_posix(): path
        for path in paths
        if len(path.parts) > 1
    }
    return "ark-story-comic", stripped


def is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    try:
        with zipfile.ZipFile(args.zip_path) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if not infos:
                raise ValueError("archive is empty")
            for info in infos:
                normalized_member(info.filename)
                if is_symlink(info):
                    raise ValueError(f"symlink is not allowed: {info.filename}")

            paths = [normalized_member(info.filename) for info in infos]
            _, members = strip_single_root(paths)
            missing = sorted(REQUIRED_FILES - members.keys())
            if missing:
                raise ValueError(f"missing required files: {missing}")

            for logical_name, archive_path in members.items():
                suffix = PurePosixPath(logical_name).suffix.lower()
                if suffix not in TEXT_SUFFIXES:
                    continue
                data = archive.read(archive_path.as_posix())
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise ValueError(f"non-UTF-8 text file: {logical_name}") from exc
                for pattern in MACHINE_PATHS:
                    if pattern.search(text):
                        raise ValueError(f"machine-specific path in {logical_name}")

            skill_text = archive.read(members["SKILL.md"].as_posix()).decode("utf-8")
            if "name: ark-story-comic" not in skill_text or 'version: "1.0.0"' not in skill_text:
                raise ValueError("SKILL.md identity or version is invalid")

            package = json.loads(archive.read(members["package.json"].as_posix()))
            if package.get("version") != "1.0.0":
                raise ValueError("package.json version mismatch")
            if package.get("dependencies", {}).get("sharp") != "0.35.5":
                raise ValueError("sharp dependency is missing or unpinned")

            catalog = json.loads(
                archive.read(members["assets/storyboard-library/catalog.json"].as_posix())
            )
            templates = catalog.get("templates", [])
            if len(templates) != 68:
                raise ValueError(f"expected 68 storyboard recipes, got {len(templates)}")
            expected_previews = {
                f"assets/storyboard-library/previews/{item['templateId']}.webp"
                for item in templates
            }
            missing_previews = sorted(expected_previews - members.keys())
            if missing_previews:
                raise ValueError(f"missing storyboard previews: {missing_previews}")

        print(
            "ARK_STORY_COMIC_DISTRIBUTION_PASS: "
            f"{len(infos)} files, 68 storyboard recipes, sha256={sha256(args.zip_path)}"
        )
        return 0
    except (OSError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        print(f"ARK_STORY_COMIC_DISTRIBUTION_FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
