#!/usr/bin/env python3
"""Validate a JSON character pack and flag likely cast convergence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from itertools import combinations
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = (
    "name",
    "age_read",
    "build",
    "identity_lock",
    "immutable_features",
    "asymmetries",
    "skin_texture",
    "hairline_grooming",
    "expression_baseline",
    "movement_signature",
    "forbidden_drift",
)

GENERIC_BEAUTY_TERMS = (
    "beautiful",
    "handsome",
    "perfect face",
    "flawless skin",
    "model face",
    "精致脸",
    "完美五官",
    "无瑕肌肤",
    "网红脸",
    "高级脸",
)

STOPWORDS = {
    "a",
    "an",
    "and",
    "the",
    "with",
    "slight",
    "slightly",
    "subtle",
    "natural",
    "face",
    "eyes",
    "eye",
}

# Generic anatomical vocabulary. Two characters share these words by
# definition, so bigrams like 下巴 or 鼻梁 carry no similarity evidence; only
# the distinguishing qualifiers around them should count.
CJK_STOP_BIGRAMS = {
    "下巴",
    "下颌",
    "人中",
    "五官",
    "嘴唇",
    "鼻子",
    "鼻梁",
    "鼻尖",
    "鼻翼",
    "眼睛",
    "眼距",
    "眼窝",
    "眼睑",
    "眉毛",
    "脸型",
    "脸颊",
    "颧骨",
    "额头",
    "皮肤",
    "耳朵",
    "耳垂",
    "头发",
    "发际",
    "发型",
    "轮廓",
}

SALIENCE_AXES = (
    "silhouette",
    "eye_spacing",
    "nose",
    "jaw",
    "age_read",
    "skin_texture",
    "hairline_grooming",
    "expression_baseline",
    "movement_signature",
)


def normalized(value: Any) -> str:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    return " ".join(str(value).strip().lower().split())


def tokens(value: Any) -> set[str]:
    text = normalized(value)
    latin = {
        token
        for token in re.findall(r"[a-z0-9]+", text)
        if len(token) > 1 and token not in STOPWORDS
    }
    bigrams = {
        sequence[index : index + 2]
        for sequence in re.findall(r"[\u3400-\u9fff]+", text)
        for index in range(max(0, len(sequence) - 1))
        if sequence[index : index + 2] not in CJK_STOP_BIGRAMS
    }
    return latin | bigrams


def similarity(left: Any, right: Any) -> float:
    left_text = normalized(left)
    right_text = normalized(right)
    if not left_text or not right_text:
        return 0.0
    if left_text == right_text:
        return 1.0
    left_tokens = tokens(left_text)
    right_tokens = tokens(right_text)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def axis_value(character: dict[str, Any], axis: str) -> str:
    features = character.get("immutable_features", {})
    if isinstance(features, dict) and axis in features:
        return normalized(features[axis])
    return normalized(character.get(axis, ""))


def audit(
    data: dict[str, Any],
    similar_axis: float = 0.72,
    collision_axes: int = 5,
    min_uniqueness: float = 55.0,
) -> dict[str, Any]:
    characters = data.get("characters")
    errors: list[str] = []
    warnings: list[str] = []
    pairs: list[dict[str, Any]] = []

    if not isinstance(characters, list) or not characters:
        return {
            "valid": False,
            "errors": ["`characters` must be a non-empty list."],
            "warnings": [],
            "pairs": [],
        }

    names: set[str] = set()
    for index, character in enumerate(characters):
        label = f"characters[{index}]"
        if not isinstance(character, dict):
            errors.append(f"{label} must be an object.")
            continue
        missing = [field for field in REQUIRED_FIELDS if not character.get(field)]
        if missing:
            errors.append(f"{label} is missing: {', '.join(missing)}.")
        name = normalized(character.get("name", ""))
        if name in names and name:
            errors.append(f"Duplicate character name: {character.get('name')}.")
        names.add(name)
        features = character.get("immutable_features", {})
        if not isinstance(features, dict):
            errors.append(f"{label}.immutable_features must be an object.")
        elif len([value for value in features.values() if normalized(value)]) < 6:
            warnings.append(
                f"{character.get('name', label)} has fewer than 6 populated immutable feature anchors."
            )
        asymmetries = character.get("asymmetries", [])
        if not isinstance(asymmetries, list) or not 2 <= len(asymmetries) <= 4:
            warnings.append(f"{character.get('name', label)} should have 2–4 subtle asymmetries.")
        searchable = " ".join(
            [
                normalized(character.get("identity_lock", "")),
                normalized(features),
                normalized(character.get("skin_texture", "")),
            ]
        )
        found_generic = [term for term in GENERIC_BEAUTY_TERMS if term in searchable]
        if found_generic:
            warnings.append(
                f"{character.get('name', label)} uses generic beauty pressure: "
                f"{', '.join(found_generic)}. Replace it with observable geometry or texture."
            )

    valid_characters = [item for item in characters if isinstance(item, dict)]
    for left, right in combinations(valid_characters, 2):
        shared: list[str] = []
        axis_similarities: dict[str, float] = {}
        for axis in SALIENCE_AXES:
            left_value = axis_value(left, axis)
            right_value = axis_value(right, axis)
            score = similarity(left_value, right_value)
            axis_similarities[axis] = round(score, 3)
            if score >= similar_axis:
                shared.append(axis)
        mean_similarity = sum(axis_similarities.values()) / len(SALIENCE_AXES)
        uniqueness_score = round(100 * (1 - mean_similarity), 1)
        collision = len(shared) >= collision_axes or uniqueness_score < min_uniqueness
        if collision:
            warnings.append(
                f"Likely cast collision: {left.get('name')} and {right.get('name')} "
                f"have uniqueness score {uniqueness_score}/100 and share {len(shared)} axes "
                f"({', '.join(shared) or 'distributed similarity'})."
            )
        pairs.append(
            {
                "characters": [left.get("name"), right.get("name")],
                "shared_axes": shared,
                "axis_similarities": axis_similarities,
                "uniqueness_score": uniqueness_score,
                "collision": collision,
            }
        )

    return {"valid": not errors, "errors": errors, "warnings": warnings, "pairs": pairs}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "character_pack",
        type=Path,
        help="Path to a JSON file containing a `characters` list.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--similar-axis", type=float, default=0.72, help="Axis similarity at or above this counts as shared (default: %(default)s).")
    parser.add_argument("--collision-axes", type=int, default=5, help="Shared axes at or above this count flag a collision (default: %(default)s).")
    parser.add_argument("--min-uniqueness", type=float, default=55.0, help="Uniqueness score below this flags a collision (default: %(default)s).")
    args = parser.parse_args()
    if not 0 <= args.similar_axis <= 1:
        parser.error("--similar-axis must be between 0 and 1")
    if args.collision_axes < 1:
        parser.error("--collision-axes must be at least 1")
    if not 0 <= args.min_uniqueness <= 100:
        parser.error("--min-uniqueness must be between 0 and 100")

    try:
        data = json.loads(args.character_pack.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read character pack: {exc}", file=sys.stderr)
        return 2

    result = audit(
        data,
        similar_axis=args.similar_axis,
        collision_axes=args.collision_axes,
        min_uniqueness=args.min_uniqueness,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("PASS" if result["valid"] and not result["warnings"] else "REVIEW")
        for error in result["errors"]:
            print(f"ERROR: {error}")
        for warning in result["warnings"]:
            print(f"WARNING: {warning}")
        for pair in result["pairs"]:
            shared = ", ".join(pair["shared_axes"]) or "none"
            names = " / ".join(str(value) for value in pair["characters"])
            print(
                f"PAIR: {names} | uniqueness: {pair['uniqueness_score']}/100 "
                f"| similar axes: {shared}"
            )
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
