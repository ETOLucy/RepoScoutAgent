# ETOLucy Skills

English | [简体中文](README.md)

A personal collection of Codex skills. It currently includes:

- `find-open-source-solutions`: uses GitHub MCP to discover and verify current candidates, then uses
  Context7 semantic retrieval over repository code and official documentation before producing a
  decisive single-repository or composed solution.
- `learn-by-building`: advances real projects through small, runnable steps while prioritizing mental
  models, implementation reasoning, verification, and transferable hands-on practice.

## Install

Add the GitHub repository directly as a Codex marketplace:

```powershell
codex.cmd plugin marketplace add ETOLucy/etolucy-skills
```

On macOS or Linux, use `codex plugin marketplace add ETOLucy/etolucy-skills`.
Install `etolucy-skills` from Marketplace in the Codex app, then start a new conversation so Codex
loads the skills, read-only GitHub MCP, and Context7 MCP dependencies. GitHub authentication is
requested during MCP installation.

## Layout

```text
.agents/plugins/marketplace.json
plugins/etolucy-skills/
├── .codex-plugin/plugin.json
├── .mcp.json
└── skills/
    ├── find-open-source-solutions/
    └── learn-by-building/
```

Add future skills under `plugins/etolucy-skills/skills/` and update the plugin version.
