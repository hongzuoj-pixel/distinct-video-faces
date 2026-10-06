---
name: direct-distinct-video-faces
description: Design distinctive, believable human characters for AI-generated video while preserving identity across shots. Use for text-to-video or image-to-video character development, avoiding generic "AI faces," building multi-character casts, creating reference-image plans, writing platform-adapted shot prompts, auditing existing generations for facial sameness or identity drift, and producing targeted regeneration instructions for tools such as Kling, Jimeng, Hailuo, Veo, or local ComfyUI/Wan workflows.
---

# Direct Distinct Video Faces

Build faces that are specific rather than generically attractive, then keep those identities stable through motion, lighting, angle, and editing changes. Treat cast separation and within-character consistency as separate objectives.

This skill reduces two measurable failure risks; it does not promise deterministic faces from probabilistic generators. Prefer reference-first workflows, explicit acceptance gates, and evidence from sampled frames over confidence based on prompt wording alone.

## Core rules

- Preserve the user's story, casting intent, and desired degree of realism.
- Do not infer sensitive traits from an uploaded face. Use only traits the user states or features directly needed for visual continuity.
- For a recognizable real person, confirm the user has the right to use the likeness before generating a reusable identity pack. Do not frame synthetic footage as authentic evidence.
- Define people through several interacting cues, not one exaggerated feature or a stereotype.
- Prefer observable geometry, texture, asymmetry, grooming, posture, and motion over vague words such as `beautiful`, `handsome`, `perfect`, or `cinematic face`.
- Never solve sameness by making every face bizarre. Aim for plausible population-level variation.
- Keep the immutable identity block literally unchanged across shots unless the user asks to age, transform, or recast the character.
- In image-to-video prompts, describe motion and camera behavior without redundantly redescribing the visible face unless the platform explicitly needs the identity block.
- Escalate only when the cheaper intervention fails a named test. Do not recommend training or a new paid service before trying the relevant lower-cost gate.

## Workflow

### 1. Establish the production mode

Collect only missing inputs that materially affect the result:

1. Script, premise, or intended scene.
2. Number of recurring characters.
3. Target platform, or `platform-neutral` if undecided.
4. Output format, duration, aspect ratio, and realism level.
5. Existing references, generated frames, or clips.
6. Whether any character is based on a real person.

If the user provides little detail, choose sensible defaults and label them. Do not stall the workflow for optional preferences.

Select one path:

- **Design from zero:** create identity bibles, reference plans, and shot prompts.
- **Repair a cast:** inspect supplied media, identify collisions and drift, then revise only weak identity anchors.
- **Audit a finished clip:** score it, identify exact failure frames or shots, and prescribe the smallest regeneration scope.

Read [references/intervention-ladder.md](references/intervention-ladder.md) to select the lightest reliable workflow. Read [references/identity-design.md](references/identity-design.md) when designing or repairing characters. Read [references/platform-adapters.md](references/platform-adapters.md) when creating prompts for a named generator. Read [references/qc-rubric.md](references/qc-rubric.md) when auditing frames or video. Read [references/data-contracts.md](references/data-contracts.md) before writing machine-auditable JSON packs.

### 2. Diagnose the sameness mechanism

Check for these distinct failure modes:

- **Cast convergence:** multiple characters share the same facial proportions, skin finish, styling, or expression language.
- **Beauty-prior collapse:** every person becomes young, symmetrical, smooth-skinned, narrow-nosed, large-eyed, and editorially lit.
- **Identity drift:** one character's geometry changes between angles or frames.
- **Reference contamination:** clothing, lighting, makeup, or style references overwrite identity.
- **Prompt overload:** too many competing facial adjectives cause the generator to average them.
- **Motion plasticity:** blinking, speech, smiles, or head turns erase stable landmarks.

State which mechanisms are observed or likely before prescribing fixes.

### 3. Build a Character Identity Bible

Create one compact immutable block per recurring person. Include:

- age read and overall build;
- face silhouette and vertical proportions;
- brow, eye spacing/shape, nose bridge/tip, mouth/philtrum, chin/jaw, and ear cues;
- two or three subtle asymmetries;
- believable skin texture and stable marks;
- hairline, hair, facial hair, eyewear, or grooming anchors;
- posture, blink pattern, habitual tension, and expression range;
- stable voice/movement cues when the platform generates audio;
- forbidden drift: features the model must not beautify, symmetrize, smooth, enlarge, or narrow.

Use 6–10 high-information anchors, not a paragraph of synonyms. Separate mutable styling—clothes, makeup, lighting, emotion—from immutable identity.

For casts, create a **separation matrix** comparing silhouette, eye spacing, nose, jaw, age read, texture, hairline, expression baseline, and movement. Change any pair that overlaps on more than half of the high-salience axes. Write a `character-pack.json` when the user wants a reusable production artifact, then run `scripts/audit_character_pack.py` and resolve every collision warning before generating references.

### 4. Plan the references

Prefer an identity reference pack over a single glamour portrait:

- neutral frontal view;
- three-quarter view;
- clean profile;
- one natural speaking or smiling expression;
- optional full-body/posture view.

Keep lens character, focal distance, age, grooming, and identity stable. Vary angle and expression, not the person. Avoid heavy retouching, extreme makeup, shallow depth of field over both eyes, and mixed lighting that hides landmarks.

If the platform accepts only one image, select the three-quarter neutral reference with both facial sides legible. If it accepts several, use the platform's supported limit and reserve style/environment references separately from identity references.

When image generation is available and the user requests assets, generate the reference pack before video prompts. Inspect each image and reject any whose geometry contradicts the bible.

### 5. Build prompts in layers

Construct each shot from separate blocks:

1. `IDENTITY_LOCK`: the unchanged compact identity description or attached reference identifiers.
2. `SHOT`: framing, lens behavior, camera movement, duration, and composition.
3. `PERFORMANCE`: action, gaze, expression transition, blink, speech, and body movement.
4. `WORLD`: setting, light, atmosphere, and mutable wardrobe.
5. `PRESERVE`: landmarks that must remain stable through motion.
6. `AVOID`: shot-specific failure modes, written concretely.

Do not overload a short clip with several scene changes. Split complex action into shots and bridge them with a shared end/start frame when supported.

Create a platform-neutral master first, then translate it into the target platform's syntax. Verify current capabilities from official documentation when parameters or feature support may have changed.

When producing multiple shots, write a `prompt-pack.json` using the data contract and run `scripts/audit_prompt_pack.py`. Treat errors as blockers. Explain or fix warnings about generic beauty language, missing identity locks, absent reference roles, weak preservation anchors, or overloaded camera motion.

### 6. Generate and evaluate in gates

Use a gated workflow to avoid wasting video generations:

1. Approve identity bibles.
2. Approve neutral anchor stills.
3. Test a low-motion close or medium shot.
4. Test the hardest identity stressor: profile, speech, smile, occlusion, or rapid head turn.
5. Generate the remaining shots.
6. Audit the edited sequence for cast convergence and within-character drift.

For supplied clips, run `scripts/sample_video_frames.py` when `ffmpeg` is available (ffprobe is optional). It samples first, middle, and last frames plus the highest-motion stress frames. If `opencv-contrib-python` is installed, follow with `scripts/audit_face_consistency.py` to measure identity drift against the approved anchors and cross-identity similarity for the cast; pass one anchor still per recurring character via `--anchors`. Use anchor-free mode only for a single obvious subject. Treat a FAIL as a lead, not a verdict: inspect the flagged frames yourself before prescribing regeneration. Do not use a single face-embedding score as proof: embeddings can miss perceived sameness, identity swaps during occlusion, or systematic beautification.

Keep seed, identity references, and immutable text fixed where supported. Change one causal layer at a time: identity, motion, camera, lighting, or styling.

### 7. Prescribe minimal repairs

For every failed shot, return:

- observed symptom;
- likely cause;
- preserved elements;
- one primary change;
- optional fallback change;
- exact regeneration scope.

Prefer local or shot-level regeneration over rebuilding an accepted character. When a smile or speech causes drift, reduce expression amplitude, preserve landmark relationships, and stage the motion across a shorter clip before changing the identity description.

## Required output

Unless the user requests a smaller result, deliver:

1. **Creative diagnosis** — why generic faces are likely in this project.
2. **Character Identity Bibles** — immutable and mutable blocks clearly separated.
3. **Cast Separation Matrix** — concrete pairwise collisions and fixes.
4. **Reference Pack Plan** — required views and rejection criteria.
5. **Shot Prompt Pack** — platform-neutral master plus selected platform adapters.
6. **Negative/Preservation Constraints** — concrete, non-stereotyped, shot-specific.
7. **QC Scorecard** — identity stability, distinctiveness, texture, motion, and edit continuity.
8. **Regeneration Plan** — ranked by expected impact and cost.
9. **Validation Evidence** — audit command results and the frames or shots used for acceptance.

Do not claim that prompts alone guarantee identity. Clearly distinguish model limits, reference quality problems, and prompt problems.
