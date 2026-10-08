#!/usr/bin/env python3
"""Search the bundled storyboard recipe catalog with explainable scoring."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


FEATURE_ALIASES = {
    "dialogue": ["对白", "对话", "交谈", "聊天", "双人"],
    "everyday": ["日常", "生活", "轻松"],
    "stable-order": ["稳定", "清晰顺序", "规则", "易读"],
    "four-beat": ["四格", "起承转合", "短故事"],
    "opening": ["开场", "建立场景", "第一眼"],
    "ending": ["收尾", "告别", "结尾", "余韵"],
    "primary-panel": ["主格", "重点", "大格", "视觉中心"],
    "impact": ["爆发", "高潮", "冲击", "震撼", "大场面"],
    "action": ["动作", "追逐", "高速", "速度", "运动", "打斗"],
    "action-sequence": ["多阶段", "连续动作", "动作分解", "过程"],
    "reaction": ["反应", "表情", "震惊"],
    "close-up": ["特写", "靠近", "细节"],
    "pull-back": ["拉远", "由近到远", "全貌"],
    "pause": ["停顿", "骤停", "静止"],
    "negative-space": ["留白", "空白", "稀疏"],
    "quiet": ["安静", "诗意", "克制", "平静"],
    "contrast": ["对比", "对峙", "镜像", "前后变化"],
    "parallel": ["双线", "并行", "交叉剪辑", "两地"],
    "memory": ["回忆", "闪回", "过去"],
    "imagination": ["幻想", "想象", "梦境"],
    "screen": ["屏幕", "手机", "监控", "窗口"],
    "investigation": ["调查", "档案", "线索", "拼贴"],
    "knowledge": ["知识", "说明", "科普", "信息图", "数据"],
    "route": ["路线", "地图", "旅程", "移动路径"],
    "timeline": ["时间轴", "一天", "过去现在未来"],
    "countdown": ["倒计时", "时钟", "时间压力"],
    "object-centered": ["物件", "道具", "中心物体"],
    "character-centered": ["人物中心", "围绕主角", "角色中心"],
    "loop": ["循环", "首尾相接", "宿命"],
    "vertical-flow": ["向下", "竖向", "坠落", "楼层"],
    "horizontal-flow": ["横向", "宽银幕", "长卷"],
    "progression": ["递进", "升级", "逐步"],
    "freeform": ["自由", "无边框", "不规则", "实验"],
    "cover": ["封面", "海报", "标题页"],
    "fixed-stage": ["固定场景", "舞台", "同一空间"],
    "reflection": ["镜子", "反射", "心理对照"],
    "natural-frame": ["门框", "窗框", "遮挡", "前景"],
    "text-led": ["文字主导", "大字", "标题"],
    "sound-led": ["音效", "拟声词", "声音"],
    "color-led": ["色块", "颜色分区", "情绪色"],
    "geometric": ["几何", "多边形", "三角形", "圆形"],
}

REQUIREMENT_ALIASES = {
    "preceding-intensity": {"preceding-intensity", "preceding-fast-pace"},
    "preceding-high-energy": {"preceding-intensity", "preceding-fast-pace"},
}

LEVEL = {"low": 1, "medium": 2, "high": 3}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--query", default="")
    parser.add_argument("--requirements", type=Path)
    parser.add_argument("--require-tag", action="append", default=[])
    parser.add_argument("--exclude-tag", action="append", default=[])
    parser.add_argument("--forbid-requirement", action="append", default=[])
    parser.add_argument(
        "--dialogue-density", choices=["none", "low", "medium", "high"]
    )
    parser.add_argument(
        "--action-continuity", choices=["low", "medium", "high"]
    )
    parser.add_argument(
        "--max-reading-complexity", choices=["low", "medium", "high"]
    )
    parser.add_argument("--min-score", type=float, default=0.1)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def flatten_text(value) -> list[str]:
    if isinstance(value, dict):
        result = []
        for item in value.values():
            result.extend(flatten_text(item))
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(flatten_text(item))
        return result
    if value is None:
        return []
    return [str(value)]


def matched_features(query: str) -> set[str]:
    return {
        feature
        for feature, aliases in FEATURE_ALIASES.items()
        if any(alias in query for alias in aliases)
    }


def meaningful_terms(query: str) -> list[str]:
    pieces = re.split(r"[\s，。；、：,:;!?！？/]+", query)
    terms = []
    for piece in pieces:
        piece = piece.strip()
        if len(piece) >= 2:
            terms.append(piece)
            if len(piece) >= 4:
                terms.extend(piece[index : index + 2] for index in range(len(piece) - 1))
    return sorted(set(terms))


def score(template: dict, query: str) -> tuple[float, list[str]]:
    wanted = matched_features(query)
    available = set(template.get("tags", []))
    feature_hits = sorted(wanted & available)
    title = template["titleZh"]
    prompt = template["promptZh"]
    document = f"{title} {prompt}"
    term_hits = [term for term in meaningful_terms(query) if term in document]
    value = len(feature_hits) * 12 + len(term_hits) * 2
    if title and title in query:
        value += 20
    if template["templateId"] in query.upper():
        value += 50
    evidence = [f"匹配特征:{item}" for item in feature_hits]
    evidence.extend(f"文本命中:{item}" for item in term_hits[:6])
    if not evidence:
        evidence.append("弱匹配：仅作为相邻构图候选")
    return value, evidence


def main() -> None:
    args = parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    query_parts = [args.query]
    required_tags = set(args.require_tag)
    excluded_tags = set(args.exclude_tag)
    forbidden_requirements = set(args.forbid_requirement)
    dialogue_density = args.dialogue_density
    action_continuity = args.action_continuity
    max_reading_complexity = args.max_reading_complexity
    min_score = args.min_score
    if args.requirements:
        requirements = json.loads(args.requirements.read_text(encoding="utf-8"))
        query_parts.extend(flatten_text(requirements))
        required_tags.update(requirements.get("requireTags", []))
        excluded_tags.update(requirements.get("excludeTags", []))
        forbidden_requirements.update(requirements.get("forbidRequirements", []))
        dialogue_density = requirements.get("dialogueDensity", dialogue_density)
        action_continuity = requirements.get("actionContinuity", action_continuity)
        max_reading_complexity = requirements.get(
            "maxReadingComplexity", max_reading_complexity
        )
        min_score = float(requirements.get("minScore", min_score))
    query = " ".join(part for part in query_parts if part).strip()
    if not query:
        raise SystemExit("provide --query or --requirements")

    known_tags = {
        tag for template in catalog["templates"] for tag in template.get("tags", [])
    }
    unknown_tags = (required_tags | excluded_tags) - known_tags
    if unknown_tags:
        raise SystemExit(f"unknown tag: {', '.join(sorted(unknown_tags))}")
    known_requirements = {
        requirement
        for template in catalog["templates"]
        for requirement in template.get("requirements", [])
    }
    valid_requirement_names = known_requirements | set(REQUIREMENT_ALIASES)
    unknown_requirements = forbidden_requirements - valid_requirement_names
    if unknown_requirements:
        raise SystemExit(
            f"unknown requirement: {', '.join(sorted(unknown_requirements))}"
        )
    expanded_forbidden_requirements = set()
    for requirement in forbidden_requirements:
        expanded_forbidden_requirements.update(
            REQUIREMENT_ALIASES.get(requirement, {requirement})
        )

    ranked = []
    for template in catalog["templates"]:
        template_tags = set(template.get("tags", []))
        template_requirements = set(template.get("requirements", []))
        if not required_tags.issubset(template_tags):
            continue
        if excluded_tags & template_tags:
            continue
        if expanded_forbidden_requirements & template_requirements:
            continue
        capacities = template.get("capacities", {})
        if dialogue_density and dialogue_density not in capacities.get(
            "recommendedDialogueDensity", []
        ):
            continue
        if action_continuity:
            available_action = capacities.get("recommendedActionContinuity", "low")
            if LEVEL[available_action] < LEVEL[action_continuity]:
                continue
        if max_reading_complexity:
            available_reading = capacities.get("readingComplexity", "high")
            if LEVEL[available_reading] > LEVEL[max_reading_complexity]:
                continue
        value, evidence = score(template, query)
        if value < min_score:
            continue
        ranked.append(
            {
                "templateId": template["templateId"],
                "titleZh": template["titleZh"],
                "score": value,
                "evidence": evidence,
                "tags": template.get("tags", []),
                "strengths": template.get("strengths", []),
                "requirements": template.get("requirements", []),
                "risks": template.get("risks", []),
                "capacities": template.get("capacities", {}),
                "preview": template["preview"],
                "geometryStatus": template["geometryStatus"],
                "nextStep": "结合当前页面节拍实例化格数、几何与阅读顺序",
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["templateId"]))
    result = ranked[: max(1, args.top)]
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    for index, candidate in enumerate(result, 1):
        evidence = "；".join(candidate["evidence"])
        print(
            f"{index}. {candidate['templateId']} {candidate['titleZh']} "
            f"score={candidate['score']}: {evidence}"
        )


if __name__ == "__main__":
    main()
