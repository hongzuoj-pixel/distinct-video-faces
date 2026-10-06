# Identity design reference

## Contents

1. Design objective
2. High-information feature axes
3. Character bible template
4. Cast separation matrix
5. Prompt language patterns
6. Anti-patterns

## 1. Design objective

Optimize two quantities independently:

- **Between-character distance:** viewers can identify each cast member from silhouette, profile, or expression without relying on clothing.
- **Within-character stability:** the same landmark relationships survive lighting, angle, speech, emotion, and motion.

Distinctiveness should come from a coherent combination of ordinary traits. A believable person can have a broad lower face, slightly close-set eyes, a high nasal bridge with a soft tip, uneven brows, textured cheeks, and a reserved half-smile without any single trait becoming caricature.

## 2. High-information feature axes

Choose a small number of independent anchors across these axes:

| Axis | Useful observations | Weak language to avoid |
|---|---|---|
| Silhouette | oval, long, compact, broad lower third, tapered jaw | attractive face |
| Vertical ratios | short forehead, long midface, compact lower third | perfect proportions |
| Eyes/brows | spacing, lid exposure, tilt, brow height and asymmetry | beautiful eyes |
| Nose | bridge height/width, length, tip projection, nostril shape | elegant nose |
| Mouth | width, lip balance, philtrum length, resting corner angle | pretty lips |
| Chin/jaw | projection, width, angle, masseter fullness | model jawline |
| Ears | size, projection, lobe attachment | normal ears |
| Skin | pores, freckles, sun variation, acne marks, smile lines | flawless skin |
| Stable marks | mole, scar, eyebrow gap, tooth spacing | unique face |
| Hair/grooming | hairline geometry, part, curl, facial hair density | stylish hair |
| Expression | resting tension, smile asymmetry, blink rhythm | natural expression |
| Movement | head-leading gesture, shoulder posture, speaking cadence | realistic motion |

Do not use protected identity labels as shorthand for facial geometry. If a user's story specifies cultural or demographic casting, preserve it respectfully while still describing the individual rather than a stereotype.

## 3. Character bible template

```text
CHARACTER: [name / role]
AGE READ + BUILD: [...]
FACE SILHOUETTE + RATIOS: [...]
LANDMARKS:
- brows/eyes: [...]
- nose: [...]
- mouth/philtrum: [...]
- chin/jaw/ears: [...]
ASYMMETRIES: [2–3 subtle stable differences]
SKIN + STABLE MARKS: [...]
HAIRLINE + GROOMING: [...]
RESTING EXPRESSION: [...]
MOTION/VOICE SIGNATURE: [...]
FORBIDDEN DRIFT: [...]

MUTABLE PER SHOT:
- wardrobe, makeup, lighting, emotion, dirt/wetness, temporary injury
```

Keep the reusable identity block concise enough to paste unchanged. If every field is long, compress it to the highest-information anchors.

## 4. Cast separation matrix

Compare each pair using:

| Character | silhouette | eye spacing | nose | jaw | age read | texture | hairline | baseline expression | movement |
|---|---|---|---|---|---|---|---|---|---|

Flag a collision when a pair shares five or more axes, or when their three most salient axes overlap. Repair the smallest set of anchors that restores separation. Clothing color alone is not sufficient.

## 5. Prompt language patterns

Use relational geometry:

- `eyes set slightly closer than one eye-width`
- `lower third broader than the temples`
- `left brow sits subtly higher at rest`
- `nose tip projects beyond a shallow philtrum`
- `smile begins on the right before becoming bilateral`

Use preservation instructions during difficult motion:

- `preserve the spacing between the inner eye corners and nasal bridge`
- `retain the broad lower-face silhouette through the three-quarter turn`
- `natural cheek compression while smiling; do not narrow the jaw`
- `speech moves the lips and cheeks without changing nose length or eye size`

Use concrete negative constraints sparingly:

- `no beauty retouching, no pore removal, no facial symmetrization`
- `do not enlarge the eyes, sharpen the jaw, narrow the nose, or erase the eyebrow height difference`
- `no identity swap during profile turn; no frozen forehead during speech`

## 6. Anti-patterns

- Long lists of contradictory ethnic, celebrity, or aesthetic references.
- Celebrity mixtures used as an identity shortcut.
- One generic positive block copied to every cast member.
- The same age, skin treatment, jawline, nose, hairstyle, and expression baseline across the cast.
- Excessive negative prompting that causes waxy or frozen faces.
- Treating wardrobe or hair color as the only identity difference.
- Generating all references under different lenses, ages, makeup, or lighting and calling the drift “variation.”
