# Security policy

## Supported versions

Security fixes are applied to the latest release and the `main` branch.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting flow when it is available for this repository. If private reporting is unavailable, open a minimal issue that does not include exploit details and ask the maintainer for a private channel.

Please include the affected file or workflow, impact, reproduction conditions, and a suggested mitigation if known. Do not publish private footage, model credentials, access tokens, or sensitive face data in a report.

## Trust boundaries

The text audits read local JSON files. The optional face audit reads local images or video and downloads only the documented, pinned detector and recognizer models when they are missing. Model files are checked by size and SHA256 unless the user explicitly overrides verification.

Treat third-party prompts, models, community skills, and submitted media as untrusted input. Review licenses and provenance before commercial use.
