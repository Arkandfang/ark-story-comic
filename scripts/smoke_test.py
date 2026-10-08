#!/usr/bin/env python3
"""Run the local ark-story-comic render, lettering-audit, and delivery smoke test."""

from __future__ import annotations

import binascii
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def png_chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return (
        struct.pack(">I", len(data))
        + payload
        + struct.pack(">I", binascii.crc32(payload) & 0xFFFFFFFF)
    )


def write_white_png(path: Path, width: int, height: int) -> None:
    row = b"\x00" + b"\xff\xff\xff" * width
    raw = row * height
    png = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(raw, level=9))
        + png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def run(command: list[str], env: dict[str, str] | None = None) -> str:
    result = subprocess.run(command, text=True, capture_output=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"{result.stdout}{result.stderr}"
        )
    return result.stdout


def node_commands(node: str) -> list[list[str]]:
    commands = [[node]]
    arch = Path("/usr/bin/arch")
    if sys.platform == "darwin" and arch.is_file():
        commands.extend([[str(arch), "-arm64", node], [str(arch), "-x86_64", node]])
    return commands


def supports_sharp(node_command: list[str], candidate: str | None) -> bool:
    expression = """
const modulePath = process.argv[1];
const sharp = modulePath ? require(modulePath) : require("sharp");
(async () => {
  if (!sharp.versions || !sharp.versions.sharp) process.exit(2);
  const svg = Buffer.from(
    '<svg width="64" height="64" xmlns="http://www.w3.org/2000/svg">'
    + '<text x="32" y="32" text-anchor="middle" dominant-baseline="central" '
    + 'font-family="sans-serif" font-size="16" fill="#000">TEST</text></svg>'
  );
  const { info } = await sharp(svg)
    .trim({ background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .png()
    .toBuffer({ resolveWithObject: true });
  if (info.width >= 64 || info.height >= 64 || info.width < 1 || info.height < 1) process.exit(3);
})().catch(() => process.exit(4));
"""
    command = [*node_command, "-e", expression]
    if candidate:
        command.append(candidate)
    return subprocess.run(command, text=True, capture_output=True).returncode == 0


def sharp_candidates() -> list[str | None]:
    configured = os.environ.get("COMIC_SHARP_PATH")
    candidates: list[Path] = []
    npm = shutil.which("npm")
    if npm:
        result = subprocess.run([npm, "root", "-g"], text=True, capture_output=True)
        if result.returncode == 0:
            global_root = Path(result.stdout.strip())
            candidates.append(global_root / "sharp")
            candidates.extend(global_root.glob("*/node_modules/sharp"))

    search_roots = [
        Path.home() / ".cache" / "codex-runtimes",
        Path("/Applications/ChatGPT.app/Contents/Resources"),
    ]
    for root in search_roots:
        if root.is_dir():
            candidates.extend(path.parent for path in root.rglob("node_modules/sharp/package.json"))

    resolved_candidates: list[str | None] = [configured] if configured else []
    resolved_candidates.append(None)
    seen: set[str] = set()
    for candidate in candidates:
        resolved = str(candidate.resolve())
        if resolved in seen or not candidate.is_dir():
            continue
        seen.add(resolved)
        resolved_candidates.append(resolved)
    return resolved_candidates


def find_compatible_runtime(node: str) -> tuple[list[str], str | None]:
    candidates = sharp_candidates()
    for node_command in node_commands(node):
        for candidate in candidates:
            if supports_sharp(node_command, candidate):
                return node_command, candidate
    raise RuntimeError(
        "No sharp installation compatible with the active Node.js runtime. "
        "Install sharp or set COMIC_SHARP_PATH."
    )


def main() -> int:
    node = shutil.which("node")
    if not node:
        print("ERROR: Node.js is required for the ark-story-comic smoke test", file=sys.stderr)
        return 2

    try:
        node_command, sharp_path = find_compatible_runtime(node)
        runtime_env = os.environ.copy()
        if sharp_path:
            runtime_env["COMIC_SHARP_PATH"] = sharp_path
        with tempfile.TemporaryDirectory(prefix="ark-story-comic-smoke-") as temp_dir:
            project = Path(temp_dir) / "project"
            final_dir = project / "episodes" / "episode-01" / "final-v1"
            layout_path = final_dir / "comic-layout.json"

            run(
                [
                    sys.executable,
                    str(SKILL_ROOT / "scripts" / "init_comic_project.py"),
                    str(project),
                    "--episode",
                    "episode-01",
                    "--pages",
                    "1",
                    "--width",
                    "1200",
                    "--height",
                    "1600",
                ],
                env=runtime_env,
            )
            shutil.copy2(SKILL_ROOT / "assets" / "comic-layout.example.json", layout_path)
            write_white_png(final_dir / "raw" / "page-01-art.png", 1200, 1600)

            run(
                [
                    *node_command,
                    str(SKILL_ROOT / "scripts" / "render_comic.cjs"),
                    "--root",
                    str(final_dir),
                    "--layout",
                    str(layout_path),
                ],
                env=runtime_env,
            )

            (final_dir / "qa" / "visual-review.md").write_text(
                "# 视觉审核\n\n"
                "状态：PASS\n\n"
                "- 原尺寸逐页：PASS\n"
                "- 气泡联系表：PASS\n"
                "- 逐字核对：PASS\n"
                "- 原画冻结区对照：PASS\n"
                "- 目标观看尺寸预览：PASS\n",
                encoding="utf-8",
            )

            run(
                [sys.executable, str(SKILL_ROOT / "scripts" / "validate_release.py"), str(final_dir)],
                env=runtime_env,
            )
            run(
                [
                    *node_command,
                    str(SKILL_ROOT / "scripts" / "audit_direct_lettering.cjs"),
                    "--root",
                    str(final_dir),
                    "--layout",
                    str(layout_path),
                ],
                env=runtime_env,
            )
            run(
                [sys.executable, str(SKILL_ROOT / "scripts" / "validate_release.py"), str(final_dir)],
                env=runtime_env,
            )

            bubble_audit = json.loads(
                (final_dir / "qa" / "bubble-layout-audit.json").read_text(encoding="utf-8")
            )
            framed_audit = json.loads(
                (final_dir / "qa" / "framed-text-layout-audit.json").read_text(encoding="utf-8")
            )
            if bubble_audit.get("audited") != 2 or bubble_audit.get("result") != "PASS":
                raise RuntimeError("Expected two passing balloon audits")
            if framed_audit.get("audited") != 1 or framed_audit.get("result") != "PASS":
                raise RuntimeError("Expected one passing framed-text audit")
    except Exception as exc:
        print(f"ARK_STORY_COMIC_SMOKE_FAIL: {exc}", file=sys.stderr)
        return 1

    print("ARK_STORY_COMIC_SMOKE_PASS: render, direct lettering audit, and delivery validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
