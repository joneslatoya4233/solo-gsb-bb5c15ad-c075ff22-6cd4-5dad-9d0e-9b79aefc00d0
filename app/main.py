"""FastAPI 入口：批次管理、审查分析、场景保存/恢复、结果导出。"""

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import (FileResponse, PlainTextResponse, Response)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import db
from .analysis import run_review
from .rules import LEVEL_LABELS, RULES, TAG_LABELS

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="化学废液混配审查系统", version="1.0.0")


@app.on_event("startup")
def startup():
    db.init_db()


# ---------- 请求模型 ----------

class BatchIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    volume: float = Field(default=0, ge=0, le=1_000_000, description="体积(L)")
    ph: float = Field(default=7.0, ge=0, le=14)
    oxidizing: bool = False
    volatile: bool = False
    tags: list[str] = []

    @field_validator("tags")
    @classmethod
    def _check_tags(cls, tags):
        unknown = [t for t in tags if t not in TAG_LABELS]
        if unknown:
            raise ValueError(f"未知标签: {unknown}")
        return sorted(set(tags))


class ScenarioIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


# ---------- 批次 ----------

@app.get("/api/batches")
def api_list_batches():
    return db.list_batches()


@app.post("/api/batches", status_code=201)
def api_create_batch(batch: BatchIn):
    return db.create_batch(batch.model_dump())


@app.delete("/api/batches/{batch_id}")
def api_delete_batch(batch_id: int):
    if not db.delete_batch(batch_id):
        raise HTTPException(404, "批次不存在")
    return {"ok": True}


@app.delete("/api/batches")
def api_clear_batches():
    db.clear_batches()
    return {"ok": True}


# ---------- 审查 ----------

def _current_review():
    return run_review(db.list_batches())


@app.post("/api/review")
def api_review():
    return _current_review()


@app.get("/api/rules")
def api_rules():
    return {"rules": [{**r, "level_label": LEVEL_LABELS[r["level"]]} for r in RULES],
            "tags": TAG_LABELS}


# ---------- 场景 ----------

@app.post("/api/scenarios", status_code=201)
def api_save_scenario(scenario: ScenarioIn):
    payload = {
        "batches": db.list_batches(),
        "review": _current_review(),
        "saved_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }
    return db.save_scenario(scenario.name, payload)


@app.get("/api/scenarios")
def api_list_scenarios():
    return db.list_scenarios()


@app.get("/api/scenarios/{scenario_id}")
def api_get_scenario(scenario_id: int):
    item = db.get_scenario(scenario_id)
    if not item:
        raise HTTPException(404, "场景不存在")
    return item


@app.post("/api/scenarios/{scenario_id}/restore")
def api_restore_scenario(scenario_id: int):
    item = db.get_scenario(scenario_id)
    if not item:
        raise HTTPException(404, "场景不存在")
    db.replace_batches(item["payload"].get("batches", []))
    return {"ok": True, "restored": item["batch_count"]}


@app.delete("/api/scenarios/{scenario_id}")
def api_delete_scenario(scenario_id: int):
    if not db.delete_scenario(scenario_id):
        raise HTTPException(404, "场景不存在")
    return {"ok": True}


# ---------- 导出 ----------

@app.get("/api/export")
def api_export(fmt: str = Query("json", pattern="^(json|csv|md)$")):
    batches = db.list_batches()
    review = run_review(batches)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if fmt == "json":
        content = json.dumps({"batches": batches, "review": review},
                             ensure_ascii=False, indent=2)
        return Response(
            content, media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="review_{stamp}.json"'})
    if fmt == "csv":
        return _export_csv(batches, review, stamp)
    return _export_md(batches, review, stamp)


def _container_of(review):
    mapping = {}
    for c in review["containers"]:
        for m in c["members"]:
            mapping[m["id"]] = c["name"]
    return mapping


def _export_csv(batches, review, stamp):
    mapping = _container_of(review)
    buf = io.StringIO()
    buf.write("﻿")  # BOM，便于 Excel 识别 UTF-8
    w = csv.writer(buf)
    w.writerow(["批次ID", "名称", "体积(L)", "pH", "氧化性", "挥发性", "标签", "分配容器"])
    for b in batches:
        w.writerow([b["id"], b["name"], b["volume"], b["ph"],
                    "是" if b["oxidizing"] else "否",
                    "是" if b["volatile"] else "否",
                    "|".join(b["tags"]), mapping.get(b["id"], "")])
    w.writerow([])
    w.writerow(["冲突批次A", "冲突批次B", "规则", "危险", "等级", "说明"])
    for c in review["conflicts"]:
        w.writerow([c["a_name"], c["b_name"], c["rule_id"],
                    c["hazard"], c["level_label"], c["desc"]])
    return PlainTextResponse(
        buf.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="review_{stamp}.csv"'})


def _export_md(batches, review, stamp):
    s = review["summary"]
    lines = [
        "# 化学废液混配审查报告",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 批次数：{s['batch_count']}　直接冲突：{s['conflict_count']}　"
        f"自反应风险：{s['self_reactive_count']}",
        f"- 需要容器：{s['container_count']}　传递冲突链：{s['transitive_count']}　"
        f"最高危险等级：{s['max_level_label']}",
        f"- 结论：**{'✅ 全部兼容' if s['safe'] else '⚠️ 存在禁配冲突，须分组存放'}**",
        "",
        "## 容器分组",
    ]
    for c in review["containers"]:
        lines.append(f"\n### {c['name']}（{c['member_count']} 批，共 {c['total_volume']} L）")
        for m in c["members"]:
            lines.append(
                f"- {m['name']}：{m['volume']} L，pH {m['ph']}，"
                f"类别：{'、'.join(m['category_labels']) or '无'}")
    if review["conflicts"]:
        lines += ["", "## 直接冲突"]
        for c in review["conflicts"]:
            lines.append(f"- [{c['level_label']}] {c['a_name']} × {c['b_name']}："
                         f"{c['hazard']}（{c['rule_id']}）— {c['desc']}")
    if review["self_reactive"]:
        lines += ["", "## 自反应风险"]
        for c in review["self_reactive"]:
            lines.append(f"- [{c['level_label']}] {c['name']}："
                         f"{c['hazard']}（{c['rule_id']}）— {c['desc']}")
    if review["transitive"]:
        lines += ["", "## 传递冲突链"]
        for t in review["transitive"]:
            lines.append(f"- {' → '.join(t['names'])}（{t['hops']} 级传递）")
    mr = review["minimal_removal"]
    if mr["ids"]:
        lines += ["", "## 最小冲突批次",
                  f"移除 **{'、'.join(mr['names'])}** 后，其余批次两两兼容"
                  f"（{'精确' if mr['exact'] else '近似'}最小集合）。"]
    content = "\n".join(lines) + "\n"
    return PlainTextResponse(
        content, media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="review_{stamp}.md"'})


# ---------- 前端静态资源 ----------

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
