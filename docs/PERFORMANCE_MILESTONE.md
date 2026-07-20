# Performance Engineering v1

[简体中文](PERFORMANCE_MILESTONE.md) | [English](PERFORMANCE_MILESTONE.en.md)

## Goal

在不降低 Recall@analysis、Success@5、NDCG@5、L2 Precision 和 Citation Accuracy 的前提下，
降低当前 `100.6 秒` 单次真实观察的端到端延迟，并建立可复现的冷/热缓存 p50、p95 基线。

## Milestone Description

Reduce end-to-end search latency from the observed 100.6s baseline while preserving
Recall@analysis, Success@5, NDCG@5, L2 precision, and Citation Accuracy. Establish
reproducible cold/warm-cache p50/p95, TTFC/TTFV, call/token/cost traces, progressive
results, conversation reuse, and adaptive analysis budgets.

## Completed Foundation

- [x] `60→24→8` 候选漏斗和 8 路动态 worker
- [x] 单仓库超时隔离与显式降级
- [x] embedding 批处理、内容缓存和请求内失败熔断
- [x] embedding 跨请求 TTL 熔断
- [x] 节点耗时进入 API 与 SSE
- [x] 暂定候选和分析候选数提前展示

## Proposed GitHub Issues

1. **建立可复现的冷/热缓存 p50/p95 基准与调用追踪**  
   冻结查询计划、候选响应和文档 SHA；采集 TTFC、TTFV、节点耗时、调用数、Token、成本、缓存命中、429/5xx，并至少运行 10 次。
2. **流式返回逐仓库 verified 结果**  
   worker 完成一个仓库后立即发布带引用的验证结果，保持最终排序可更新，并清楚区分 provisional 与 verified。
3. **复用多轮会话的候选、文档与证据判断**  
   以需求契约、仓库 SHA 和模型版本作为缓存边界，评估命中率、失效正确性和延迟收益。
4. **评测自适应 6/8/12/24 分析预算**  
   按请求复杂度和候选分差选择预算，绘制延迟与 Recall@analysis、Success@5、NDCG@5 的 Pareto 曲线。
5. **实验每次 2–3 个仓库的小批量 LLM 判断**  
   对比单仓库调用的 p50/p95、Token、解析失败率和引用准确率；只有通过质量门槛才进入主链路。

## Exit Criteria

- 冷缓存和热缓存分别有至少 10 次可复现运行及 p50/p95。
- TTFC、TTFV、节点耗时、外部调用数、Token 和成本可追踪。
- `Citation Accuracy = 1.00`，`Recall@analysis >= 0.98`，L2 Precision 不低于当前固定集基线。
- Success@5 和 NDCG@5 无统计上稳定的下降。
- 性能结果追加到 `docs/PERFORMANCE_STAR.md`，保留全部旧基线和失败方案。

## GitHub Setup Note

该文件是可版本控制的 Milestone 定义。GitHub 网页中的 Milestone 需要仓库 `Issues: Read and write`
权限；获得该权限后，可在仓库的 Issues / Milestones 页面创建同名 Milestone，并将上述五项拆成 Issues 关联进去。
