# Contributing to Distinct Video Faces

Thanks for helping AI-video creators build casts that are both distinctive and stable.

## Good contributions

- reproducible before/after tests on a named video model and version;
- platform-adapter corrections backed by current official documentation;
- benchmark cases that reveal cast convergence or identity drift;
- privacy-preserving improvements to the local audit tools;
- focused bug fixes with regression tests.

## Evidence for generation results

Include enough information for another creator to understand the comparison:

1. model, product or workflow name, version, and test date;
2. text-to-video or image-to-video mode and relevant settings;
3. number of generations or retries and approximate cost, if known;
4. the baseline prompt or workflow and the Skill-assisted workflow;
5. what was held constant between the two runs;
6. accepted and failed examples, not only the best frame;
7. face-audit JSON or annotated report when available;
8. a short human assessment of identity stability and cast separation.

Do not claim that a result is scientific, universal, or deterministic unless the evidence supports that claim.

## Privacy and rights

- Do not upload private footage, unlicensed face datasets, celebrity deepfakes, or material you do not have permission to share.
- Prefer fictional characters, consenting adults, licensed stock, or clearly documented synthetic inputs.
- Remove personal metadata before attaching files.
- The optional face audit runs locally; do not add telemetry or remote uploads without an explicit, reviewed proposal.

## Code changes

Before opening a pull request, run:

```bash
python3 -m unittest discover -s tests -v
npx --yes skills@latest add . --list
```

For changes to `skills/direct-distinct-video-faces/SKILL.md`, keep the frontmatter limited to `name` and `description`, keep instructions concise, and put detailed supporting material in `references/`.

For script changes:

- preserve dependency-light behavior where practical;
- add a regression test for each fixed failure mode;
- keep thresholds configurable rather than hiding pipeline-specific constants;
- document output-contract changes in `references/data-contracts.md`;
- avoid network access except the documented, checksum-verified model download.

## Pull requests

Keep each pull request focused. Explain the failure, the smallest fix, the evidence, and any remaining limitation. Screenshots are welcome, but tests and reproducible inputs are preferred.
