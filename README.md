<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/logo-mark-dark.svg">
    <img src="assets/brand/logo-mark.svg" width="112" alt="Codex Workflow Skills logo">
  </picture>
</p>

<h1 align="center">Codex Workflow Skills</h1>

<p align="center"><strong>面向研究、设计与开发任务的可靠 Codex 工作流</strong></p>

<p align="center">
  <a href="README.en.md">English</a> · 简体中文
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/ETOLucy/codex-workflow-skills?style=flat-square&color=18A889" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/skills-4-17202A?style=flat-square" alt="4 Skills">
  <img src="https://img.shields.io/badge/plugin-v0.5.0-18A889?style=flat-square" alt="Plugin version 0.5.0">
</p>

这组 Skills 为 Codex 提供可复用的端到端流程：明确目标、选择工具、验证证据、处理不确定性，
并交付可以直接执行或继续迭代的结果。每个 Skill 都针对真实工作场景设计，而不是一组孤立提示词。

## 快速开始

将本仓库添加为 Codex Marketplace：

```powershell
codex.cmd plugin marketplace add ETOLucy/codex-workflow-skills
```

macOS 或 Linux：

```bash
codex plugin marketplace add ETOLucy/codex-workflow-skills
```

然后在 Codex 应用的 Marketplace 中安装 `etolucy-skills`，并开启一个新对话以加载 Skills
和 MCP 依赖。

## Skill 一览

| Skill | 用途 | 适用场景 |
|---|---|---|
| [`create-context-aware-logos`](plugins/etolucy-skills/skills/create-context-aware-logos/) | 根据目标平台设计原创 Logo，并交付可直接使用的资产组合 | GitHub 仓库、应用图标、CLI、网站品牌、Codex Skill/插件 |
| [`general-web-research`](plugins/etolucy-skills/skills/general-web-research/) | 将开放问题转化为可追溯证据和面向决策的尽调报告 | 人物、组织、产品、市场、声誉、职业选择和其他时效性课题 |
| [`find-open-source-solutions`](plugins/etolucy-skills/skills/find-open-source-solutions/) | 发现、核验并比较 GitHub 项目，给出明确的单仓库或组合方案 | 技术选型、开源替代品、项目基础和多仓库方案设计 |
| [`learn-by-building`](plugins/etolucy-skills/skills/learn-by-building/) | 在交付可运行项目的同时讲清思路，建立可迁移的开发能力 | 项目创建、功能开发、调试、重构、代码理解和结对式学习 |

### Context-Aware Logo Design

默认从三个真正不同的方向开始，再精修选定方案。它会根据目标场景自动选择 SVG、深浅色版本、
README 字标、Social Preview 或应用图标等交付物，并检查小尺寸识别、无障碍信息和文件安全。

> 示例：为我的 GitHub 仓库设计一个简洁 Logo，并交付 README 标志和 Social Preview。

### General Web Research

先定义决策、范围和证据标准，再检索官方来源、独立报道、论坛和公开数据。输出会区分事实、
他人陈述、推断与未知项，并保留日期、冲突、风险和可审计来源。

> 示例：调查这家公司是否适合作为长期供应商，重点核查经营稳定性、公开争议和交付风险。

### Find Open Source Solutions

使用只读 GitHub MCP 发现并核验候选，通过 Context7 阅读代码和官方文档，比较维护状态、架构、
集成成本与生态成熟度，最后给出一个默认推荐和有条件的替代方案。

> 示例：为内部知识库推荐可自托管方案，需要权限控制、全文检索和中文支持。

### Learn by Building

把实现拆成可运行、可验证的小步，在关键决策处解释原理和权衡，维护中英文项目文档，
并在任何 GitHub 发布操作前请求确认。

> 示例：帮我做一个 React 记账应用；每完成一个模块，解释数据流和设计选择。

## 设计原则

- **面向结果：** 从用户要做的决策或交付物出发，而不是从工具列表出发。
- **证据优先：** 对会变化或影响决策的事实进行实时核验。
- **渐进披露：** 只在需要时加载详细参考资料，控制上下文成本。
- **安全默认：** 不包含密钥、个人数据、本机路径或私有服务配置。
- **确认后发布：** 涉及外部写入或 GitHub 发布时保留明确的用户确认边界。

## 工具与权限

- `create-context-aware-logos` 默认使用本地 SVG 和校验工具；插画型需求才需要图片生成能力。
- `general-web-research` 使用当前环境可用的网页搜索和浏览工具。
- `find-open-source-solutions` 配置只读 GitHub MCP 和 Context7 MCP；GitHub MCP 安装时请求认证。
- `learn-by-building` 使用当前项目的开发工具，并在发布前请求确认。

## 仓库结构

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

## 支持与维护

遇到问题或希望提出改进，请使用 [GitHub Issues](https://github.com/ETOLucy/codex-workflow-skills/issues)。
项目由 [ETOLucy](https://github.com/ETOLucy) 维护。

## License

[MIT](LICENSE)