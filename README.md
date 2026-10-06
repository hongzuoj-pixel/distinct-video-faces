# Distinct Video Faces

[![CI](https://github.com/hongzuoj-pixel/distinct-video-faces/actions/workflows/validate.yml/badge.svg)](https://github.com/hongzuoj-pixel/distinct-video-faces/actions/workflows/validate.yml)
[![Release](https://img.shields.io/github/v/release/hongzuoj-pixel/distinct-video-faces?include_prereleases)](https://github.com/hongzuoj-pixel/distinct-video-faces/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-open%20format-111827)](skills/direct-distinct-video-faces/SKILL.md)

## Stop casting the same AI face in every role.

**Keep each character consistent—without making the whole cast look alike.**

AI-video workflows usually solve only half the problem: they try to keep one character stable from shot to shot. But a film can have perfect continuity and still look synthetic when every actor shares the same polished face.

`direct-distinct-video-faces` is an open Agent Skill that treats both goals as first-class constraints:

- **Within-character stability:** person A remains person A through speech, profiles, expressions, lighting, and motion.
- **Between-character distinctiveness:** person A, B, and C do not collapse into variations of one generated face.

Built for AI filmmakers using Kling, Jimeng, Hailuo, Veo, Wan/ComfyUI, or other text-to-video and image-to-video workflows.

> The skill plans, prompts, audits, and repairs your workflow. Your chosen video generator still renders the footage. No new generation API or paid dependency is required by this repository.

**[中文快速开始](#中文快速开始)**

## Try it in 60 seconds

Install with the open Skills CLI:

```bash
npx skills@latest add hongzuoj-pixel/distinct-video-faces
```

Then ask your agent:

```text
Use $direct-distinct-video-faces to design two believable leads for a
30-second convenience-store argument. Make their faces unmistakably
different, keep each identity stable through dialogue and profile turns,
and give me a Kling-ready reference plan, shot prompts, and QC checklist.
```

Already generated footage? Start with an audit instead:

```text
Audit these clips with $direct-distinct-video-faces. Show me where the cast
looks related or a face drifts, explain the likely cause, and give me the
smallest regeneration plan that preserves accepted shots.
```

For a first test, use a two-person dialogue with one close-up, one profile, and one speaking shot per character. That exposes both cast convergence and identity drift without spending on a full film.

## What you get

The agent produces a practical production pack—not just a longer prompt:

1. **Identity bibles** with stable geometry, texture, asymmetry, movement, and forbidden drift for each character.
2. **Cast-separation matrix** showing exactly where two characters still overlap.
3. **Reference-image plan** with approval and rejection gates before expensive video generation.
4. **Platform-adapted shot prompts** with identity, performance, camera, world, preservation, and failure constraints separated.
5. **Frame-level QC and repair plan** that regenerates the smallest failed shot or span instead of restarting everything.

## Why this is different

Most character-consistency methods optimize only this:

> Does this character still look like the same person?

Distinct Video Faces also asks:

> Do these different characters actually look like different people?

| Common AI-video workflow | Distinct Video Faces |
|---|---|
| “Beautiful cinematic woman” reused across the cast | Observable geometry, texture, asymmetry, expression, and movement per person |
| Hair and clothing carry all the difference | Pairwise separation across nine identity axes |
| Each shot is generated independently | Reference-first gates and immutable identity locks |
| A detailed-sounding prompt is assumed to be good | Character and prompt packs are checked by executable audits |
| One attractive frame is accepted | First, middle, last, and stress-motion frames are inspected |
| One bad moment triggers a complete rerender | The smallest failed shot or temporal span is repaired first |

The goal is not to make every face strange. It is to build a believable cast with the natural variation real productions get from actual casting.

## Built-in checks

The repository includes dependency-light tools that can catch expensive mistakes before or after rendering:

```bash
# Find incomplete identity bibles, generic beauty language, and cast collisions
python3 skills/direct-distinct-video-faces/scripts/audit_character_pack.py \
  examples/character-pack.json

# Check identity-lock reuse, references, preservation anchors, and overloaded shots
python3 skills/direct-distinct-video-faces/scripts/audit_prompt_pack.py \
  examples/prompt-pack.json

# Sample a video for first/middle/last plus the highest-motion stress frames
# Requires ffmpeg (ffprobe optional)
python3 skills/direct-distinct-video-faces/scripts/sample_video_frames.py clip.mp4 \
  --out audit-frames --samples 7
```

The included two-character example currently returns:

```text
PASS
PAIR: Lin Qiao / Zhou Ning | uniqueness: 82.6/100 | similar axes: none
```

The score is a production warning signal, not a scientific claim that facial identity can be reduced to one number. Human review remains the final gate.

## Face-level embedding audit

Text audits cannot see rendered pixels. For measured face QC, the optional
`audit_face_consistency.py` detects every face with the YuNet detector,
extracts 128-dimensional SFace embeddings, and compares them by cosine
similarity:

- **Within-character drift** — each sampled frame against the character's
  approved anchor still (or the most central frame when no anchors exist),
  with the worst frame pinpointed.
- **Between-character distinctiveness** — cross-identity similarity across
  all frames and inside two-shots, so cast convergence is measured, not guessed.
- **Identity discontinuities** — a frame where a character is missing while an
  unmatched near-miss face appears (recast, heavy drift, or an extra).

```bash
pip install -r skills/direct-distinct-video-faces/requirements-cv.txt

python3 skills/direct-distinct-video-faces/scripts/audit_face_consistency.py \
  clip.mp4 --anchors anchors/ --out face-report.json
```

Models download automatically on first use (~39 MB, SHA256-verified, cached in
`~/.cache/distinct-video-faces/models`; override with `--models-dir` or
`DVF_MODELS_DIR`). A real run on a two-identity clip reports:

```text
FACE AUDIT — clip8s.mp4 — FAIL
Model: sface:face_recognition_sface_2021dec.onnx embeddings, cosine metric | frames: 9
  Lin Qiao: 4/9 frames, drift mean 0.9777 min 0.9411 (frame 6) — PASS
  Zhou Ning: 2/9 frames, drift mean 0.5699 min 0.2812 (frame 5) — FAIL
  PAIR Lin Qiao / Zhou Ning: mean 0.0712 max 0.0899 — PASS
  NOTE: identity drift: Zhou Ning drops to 0.2812 similarity at frame 5.
```

Add `--report-dir out/` to get the same audit as annotated frames (boxes,
similarity tags, red borders on flagged frames) plus a single-file
`report.html` with the tables and gallery embedded — the artifact a human
reviewer or agent opens first.

Recognizer backends: the default `--recognizer sface` uses OpenCV's light
128-d SFace. An experimental `--recognizer insightface` swaps in 512-d ArcFace
(`pip install -r requirements-cv-insightface.txt`, then point
`--recognizer-model` at a recognition ONNX such as `w600k_r50.onnx` from the
buffalo_l pack). Threshold defaults are per-backend; re-tune either one per
pipeline.

How to read the numbers honestly: near-duplicate clean crops can score 0.9+,
but same-identity scores can be much lower when pose, crop, blur, lighting, or
stylization changes. OpenCV documents 0.363 as SFace's cosine decision
threshold on its benchmark; that is a starting point, not a universal law for
AI-video frames. Cast-collision gates use the highest observed cross-identity
similarity so one severe collision is not hidden by a low average. All
thresholds are CLI flags (`--drift-fail`, `--collision-*`, and friends) — tune
them per pipeline, and treat every FAIL as a lead for visual confirmation.

Anchor-free mode is useful for a single obvious subject. If sampled frames
contain multiple people, provide one approved anchor image per recurring
character; otherwise the report is marked REVIEW because drift attribution is
ambiguous.

Data formats are documented in [`data-contracts.md`](skills/direct-distinct-video-faces/references/data-contracts.md), with ready-to-run packs under [`examples/`](examples/).

## Production workflow

```mermaid
flowchart TD
    A[Diagnose face convergence] --> B[Design identity bibles]
    B --> C[Separate the cast]
    C --> D[Approve reference atlas]
    D --> E[Test low-motion shot]
    E --> F[Test speech, profile, or occlusion]
    F --> G[Generate remaining shots]
    G --> H[Sample frames and audit]
    H -->|fail| I[Repair smallest scope]
    I --> F
    H -->|pass| J[Edit and deliver]
```

The intervention ladder starts with the cheapest fix—prompt pressure and reference selection—before recommending staging changes, model routing, adapters, or training.

## Install options

Interactive installation:

```bash
npx skills@latest add hongzuoj-pixel/distinct-video-faces
```

Install globally for Codex without prompts:

```bash
npx skills@latest add hongzuoj-pixel/distinct-video-faces \
  --skill direct-distinct-video-faces -g -a codex -y
```

The repository can also be installed for Claude Code, Cursor, Gemini CLI, GitHub Copilot, and other clients supported by the open Skills CLI.

## Honest status

This is a public beta. The workflow, data contracts, text audits, tests, and installation path are implemented. The embedding-based face audit measures rendered output with real detections and embeddings, but it is a screening tool: embeddings miss what humans catch (and vice versa), thresholds are heuristics, and no face-embedding score is identity proof.

The optional face audit runs locally: these scripts do not upload clips,
frames, or embeddings. On first use they download the pinned YuNet and SFace
model files from OpenCV Zoo and verify exact file sizes and SHA256 checksums.
Review the upstream model terms and training-data provenance for your own
commercial compliance requirements.

The skill reduces convergence and identity-drift risk. It cannot make a probabilistic generator deterministic, modify model weights, or rescue every long dialogue, occlusion, rapid head turn, or crowded multi-person shot. Platform capabilities also change, so current controls should be checked against official documentation.

If you publish a test, please include the model/version/date, generation count, failed attempts, and repair steps—not only the best hero frame.

## Evaluation

Benchmark scenarios live in [`evals/benchmark.json`](evals/benchmark.json). Useful reports include:

- cast pairwise uniqueness before and after;
- identity geometry, temporal stability, and angle robustness;
- low-motion and stress-shot pass rates;
- generation count or cost needed to reach a pass;
- model, version, settings, and date.

## Related work

This project learns from the wider character-consistency and AI-video ecosystem, especially reference-first production, intervention ladders, model routing, and testable output contracts. Its primary contribution is making **cast-level distinctiveness** and **per-character continuity** separate, auditable objectives.

Useful neighboring projects include:

- [`divolleggett/character-consistency-skill`](https://github.com/divolleggett/character-consistency-skill)
- [`Nagacash/character-continuity-skill`](https://github.com/Nagacash/character-continuity-skill)
- [`GenielabsOpenSource/style-consistency-ai`](https://github.com/GenielabsOpenSource/style-consistency-ai)
- [`vercel-labs/skills`](https://github.com/vercel-labs/skills)

## Contributing

Issues and pull requests are especially welcome for:

- reproducible before/after runs on named model versions;
- platform-adapter corrections backed by official documentation;
- benchmark cases that expose identity convergence;
- multilingual face-attribute comparisons;
- privacy-preserving local evaluation tools.

Please do not submit unlicensed face datasets or real-person deepfake examples.

## 中文快速开始

**别再让一部 AI 视频里的所有角色，都像同一张“网红脸”换了发型。**

这个 Skill 同时解决两个不同的问题：

- **同一个人跨镜头不变脸**：说话、侧脸、表情、灯光和运动时仍能认出是同一角色；
- **不同角色之间不撞脸**：不是只换衣服和发型，而是从脸型、比例、五官关系、皮肤质感、不对称、表情习惯和动作特征上真正拉开差异。

安装：

```bash
npx skills@latest add hongzuoj-pixel/distinct-video-faces
```

安装后可以直接对 Agent 说：

```text
使用 $direct-distinct-video-faces，为一段 30 秒便利店争执设计两名主角。
两个人必须一眼就能区分，并且在说话和侧脸镜头中保持各自身份稳定。
请输出适用于 Kling 的参考图计划、分镜提示词和质检清单。
```

你也可以上传已经生成的图片或视频，让它找出哪些角色长得太像、哪一个镜头发生了变脸，以及最省成本的重生成方案。

除了文本层面的审计，仓库还提供可选的**人脸级 embedding 审计**：`pip install opencv-contrib-python` 之后，用 `audit_face_consistency.py` 传入视频和锚点参考图，脚本会检测每一帧人脸、提取 SFace 向量，给出每个角色的漂移分数（最低分定位到具体帧）、不同角色之间的相似度（撞脸检测），以及“角色被换人”式的身份断点告警。首次运行会自动下载约 39 MB 的模型（带 SHA256 校验）。分数只用来定位和排序问题，边界案例仍需人眼确认。

如果它帮助了你的项目，欢迎提交测试结果、Issue 或 Pull Request。真实的失败案例和修复过程，比只展示一张最好看的成片更有价值。

## License

MIT © 2026 金宏祚
