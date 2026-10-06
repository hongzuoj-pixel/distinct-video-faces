# Platform adapters

## Contents

1. Capability check
2. Text-to-video
3. First-frame image-to-video
4. Multi-reference generation
5. Local controllable workflows
6. Named-platform output

## 1. Capability check

Platform features change. Before promising a parameter or workflow, verify current official documentation for:

- number and type of identity references;
- start/end frame support;
- seed exposure;
- negative prompt support;
- character or ingredient features;
- clip lengths and aspect ratios;
- extension, edit, inpaint, or object-removal support;
- audio and dialogue generation;
- restrictions on real-person likenesses.

If browsing is unavailable, describe the adapter by capability and label uncertain platform-specific controls for user confirmation.

## 2. Text-to-video

Use the complete compact identity block in every recurring shot. Put identity before mutable styling. Keep one principal action per short shot.

```text
[IDENTITY_LOCK]
[shot size + camera + duration]
[single performance beat]
[setting + lighting + wardrobe]
[landmarks to preserve]
[concrete avoid list]
```

Text-to-video is the weakest path for recurring identity. Recommend approving an anchor still and moving to image-to-video when possible.

## 3. First-frame image-to-video

Treat the image as the identity and visual-style source. Focus the prompt on:

- camera motion;
- subject motion;
- expression transition;
- environmental motion;
- identity landmarks at risk during that motion.

Avoid restating visible appearance in conflicting language. Use a separate end frame only when the platform supports it and the two frames depict the same identity geometry.

## 4. Multi-reference generation

Assign every reference a role:

```text
REF-A: identity, neutral three-quarter
REF-B: same identity, clean profile
REF-C: same identity, natural speaking expression
STYLE-1: palette and texture only; do not borrow faces
WORLD-1: location only; do not borrow people
```

Do not mix identity references from separate generations until landmark consistency has been checked. Use the platform's supported reference limit rather than assuming an arbitrary count.

For systems with an “ingredients” or character-reference feature, keep character references separate from environment/style references where the UI allows it. Current Google guidance for Veo describes structured prompts and reference-image workflows; verify the exact deployed model before outputting settings:

- https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-veo-3-1/
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/best-practice
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/generate-videos-from-references

## 5. Local controllable workflows

For ComfyUI, Wan, or similar pipelines, express the plan in capability modules rather than inventing node names:

1. identity/reference conditioning;
2. pose or depth control when needed;
3. temporal video model;
4. face-region refinement with low enough strength to preserve geometry;
5. frame sampling and identity-similarity audit;
6. localized retry for failed spans.

Do not use face restoration at a strength that replaces the designed face with the restorer's average face. LoRA training is a later option when references and prompt locking are insufficient; require a licensed, internally consistent dataset and hold-out validation angles.

## 6. Named-platform output

For each selected platform, provide:

- ready-to-paste prompt;
- uploaded-reference mapping;
- exposed settings to keep fixed;
- features that are unavailable or uncertain;
- platform-specific failure risk;
- fallback adapter if the platform cannot preserve identity.

Do not merely translate the same prose into another language. Adapt prompt length, whether identity should be text or reference-led, and how motion is expressed.
