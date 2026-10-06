#!/usr/bin/env python3
"""Validate a layered AI-video prompt pack for identity preservation risks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


MODES = {"text-to-video", "image-to-video", "multi-reference"}
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
CAMERA_MOVES = (
    "pan",
    "tilt",
    "dolly",
    "truck",
    "orbit",
    "crane",
    "zoom",
    "handheld",
    "推镜",
    "拉镜",
    "摇镜",
    "环绕",
    "升降",
    "手持",
)


def normalized(value: Any) -> str:
    return " ".join(str(value).strip().lower().split())


def audit(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    shots = data.get("shots")
    characters = data.get("characters")

    if not isinstance(characters, list) or not characters:
        errors.append("`characters` must be a non-empty list.")
        characters = []
    if not isinstance(shots, list) or not shots:
        errors.append("`shots` must be a non-empty list.")
        shots = []

    identity_locks: dict[str, str] = {}
    for index, character in enumerate(characters):
        if not isinstance(character, dict):
            errors.append(f"characters[{index}] must be an object.")
            continue
        name = normalized(character.get("name", ""))
        lock = normalized(character.get("identity_lock", ""))
        if not name or not lock:
            errors.append(f"characters[{index}] requires `name` and `identity_lock`.")
            continue
        identity_locks[name] = lock

    seen_ids: set[str] = set()
    for index, shot in enumerate(shots):
        label = f"shots[{index}]"
        if not isinstance(shot, dict):
            errors.append(f"{label} must be an object.")
            continue
        shot_id = normalized(shot.get("id", ""))
        if not shot_id:
            errors.append(f"{label} requires `id`.")
        elif shot_id in seen_ids:
            errors.append(f"Duplicate shot id: {shot.get('id')}.")
        seen_ids.add(shot_id)

        mode = normalized(shot.get("mode", ""))
        prompt = normalized(shot.get("prompt", ""))
        cast = shot.get("characters", [])
        references = shot.get("references", [])
        preserve = shot.get("preserve", [])
        avoid = shot.get("avoid", [])

        if mode not in MODES:
            errors.append(f"{label}.mode must be one of: {', '.join(sorted(MODES))}.")
        if not prompt:
            errors.append(f"{label} requires a non-empty `prompt`.")
        if not isinstance(cast, list) or not cast:
            errors.append(f"{label}.characters must be a non-empty list.")
            cast = []
        if not isinstance(preserve, list) or not preserve:
            warnings.append(f"{shot.get('id', label)} has no preservation anchors.")
        if not isinstance(avoid, list) or not avoid:
            warnings.append(f"{shot.get('id', label)} has no shot-specific avoid constraints.")

        for cast_name in cast:
            key = normalized(cast_name)
            if key not in identity_locks:
                errors.append(f"{shot.get('id', label)} references unknown character: {cast_name}.")
            elif mode == "text-to-video" and identity_locks[key] not in prompt:
                errors.append(
                    f"{shot.get('id', label)} is text-to-video but does not contain the literal "
                    f"identity lock for {cast_name}."
                )

        if mode in {"image-to-video", "multi-reference"}:
            if not isinstance(references, list) or not references:
                errors.append(f"{shot.get('id', label)} is reference-led but lists no references.")
        if mode == "multi-reference" and len(references) < 2:
            warnings.append(f"{shot.get('id', label)} uses multi-reference mode with fewer than 2 references.")

        found_generic = [term for term in GENERIC_BEAUTY_TERMS if term in prompt]
        if found_generic:
            warnings.append(
                f"{shot.get('id', label)} contains generic beauty pressure: {', '.join(found_generic)}."
            )

        moves = [move for move in CAMERA_MOVES if re.search(rf"(?<!\w){re.escape(move)}(?!\w)", prompt)]
        duration = shot.get("duration_seconds")
        if len(moves) > 2 and isinstance(duration, (int, float)) and duration <= 8:
            warnings.append(
                f"{shot.get('id', label)} packs {len(moves)} camera moves into {duration}s: "
                f"{', '.join(moves)}. Simplify to reduce identity stress."
            )

    return {"valid": not errors, "errors": errors, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt_pack", type=Path)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    try:
        data = json.loads(args.prompt_pack.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read prompt pack: {exc}", file=sys.stderr)
        return 2

    result = audit(data)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("PASS" if result["valid"] and not result["warnings"] else "REVIEW")
        for error in result["errors"]:
            print(f"ERROR: {error}")
        for warning in result["warnings"]:
            print(f"WARNING: {warning}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
