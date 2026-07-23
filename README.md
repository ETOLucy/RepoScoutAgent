# ETOLucy Skills

[English](README.en.md) | 简体中文

这是一个个人 Codex Skill 集。当前包含：

- `find-open-source-solutions`：使用 GitHub MCP 实时发现并核验候选，再通过 Context7
  语义检索仓库代码和官方文档，生成明确的单仓库或多仓库解决方案。
- `learn-by-building`：在推进真实项目的同时，以教学和能力迁移为核心，通过小步实现、
  原理讲解、验证和练习，让用户逐步具备独立完成类似工作的能力。
- `general-web-research`：开展可复现、面向决策的通用尽调，提供带日期的来源、证据分级、
  明确的不确定性和可执行结论。

## 安装

直接将 GitHub 仓库添加为 Codex Marketplace：

```powershell
codex.cmd plugin marketplace add ETOLucy/etolucy-skills
```

在 macOS 或 Linux 上使用 `codex plugin marketplace add ETOLucy/etolucy-skills`。
然后在 Codex 应用的 Marketplace 中安装 `etolucy-skills`，并开启一个新对话，让 Codex
加载新的 Skill、只读 GitHub MCP 和 Context7 MCP。GitHub MCP 会在安装时请求 GitHub 认证。

## 目录

```text
.agents/plugins/marketplace.json
plugins/etolucy-skills/
├── .codex-plugin/plugin.json
├── .mcp.json
└── skills/
    ├── find-open-source-solutions/
    ├── learn-by-building/
    └── general-web-research/
```

以后新增 Skill 时，将其放入 `plugins/etolucy-skills/skills/`，再更新插件版本。
