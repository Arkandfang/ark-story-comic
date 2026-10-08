#!/usr/bin/env python3
"""Create a non-destructive ark-story-comic project or add one episode."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
ASSETS = SKILL_ROOT / "assets"


def write_new(path: Path, content: str) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_new(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def make_episode(
    project: Path,
    slug: str,
    pages: int,
    width: int,
    height: int,
    with_publish: bool,
) -> Path:
    episode = project / "episodes" / slug
    if episode.exists():
        raise FileExistsError(f"Episode already exists: {episode}")

    copy_new(ASSETS / "story-brief-template.md", episode / "story-brief.md")
    copy_new(ASSETS / "storyboard-template.md", episode / "storyboard.md")
    write_new(episode / "prompts.md", "# 生成与修改记录\n\n")
    if with_publish:
        write_new(
            episode / "publish" / "release-copy.md",
            "# 发布包\n\n## 平台与目标\n\n## 标题\n\n## 正文\n\n## 其他交付\n",
        )

    final_dir = episode / "final-v1"
    (final_dir / "raw").mkdir(parents=True)
    (final_dir / "qa" / "review-preview-pages").mkdir(parents=True)
    write_new(
        final_dir / "qa" / "visual-review.md",
        "# 视觉审核\n\n"
        "状态：NOT_REVIEWED\n\n"
        "- 原尺寸逐页：NOT_REVIEWED\n"
        "- 气泡联系表：NOT_REVIEWED\n"
        "- 目标观看尺寸预览：NOT_REVIEWED\n",
    )

    layout = {
        "width": width,
        "height": height,
        "font_family": "PingFang SC, Hiragino Sans GB, Noto Sans CJK SC, sans-serif",
        "expected_balloon_count": 0,
        "expected_framed_text_count": 0,
        "pages": [],
    }
    for index in range(1, pages + 1):
        number = f"{index:02d}"
        layout["pages"].append(
            {
                "number": number,
                "source": f"raw/page-{number}-art.png",
                "balloons": [],
                "framed_text": [],
            }
        )
    write_new(
        final_dir / "comic-layout.json",
        json.dumps(layout, ensure_ascii=False, indent=2) + "\n",
    )
    return episode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--title", default="未命名漫画系列")
    parser.add_argument("--episode", required=True, help="Episode directory name, e.g. episode-01")
    parser.add_argument("--pages", type=int, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--episode-only", action="store_true")
    parser.add_argument("--with-publish", action="store_true")
    parser.add_argument("--with-style-tests", action="store_true")
    args = parser.parse_args()

    project = args.project.expanduser().resolve()
    if args.pages < 1:
        parser.error("--pages must be at least 1")
    if args.width < 1 or args.height < 1:
        parser.error("--width and --height must be positive")

    if args.episode_only:
        if not project.is_dir():
            parser.error(f"Existing project not found: {project}")
    else:
        if project.exists() and any(project.iterdir()):
            parser.error(f"Project directory is not empty: {project}")
        project.mkdir(parents=True, exist_ok=True)
        write_new(project / "visual-bible.md", f"# {args.title}｜视觉圣经\n\n状态：DRAFT\n")
        copy_new(ASSETS / "asset-lock-template.md", project / "asset-lock.md")
        (project / "references").mkdir()
        if args.with_style_tests:
            (project / "style-tests").mkdir()

    try:
        episode = make_episode(
            project,
            args.episode,
            args.pages,
            args.width,
            args.height,
            args.with_publish,
        )
    except FileExistsError as exc:
        parser.error(str(exc))
    print(f"Created comic episode scaffold: {episode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
