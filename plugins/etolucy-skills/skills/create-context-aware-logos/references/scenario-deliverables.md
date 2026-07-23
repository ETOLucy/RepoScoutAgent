# Scenario Deliverables

Read the section matching the user's primary context. Combine sections only when the identity will
ship across multiple surfaces.

## GitHub repository

Deliver:

- `logo-mark.svg`: square, transparent, recognizable at 32 px;
- `logo-lockup.svg`: mark plus repository name for README use;
- `social-preview.png`: 1280 x 640 px and under 1 MB;
- light and dark README variants when one asset cannot adapt cleanly;
- concise README header markup and alt text;
- a restrained badge and repository-topic recommendation.

GitHub has no dedicated repository-logo field. Treat the README header, social preview, repository
description, topics, and owner avatar as separate surfaces. Do not imply that README badges are
official certifications.

## GitHub organization

Deliver a square avatar that survives circular cropping, plus the repository assets above when
requested. Keep critical geometry away from the outer edge.

## Application

Deliver a square master icon, monochrome symbol, light/dark variants, and platform export guidance.
Use a generous safe area and avoid thin strokes. Ask which operating systems or stores matter before
creating platform-specific packages.

## CLI or developer tool

Prioritize a monochrome mark, terminal readability, a compact README lockup, and an optional simple
wordmark. Do not make animation, gradients, or detailed illustration part of the core identity.

## Website or web product

Deliver a primary lockup, compact mark, favicon source, light/dark variants, and an Open Graph image.
Include header placement guidance and accessible alt text.

## Codex skill or plugin

Deliver small and large logo assets under the component's `assets/` directory. Reference them from
`agents/openai.yaml` with `icon_small` and `icon_large`; add `brand_color` only after selecting a
final palette. For a plugin, use the manifest-supported `composerIcon`, `logo`, `logoDark`, and
`brandColor` fields only when the corresponding files exist and pass plugin validation.

## General brand identity

If no platform is primary, deliver a square mark, horizontal lockup, monochrome and reversed
variants, palette, minimum-size guidance, and SVG source files. Ask which real surface should be
tested first before producing a large export matrix.

## Optional expansion

Add these only when requested:

- animated logo;
- print color specifications;
- presentation or social templates;
- favicon and app-icon packages;
- physical or environmental mockups;
- a full brand-guidelines document;
- extensive concept exploration beyond three directions.