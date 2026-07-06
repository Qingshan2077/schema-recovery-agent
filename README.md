# Schema Recovery Agent

智能数据库 Schema 逆向工程 Agent — 连上无外键约束、无文档的老数据库，自动推理出完整的表间关系图，每一条关系附带证据链和置信度。

## 架构

6 个 Worker 流水线编排：

1. **SurveyWorker** — 扫描数据库全部对象（表/视图/存储过程/ORM 配置）
2. **ColumnWorker** — 逐表分析列名、类型、索引，推测潜在外键
3. **NameWorker** — 跨表分析命名模式，识别关联表
4. **CodeWorker** — 解析存储过程/视图中的 JOIN 语句（最高质量证据）
5. **ORMWorker** — 解析 MyBatis XML 中的关系定义
6. **MergeWorker** — 加权融合所有证据，输出 ER 图

## 六大考点

| 考点 | 体现 |
|------|------|
| 三路意图识别 | NameWorker 的关联表检测 / Router 的分发决策 |
| MCP 工具调用 | 15+ 工具，查询改写 + 结果重排 |
| 三级记忆 | L1 会话 / L2 跨分析 Schema / L3 全局设计模式 |
| 多 Agent 路由 | 4 阶段流水线，并行 + 串行混合调度 |
| Monitor 闭环 | 证据源贡献率跟踪 → 权重调整建议 |
| 端到端评测 | 30 表测试集，查全率/查准率/F1 + LLM-as-Judge |

## 快速开始

```bash
docker compose up -d
python scripts/init_db.py
# 启动后：
curl -X POST http://localhost:8080/api/analyze
```

## 开发文档

见 `docs/` 目录下的 5 份文档，按编号顺序喂给 GPT 生成代码。
