"""化学废液混配审查系统 —— FastAPI 入口。"""

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import database as db
from .grouping import assign_containers, conflict_clusters, minimum_conflict_set
from .rules import KNOWN_TAGS, RULES, find_conflicts

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="化学废液混配审查系统", version="1.0.0")


@app.on_event("startup")
def startup():
    db.init_db()


# ---------- 请求模型 ----------

class BatchIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    volume_l: float = Field(default=0.0, ge=0, le=1_000_000)
    ph: float = Field(default=7.0, ge=0, le=14)
    oxidizing: bool = False
    volatile: bool = False
    tags: list[str] = []

    def cleaned(self):
        tags = []
        for t in self.tags:
            t = str(t).strip()
            if t and t not in tags:
                tags.append(t)
        return {
            "name": self.name.strip(),
            "volume_l": self.volume_l,
            "ph": self.ph,
            "oxidizing": self.oxidizing,
            "volatile": self.volatile,
            "tags": tags[:20],
        }


class ScenarioIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


# ---------- 审查计算 ----------

def _container_warnings(members):
    warnings = []
    if any(b["volatile"] for b in members):
        warnings.append("含挥发性废液：使用带泄压的密闭容器，存放处保持通风")
    if any(b["oxidizing"] for b in members):
        warnings.append("含氧化性废液：远离还原剂、有机物与热源存放")
    if any(b["ph"] <= 4.5 for b in members):
        warnings.append("含强酸性废液：使用耐酸容器")
    if any(b["ph"] >= 9.5 for b in members):
        warnings.append("含强碱性废液：使用耐碱容器，避免玻璃塞粘结")
    total = sum(b["volume_l"] for b in members)
    if total > 50:
        warnings.append(f"总体积 {total:.1f} L 较大，建议分装并控制单容器液位")
    return warnings


def compute_review(batches):
    """对给定批次执行完整审查，返回分组、冲突、传递簇与最小冲突集。"""
    ids = [b["id"] for b in batches]
    conflicts = find_conflicts(batches)
    edges = [(c["a_id"], c["b_id"]) for c in conflicts]
    by_id = {b["id"]: b for b in batches}

    containers = []
    for idx, member_ids in enumerate(assign_containers(ids, edges), start=1):
        members = [by_id[i] for i in member_ids]
        containers.append({
            "id": idx,
            "batches": members,
            "total_volume_l": round(sum(b["volume_l"] for b in members), 3),
            "warnings": _container_warnings(members),
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batch_count": len(batches),
        "container_count": len(containers),
        "ok": not conflicts,
        "containers": containers,
        "conflicts": conflicts,
        "clusters": conflict_clusters(ids, edges),
        "minimal_conflict_batch_ids": minimum_conflict_set(ids, edges),
    }


# ---------- API：批次 ----------

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/meta")
def meta():
    """前端渲染所需的标签与规则清单。"""
    return {
        "tags": KNOWN_TAGS,
        "rules": [
            {"id": r["id"], "name": r["name"],
             "severity": r["severity"], "description": r["description"]}
            for r in RULES
        ],
    }


@app.get("/api/batches")
def list_batches():
    return db.list_batches()


@app.post("/api/batches", status_code=201)
def create_batch(batch: BatchIn):
    return db.create_batch(batch.cleaned())


@app.delete("/api/batches/{batch_id}", status_code=204)
def delete_batch(batch_id: int):
    if not db.delete_batch(batch_id):
        raise HTTPException(status_code=404, detail="批次不存在")


@app.post("/api/batches/clear", status_code=204)
def clear_batches():
    db.clear_batches()


# ---------- API：审查 ----------

@app.get("/api/review")
def review():
    return compute_review(db.list_batches())


# ---------- API：场景 ----------

@app.post("/api/scenarios", status_code=201)
def save_scenario(body: ScenarioIn):
    """把当前工作区批次与审查结果保存为命名场景（同名覆盖）。"""
    batches = db.list_batches()
    payload = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "batches": batches,
        "review": compute_review(batches),
    }
    return db.save_scenario(body.name.strip(), payload)


@app.get("/api/scenarios")
def list_scenarios():
    return db.list_scenarios()


@app.get("/api/scenarios/{scenario_id}")
def get_scenario(scenario_id: int):
    scenario = db.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="场景不存在")
    return scenario


@app.post("/api/scenarios/{scenario_id}/restore")
def restore_scenario(scenario_id: int):
    """恢复场景：用场景中的批次整体替换当前工作区。"""
    scenario = db.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="场景不存在")
    batches = db.replace_batches(scenario["payload"]["batches"])
    return {"restored": len(batches), "batches": batches}


@app.delete("/api/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: int):
    if not db.delete_scenario(scenario_id):
        raise HTTPException(status_code=404, detail="场景不存在")


@app.get("/api/scenarios/{scenario_id}/export")
def export_scenario(scenario_id: int):
    """导出场景（含批次与审查结果）为 JSON 文件。"""
    scenario = db.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="场景不存在")
    content = json.dumps(scenario, ensure_ascii=False, indent=2)
    filename = f"scenario-{scenario_id}.json"
    disposition = (
        f"attachment; filename=\"{filename}\";"
        f" filename*=UTF-8''{quote(scenario['name'])}.json"
    )
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": disposition},
    )


# ---------- 前端静态资源（最后挂载，避免覆盖 API 路由） ----------

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
