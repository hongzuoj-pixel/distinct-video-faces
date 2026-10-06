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

Allowed modes are `text-to-video`, `image-to-video`, and `multi-reference`. A text-to-video prompt must contain the literal identity lock for every named character. Reference-led modes must list references and explicit preservation anchors.

## Commands

```bash
python3 scripts/audit_character_pack.py character-pack.json
python3 scripts/audit_prompt_pack.py prompt-pack.json
python3 scripts/sample_video_frames.py clip.mp4 --out audit-frames --samples 7
```
