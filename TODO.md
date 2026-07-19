# RepoScoutAgent Roadmap

> 自然语言需求 -> Agent 关键词 -> GitHub 搜索 -> README/docs 证据匹配。

## 产品原则

1. 用户只需描述想找的项目、用途和功能，不需要编写 GitHub 查询。
2. LLM 负责理解需求、生成关键词和归纳文档；查询语法与硬条件由代码控制。
3. 每项“满足需求”的结论必须引用仓库文档原文。
4. 没有证据时返回 `unknown`，不能根据 Star、描述或常识猜测。
5. 仓库文档是不可信输入，必须限制路径、文件类型和内容预算。

## Milestone 0：可靠基础

- [x] 自然语言请求校验
- [x] GitHub 搜索及 403、429、超时和异常响应处理
- [x] 语言、Star、License、归档和活跃度确定性约束
- [x] 空仓库、禁用仓库和无默认分支过滤
- [x] 零结果查询自动放宽一次
- [x] Ruff、mypy、pytest-cov 和 GitHub Actions

## Milestone 1：关键词到文档证据

- [x] 定义通用 `SearchIntent` 和原子需求模型
- [x] LLM 生成 2 至 8 个英文 GitHub 搜索关键词
- [x] 防止 LLM 增加用户未提出的硬条件
- [x] 确定性编译 GitHub 查询
- [x] 读取默认分支 README 和 docs 文档
- [x] 限制仓库数、文件数、单文件和总内容预算
- [x] 无 README/docs 的仓库记录为不可分析候选
- [x] 对每条需求输出 `satisfied / violated / unknown`
- [x] 保存证据原文和来源文件
- [x] 校验 LLM 引用确实存在于来源文档
- [x] 按必需需求证据覆盖度排序
- [x] 前端展示关键词、需求和逐项文档证据

完成定义：用户输入任意项目需求后，结果必须来自实际仓库 README/docs；无证据的能力不能显示为满足。

## Milestone 2：更强的仓库有效性判断

- [ ] 分析 Release、Commit 和 Issue 活跃度
- [ ] 区分源码仓库、文档仓库、模板、Demo、Fork 和 Mirror
- [ ] 检查依赖清单、构建配置和项目关键清单文件
- [ ] 针对项目类型检查合理目录结构
- [ ] 识别 README 声明与仓库实现结构的明显矛盾
- [ ] 使用 LangGraph `Send` 并行分析候选
- [ ] 使用 semaphore 控制并发和 GitHub 二级限流
- [ ] 单仓库失败不影响其他候选
- [ ] 增加 API、Token、时间和文档字符预算
- [ ] 使用 SQLite checkpointer 支持中断恢复

## Milestone 3：评测与交付

- [ ] 建立 30 至 50 条自然语言需求标注集
- [ ] 保存固定 GitHub 和仓库文档响应用于离线回放
- [ ] 评测 Keyword Recall、Precision@5 和 Evidence Coverage
- [ ] 评测 Unsupported Inference Rate 和无效仓库检出率
- [ ] 比较单查询、关键词放宽和补充查询
- [ ] 记录延迟、Token、API 调用数和单次成本
- [ ] 支持 SSE 任务进度
- [ ] 增加 Dockerfile 和在线 Demo
- [ ] 展示仓库详情和横向证据对比

## 当前进度

Milestone 0 和 Milestone 1 的同步闭环已经完成。当前结论基于 README/docs 文档证据，还不能证明项目可构建、可运行或实现与文档完全一致；这些属于 Milestone 2。
