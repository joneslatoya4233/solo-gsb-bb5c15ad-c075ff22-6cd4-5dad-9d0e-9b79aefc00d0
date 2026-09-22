/* 化学废液混配审查 —— 原生 JS 前端 */

const $ = (id) => document.getElementById(id);
let TAGS = {};

const DEMO_BATCHES = [
  { name: "含氰电镀废液", volume: 50, ph: 9, oxidizing: false, volatile: false, tags: ["cyanide"] },
  { name: "盐酸清洗废液", volume: 30, ph: 1.5, oxidizing: false, volatile: false, tags: [] },
  { name: "次氯酸钠消毒废液", volume: 25, ph: 11, oxidizing: false, volatile: false, tags: ["hypochlorite"] },
  { name: "含硫废碱液", volume: 20, ph: 8, oxidizing: false, volatile: false, tags: ["sulfide"] },
  { name: "重铬酸钾氧化废液", volume: 15, ph: 3, oxidizing: true, volatile: false, tags: ["heavy_metal"] },
  { name: "废丙酮", volume: 40, ph: 7, oxidizing: false, volatile: true, tags: ["organic", "flammable"] },
  { name: "氨水洗废液", volume: 20, ph: 11.5, oxidizing: false, volatile: true, tags: ["ammonia"] },
  { name: "硝酸废液", volume: 18, ph: 1, oxidizing: true, volatile: false, tags: ["nitrate"] },
  { name: "废氢氧化钠溶液", volume: 25, ph: 13, oxidizing: false, volatile: false, tags: [] },
  { name: "废乙醇", volume: 35, ph: 7, oxidizing: false, volatile: true, tags: ["organic", "flammable"] },
];

async function api(url, opts) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || res.statusText);
  }
  return res.json();
}

const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const levelClass = (lv) => `<span class="lv lv-${lv}">${{
  critical: "极危", high: "高危", medium: "中危", low: "低危" }[lv]}</span>`;

/* ---------- 批次 ---------- */

async function loadBatches() {
  const batches = await api("/api/batches");
  $("batch-count").textContent = batches.length;
  $("batch-list").innerHTML = batches.length
    ? batches.map(renderBatchItem).join("")
    : '<li><span class="hint">暂无批次</span></li>';
}

function renderBatchItem(b) {
  const chips = [
    b.oxidizing ? '<span class="chip ox">氧化性</span>' : "",
    b.volatile ? '<span class="chip vol">挥发性</span>' : "",
    ...b.tags.map((t) => `<span class="chip">${esc(TAGS[t] || t)}</span>`),
  ].join("");
  return `<li>
    <div><strong>${esc(b.name)}</strong>
      <div class="meta">${b.volume} L · pH ${b.ph} ${chips}</div>
    </div>
    <button onclick="deleteBatch(${b.id})">删除</button>
  </li>`;
}

async function deleteBatch(id) {
  await api(`/api/batches/${id}`, { method: "DELETE" });
  await loadBatches();
}
window.deleteBatch = deleteBatch;

$("batch-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = {
    name: $("f-name").value.trim(),
    volume: parseFloat($("f-volume").value) || 0,
    ph: parseFloat($("f-ph").value),
    oxidizing: $("f-oxidizing").checked,
    volatile: $("f-volatile").checked,
    tags: [...document.querySelectorAll('#tag-box input:checked')].map((i) => i.value),
  };
  try {
    await api("/api/batches", { method: "POST", body: JSON.stringify(body) });
    $("f-name").value = "";
    await loadBatches();
  } catch (err) {
    alert("添加失败：" + err.message);
  }
});

$("btn-clear").addEventListener("click", async () => {
  if (!confirm("确定清空全部批次？")) return;
  await api("/api/batches", { method: "DELETE" });
  await loadBatches();
});

$("btn-demo").addEventListener("click", async () => {
  await api("/api/batches", { method: "DELETE" });
  for (const b of DEMO_BATCHES) {
    await api("/api/batches", { method: "POST", body: JSON.stringify(b) });
  }
  await loadBatches();
  await runReview();
});

/* ---------- 审查 ---------- */

$("btn-review").addEventListener("click", runReview);

async function runReview() {
  try {
    const r = await api("/api/review", { method: "POST" });
    renderReview(r);
  } catch (err) {
    alert("审查失败：" + err.message);
  }
}

function renderReview(r) {
  const s = r.summary;
  let html = `<div class="summary-box ${s.safe ? "safe" : "unsafe"}">
    <h4>${s.safe ? "✅ 全部批次兼容，可集中收集" : "⚠️ 存在禁配冲突，必须分组隔离"}（最高等级：${s.max_level_label}）</h4>
    <div class="summary-grid">
      <span>批次：<strong>${s.batch_count}</strong></span>
      <span>直接冲突：<strong>${s.conflict_count}</strong></span>
      <span>自反应风险：<strong>${s.self_reactive_count}</strong></span>
      <span>安全容器数：<strong>${s.container_count}</strong></span>
      <span>传递冲突链：<strong>${s.transitive_count}</strong></span>
    </div></div>`;

  html += `<h3>安全容器分组（容器内两两无直接冲突）</h3><div class="containers">`;
  for (const c of r.containers) {
    html += `<div class="container-card">
      <h5>🛢️ ${c.name} <span class="cap">(${c.member_count} 批 / ${c.total_volume} L)</span></h5>
      <ul>${c.members.map((m) => `<li>${esc(m.name)}
        <div class="cap">${m.volume} L，pH ${m.ph}${m.category_labels.length ? "：" + m.category_labels.map(esc).join("、") : ""}</div></li>`).join("")}</ul>
    </div>`;
  }
  html += "</div>";

  if (r.conflicts.length) {
    html += `<h3>直接禁配冲突（${r.conflicts.length}）</h3>
      <table><thead><tr><th>等级</th><th>批次 A</th><th>批次 B</th><th>危险类型</th><th>说明</th><th>规则</th></tr></thead><tbody>
      ${r.conflicts.map((c) => `<tr><td>${levelClass(c.level)}</td>
        <td>${esc(c.a_name)}</td><td>${esc(c.b_name)}</td>
        <td>${esc(c.hazard)}</td><td>${esc(c.desc)}</td><td>${c.rule_id}</td></tr>`).join("")}
      </tbody></table>`;
  }

  if (r.self_reactive.length) {
    html += `<h3>单批次自反应风险（${r.self_reactive.length}）</h3>
      <table><thead><tr><th>等级</th><th>批次</th><th>危险类型</th><th>说明</th><th>规则</th></tr></thead><tbody>
      ${r.self_reactive.map((c) => `<tr><td>${levelClass(c.level)}</td>
        <td>${esc(c.name)}</td><td>${esc(c.hazard)}</td><td>${esc(c.desc)}</td><td>${c.rule_id}</td></tr>`).join("")}
      </tbody></table>`;
  }

  if (r.transitive.length) {
    html += `<h3>传递冲突链（${r.transitive.length}，展示前 ${Math.min(r.transitive.length, 60)} 条）</h3>
      <p class="hint">以下批次对无直接反应，却经中间批次形成风险链——中间批次被移除或隔离后风险即解除。</p>
      <table><thead><tr><th>传递层级</th><th>冲突路径</th></tr></thead><tbody>
      ${r.transitive.map((t) => `<tr><td>${t.hops} 级</td>
        <td class="chain">${t.names.map(esc).join(" → ")}</td></tr>`).join("")}
      </tbody></table>`;
  }

  const mr = r.minimal_removal;
  if (mr.ids.length) {
    html += `<div class="minimal-box"><h3 style="margin-top:0">🎯 最小冲突批次集合（${mr.ids.length} 个，${mr.exact ? "精确最小" : "近似最小"}）</h3>
      <p>只需优先隔离/移除以下批次，其余全部批次即可两两兼容：<br>
      <strong>${mr.names.map(esc).join("、")}</strong></p></div>`;
  }

  if (r.conflict_degree.some((d) => d.conflict_count > 0)) {
    const rows = r.conflict_degree.filter((d) => d.conflict_count > 0)
      .map((d) => `<tr><td>${esc(d.name)}</td><td>${d.conflict_count}</td></tr>`).join("");
    html += `<h3>各批次冲突度</h3>
      <table><thead><tr><th>批次</th><th>直接冲突数</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  $("review-result").innerHTML = html;
}

/* ---------- 场景 ---------- */

$("btn-save-scenario").addEventListener("click", async () => {
  const name = $("scenario-name").value.trim();
  if (!name) return alert("请输入场景名称");
  await api("/api/scenarios", { method: "POST", body: JSON.stringify({ name }) });
  $("scenario-name").value = "";
  await loadScenarios();
});

async function loadScenarios() {
  const list = await api("/api/scenarios");
  $("scenario-list").innerHTML = list.length
    ? list.map((s) => `<li>
        <div><strong>${esc(s.name)}</strong>
          <div class="smeta">${s.batch_count} 批 · ${s.created_at.replace("T", " ").replace(/\+.*/, "")}</div></div>
        <div class="acts">
          <button onclick="restoreScenario(${s.id})">恢复</button>
          <button class="danger" onclick="deleteScenario(${s.id})">删除</button>
        </div></li>`).join("")
    : '<li><span class="hint">尚无存档</span></li>';
}

async function restoreScenario(id) {
  const { restored } = await api(`/api/scenarios/${id}/restore`, { method: "POST" });
  await loadBatches();
  await runReview();
  alert(`已恢复 ${restored} 个批次`);
}
window.restoreScenario = restoreScenario;

async function deleteScenario(id) {
  if (!confirm("确定删除该场景存档？")) return;
  await api(`/api/scenarios/${id}`, { method: "DELETE" });
  await loadScenarios();
}
window.deleteScenario = deleteScenario;

/* ---------- 导出 ---------- */

for (const [btn, fmt] of [["btn-export-json", "json"], ["btn-export-csv", "csv"], ["btn-export-md", "md"]]) {
  $(btn).addEventListener("click", () => { window.location.href = `/api/export?fmt=${fmt}`; });
}

/* ---------- 初始化 ---------- */

(async function init() {
  const data = await api("/api/rules");
  TAGS = data.tags;
  $("rule-count").textContent = data.rules.length;
  $("tag-box").innerHTML = Object.entries(TAGS)
    .map(([v, label]) => `<label><input type="checkbox" value="${v}"> ${label}</label>`).join("");
  await loadBatches();
  await loadScenarios();
})();
