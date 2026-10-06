# Intervention ladder

Use the lowest level that can pass the project's acceptance test. Escalate only after recording the failed test and preserving what already works.

| Level | Intervention | Use when | Exit test |
|---|---|---|---|
| 0 | Diagnose and remove generic beauty pressure | The cast is still conceptual or prompts use vague aesthetic language | Identity bibles differ on at least five high-salience axes |
| 1 | Immutable identity blocks and shot constraints | Text-to-video or early ideation without references | Low-motion close shot passes geometry and distinctiveness QC |
| 2 | Reference atlas and reference-first video | One or more good stills exist, or text prompting drifts | Neutral, three-quarter, profile, and speaking anchors depict the same person |
| 3 | Staged generation and model routing | Identity survives stills but fails speech, turns, groups, or specific models | Stress shot passes after separating identity, motion, and environment stages |
| 4 | Local repair, dataset, or LoRA/fine-tune | High-volume recurring production still fails Levels 1–3 | Held-out angles and expressions pass before production use |

## Escalation rules

- Move from Level 0 to 1 only after removing generic terms such as `perfect`, `flawless`, `model face`, or their equivalents.
- Move from Level 1 to 2 when the same character fails profile, smile, or cross-shot identity, or when a cast converges despite distinct text anchors.
- Move from Level 2 to 3 when references are internally consistent but the target video model cannot handle the motion or number of characters.
- Move from Level 3 to 4 only for repeated production, not a single clip. State data licensing, privacy, compute, and maintenance costs.
- Step down after a change succeeds. Do not stack every control by default; excessive conditioning can freeze expression or create artifacts.

## Reference-first production pattern

1. Generate or select identity anchors separately for each person.
2. Reject drift before combining people or spending video credits.
3. Generate a low-motion identity proof.
4. Generate the hardest stress shot.
5. Expand to the full shot list.
6. Repair only failed spans or shots.

For a platform that supports one continuous storyboard or reusable subject asset, use it when it reduces independent re-generation of the same identity. Still audit each shot: a shared reference reduces drift but does not guarantee distinct faces or correct temporal anatomy.
