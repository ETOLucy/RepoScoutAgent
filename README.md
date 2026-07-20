# ETOLucy Skills

[English](README.en.md) | 简体中文

这是一个个人 Codex Skill 集。当前包含：

- `find-open-source-solutions`：使用模型知识和实时发现寻找 GitHub 候选，并优先通过
  Context7 检索仓库代码和官方文档，生成明确的单仓库或多仓库解决方案。

## 安装

直接将 GitHub 仓库添加为 Codex Marketplace：

```powershell
codex.cmd plugin marketplace add ETOLucy/find-open-source-solutions
```

在 macOS 或 Linux 上使用 `codex plugin marketplace add ETOLucy/find-open-source-solutions`。
然后在 Codex 应用的 Marketplace 中安装 `etolucy-skills`，并开启一个新对话，让 Codex
加载新的 Skill 和 Context7 MCP。

## 目录

```text
.agents/plugins/marketplace.json
plugins/etolucy-skills/
├── .codex-plugin/plugin.json
├── .mcp.json
└── skills/
    └── find-open-source-solutions/
```

以后新增 Skill 时，将其放入 `plugins/etolucy-skills/skills/`，再更新插件版本。
