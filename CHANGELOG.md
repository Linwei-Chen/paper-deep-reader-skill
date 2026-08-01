# Changelog

## 2.1.0 — 2026-08-01

- Added explicit `visual` and `text-only` execution routes for models without image understanding.
- Added `inventory --text-only`, which emits page text, per-visual text cards, body-reference contexts, and a text evidence ledger without rendering PNG assets.
- Added A/B/C/D text evidence grades and strict rules against presenting caption/OCR inference as direct visual observation.
- Added `validate_report.py --text-only` checks for disclosure, text-review completion, source recording, unverified-crop handling, and source-map execution metadata.
- Upgraded the source-map template to schema v3 with visual capability and verification fields.
- Documented structured-source, PDF-text, OCR, user-description, and human/vision-model handoff paths.

## 2.0.0 — 2026-08-01

- Broadened the default audience from computer-vision Ph.D. readers to research-trained readers across disciplines.
- Added structured routing for domain, audience, goal, depth, and language.
- Added project-level `.paper-reader.yaml` preferences and an example configuration.
- Separated method, theory, empirical/observational, dataset, system, and review paper types from domain-specific evidence norms.
- Added domain lenses for AI/CS, biomedicine, physics/mathematics, chemistry/materials, engineering, social science, earth/environment, and humanities/qualitative research.
- Kept computer vision as a deeply supported optional lens.
- Generalized report, reading, quality, and source-map protocols from model/experiment language to methods, theory, observation, qualitative evidence, and other research designs.
- Extended PDF caption detection to Scheme, Plate, Box, Chart, supplementary visuals, and Extended Data visuals.
- Added multilingual elevator-pitch validation and reader-profile validation for source-map schema v2.

## 1.0.0 — 2026-07-31

- Initial open-source release with source-grounded deep reading, visual extraction, report validation, and computer-vision-focused review guidance.
