# ETOLucy Skills

English | [简体中文](README.md)

A personal collection of Codex skills. It currently includes:

- `find-open-source-solutions`: discovers GitHub candidates using model knowledge and live search,
  then prefers Context7 retrieval over repository code and official documentation before producing
  a decisive single-repository or composed solution.

## Install

Add the GitHub repository directly as a Codex marketplace:

```powershell
codex.cmd plugin marketplace add ETOLucy/find-open-source-solutions
```

On macOS or Linux, use `codex plugin marketplace add ETOLucy/find-open-source-solutions`.
Install `etolucy-skills` from Marketplace in the Codex app, then start a new conversation so Codex
loads the skills and Context7 MCP dependency.

## Layout

```text
.agents/plugins/marketplace.json
plugins/etolucy-skills/
├── .codex-plugin/plugin.json
├── .mcp.json
└── skills/
    └── find-open-source-solutions/
```

Add future skills under `plugins/etolucy-skills/skills/` and update the plugin version.
