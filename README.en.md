<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/logo-mark-dark.svg">
    <img src="assets/brand/logo-mark.svg" width="112" alt="Codex Workflow Skills logo">
  </picture>
</p>

<h1 align="center">Codex Workflow Skills</h1>

<p align="center"><strong>Reliable Codex workflows for research, design, and development</strong></p>

<p align="center">
  English · <a href="README.md">简体中文</a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/ETOLucy/codex-workflow-skills?style=flat-square&color=18A889" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/skills-4-17202A?style=flat-square" alt="4 Skills">
  <img src="https://img.shields.io/badge/plugin-v0.5.0-18A889?style=flat-square" alt="Plugin version 0.5.0">
</p>

These Skills give Codex reusable, end-to-end methods for clarifying goals, selecting tools,
validating evidence, handling uncertainty, and delivering results that are ready to use or iterate.
Each Skill is designed around a real workflow rather than an isolated prompt template.

## Quick Start

Add this repository as a Codex Marketplace:

```powershell
codex.cmd plugin marketplace add ETOLucy/codex-workflow-skills
```

On macOS or Linux:

```bash
codex plugin marketplace add ETOLucy/codex-workflow-skills
```

Install `etolucy-skills` from Marketplace in the Codex app, then start a new conversation to load
its Skills and MCP dependencies.

## Skill Catalog

| Skill | Purpose | Best for |
|---|---|---|
| [`create-context-aware-logos`](plugins/etolucy-skills/skills/create-context-aware-logos/) | Designs an original logo for its target platform and delivers production-ready assets | GitHub repositories, app icons, CLIs, website brands, and Codex skills/plugins |
| [`general-web-research`](plugins/etolucy-skills/skills/general-web-research/) | Turns open questions into traceable evidence and decision-ready due diligence | People, organizations, products, markets, reputation, career choices, and other current topics |
| [`find-open-source-solutions`](plugins/etolucy-skills/skills/find-open-source-solutions/) | Discovers, verifies, and compares GitHub projects, then recommends a repository or composed stack | Technical selection, open-source alternatives, project foundations, and multi-repository solutions |
| [`learn-by-building`](plugins/etolucy-skills/skills/learn-by-building/) | Delivers working software while building transferable development ability | Project creation, feature development, debugging, refactoring, code understanding, and guided practice |

### Context-Aware Logo Design

Starts with three genuinely different directions, then refines the selected concept. It chooses the
right SVGs, light/dark variants, README lockup, social preview, or app icon for the target context and
checks small-size recognition, accessibility metadata, and file safety.

> Example: Design a concise logo for my GitHub repository and deliver a README mark and social preview.

### General Web Research

Defines the decision, scope, and evidence standard before searching official sources, independent
reporting, forums, and public data. It separates facts, reported claims, inferences, and unknowns while
preserving dates, conflicts, risks, and auditable sources.

> Example: Investigate whether this company is suitable as a long-term supplier, focusing on stability,
> public controversies, and delivery risk.

### Find Open Source Solutions

Uses read-only GitHub MCP to discover and verify candidates and Context7 to inspect code and official
documentation. It compares maintenance, architecture, integration cost, and ecosystem maturity before
making one default recommendation with conditional alternatives.

> Example: Recommend a self-hosted internal knowledge-base stack with access control, full-text search,
> and Chinese-language support.

### Learn by Building

Breaks implementation into runnable, verifiable steps, explains principles and tradeoffs at important
decisions, maintains bilingual project documentation, and asks before publishing anything to GitHub.

> Example: Help me build a React expense tracker and explain the data flow after each module.

## Design Principles

- **Outcome first:** Start from the decision or deliverable, not a list of tools.
- **Evidence over assumption:** Verify changing or decision-critical facts with current sources.
- **Progressive disclosure:** Load detailed references only when they are relevant.
- **Safe by default:** Include no keys, personal data, machine-specific paths, or private services.
- **Confirm before publishing:** Keep a clear user-confirmation boundary for external writes.

## Tools and Permissions

- `create-context-aware-logos` defaults to local SVG and validation tools; only illustrative work needs image generation.
- `general-web-research` uses the web search and browsing tools available in the current environment.
- `find-open-source-solutions` configures read-only GitHub MCP and Context7 MCP. GitHub MCP requests authentication during installation.
- `learn-by-building` uses the current project's development tools and asks before publishing.

## Repository Layout

```text
.agents/plugins/marketplace.json
assets/brand/
plugins/etolucy-skills/
├── .codex-plugin/plugin.json
├── .mcp.json
├── assets/
└── skills/
    ├── create-context-aware-logos/
    ├── find-open-source-solutions/
    ├── general-web-research/
    └── learn-by-building/
```

## Support and Maintenance

Open a [GitHub Issue](https://github.com/ETOLucy/codex-workflow-skills/issues) for bugs or improvement
requests. The project is maintained by [ETOLucy](https://github.com/ETOLucy).

## License

[MIT](LICENSE)