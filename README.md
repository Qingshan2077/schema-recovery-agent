# Schema Recovery Agent

一个用于老旧数据库关系逆向恢复的 Agent 项目。后端通过 MCP 工具扫描表、列、视图、存储过程和 MyBatis XML，再用多 Worker + LangGraph 编排生成 ER 关系、证据链和置信度。

## 目录结构

```text
backend/   FastAPI、LangGraph、Worker、MCP 工具、评测和监控
frontend/  React + Vite 可视化控制台
data/      模拟数据库、ORM XML、评测集
docs/      设计文档和开发方案
```

## 配置

运行配置放在根目录 `.env`，该文件不会提交到 Git。仓库提交 `.env.example` 作为模板。

首次运行：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

## 后端能力

- LangGraph 主编排，手写 Orchestrator 作为 fallback
- `/api/analyze` 一次性分析
- `/api/analyze/stream` NDJSON 流式节点进度
- 证据融合输出 `confidence_reason`、协同加成和冲突惩罚
- Monitor 记录 Worker 耗时、工具调用和证据源贡献
- Eval 计算 exact precision/recall、partial FK recall、目标表错误、关系类型错误和高置信度校准

## Docker 快速开始

```bash
docker compose up -d
curl -X POST http://localhost:8080/api/analyze
```

## 本地后端运行

```bash
uv sync
python -m backend.scripts.init_db
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

## 本地前端运行

```bash
cd frontend
npm install
npm run dev
```


