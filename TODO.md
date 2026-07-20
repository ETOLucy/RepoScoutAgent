# RepoScoutAgent Roadmap

[简体中文](TODO.md) | [English](TODO.en.md)

这里只记录尚未完成的工作。当前能力和使用方法见 [README.md](README.md)，公开性能工程历史见
[`docs/PERFORMANCE_HISTORY.md`](docs/PERFORMANCE_HISTORY.md)，性能验收计划见
[`docs/PERFORMANCE_MILESTONE.md`](docs/PERFORMANCE_MILESTONE.md)。

## Priority 1: Retrieval Evaluation

- [ ] 扩展到 30–50 条人工标注的真实自然语言需求。
- [ ] 在包含 25–60 个候选的真实案例上测 Candidate Recall@50 和仓库重排增益。
- [ ] 增加 Success@5、NDCG@5、硬约束违反率和 Unsupported Inference Rate。
- [ ] 分开标注需求解析错误、候选漏召回、证据漏召回和最终误排序。
- [ ] 增加否定语句、弃用说明和 roadmap 声明的回归案例。
- [ ] 证据不足时评测一次有预算的补充查询，只有稳定提升后才进入主流程。

## Priority 2: Performance Engineering v1

- [ ] 建立可复现的冷/热缓存 p50、p95 与 TTFC、TTFV 基线。
- [ ] 增加结构化 trace ID、外部调用数、Token、成本和缓存命中率。
- [ ] 流式返回逐仓库 verified 结果。
- [ ] 复用多轮会话的候选、文档与证据判断，并验证缓存失效正确性。
- [ ] 评测自适应 6/8/12/24 分析预算的质量与延迟 Pareto。
- [ ] 实验每批 2–3 个仓库的 LLM 结构化判断。

## Priority 3: Maintainability

- [ ] 将 GitHub 搜索、文档读取和 LLM 判断的运行配置集中为类型化 Settings。
- [ ] 为节点输入输出增加更精确的 TypedDict，逐步减少 `dict[str, Any]`。
- [ ] 当节点模块再次出现多职责增长时，按 requirement、discovery、assessment 边界拆分，
      不引入只做转发的空壳模块。

## Definition Of Done

新能力只有满足以下条件才进入主链路：

1. 修复可重复的标注失败，或显著改善质量、延迟、成本；
2. 失败与降级状态对用户可见；
3. 不突破 L2 静态验证边界；
4. Ruff、mypy、pytest、覆盖率门槛和 Docker 构建保持通过；
5. 性能变更追加到公开性能工程档案，不覆盖旧基线。
