# Codex Workflow Skills

English | [简体中文](README.md)

A collection of workflow-focused Codex Skills that help Codex approach research, technical
selection, and software development with reliable, reusable methods.

These Skills go beyond prompt templates. Each one defines an end-to-end workflow for clarifying the
goal, selecting tools, validating evidence, handling uncertainty, and delivering actionable results.

## Skill Catalog

| Skill | What it solves | Best for |
|---|---|---|
| [`general-web-research`](plugins/etolucy-skills/skills/general-web-research/) | Turns open-ended questions into traceable evidence and decision-ready due diligence | Researching people, organizations, products, markets, reputation, career choices, and other current topics |
| [`find-open-source-solutions`](plugins/etolucy-skills/skills/find-open-source-solutions/) | Discovers, verifies, and compares GitHub projects, then recommends a repository or composed stack | Technical selection, open-source alternatives, project foundations, and multi-repository solution design |
| [`learn-by-building`](plugins/etolucy-skills/skills/learn-by-building/) | Delivers working software while teaching the reasoning needed to build similar projects independently | Project creation, feature development, debugging, refactoring, code understanding, and guided practice |

### General Web Research

Use this when you need to make a decision from public information rather than receive a list of
loosely related links.

- Establishes the decision, constraints, time frame, and risk tolerance
- Collects evidence by source tier with publication and access dates
- Separates verified facts, reported claims, inferences, and unknowns
- Actively searches for disconfirming evidence, conflicts, and gaps
- Delivers conclusions, risks, comparisons, next actions, and auditable sources

Example:

> Investigate whether this company is suitable as a long-term supplier, focusing on financial
> stability, public controversies, and delivery risk.

### Find Open Source Solutions

Use this when you understand the problem but do not yet know which open-source project to adopt.

- Uses GitHub MCP to discover and verify candidate repositories
- Uses Context7 to inspect project code and official documentation
- Compares maintenance, architecture, capabilities, integration cost, and ecosystem maturity
- Supports both single-repository and composed solutions
- Makes one default recommendation and explains when alternatives are preferable

Example:

> Recommend a self-hosted stack for an internal knowledge base with access control, full-text
> search, and Chinese-language support.

### Learn by Building

Use this when you want a working project and a clear understanding of why it is built that way.

- Breaks implementation into small, runnable, verifiable steps
- Explains principles, tradeoffs, and common mistakes at important decisions
- Maintains bilingual English and Chinese project documentation
- Protects private context and asks before publishing to GitHub
- Uses practice and review to build independent problem-solving ability

Example:

> Help me build a React expense tracker. After each module, explain the data flow and design choices
> so I can extend it myself.

## Install

Add this repository as a Codex Marketplace:

```powershell
codex.cmd plugin marketplace add ETOLucy/Lucy_skills
```

On macOS or Linux:

```bash
codex plugin marketplace add ETOLucy/Lucy_skills
```

Install `etolucy-skills` from Marketplace in the Codex app, then start a new conversation to load
the Skills and MCP dependencies.

## Tools and Permissions

- `general-web-research` uses the web search and browsing tools available in the current environment.
- `find-open-source-solutions` configures read-only GitHub MCP and Context7 MCP. GitHub MCP requests
  authentication during installation.
- `learn-by-building` uses the current project's development tools and asks for confirmation before
  publishing anything to GitHub.
- The Skills contain no API keys, personal data, machine-specific paths, or private service settings.

## Repository Layout

```text
.agents/plugins/marketplace.json
plugins/etolucy-skills/
├── .codex-plugin/plugin.json
├── .mcp.json
└── skills/
    ├── find-open-source-solutions/
    ├── general-web-research/
    └── learn-by-building/
```

## License

[MIT](LICENSE)
