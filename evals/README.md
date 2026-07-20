# 离线评测

[简体中文](README.md) | [English](README.en.md)

`baseline_cases.json` 包含 15 条人工标注的自然语言搜索案例。每条案例固定任务契约、
GitHub Search 仓库、Tree 路径、Contents 文本、模型判断、相关仓库及预期证据，因此可以
在不联网的情况下重复比较检索和证据逻辑。

运行全文文档基线：

```powershell
.\.venv\Scripts\python.exe -m evals.run_baseline
```

结果写入 `baseline_report.json`，包含质量、延迟、模型调用、GitHub 调用和估算 Token。
Token 使用确定性字符估算，只适合相对比较。模型供应商和价格可以配置，因此未提供版本化
价格时成本保持 `null`，不会套用虚构公开价格。

已知价格时可显式传入：

```powershell
.\.venv\Scripts\python.exe -m evals.run_baseline `
  --input-price-per-million 1.00 `
  --output-price-per-million 2.00
```

以上价格仅演示语法。固定集会保留已知失败案例，后续混合检索、重排和查询规划改动必须
对同一批 fixtures 报告改善与回退。

`evals/search_quality.py` 分别报告重排前候选召回、检查截断后的 Recall@24、NDCG@24、
从未召回的相关仓库，以及文档读取前被丢弃的相关仓库，避免最终推荐指标掩盖失败阶段。

运行 BM25 + 多查询稠密检索 + RRF + MMR：

```powershell
.\.venv\Scripts\python.exe -m evals.run_rag
```

结果写入 `rag_report.json`。离线回放使用确定性本地 embedding；生产环境使用
`OPENAI_EMBEDDING_MODEL`。`REPOSCOUT_RETRIEVAL_MODE=semantic` 只应用于纯稠密消融。

L2 静态证据评测：

```powershell
.\.venv\Scripts\python.exe -m evals.run_l2
```

Deep Code 与 L2 目标不同，后续需要独立评测整体职责摘要、入口召回、模块解释准确率、
源码引用准确率和不同仓库规模下的预算覆盖，不能复用 L2 的功能存在性指标。
