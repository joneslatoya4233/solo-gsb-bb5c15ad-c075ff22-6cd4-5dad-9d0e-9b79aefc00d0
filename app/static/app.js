/* 化学废液混配审查系统 —— 前端逻辑（原生 JS，无框架依赖） */

const $ = (sel) => document.querySelector(sel);
let batchesCache = [];
let lastReview = null;

const SAMPLES = [
  { name: "含氰电镀废液", volume_l: 20, ph: 10.5, oxidizing: false, volatile: false, tags: ["氰化物", "碱性", "重金属"] },
  { name: "废盐酸", volume_l: 30, ph: 1.5, oxidizing: false, volatile: true, tags: ["酸性"] },
  { name: "高锰酸钾废液", volume_l: 10, ph: 7.0, oxidizing: true, volatile: false, tags: ["氧化剂"] },
  { name: "废丙酮", volume_l: 25, ph: 7.0, oxidizing: false, volatile: true, tags: ["有机溶剂", "还原剂"] },
  { name: "次氯酸钠废液", volume_l: 15, ph: 11.0, oxidizing: true, volatile: false, tags: ["次氯酸盐", "碱性"] },
  { name: "含氨废水", volume_l: 40, ph: 10.0, oxidizing: false, volatile: true, tags: ["氨/胺", "碱性"] },
  { name: "硫化钠废液", volume_l: 12, ph: 12.0, oxidizing: false, volatile: false, tags: ["硫化物", "碱性", "还原剂"] },
  { name: "废硝酸", volume_l: 8, ph: 1.0, oxidizing: true, volatile: true, tags: ["酸性", "氧化剂"] },
];

/* ---------- 基础工具 ---------- */

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (res.status === 204) return null;
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch { /* 忽略解析失败 */ }
    throw new Error(msg);
  }
  return res.json();
}

let toastTimer = null;
function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "show" + (isError ? " error" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = ""; }, 2600);
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

const nameOf = (id) => (batchesCache.find((b) => b.id === id) || {}).name || `#${id}`;

/* ---------- 元数据：标签与规则 ---------- */

async function loadMeta() {
  const meta = await api("/api/meta");
  $("#tag-checks").innerHTML = meta.tags.map((t) => `
    <label class="check"><input type="checkbox" name="tag" value="${esc(t)}"> ${esc(t)}</label>
  `).join("");
  $("#rules-table tbody").innerHTML = meta.rules.map((r) => `
    <tr>
      <td>${esc(r.id)}</td>
      <td>${esc(r.name)}</td>
      <td><span class="badge sev sev-${esc(r.severity)}">${esc(r.severity)}</span></td>
      <td style="white-space:normal">${esc(r.description)}</td>
    </tr>
  `).join("");
}

/* ---------- 批次 ---------- */

async function loadBatches() {
  batchesCache = await api("/api/batches");
  renderBatches();
}

function renderBatches() {
  const minimal = new Set(lastReview ? lastReview.minimal_conflict_batch_ids : []);
  $("#batch-count").textContent = batchesCache.length ? `${batchesCache.length} 个` : "";
  $("#batch-empty").style.display = batchesCache.length ? "none" : "";
  $("#batch-table tbody").innerHTML = batchesCache.map((b) => `
    <tr class="${minimal.has(b.id) ? "minimal" : ""}">
      <td>${b.id}</td>
      <td>${esc(b.name)}${minimal.has(b.id) ? ' <span class="badge minimal">最小冲突集</span>' : ""}</td>
      <td>${b.volume_l}</td>
      <td>${b.ph}</td>
      <td>${b.oxidizing ? "✔" : ""}</td>
      <td>${b.volatile ? "✔" : ""}</td>
      <td>${b.tags.map((t) => `<span class="badge">${esc(t)}</span>`).join("")}</td>
      <td><button class="danger small" data-del="${b.id}">删除</button></td>
    </tr>
  `).join("");
}

async function addBatch(e) {
  e.preventDefault();
  const body = {
    name: $("#f-name").value.trim(),
    volume_l: parseFloat($("#f-volume").value) || 0,
    ph: parseFloat($("#f-ph").value),
    oxidizing: $("#f-oxidizing").checked,
    volatile: $("#f-volatile").checked,
    tags: [...document.querySelectorAll('input[name="tag"]:checked')].map((c) => c.value),
  };
  try {
    await api("/api/batches", { method: "POST", body: JSON.stringify(body) });
    $("#batch-form").reset();
    $("#f-volume").value = 10;
    $("#f-ph").value = 7;
    toast(`已添加批次「${body.name}」`);
    await refresh();
  } catch (err) {
    toast(`添加失败：${err.message}`, true);
  }
}

async function refresh() {
  await loadBatches();
  if (batchesCache.length) await runReview(true);
  else { lastReview = null; $("#review-result").innerHTML = '<p class="empty">尚未运行审查。</p>'; }
}

/* ---------- 审查 ---------- */

async function runReview(silent = false) {
  try {
    lastReview = await api("/api/review");
    renderReview(lastReview);
    renderBatches(); // 重新渲染以标出最小冲突集
    if (!silent) toast("审查完成");
  } catch (err) {
    toast(`审查失败：${err.message}`, true);
  }
}

function renderReview(r) {
  const el = $("#review-result");
  if (!r.batch_count) {
    el.innerHTML = '<p class="empty">当前没有批次，无法审查。</p>';
    return;
  }

  const banner = r.ok
    ? `<div class="banner ok">✔ 未发现禁配冲突，${r.batch_count} 个批次可分入 ${r.container_count} 个容器。</div>`
    : `<div class="banner bad">⚠ 检出 ${r.conflicts.length} 组直接冲突，已按禁配规则分为 ${r.container_count} 个安全容器。</div>`;

  const minimalHtml = r.minimal_conflict_batch_ids.length
    ? `<div class="banner bad">最小冲突批次集（移除后可消除全部 ${r.conflicts.length} 组冲突）：
        ${r.minimal_conflict_batch_ids.map((id) => `<span class="badge minimal">${esc(nameOf(id))}</span>`).join("")}
      </div>`
    : "";

  const containersHtml = `
    <h3>安全容器分组（${r.container_count} 个）</h3>
    <div class="container-grid">
      ${r.containers.map((c) => `
        <div class="container-card">
          <h4>容器 ${c.id} <span class="vol">共 ${c.total_volume_l} L</span></h4>
          <ul>${c.batches.map((b) => `<li>${esc(b.name)}（${b.volume_l} L, pH ${b.ph}）</li>`).join("")}</ul>
          ${c.warnings.length ? `<ul class="warn-list">${c.warnings.map((w) => `<li><span class="badge warn">注意</span> ${esc(w)}</li>`).join("")}</ul>` : ""}
        </div>
      `).join("")}
    </div>`;

  const conflictsHtml = r.conflicts.length ? `
    <h3>直接冲突（${r.conflicts.length} 组）</h3>
    <div class="table-wrap"><table>
      <thead><tr><th>批次 A</th><th>批次 B</th><th>触发规则</th><th>等级</th><th>说明</th></tr></thead>
      <tbody>
        ${r.conflicts.map((c) => `
          <tr>
            <td>${esc(c.a_name)}</td>
            <td>${esc(c.b_name)}</td>
            <td>${c.rules.map((x) => `<span class="badge">${esc(x.id)} ${esc(x.name)}</span>`).join("")}</td>
            <td><span class="badge sev sev-${esc(c.severity)}">${esc(c.severity)}</span></td>
            <td style="white-space:normal">${c.rules.map((x) => esc(x.description)).join("<br>")}</td>
          </tr>
        `).join("")}
      </tbody>
    </table></div>` : "";

  const clustersHtml = r.clusters.length ? `
    <h3>传递冲突簇（${r.clusters.length} 个）</h3>
    ${r.clusters.map((cl, i) => `
      <div class="container-card">
        <h4>冲突簇 ${i + 1}：${cl.batch_ids.map((id) => `<span class="badge">${esc(nameOf(id))}</span>`).join("")}</h4>
        ${cl.indirect_chains.length
          ? cl.indirect_chains.map((chain) => `
            <p class="chain">↳ 间接传递：${chain.map((id) => `<b>${esc(nameOf(id))}</b>`).join('<span class="arrow">→</span>')}</p>
          `).join("")
          : '<p class="chain">簇内批次两两直接冲突。</p>'}
      </div>
    `).join("")}` : "";

  el.innerHTML = banner + minimalHtml
    + `<div class="result-grid">${containersHtml}${conflictsHtml}${clustersHtml}</div>`;
}

function exportCurrentReview() {
  if (!lastReview) { toast("请先运行审查", true); return; }
  const blob = new Blob([JSON.stringify(lastReview, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `review-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ---------- 场景 ---------- */

async function loadScenarios() {
  const list = await api("/api/scenarios");
  $("#scenario-empty").style.display = list.length ? "none" : "";
  $("#scenario-list").innerHTML = list.map((s) => `
    <li>
      <span class="name">${esc(s.name)}</span>
      <span class="time">更新于 ${esc(s.updated_at)}</span>
      <button class="secondary small" data-restore="${s.id}">恢复</button>
      <button class="secondary small" data-export="${s.id}">导出</button>
      <button class="danger small" data-del-scenario="${s.id}">删除</button>
    </li>
  `).join("");
}

async function saveScenario() {
  const name = $("#scenario-name").value.trim();
  if (!name) { toast("请输入场景名称", true); return; }
  try {
    await api("/api/scenarios", { method: "POST", body: JSON.stringify({ name }) });
    $("#scenario-name").value = "";
    toast(`场景「${name}」已保存`);
    await loadScenarios();
  } catch (err) {
    toast(`保存失败：${err.message}`, true);
  }
}

async function restoreScenario(id) {
  try {
    const res = await api(`/api/scenarios/${id}/restore`, { method: "POST" });
    toast(`已恢复 ${res.restored} 个批次到工作区`);
    await refresh();
  } catch (err) {
    toast(`恢复失败：${err.message}`, true);
  }
}

/* ---------- 事件绑定与初始化 ---------- */

document.addEventListener("DOMContentLoaded", async () => {
  $("#batch-form").addEventListener("submit", addBatch);
  $("#btn-review").addEventListener("click", () => runReview());
  $("#btn-export-current").addEventListener("click", exportCurrentReview);
  $("#btn-save-scenario").addEventListener("click", saveScenario);

  $("#btn-samples").addEventListener("click", async () => {
    for (const s of SAMPLES) {
      await api("/api/batches", { method: "POST", body: JSON.stringify(s) });
    }
    toast("已载入示例批次");
    await refresh();
  });

  $("#btn-clear").addEventListener("click", async () => {
    if (!confirm("确定清空全部批次？")) return;
    await api("/api/batches/clear", { method: "POST" });
    toast("已清空");
    await refresh();
  });

  $("#batch-table").addEventListener("click", async (e) => {
    const id = e.target.dataset.del;
    if (!id) return;
    await api(`/api/batches/${id}`, { method: "DELETE" });
    await refresh();
  });

  $("#scenario-list").addEventListener("click", async (e) => {
    const { restore, export: exp, delScenario } = e.target.dataset;
    if (restore) await restoreScenario(restore);
    else if (exp) window.location = `/api/scenarios/${exp}/export`;
    else if (delScenario) {
      if (!confirm("确定删除该场景？")) return;
      await api(`/api/scenarios/${delScenario}`, { method: "DELETE" });
      await loadScenarios();
    }
  });

  await loadMeta();
  await loadBatches();
  await loadScenarios();
  if (batchesCache.length) await runReview(true);
});
