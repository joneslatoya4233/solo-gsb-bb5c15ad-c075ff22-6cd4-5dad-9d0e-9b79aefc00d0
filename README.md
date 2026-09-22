# 化学废液混配审查系统

基于 **FastAPI + SQLite + 原生前端** 的实验室化学废液混配安全审查应用。
录入带 pH、氧化性、挥发性与禁配标签的废液批次后，系统依据内置反应禁配规则
自动完成冲突检测、安全容器分组、传递冲突分析，并指出最小冲突批次集；
审查现场可按场景保存、恢复与导出。

## 快速开始（一条命令）

```bash
docker compose up --build
```

启动后访问：**http://localhost:8000**

- 前端页面：`http://localhost:8000/`
- 交互式 API 文档（Swagger UI）：`http://localhost:8000/docs`
- 数据通过命名卷 `waste-data` 持久化，容器重建不丢失

### 本地开发（不用 Docker）

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## 功能

| 模块 | 说明 |
| --- | --- |
| 批次录入 | 名称、体积、pH、氧化性、挥发性、13 种内置禁配标签 |
| 禁配审查 | 9 条内置反应规则两两配对检测，输出冲突对、触发规则与严重等级 |
| 容器分组 | 冲突图贪心着色，保证同一容器内任意两批次均不禁配，并给出存放注意事项 |
| 传递冲突 | 冲突图连通分量即传递冲突簇；簇内无直接冲突的批次对给出最短传递链（A→B→C） |
| 最小冲突批次 | 冲突图最小点覆盖（分支限界精确求解）：移除这些批次即可消除全部冲突 |
| 场景管理 | 当前工作区（批次+审查结果）按名保存/覆盖、恢复、删除、导出 JSON |

## 内置禁配规则

| 编号 | 规则 | 等级 |
| --- | --- | --- |
| R1 | 强酸（pH≤4.5）遇强碱（pH≥9.5）剧烈中和放热 | 高 |
| R2 | 氧化剂遇还原剂/有机溶剂，起火爆炸风险 | 高 |
| R3 | 氰化物遇酸释放剧毒 HCN | 极高 |
| R4 | 硫化物遇酸释放剧毒 H2S | 极高 |
| R5 | 次氯酸盐遇酸释放 Cl2 | 高 |
| R6 | 次氯酸盐遇氨/胺生成氯胺毒气 | 高 |
| R7 | 挥发性废液遇氧化剂形成可燃爆气氛 | 中 |
| R8 | 叠氮化物遇重金属生成爆炸性叠氮盐 | 极高 |
| R9 | 过氧化物遇酸/还原剂剧烈分解 | 高 |

> 规则仅供辅助审查，实际处置请遵循当地法规与各化学品 SDS。

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/meta` | 内置标签与规则清单 |
| GET/POST | `/api/batches` | 批次列表 / 新建批次 |
| DELETE | `/api/batches/{id}` | 删除批次 |
| POST | `/api/batches/clear` | 清空工作区 |
| GET | `/api/review` | 对当前批次运行审查 |
| GET/POST | `/api/scenarios` | 场景列表 / 保存当前为场景（同名覆盖） |
| GET/DELETE | `/api/scenarios/{id}` | 场景详情 / 删除 |
| POST | `/api/scenarios/{id}/restore` | 恢复场景到工作区 |
| GET | `/api/scenarios/{id}/export` | 导出场景 JSON（含审查结果） |

## 项目结构

```
├── app/
│   ├── main.py        # FastAPI 路由与审查编排
│   ├── rules.py       # 内置反应禁配规则引擎
│   ├── grouping.py    # 图着色分组 / 传递冲突簇 / 最小点覆盖
│   ├── database.py    # SQLite 数据访问（批次、场景）
│   └── static/        # 原生前端（index.html / app.js / style.css）
├── data/              # SQLite 数据库（运行时生成）
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DB_PATH` | `./data/app.db`（容器内 `/app/data/app.db`） | SQLite 数据库文件路径 |
