# 化学废液混配审查系统

基于 **FastAPI + SQLite + 原生 HTML/JS** 的单页 Web 应用。录入带 pH、氧化性、挥发性及禁配标签的废液批次后，系统依据内置的 **20 条反应禁配规则** 自动将批次分组到安全容器，检测传递冲突链并指出最小冲突批次集合；支持按场景保存/恢复审查结果，并导出 JSON / CSV / Markdown 报告。

## 功能特性

- **批次管理**：名称、体积、pH、氧化性、挥发性 + 12 类禁配标签（氰化物、硫化物、次氯酸盐、过氧化物、氯酸盐……）
- **禁配规则引擎**：由理化性质推导类别，两两匹配规则（酸碱中和、酸 + 氰化物 → HCN、氧化剂 + 有机物 → 燃爆等），并能检出**单批次自反应风险**
- **安全容器分组**：冲突图贪心着色，容器内批次两两兼容，给出每组的批次与总容积
- **传递冲突检测**：对同一连通分量内无直接反应的批次对，输出最短冲突路径（A→B→C），定位"中间风险桥"
- **最小冲突批次**：分支限界求最小点覆盖（小图精确解），指出最少需隔离/移除哪些批次即可让其余全部兼容
- **场景存档**：保存当前批次 + 审查结果，随时一键恢复；持久化于 SQLite
- **结果导出**：`.json`（完整数据）、`.csv`（含冲突区，Excel 可直接打开）、`.md`（可读审查报告）

## 一条命令启动

```bash
docker compose up --build
```

启动后访问：

> **http://localhost:8000**

（容器端口 8000，映射到宿主机同端口；SQLite 数据保存在 Docker 卷 `waste-data` 中，重建容器不丢失。）

停止：`Ctrl+C`（后台运行则 `docker compose down`）。

## 本地开发运行（无需 Docker）

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

数据库默认位于 `./data/app.db`，可用环境变量 `APP_DB` 覆盖。

## 快速体验

1. 打开首页，点击 **「载入示例」**，自动录入 10 个典型废液批次（含氰废液、盐酸、次氯酸钠、废丙酮等）并运行审查；
2. 查看容器分组、直接冲突表、传递冲突链与最小冲突批次；
3. 在「场景存档」输入名称保存，之后可一键恢复；
4. 点击「导出报告」下载 Markdown 审查报告。

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/batches` | 批次列表 |
| POST | `/api/batches` | 新增批次（pH 0–14、体积≥0、标签合法性校验） |
| DELETE | `/api/batches/{id}` | 删除批次 |
| DELETE | `/api/batches` | 清空批次 |
| POST | `/api/review` | 运行审查，返回分组/冲突/传递链/最小冲突集合 |
| GET | `/api/rules` | 内置规则与可选标签 |
| POST | `/api/scenarios` | 保存场景 `{"name": "..."}` |
| GET | `/api/scenarios` | 场景列表 |
| GET | `/api/scenarios/{id}` | 场景详情（含批次快照与审查结果） |
| POST | `/api/scenarios/{id}/restore` | 恢复场景到当前批次区 |
| DELETE | `/api/scenarios/{id}` | 删除场景 |
| GET | `/api/export?fmt=json\|csv\|md` | 导出审查结果 |
| GET | `/` `/static/*` | 前端页面与静态资源 |

## 禁配规则摘要（R01–R20）

- 酸 × 碱（中和放热）；酸 × 氰化物 / 硫化物 / 次氯酸盐（HCN / H2S / Cl2 毒气）
- 次氯酸盐 × 氨（氯胺毒气）；硝酸盐 × 酸（NOx）；氯酸盐 × 酸/有机物（爆炸）
- 氧化剂 × 有机物 / 易燃物 / 氰化物 / 硫化物 / 挥发性蒸气（火灾爆炸）
- 过氧化物 × 有机物（分解爆炸）、× 重金属（催化分解）
- 活泼金属 × 酸/碱/卤代烃（放氢或剧烈反应）；氨 × 重金属（络合放热）等

规则集中在 `app/rules.py`，新增规则只需在 `RULES` 列表追加一条类别对。

## 目录结构

```
.
├── app/
│   ├── main.py          # FastAPI 路由：批次/审查/场景/导出/静态页
│   ├── analysis.py      # 冲突图、容器着色、传递冲突、最小点覆盖
│   ├── rules.py         # 类别推导 + 禁配规则表
│   ├── db.py            # SQLite 持久化（批次、场景）
│   └── static/          # 原生前端 index.html / app.js / style.css
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## 说明

本工具用于实验室废液收集的**管理辅助与风险提示**，规则为常见禁配关系的简化建模，不能替代危废处置专业规范与现场评估。
