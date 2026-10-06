# Data contracts

Use UTF-8 JSON. Keep human-readable Markdown alongside JSON if useful; the JSON exists so deterministic checks can run.

## `character-pack.json`

```json
{
  "characters": [
    {
      "name": "Character A",
      "age_read": "early 30s",
      "build": "compact",
      "identity_lock": "Exact reusable identity paragraph.",
      "immutable_features": {
        "silhouette": "short face, broad lower third",
        "eye_spacing": "slightly close-set",
        "eyes_brows": "hooded lids, left brow higher",
        "nose": "low straight bridge, rounded tip",
        "mouth_philtrum": "wide mouth, short philtrum",
        "jaw": "broad jaw, short rounded chin",
        "ears": "slightly projecting ears"
      },
      "asymmetries": ["left brow higher", "smile begins on right"],
      "skin_texture": "visible pores and shallow cheek marks",
      "hairline_grooming": "short forehead, off-center part",
      "expression_baseline": "watchful, jaw lightly tense",
      "movement_signature": "fast blink, leads turns with chin",
      "forbidden_drift": ["no jaw narrowing", "no eye enlargement"]
    }
  ]
}
```

Populate at least six immutable feature keys. Use concrete phrases. Do not copy an axis value across characters unless the shared trait is intentional and other high-salience axes remain separated.

## `prompt-pack.json`

```json
{
  "platform": "platform-neutral",
  "characters": [
    {
      "name": "Character A",
      "identity_lock": "Exact same text as character-pack.json."
    }
  ],
  "shots": [
    {
      "id": "S01",
      "mode": "image-to-video",
      "duration_seconds": 5,
      "characters": ["Character A"],
      "references": ["character-a-three-quarter.png"],
      "prompt": "Slow dolly in as Character A shifts her gaze and breathes out.",
      "preserve": ["broad lower third", "left brow higher"],
      "avoid": ["jaw narrowing", "eye enlargement"]
    }
  ]
}
```

Allowed modes are `text-to-video`, `image-to-video`, and `multi-reference`. A text-to-video prompt must contain the literal identity lock for every named character (a near-complete rewording warns; a missing lock fails). Reference-led modes must list references and explicit preservation anchors.

## Face audit report (`--json` from `audit_face_consistency.py`)

Emitted, not authored. Schema summary for agents consuming the report:

```json
{
  "tool": "audit_face_consistency",
  "input": "clip.mp4",
  "frames_evaluated": 9,
  "model": {"detector": "face_detection_yunet_2023mar.onnx", "recognizer": "sface:face_recognition_sface_2021dec.onnx", "metric": "cosine", "dimensions": 128},
  "thresholds": {"assign": 0.363, "collision_fail": 0.363, "collision_warn": 0.25, "drift_fail": 0.363, "drift_warn": 0.45, "min_face_px": 40, "min_face_score": 0.6},
  "anchors": {"Lin Qiao": "lin-qiao-three-quarter.png"},
  "identities": {
    "Lin Qiao": {
      "anchor": "lin-qiao-three-quarter.png",
      "frames_present": 7,
      "frames_missing": [4],
      "discontinuity_frames": [4],
      "drift": {"n": 7, "min": 0.2812, "mean": 0.5699, "max": 0.98, "worst_frame": 5},
      "verdict": "FAIL"
    }
  },
  "pairs": [
    {"a": "Lin Qiao", "b": "Zhou Ning", "similarity": {"n": 12, "min": 0.05, "mean": 0.07, "max": 0.09}, "co_frame_frames": [2], "verdict": "PASS"}
  ],
  "unassigned_faces": [],
  "no_face_frames": [],
  "multi_face_frames": [2],
  "verdict": "FAIL",
  "findings": ["identity drift: Lin Qiao drops to 0.2812 similarity at frame 5."],
  "notes": "Cosine similarity is a heuristic ranking signal, not identity proof."
}
```

Verdict rules: identity drift fails when the worst frame-to-anchor cosine falls below `drift_fail` and reviews between `drift_fail` and `drift_warn`. Pairs fail when their peak observed cosine rises above `collision_fail`; the mean remains for context. The overall verdict is FAIL on any FAIL, REVIEW when something is unevaluated, unmatched, faceless, or multi-face without anchors, PASS otherwise. Exit codes: 0 pass (or review unless `--strict`), 1 fail, 2 operational error.

Backend selection: `model.recognizer` is reported as `backend:model-file`. The `sface` backend (default) uses the thresholds above; the experimental `insightface` backend ships its own default operating point (0.40 fail / 0.28 warn bands) because ArcFace's cosine scale differs from SFace's. Every threshold remains a CLI flag.

With `--report-dir DIR`, the tool also writes `DIR/report.html` (single file: verdict, tables, findings, frame gallery with data-URI thumbnails, thresholds) and `DIR/frames/frame-NN-annotated.png` (boxes + ASCII similarity tags; red borders mark flagged frames). These are review artifacts; the JSON report stays the machine contract.

## Commands

```bash
python3 scripts/audit_character_pack.py character-pack.json
python3 scripts/audit_prompt_pack.py prompt-pack.json
python3 scripts/sample_video_frames.py clip.mp4 --out audit-frames --samples 7
# Optional embedding QC (pip install opencv-contrib-python; models auto-download)
python3 scripts/audit_face_consistency.py clip.mp4 --anchors anchors/ --out face-report.json
```
