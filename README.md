# Codex Workflow Skills

[English](README.en.md) | 简体中文

一组面向真实工作流的 Codex Skills，让 Codex 在研究、技术选型和项目开发中采用更可靠、
可复用的工作方法。

这些 Skills 不只是提供提示词模板，而是为任务定义完整的执行流程：如何澄清目标、选择工具、
验证证据、处理不确定性，以及交付可执行的结果。

## Skill 一览

| Skill | 解决什么问题 | 适用场景 |
|---|---|---|
| [`general-web-research`](plugins/etolucy-skills/skills/general-web-research/) | 将开放式问题转化为可追溯的证据和面向决策的尽调报告 | 人物、组织、产品、市场、声誉、职业选择和其他需要核查时效性信息的课题 |
| [`find-open-source-solutions`](plugins/etolucy-skills/skills/find-open-source-solutions/) | 发现、核验并比较 GitHub 开源项目，给出明确的单仓库或组合方案 | 技术选型、开源替代品比较、项目脚手架选择和多仓库方案设计 |
| [`learn-by-building`](plugins/etolucy-skills/skills/learn-by-building/) | 在交付可运行项目的同时讲清实现思路，帮助用户形成可迁移的开发能力 | 项目创建、功能开发、调试、重构、代码理解和结对式学习 |

### General Web Research

适合“我需要基于公开信息做判断，但不想得到一份链接堆砌”的任务。

- 先明确决策目标、约束、时间范围和风险偏好
- 按来源等级收集证据，并记录发布日期与访问日期
- 区分已验证事实、他人陈述、推断和未知项
- 主动寻找反面证据、矛盾信息和关键缺口
- 输出结论、风险、比较表、后续行动与可审计来源

示例：

> 调查这家公司是否适合作为长期供应商，重点核查经营稳定性、公开争议和交付风险。

### Find Open Source Solutions

适合“我知道要解决什么，但不知道应该采用哪个开源项目”的任务。

- 使用 GitHub MCP 发现并核验候选仓库
- 使用 Context7 阅读项目代码与官方文档
- 比较维护状态、架构、功能、集成成本和生态成熟度
- 支持单仓库方案与多仓库组合
- 给出一个默认推荐，并明确替代方案成立的条件

示例：

> 为内部知识库推荐一套可自托管的开源方案，需要权限控制、全文检索和中文支持。

### Learn by Building

适合希望“把项目做出来，同时真正理解为什么这样做”的开发任务。

- 将工作拆成可运行、可验证的小步
- 在关键决策处解释原理、权衡和常见误区
- 维护中英文项目文档
- 保护私人上下文，发布到 GitHub 前要求确认
- 通过练习和回顾帮助用户独立完成类似工作

示例：

> 帮我做一个 React 记账应用；每完成一个模块，解释数据流和设计选择，让我能自己扩展。

## 安装

将此仓库添加为 Codex Marketplace：

```powershell
codex.cmd plugin marketplace add ETOLucy/codex-workflow-skills
```

在 macOS 或 Linux 上运行：

```bash
codex plugin marketplace add ETOLucy/codex-workflow-skills
```

然后在 Codex 应用的 Marketplace 中安装 `etolucy-skills`，并开启一个新对话以加载 Skills
和 MCP 依赖。

## 工具与权限

- `general-web-research` 使用当前环境可用的网页搜索和浏览工具。
- `find-open-source-solutions` 配置了只读 GitHub MCP 和 Context7 MCP；GitHub MCP 会在安装时请求认证。
- `learn-by-building` 使用当前项目的开发工具；任何 GitHub 发布操作都需要用户先确认。
- Skills 不包含 API 密钥、个人数据、本机路径或私有服务配置。

## 仓库结构

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
