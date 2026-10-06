# Facial distinctiveness and consistency QC

## Sampling

For each shot, inspect at least the first, middle, and final clear face frame plus frames at the hardest motion. For speech, sample closed mouth, open vowel, and smile or emphasis. Compare against the approved neutral and profile anchors.

## Scorecard

Score every dimension from 0 to 4.

| Dimension | 0 | 2 | 4 |
|---|---|---|---|
| Identity geometry | different person | recognizable with drift | landmarks and ratios stable |
| Cast distinctiveness | interchangeable | some unique cues | distinct without wardrobe |
| Texture realism | wax/plastic | partially natural | stable pores, lines, marks |
| Asymmetry retention | fully symmetrized | intermittent | subtle cues remain natural |
| Expression anatomy | broken/frozen | usable with artifacts | plausible muscle and cheek motion |
| Temporal stability | severe morphing | brief drift | stable through the shot |
| Angle robustness | fails outside frontal | mild profile drift | frontal to profile remains identifiable |
| Edit continuity | obvious recast | tolerable mismatch | identity holds across cuts |

### Decision thresholds

- **Pass:** no dimension below 3 and average at least 3.25.
- **Conditional pass:** one dimension at 2, invisible at intended delivery size and speed.
- **Regenerate:** identity geometry, temporal stability, or cast distinctiveness is 0–2.

Do not hide an identity failure with color grading, motion blur, or a fast cut unless the face is narratively incidental and the user accepts the tradeoff.

## Reading embedding scores

When `audit_face_consistency.py` runs, combine its cosine numbers with the scorecard above; never let either replace the other.

- Near-duplicate clean crops can score 0.9+, but same-identity scores can fall substantially with pose, crop, blur, lighting, or stylization changes. OpenCV's documented SFace cosine threshold is 0.363 on its benchmark; treat it as a starting point, not a universal boundary.
- Embeddings are less sensitive than raw pixels, but blur, dim light, occlusion, and angle can still move the score. A beautified face can also keep a high score while a human sees a change, so the scorecard's geometry dimension stays mandatory.
- Relative drops carry more signal than absolute values: a character whose frames score 0.95 against the anchor and then 0.5 has a real discontinuity, even if 0.5 sits above the fail line.
- Pairwise cast collision uses the highest observed cross-identity similarity, not the mean.
- Identity discontinuity (character absent, unmatched face present) is a recast or occlusion event, not a gradual drift; repair accordingly.
- Empty detections (`no_face_frames`) are framing or occlusion facts, not identity facts — check the frame before failing it.

## Failure diagnosis

| Symptom | Likely cause | First repair |
|---|---|---|
| Eyes enlarge during smile | beauty prior or expression overload | reduce smile amplitude; preserve eye aperture and spacing |
| Jaw narrows in profile | weak silhouette anchor | strengthen lower-face width; add approved profile reference |
| Skin becomes porcelain | retouching/style prior | remove glamour terms; preserve texture and stable marks |
| Two cast members look related | shared high-salience anchors | change silhouette, age read, or nose/jaw—not wardrobe alone |
| Face changes on head turn | single frontal reference | add clean three-quarter/profile reference; shorten turn |
| Face changes during speech | complex phoneme/motion load | shorten dialogue, reduce camera motion, lock landmark relations |
| Restorer creates the same face | excessive restoration strength | lower/disable restoration; refine only artifact regions |
| Style image overwrites identity | reference-role contamination | isolate style and identity references; state role boundaries |

## Audit output template

```text
SHOT [id] — [PASS / CONDITIONAL / REGENERATE]
Scores: geometry _, distinctiveness _, texture _, asymmetry _, expression _, temporal _, angle _, continuity _
Observed: [...]
Likely cause: [...]
Preserve: [...]
Primary change: [...]
Fallback: [...]
Regenerate: [frames / shot / reference pack / full character]
```
