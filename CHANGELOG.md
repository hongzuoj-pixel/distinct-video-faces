# Changelog

## 0.3.1 — Reviewed reliability fixes

- Added regression coverage for model SHA256 verification.
- Made per-frame anchor assignment one-to-one.
- Changed cast-collision gates to use peak similarity so one severe collision is not averaged away.
- Fixed clean single-subject anchor-free audits and marked ambiguous multi-face runs for review.
- Fixed empty-pair report rendering, threshold errors, ffprobe fallback, and frame-extraction fallbacks.
- Tightened prompt-pack duration and duplicate-name validation.
- Corrected the copyright holder to 金宏祚.
- Added a GitHub social preview, structured issue forms, contribution guidance, and a security policy.
- Expanded the standard-library test suite from 34 to 44 tests.

## 0.3.0 — Recognizer backends and visual reports

- **Recognizer backends** (`--recognizer`): the embedding model is now a
  pluggable interface. The default `sface` backend is unchanged and fully
  tested; a new EXPERIMENTAL `insightface` backend runs 512-d ArcFace
  (`w600k_r50.onnx`-style models) through the same YuNet detections.
  Threshold defaults are per-backend and every value stays overridable on the
  CLI. The insightface path is unit-tested at the interface level but has not
  been exercised end-to-end against the real buffalo model yet — treat its
  numbers as unvalidated until then.
- **`--report-dir`**: writes annotated frames (boxes, per-face similarity
  tags, red borders on flagged frames) and a single-file `report.html`
  containing the verdict, drift and distinctiveness tables, findings, frame
  gallery, and thresholds. Chinese identity names render in HTML; drawn tags
  stay ASCII (`0:0.95`, `?1:0.12`).
- Requirements moved to `requirements-cv.txt` (and
  `requirements-cv-insightface.txt` for the experimental backend).
- CI now runs the test matrix on Python 3.11 and 3.13.
- Test suite: 34 tests.

## 0.2.0 — Face-level embedding audit

New capabilities:

- **`audit_face_consistency.py`** — optional embedding-based QC on rendered
  frames or video. Detects every face with the YuNet detector, extracts
  128-d SFace embeddings, and reports:
  - per-character identity drift against approved anchor stills (worst frame
    pinpointed), with an anchor-free mode that uses the most central frame as
    reference;
  - cross-identity similarity across all frames and inside two-shots (cast
    collision measurement);
  - identity discontinuities: a frame where a character is missing while an
    unmatched near-miss face appears (recast / heavy drift / extra);
  - frames with no detectable face and faces matching no anchor.
  Models auto-download on first use (~39 MB, SHA256-verified, cached;
  `--no-download` and `--allow-unverified` available). All thresholds are CLI
  flags. JSON output via `--json`/`--out`; exit codes 0/1/2 with `--strict`.
- **`sample_video_frames.py`** — now samples the highest-motion *stress*
  frames (frame-difference scoring at 6 fps) in addition to uniform samples,
  making the documented first/middle/last + stress workflow real. ffprobe is
  optional: durations fall back to parsing ffmpeg output. Frames are written
  as PNG (lossless), with end-of-video seeking fallbacks and a richer
  manifest.

Improvements to the text audits:

- All decision thresholds are now CLI flags in both `audit_character_pack.py`
  (`--similar-axis`, `--collision-axes`, `--min-uniqueness`) and
  `audit_prompt_pack.py` (`--lock-warn-overlap`, `--max-camera-moves`,
  `--max-shot-seconds`).
- CJK similarity no longer counts generic anatomical bigrams (下巴, 鼻梁,
  眼睛, …) so Chinese identity locks are compared on their distinguishing
  qualifiers, not shared vocabulary.
- A reworded-but-substantively-intact identity lock in text-to-video shots now
  warns instead of failing; a genuinely missing lock still fails.

Documentation:

- README gained a face-level audit section with real example output and
  honest interpretation guidance; qc-rubric.md explains how to combine
  embedding scores with the visual scorecard; data-contracts.md documents the
  face audit report schema. Removed a dead related-work link.
- Test suite extended to 28 tests covering the new scoring, assignment,
  report-building, and threshold logic (model-dependent integration tests
  skip cleanly when models are absent).
