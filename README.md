# Schema Recovery Agent

智能数据库 Schema 逆向工程 Agent — 无需外键约束，无需文档，通过多 Agent 协作自动还原数据库表间关系，每条关系附带可追溯的证据链。

## 核心能力

| 能力 | 说明 |
|------|------|
| 自动数据库扫描 | 连接目标数据库，自动发现所有表、视图、存储过程、触发器 |
| 多维度关系推理 | 列名分析 + 命名约定 + SQL JOIN 解析 + ORM 配置解析 → 加权融合 |
| 证据溯源 | 每条关系标注来源（哪条 SQL、哪个 ORM 配置），可人工复核 |
| 置信度分级 | 高置信度（≥0.7）/ 中置信度（0.4-0.7）/ 低置信度（<0.4） |
| 闭环监控 | 记录每次分析性能，追踪各证据源贡献率 |

## 架构

```
SurveyWorker (数据库初勘)
    ↓
ColumnWorker + NameWorker (列分析 + 命名分析)
    ↓
CodeWorker + ORMWorker (SQL代码解析 + ORM配置解析)
    ↓
MergeWorker (证据融合 → ER图)
```

## 快速开始

```bash
docker compose up -d
python scripts/init_db.py
curl -X POST http://localhost:8080/api/analyze
```

## 技术栈

Python FastAPI / MySQL 8.0 / SQLite / sqlparse / Docker
