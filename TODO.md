# RepoScoutAgent Roadmap

## Product Goal

让用户用自然语言描述需求，尽可能找到真正符合要求的 GitHub 项目，并让每个“满足”结论都能追溯到仓库文档原文。

当前重点是端到端匹配质量，不以堆叠 Agent、框架或检索算法为目标。

性能工程的历史基线和 STAR 简历素材长期维护在
[`docs/PERFORMANCE_STAR.md`](docs/PERFORMANCE_STAR.md)。后续性能优化必须更新该文档，保留旧基线和失败方案，不用新数字覆盖历史记录。

## Current Architecture

```text
自然语言需求
-> LLM 即兴生成任务契约：成功标准、证据需要和搜索假设
-> 最多 6 条开放式搜索假设，每条连接后续验证标准
-> 并发搜索、独立放宽、候选去重
-> 最多 60 个候选做仓库级语义重排，保留前 24 个
-> README/docs 结构化切块与 commit 缓存
-> 批量 embedding、证据预筛选并保留探索候选
-> 8 路动态 worker 执行 L1/L2 判断，慢请求有界降级
-> LLM 输出 satisfied / violated / unknown
-> 原文、路径和 commit SHA 确定性校验
-> 按必需需求证据覆盖率排序
```

这是单 Agent 的确定性 LangGraph 工作流。节点职责明确，仓库抓取已经使用受控并发，因此当前不需要主 Agent、子 Agent、checkpoint 或 Agent 自主循环。

网页和 API 支持单 Agent 多轮会话：后续用户消息可以补充或覆盖此前条件，澄清问题可以在下一轮继续回答。会话记忆当前为有界进程内存储，不等同于 LangGraph checkpoint。

## Verification Boundary

项目最终停留在 **L2 静态实现验证**，不进入 L3 构建验证或 L4 运行验证。

- L1：README/docs 明确声称支持某项能力。
- L2：在依赖清单、配置 Schema、路由、manifest 或源码模块中发现可引用的实现迹象。
- L3/L4：需要安装依赖、执行构建脚本、测试或启动服务，不在 RepoScout 范围内。

候选 GitHub 仓库始终是不可信输入。RepoScout 不执行候选仓库的任何代码、安装命令、构建脚本、测试或容器配置。Docker MVP 只表示 RepoScout 自身可容器化部署，不表示会构建候选项目。

## Docker MVP

### Completed

- [x] FastAPI JSON API、SSE 进度流和静态前端
- [x] 单 Agent 多轮对话、会话 ID、条件续写和新建会话
- [x] Pydantic 结构化需求、搜索计划和证据结果
- [x] LLM 生成开放式任务契约，不受固定意图或策略枚举限制
- [x] 搜索假设携带预期信号并关联后续验证标准
- [x] 代码编译查询语法与硬约束，LLM 不直接控制 qualifier
- [x] 单条查询失败时保留其他查询结果
- [x] 候选证据检索与 LLM 判断使用可配置的有界并发
- [x] 空结果查询独立放宽一次
- [x] 候选按仓库全名去重，最多保留 60 个
- [x] 读取文档前按任务契约进行仓库级语义重排
- [x] embedding 失败时降级为可解释的确定性元数据重排
- [x] 过滤归档、禁用、空仓库和无默认分支仓库
- [x] 最多读取 24 个候选，默认预筛选 8 个进入强模型判断
- [x] README/docs Markdown 结构化切块、去噪与内容预算
- [x] 按 commit SHA 缓存文档与 chunk
- [x] BM25 + Multi-Query Dense Retrieval + 加权 RRF + MMR 混合检索
- [x] 每项原子需求拥有独立 Top-K 证据上下文
- [x] embedding 不可用时整轮熔断为 BM25 Top-K，避免逐仓库重复失败
- [x] chunk embedding 跨仓库批量调用并按内容 hash 做进程内缓存
- [x] 强模型规划与快速证据判断使用可独立配置的模型
- [x] 单仓库 LLM 判断超时后降级，不阻塞整轮结果
- [x] LLM 证据判断与规则降级
- [x] 引用原文、路径和 commit SHA 校验
- [x] GitHub 403/429、超时、5xx 重试和部分成功处理
- [x] 离线固定数据评测和质量指标报告
- [x] 分开计算候选召回、Recall@24、NDCG@24 和阶段性丢失名单
- [x] Ruff、mypy、pytest、覆盖率门槛和 CI
- [x] 非 root Docker 镜像
- [x] Compose 一键启动、健康检查和缓存卷
- [x] Docker 部署与环境变量文档
- [x] CI 中配置生产镜像构建

### MVP Acceptance

- [x] `POST /api/search` 可完成一次端到端搜索
- [x] `POST /api/search/stream` 可返回节点进度和最终结果
- [x] `GET /api/health` 可供容器健康检查
- [x] 没有证据的需求不能标记为 `satisfied`
- [x] 单个 GitHub 查询或仓库读取失败不破坏其他结果
- [x] 全部自动化测试通过且总覆盖率不低于 80%
- [x] `docker compose up --build` 是文档化的部署入口
- [ ] Docker 镜像在安装 Docker 的本机或 CI 中实际构建通过（当前工作区未安装 Docker CLI）

## Quality Backlog

这些项目直接服务于“更容易找到真正需要的项目”，按优先级推进：

### L2 Static Verification (Completed)

- [x] 只读取候选仓库 Tree 中的白名单文件，不 clone 或执行仓库
- [x] 解析 `pyproject.toml`、`requirements*.txt`、`package.json`、`Cargo.toml`、`go.mod` 等 manifest
- [x] 读取有界的配置 Schema、路由定义和功能模块路径
- [x] 为每项需求输出 `implemented / documented_only / uncertain / contradicted`
- [x] L2 结论必须引用静态文件路径、commit SHA 和最小原文
- [x] 不将依赖名或文件名单独作为 `implemented` 的充分条件
- [x] 前端分开展示“文档声称”和“静态实现迹象”
- [x] 增加虚假 README、仅有未使用依赖和否定实现的回归样例
- [x] 增加 L2 Precision、`documented_only` 检出率和错误实现推断率

### Retrieval Quality

- [ ] 扩展到 30-50 条人工标注的真实自然语言需求
- [x] 增加候选召回、Recall@24、NDCG@24 和逐案例阶段丢失诊断
- [ ] 在包含 25-60 个候选的真实案例上测 Candidate Recall@50 和重排增益
- [ ] 增加 Success@5、NDCG@5、硬约束违反率和 Unsupported Inference Rate
- [ ] 单独标注需求解析错误、候选漏召回、证据漏召回和最终误排序
- [x] 以独立搜索假设替代机械关键词组合，保留明确 rules fallback
- [x] 将文件类型、路径、标题和静态信号加入 embedding 输入
- [ ] 对否定语句、弃用说明和 roadmap 声明增加回归案例
- [ ] 证据不足时允许一次有预算的补充查询
- [x] 将必需条件的 `violated` 作为淘汰条件，而不只是降低分数
- [ ] 增加请求级 API、Token、GitHub 配额和耗时预算
- [ ] 增加结构化 trace ID 与节点耗时日志

## Deferred Decisions

以下能力目前不进入 MVP：

| Capability | Current decision | Reconsider when |
|---|---|---|
| Multi-Agent / subagents | 不需要 | 并行深度验证能显著降低延迟，且结果一致性可证明 |
| Agentic retrieval loop | 暂缓 | 大量失败来自证据缺口，单次补充查询有稳定收益 |
| 更重的 cross-encoder / LLM reranker | 暂缓 | 当前仓库级 embedding 重排在真实标注集上仍有稳定误排序 |
| Vector database | 不需要 | 需要跨请求持久化大规模仓库语义索引 |
| GraphRAG | 不需要 | 出现大量实体关系和多跳查询场景 |
| ColBERT / late interaction | 暂缓 | 当前混合检索在更大固定集上出现可复现的细粒度匹配瓶颈 |
| GitHub CLI / clone | 不需要 | L2 通过 GitHub REST API 读取白名单静态文件，不 clone 仓库 |
| Candidate repository build/test | 不进入项目 | L3 会执行不可信代码，超出产品安全边界 |
| Candidate repository runtime probe | 不进入项目 | L4 需要独立一次性 VM/MicroVM 执行平台 |
| Checkpoint / interrupt | 暂缓 | 搜索变成长任务并需要人工恢复 |
| Fine-tuning | 不计划 | Prompt、检索和规则优化已有稳定瓶颈且有足够审核数据 |

## Definition Of Done

Docker MVP 已完成。后续工作只有在至少满足一项时才进入主链路：

1. 修复了已标注、可重复的失败案例；
2. 提高 Candidate Recall@50、Success@5、NDCG@5 或证据召回；
3. 显著降低延迟、Token、GitHub 调用或运维成本；
4. 在失败时有明确降级路径，并能通过离线回归验证。
