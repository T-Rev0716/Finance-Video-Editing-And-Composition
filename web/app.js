/* Video Prep Studio front end. Plain JavaScript, no build step. */
"use strict";

const app = document.getElementById("app");
const state = { data: null, selected: null, project: null, tab: "facts", verticalCharts: false, poll: null };

// ---------- helpers ----------
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (url) => (/^https?:\/\//i.test(url || "") ? url : "");
const link = (url, text) => (safeUrl(url) ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>` : esc(text));

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { message = (await response.json()).detail || message; } catch (_) { /* not JSON */ }
    throw new Error(message);
  }
  return response.json();
}
const postJson = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

function toast(message) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 2200);
}

async function copyText(text, what = "Copied") {
  try {
    await navigator.clipboard.writeText(text);
  } catch (_) {
    const area = document.createElement("textarea");
    area.value = text;
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  toast(what);
}

// Text that may contain [CHART 2] style markers.
const withMarkers = (text) => esc(text).replace(/\[(CHART|HEADLINE|B-ROLL) (\d+)\]/g, '<span class="marker">[$1 $2]</span>');

function setNav(name) {
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === name));
}

// ---------- router ----------
window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", route);

async function route() {
  clearInterval(state.poll);
  const hash = location.hash.replace(/^#\/?/, "");
  const [view, id] = hash.split("/");
  try {
    if (view === "settings") return await renderSettings();
    if (view === "projects") return await renderProjects();
    if (view === "project" && id) return await renderProject(decodeURIComponent(id));
    return await renderHome();
  } catch (error) {
    app.innerHTML = `<div class="notice bad">${esc(error.message)}</div>`;
  }
}

// ---------- home: pick a topic ----------
async function renderHome() {
  setNav("home");
  state.data = await api("/api/state");
  const { report, keys } = state.data;
  let html = `<div class="row spread"><h1>Pick today's topic</h1>
    <button id="import-radar" title="${esc(state.data.radar_dir)}">Import latest topic radar</button></div>`;

  const missing = [];
  if (!keys.fred) missing.push("FRED key (release dates will be left blank; the data itself still loads)");
  if (state.data.wording_engine === "templates") missing.push("wording engine (the built-in templates are used; add a key or choose local Ollama)");
  if (missing.length) {
    html += `<div class="notice info small">Optional keys not set: ${missing.map(esc).join("; ")}. <a href="#/settings">Open Settings</a></div>`;
  }

  if (!report) {
    html += `<div class="notice">No report found. Put your script's daily JSON files in <code>${esc(state.data.reports_folder)}</code>, or type a topic below.</div>`;
  } else {
    html += `<p class="sub">Top themes from <strong>${esc(report.file)}</strong>${report.date ? ` (${esc(report.date)})` : ""}. Click one, or type your own below.</p>`;
    if (report.note) html += `<div class="notice small">${esc(report.note)}</div>`;
    html += `<div class="grid cards">`;
    report.themes.forEach((theme, index) => {
      const heads = theme.headlines.slice(0, 3).map((h) => `<li>${esc(h.title)} <span class="muted">${esc(h.source)}</span></li>`).join("");
      const trends = theme.search_trends.slice(0, 4).map((t) => `<span class="chip">${esc(t)}</span>`).join(" ");
      html += `<button class="theme-card ${state.selected === index ? "selected" : ""}" data-theme="${index}" aria-pressed="${state.selected === index}">
        <span class="row spread"><span class="row"><span class="badge plain">Score ${esc(theme.score)}</span>
        ${theme.open_lane ? '<span class="badge good">Open lane</span>' : ""}</span>
        <span class="small muted">${theme.headlines.length} headlines · ${theme.competitor_videos.length} competitor videos</span></span>
        <span class="name">${esc(theme.theme)}</span>
        ${heads ? `<ul>${heads}</ul>` : ""}
        ${trends ? `<span class="row">${trends}</span>` : ""}
      </button>`;
    });
    html += `</div>`;
    if (report.emerging.length || report.tickers.length) {
      html += `<p class="small sub" style="margin-top:.9rem">`;
      if (report.emerging.length) html += `Emerging: ${report.emerging.map((e) => `<span class="chip">${esc(e)}</span>`).join(" ")} `;
      if (report.tickers.length) html += `Tickers: ${report.tickers.map((t) => `<span class="chip">${esc(t)}</span>`).join(" ")}`;
      html += `</p>`;
    }
  }

  const chosen = state.selected !== null && report ? report.themes[state.selected].theme : "";
  html += `<div class="panel generate-bar">
    <div>
      <label for="topic" style="margin-top:0">Topic</label>
      <input type="text" id="topic" maxlength="300" placeholder="Type your own topic, e.g. Why gas prices are rising" value="${esc(chosen)}">
      <label for="extra">Extra FRED series <span class="hint">Optional. Add up to 4 series IDs separated by spaces (e.g. APU0000708111) to chart something specific.</span></label>
      <input type="text" id="extra" placeholder="Optional">
    </div>
    <button class="primary" id="generate">Generate package</button>
  </div>`;
  app.innerHTML = html;

  app.querySelectorAll("[data-theme]").forEach((button) => button.addEventListener("click", () => {
    state.selected = Number(button.dataset.theme);
    document.getElementById("topic").value = report.themes[state.selected].theme;
    app.querySelectorAll("[data-theme]").forEach((b) => {
      const on = Number(b.dataset.theme) === state.selected;
      b.classList.toggle("selected", on);
      b.setAttribute("aria-pressed", on);
    });
  }));
  document.getElementById("topic").addEventListener("input", (event) => {
    // Editing the text turns the pick into a custom topic.
    if (state.selected !== null && report && event.target.value !== report.themes[state.selected].theme) {
      state.selected = null;
      app.querySelectorAll("[data-theme]").forEach((b) => { b.classList.remove("selected"); b.setAttribute("aria-pressed", false); });
    }
  });
  document.getElementById("generate").addEventListener("click", startGenerate);
  document.getElementById("import-radar").addEventListener("click", async (event) => {
    event.target.disabled = true;
    try {
      const result = await postJson("/api/reports/refresh", {});
      toast(result.status === "imported" ? `Imported ${result.file} (${result.themes} themes)` : `${result.file} is already the latest`);
      state.selected = null;
      renderHome();
    } catch (error) { event.target.disabled = false; toast(error.message); }
  });
}

async function startGenerate() {
  const topic = document.getElementById("topic").value.trim();
  if (!topic) return toast("Pick a card or type a topic first");
  const button = document.getElementById("generate");
  button.disabled = true;
  try {
    const { id } = await postJson("/api/projects", { topic, theme_index: state.selected, extra_series: document.getElementById("extra").value });
    state.selected = null;
    location.hash = `#/project/${encodeURIComponent(id)}`;
  } catch (error) {
    button.disabled = false;
    toast(error.message);
  }
}

// ---------- projects list ----------
async function renderProjects() {
  setNav("projects");
  const { projects } = await api("/api/state");
  let html = `<h1>Projects</h1><p class="sub">One folder per video, stored in <code>projects/</code> on this computer.</p>`;
  if (!projects.length) html += `<div class="notice info">No projects yet. <a href="#/">Pick a topic</a> to make the first one.</div>`;
  else {
    html += `<div class="panel table-wrap"><table><thead><tr><th>Topic</th><th>Created</th><th>Charts</th><th>Status</th></tr></thead><tbody>`;
    for (const p of projects) {
      const badge = p.status === "ready" ? complianceBadge(p.compliance) : p.status === "error" ? '<span class="badge bad">Error</span>' : '<span class="badge plain">Generating</span>';
      html += `<tr><td><a href="#/project/${encodeURIComponent(p.id)}">${esc(p.topic)}</a></td><td class="small">${esc(p.created.replace("T", " "))}</td><td>${p.charts}</td><td>${badge}</td></tr>`;
    }
    html += `</tbody></table></div>`;
  }
  app.innerHTML = html;
}

function complianceBadge(summary) {
  if (summary === "pass") return '<span class="badge good">Compliance: pass</span>';
  if (summary === "fail") return '<span class="badge bad">Compliance: fix needed</span>';
  return '<span class="badge warn">Compliance: review</span>';
}

// ---------- one project ----------
async function renderProject(id) {
  setNav("projects");
  const project = await api(`/api/projects/${encodeURIComponent(id)}`);
  state.project = project;
  if (project.status === "generating") return renderProgress(id, project);
  if (project.status === "error") {
    app.innerHTML = `<h1>${esc(project.topic)}</h1><div class="notice bad"><strong>Generation failed.</strong> ${esc(project.error)}</div>
      <p><a class="btn" href="#/">Back to topics</a></p>`;
    return;
  }
  drawProject();
}

function renderProgress(id, project) {
  app.innerHTML = `<h1>${esc(project.topic)}</h1><p class="sub">Fetching real data and building the package. This usually takes under a minute.</p>
    <div class="panel"><ul class="steps" id="steps"><li><span class="spinner"></span>Starting</li></ul></div>`;
  const tick = async () => {
    try {
      const progress = await api(`/api/projects/${encodeURIComponent(id)}/progress`);
      const steps = progress.steps.length ? progress.steps : ["Working"];
      document.getElementById("steps").innerHTML = steps.map((s, i) => `<li>${i === steps.length - 1 && !progress.done ? '<span class="spinner"></span>' : ""}${esc(s)}</li>`).join("");
      if (progress.done) { clearInterval(state.poll); renderProject(id); }
    } catch (_) { /* keep polling */ }
  };
  tick();
  state.poll = setInterval(tick, 900);
}

const TABS = [["facts", "Fact sheet"], ["cards", "Recording cards"], ["charts", "Charts & graphics"], ["outline", "Outline"], ["shots", "Asset board"], ["titles", "Titles & thumbnails"], ["clips", "Clip plan"], ["compliance", "Compliance"], ["description", "Description"], ["learning", "Learning log"]];

function drawProject() {
  const p = state.project;
  const source = p.llm_used ? `Wording: ${esc(p.wording_source.replace("llm:", "LLM, "))}` : "Wording: built-in templates";
  let html = `<div class="row spread"><div><h1>${esc(p.topic)}</h1>
    <p class="sub small">Created ${esc(p.created.replace("T", " "))} · ${p.charts.length} charts · ${p.facts.length} facts · ${source}</p></div>
    <div class="row">${complianceBadge(p.compliance.summary)} <a class="btn primary" href="/api/projects/${encodeURIComponent(p.id)}/export">Download ZIP</a></div></div>`;
  if (p.warnings && p.warnings.length) {
    html += `<details class="notice small"><summary>${p.warnings.length} data note${p.warnings.length > 1 ? "s" : ""} (things that were skipped, not guessed)</summary><ul>${p.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></details>`;
  }
  html += `<div class="tabs" role="tablist">${TABS.map(([key, label]) => `<button role="tab" aria-selected="${state.tab === key}" data-tab="${key}">${label}</button>`).join("")}</div><div id="tab"></div>`;
  app.innerHTML = html;
  app.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => { state.tab = b.dataset.tab; drawProject(); }));
  const draw = { facts: tabFacts, cards: tabCards, charts: tabCharts, outline: tabOutline, shots: tabShots, titles: tabTitles, clips: tabClips, compliance: tabCompliance, description: tabDescription, learning: tabLearning }[state.tab];
  Promise.resolve(draw()).catch((error) => { document.getElementById("tab").innerHTML = `<div class="notice bad">${esc(error.message)}</div>`; }).then(bindCopy);
}

// Copy buttons can appear after a tab finishes loading, so this is safe to call again.
function bindCopy() {
  app.querySelectorAll("[data-copy]").forEach((b) => {
    if (b.dataset.bound) return;
    b.dataset.bound = "1";
    b.addEventListener("click", () => copyText(b.dataset.copy));
  });
}

// Reload the project from disk and redraw the current tab.
async function refreshProject() {
  state.project = await api(`/api/projects/${encodeURIComponent(state.project.id)}`);
  drawProject();
}

const pid = () => encodeURIComponent(state.project.id);
const fileUrl = (relative) => `/api/projects/${pid()}/file/${relative.split("/").map(encodeURIComponent).join("/")}`;
const del = (path) => api(path, { method: "DELETE" });
const putJson = (path, body) => api(path, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const usableFacts = () => state.project.facts.filter((f) => f.status !== "verify" && f.value);
const factOptions = (selected) => usableFacts().map((f) => `<option value="${esc(f.id)}" ${f.id === selected ? "selected" : ""}>${esc(f.id)}: ${esc(f.value)} — ${esc(f.claim.slice(0, 70))}</option>`).join("");
const chartOptions = (selected) => state.project.charts.map((c) => `<option value="${c.n}" ${c.n === selected ? "selected" : ""}>Chart ${c.n}: ${esc(c.title)}</option>`).join("");

const STATUS = { primary: ['good', 'Primary source'], calculated: ['plain', 'Calculated'], verify: ['warn', 'Verify'] };
const factById = (id) => state.project.facts.find((f) => f.id === id);

function refs(ids) {
  return (ids || []).map((id) => {
    const fact = factById(id);
    const url = fact && safeUrl(fact.source_url);
    const title = fact ? esc(`${fact.source_name}`) : "";
    return url ? `<a class="ref" href="${esc(url)}" target="_blank" rel="noopener noreferrer" title="${title}">${esc(id)}</a>` : `<span class="ref" title="${title}">${esc(id)}</span>`;
  }).join("");
}

function tabFacts() {
  const p = state.project;
  const verify = p.facts.filter((f) => f.status === "verify").length;
  let html = `<p class="sub">Every number was fetched from the linked source or calculated from fetched numbers. Nothing here was written by AI.
    ${verify ? `<strong>${verify} item${verify > 1 ? "s" : ""} marked Verify</strong> appear only in news articles: check them before you say them.` : ""}</p>
    <div class="panel table-wrap"><table><thead><tr><th>ID</th><th>Claim</th><th>Status</th><th>Source</th></tr></thead><tbody>`;
  let group = null;
  for (const fact of p.facts) {
    if (fact.group !== group) { group = fact.group; html += `<tr class="group-row"><td colspan="4">${esc(group)}</td></tr>`; }
    const [cls, label] = STATUS[fact.status] || ["plain", fact.status];
    html += `<tr><td class="id">${esc(fact.id)}</td><td>${esc(fact.claim)}${fact.note ? `<div class="note">${esc(fact.note)}</div>` : ""}</td>
      <td><span class="badge ${cls}">${label}</span></td><td class="small">${link(fact.source_url, fact.source_name)}</td></tr>`;
  }
  html += `</tbody></table></div>`;
  document.getElementById("tab").innerHTML = `<div id="changes"></div>` + html;
  return drawChanges();
}

function tabCharts() {
  const p = state.project;
  const size = state.verticalCharts ? "1080x1920" : "1920x1080";
  const base = `/api/projects/${encodeURIComponent(p.id)}/file/charts/`;
  let html = `<div class="row spread"><p class="sub">Real data only. Each chart is saved as a 1920x1080 PNG and a 1080x1920 vertical PNG with the source printed in the corner.</p>
    <button id="flip">${state.verticalCharts ? "Show 16:9 versions" : "Show vertical versions"}</button></div><div class="grid chart-grid">`;
  for (const chart of p.charts) {
    html += `<div class="panel chart-card"><img class="${state.verticalCharts ? "vertical" : ""}" loading="lazy" src="${base}${esc(chart.files[size])}" alt="Chart ${chart.n}: ${esc(chart.title)}">
      <h3>Chart ${chart.n}: ${esc(chart.title)}</h3>
      ${chart.teaches ? `<p class="small">${esc(chart.teaches)}</p>` : ""}
      <p class="small sub">Data through ${esc(chart.data_through)}. Sources: ${chart.series.map((s) => link(s.source_url, `${s.title}, ${s.source_name}`)).join("; ")}</p>
      <div class="row"><a class="btn small" href="${base}${esc(chart.files["1920x1080"])}?download=1">Download 1920x1080</a>
      <a class="btn small" href="${base}${esc(chart.files["1080x1920"])}?download=1">Download 1080x1920</a></div></div>`;
  }
  html += `</div><div id="graphics"></div>`;
  document.getElementById("tab").innerHTML = html;
  document.getElementById("flip").addEventListener("click", () => { state.verticalCharts = !state.verticalCharts; drawProject(); });
  drawGraphics();
}

const bulletList = (bullets) => `<ul>${bullets.map((b) => `<li>${withMarkers(b.text)}${refs(b.facts)}</li>`).join("")}</ul>`;
const ANGLES = { mortgage: "Mortgage", job: "Job", groceries: "Groceries", retirement: "401(k)" };

function outlineText() {
  const o = state.project.outline;
  const lines = [];
  const add = (bullets) => bullets.forEach((b) => lines.push(`- ${b.text}`));
  lines.push(o.hook.title.toUpperCase()); add(o.hook.bullets); lines.push("");
  lines.push(o.what_happened.title.toUpperCase()); add(o.what_happened.bullets); lines.push("");
  lines.push("WHY IT HAPPENED");
  o.why.forEach((c, i) => { lines.push(`Cause ${i + 1}: ${c.cause} [CHART ${c.chart}]`); add(c.bullets); });
  lines.push("", "WHAT IT MEANS FOR YOU");
  Object.entries(o.what_it_means).forEach(([angle, bullets]) => { lines.push(`${ANGLES[angle] || angle}:`); add(bullets); });
  lines.push("", o.watch_next.title.toUpperCase()); add(o.watch_next.bullets);
  if (o.watch_next.takeaway) lines.push(`- ${o.watch_next.takeaway.text}`);
  lines.push("", o.closing.title.toUpperCase(), `- ${o.closing.line}`, `- ${o.closing.cta}`);
  return lines.join("\n");
}

function tabOutline() {
  const o = state.project.outline;
  let html = `<div class="row spread"><p class="sub">Talking points, not a script. Blue tags link each number to its source; <span class="marker">[CHART n]</span> marks where a visual goes.</p>
    <button id="copy-outline">Copy outline</button></div><div class="panel outline">`;
  html += `<section><h2 style="margin-top:0">${esc(o.hook.title)}</h2>${bulletList(o.hook.bullets)}</section>`;
  html += `<section><h2>${esc(o.what_happened.title)}</h2>${bulletList(o.what_happened.bullets)}</section>`;
  html += `<section><h2>Why it happened</h2>`;
  o.why.forEach((cause, i) => { html += `<h3>Cause ${i + 1}: ${esc(cause.cause)} <span class="marker">[CHART ${cause.chart}]</span></h3>${bulletList(cause.bullets)}`; });
  html += `</section><section><h2>What it means for you</h2>`;
  for (const [angle, bullets] of Object.entries(o.what_it_means)) html += `<h3>${esc(ANGLES[angle] || angle)}</h3>${bulletList(bullets)}`;
  html += `</section><section><h2>${esc(o.watch_next.title)}</h2><ul>`;
  for (const item of o.watch_next.bullets) html += `<li>${esc(item.text)} <span class="note">${link(item.source_url, item.status)}</span></li>`;
  if (o.watch_next.takeaway) html += `<li>${esc(o.watch_next.takeaway.text)}</li>`;
  html += `</ul></section><section><h2>${esc(o.closing.title)}</h2><ul><li>${esc(o.closing.line)}${refs(o.closing.facts)}</li><li>${esc(o.closing.cta)}</li></ul></section></div>`;
  document.getElementById("tab").innerHTML = html;
  document.getElementById("copy-outline").addEventListener("click", () => copyText(outlineText(), "Outline copied"));
}

function tabTitles() {
  const p = state.project;
  const outliers = p.competitor_outliers || [];
  let html = `<div class="two-col"><div class="panel"><h2 style="margin-top:0">Title options</h2><p class="small sub">60 characters or fewer. Numbers are filled in from the fact sheet.</p><ol class="titles">`;
  for (const title of p.titles) html += `<li><div class="row spread"><span>${esc(title)}</span><span class="row"><span class="chip">${title.length}/60</span><button class="small" data-copy="${esc(title)}">Copy</button></span></div></li>`;
  html += `</ol><h2>Thumbnail text</h2><p class="small sub">4 words or fewer.</p><div class="row">`;
  for (const thumb of p.thumbnails) html += `<button data-copy="${esc(thumb)}" title="Click to copy"><strong>${esc(thumb)}</strong></button>`;
  html += `</div></div><div class="panel"><h2 style="margin-top:0">Competitor outlier titles</h2><p class="small sub">From your report, for comparison.</p>`;
  if (!outliers.length) html += `<p class="muted">This report has no competitor titles for this topic.</p>`;
  else {
    html += `<ol class="titles">`;
    for (const video of outliers) {
      const views = video.views !== null && video.views !== undefined ? `${Number(video.views).toLocaleString()} views` : "views not in report";
      html += `<li>${link(video.url, video.title)}<div class="note">${esc(video.channel || "")} ${esc(views)} · ${video.title.length} chars</div></li>`;
    }
    html += `</ol>`;
  }
  html += `</div></div><div id="workshop"></div>`;
  document.getElementById("tab").innerHTML = html;
  return drawWorkshop();
}

function tabCompliance() {
  const p = state.project;
  const mark = { pass: ["good", "Pass"], fail: ["bad", "Fix"], warn: ["warn", "Review"] };
  let html = `<p class="sub">Education and commentary only, never personal investment advice. These checks run on every package.</p>
    <div class="panel"><h2 style="margin-top:0">Automatic checks</h2>`;
  for (const item of p.compliance.automatic) {
    const [cls, label] = mark[item.status];
    html += `<div class="check"><span class="badge ${cls}">${label}</span><div><strong>${esc(item.label)}</strong><div class="note">${esc(item.detail)}</div></div></div>`;
  }
  html += `</div><div class="panel" style="margin-top:1rem"><h2 style="margin-top:0">Confirm before you publish</h2><p class="small sub">You talk freestyle, so only you can confirm these.</p>`;
  for (const item of p.compliance.manual) {
    html += `<label class="check" style="font-weight:400;margin:0"><input type="checkbox" data-check="${esc(item.id)}" ${item.checked ? "checked" : ""}><span>${esc(item.label)}</span></label>`;
  }
  html += `</div>`;
  document.getElementById("tab").innerHTML = html;
  document.querySelectorAll("[data-check]").forEach((box) => box.addEventListener("change", async () => {
    const checks = {};
    document.querySelectorAll("[data-check]").forEach((b) => { checks[b.dataset.check] = b.checked; });
    try {
      state.project = await postJson(`/api/projects/${encodeURIComponent(p.id)}/checks`, { checks });
      toast("Saved");
    } catch (error) { toast(error.message); }
  }));
}

function tabDescription() {
  const p = state.project;
  document.getElementById("tab").innerHTML = `<div class="row spread"><p class="sub">Ready to paste into YouTube: sources, AI disclosure and the disclaimer are included.</p>
    <button class="primary" id="copy-desc">Copy description</button></div><pre class="desc">${esc(p.description)}</pre>`;
  document.getElementById("copy-desc").addEventListener("click", () => copyText(p.description, "Description copied"));
}

// ---------- settings ----------
const FIELDS = [
  ["FRED_API_KEY", "FRED API key", "Free from fred.stlouisfed.org. Adds upcoming release dates. Data loads without it."],
  ["ANTHROPIC_API_KEY", "Anthropic API key", "Used only for wording (outline, titles, B-roll prompts). Never for numbers. Leave blank to use the built-in templates."],
  ["ANTHROPIC_MODEL", "LLM model", "Model ID used for wording."],
  ["BLS_API_KEY", "BLS API key", "Optional. Raises the daily limit for cross-checking BLS numbers."],
  ["SEC_CONTACT", "SEC contact", "The SEC asks tools to identify themselves, e.g. Your Name you@example.com. Sent only to sec.gov."],
  ["CHANNEL_NAME", "Channel name", "Optional. Added to the description, the subscribe line and the thumbnail phone preview."],
  ["OLLAMA_URL", "Ollama address", "Only used when the wording engine is Local Ollama. The default is this computer."],
  ["OLLAMA_MODEL", "Ollama model", "The exact model tag as shown by 'ollama list'. Blank = the first installed model with 'qwen' in its name."],
  ["WHISPER_MODEL", "Transcription model", "faster-whisper model for local transcription. auto = large-v3 on an NVIDIA GPU, small on CPU."],
  ["RADAR_REPORTS_DIR", "Topic radar reports folder", "Where 'Import latest topic radar' looks for the newest report."],
];

async function renderSettings() {
  setNav("settings");
  const { settings, env_file } = await api("/api/settings");
  let html = `<h1>Settings</h1><p class="sub">Saved to <code>${esc(env_file)}</code> on this computer. Keys are never shown again after saving and never sent anywhere except the service they belong to.</p><div class="panel">`;
  for (const [key, label, hint] of FIELDS) {
    const s = settings[key];
    if (s.secret) {
      html += `<label for="${key}">${esc(label)} ${s.set ? `<span class="badge good">Saved ${esc(s.hint)}</span>` : '<span class="badge plain">Not set</span>'}<span class="hint">${esc(hint)}</span></label>
        <div class="row" style="flex-wrap:nowrap"><input type="password" id="${key}" autocomplete="off" placeholder="${s.set ? "Leave blank to keep the saved key" : "Paste key"}">
        ${s.set ? `<button class="small" data-clear="${key}">Remove</button>` : ""}</div>`;
    } else {
      html += `<label for="${key}">${esc(label)}<span class="hint">${esc(hint)}</span></label><input type="text" id="${key}" value="${esc(s.value)}">`;
    }
  }
  html += `<label for="LLM_PROVIDER">Wording engine<span class="hint">Writes the outline, titles and B-roll prompts. Every engine goes through the same number guard and compliance checks.</span></label>
    <div class="row" style="flex-wrap:nowrap"><select id="LLM_PROVIDER">${[["auto", "Automatic (Anthropic if a key is saved, else templates)"], ["ollama", "Local Ollama (free, runs on this computer)"], ["anthropic", "Anthropic API"], ["templates", "Built-in templates only"]].map(([v, l]) => `<option value="${v}" ${settings.LLM_PROVIDER.value === v ? "selected" : ""}>${l}</option>`).join("")}</select>
    <button class="small" id="ollama-list">List Ollama models</button></div><div id="ollama-result" class="small sub"></div>`;
  html += `<label for="CHART_THEME">Chart style<span class="hint">Dark suits most video edits.</span></label>
    <select id="CHART_THEME"><option value="dark" ${settings.CHART_THEME.value === "dark" ? "selected" : ""}>Dark</option><option value="light" ${settings.CHART_THEME.value === "light" ? "selected" : ""}>Light</option></select>
    <label for="DISCLAIMER">Disclaimer<span class="hint">Goes at the end of every description. Keep the words "education" and "not investment advice".</span></label>
    <textarea id="DISCLAIMER">${esc(settings.DISCLAIMER.value)}</textarea>
    <div class="row" style="margin-top:1rem"><button class="primary" id="save">Save settings</button><button id="test-fred">Test FRED connection</button><span id="test-result" class="small"></span></div></div>`;
  app.innerHTML = html;

  document.getElementById("save").addEventListener("click", async () => {
    const values = {};
    [...FIELDS.map((f) => f[0]), "CHART_THEME", "DISCLAIMER", "LLM_PROVIDER"].forEach((key) => { values[key] = document.getElementById(key).value; });
    try { await postJson("/api/settings", { values }); toast("Settings saved"); renderSettings(); } catch (error) { toast(error.message); }
  });
  app.querySelectorAll("[data-clear]").forEach((b) => b.addEventListener("click", async () => {
    await postJson("/api/settings", { values: {}, clear: [b.dataset.clear] });
    toast("Key removed");
    renderSettings();
  }));
  document.getElementById("ollama-list").addEventListener("click", async () => {
    const out = document.getElementById("ollama-result");
    out.textContent = "Asking Ollama...";
    const result = await api("/api/ollama/models");
    out.textContent = result.ok ? (result.models.length ? `Installed: ${result.models.join(", ")}` : "Ollama is running but has no models installed.") : result.message;
  });
  document.getElementById("test-fred").addEventListener("click", async () => {
    const out = document.getElementById("test-result");
    out.textContent = "Testing...";
    try { const r = await postJson("/api/settings/test-fred", {}); out.textContent = r.message; } catch (error) { out.textContent = error.message; }
  });
}

// =====================================================================================
// Recording cards + camera-line recording view
// =====================================================================================
let cardsView = null;
const cardTimers = {};
const cardSessions = {};
const STATUS_LABEL = { unrecorded: "Not recorded", recorded: "Recorded", needs_another_take: "Needs another take" };
const STATUS_BADGE = { unrecorded: "plain", recorded: "good", needs_another_take: "warn" };

async function tabCards() {
  cardsView = await api(`/api/projects/${pid()}/cards`);
  drawCards();
}

function warningsHtml(w) {
  if (w.ok) return `<span class="badge good">Numbers and wording check out</span>`;
  const parts = [];
  if (w.unverified_numbers.length) parts.push(`<div><strong>Not on the fact sheet:</strong> ${w.unverified_numbers.map(esc).join(", ")}. Use a pinned number, or verify it and add it as a source first.</div>`);
  if (w.unknown_facts.length) parts.push(`<div><strong>Unknown fact:</strong> ${w.unknown_facts.map(esc).join(", ")} is not on this fact sheet.</div>`);
  if (w.advice.length) parts.push(`<div><strong>Reads like advice or a promise:</strong> \u201c${esc(w.advice[0])}\u201d. Explain what happened instead of what to do.</div>`);
  return `<div class="notice bad small">${parts.join("")}</div>`;
}

function visualHtml(v) {
  const tag = `<span class="marker">[${esc(v.kind)} ${v.n}]</span>`;
  if (v.file && v.media === "video") return `<figure class="cue">${tag}<video src="${fileUrl(v.file)}" muted controls preload="metadata"></video><figcaption>${esc(v.title || "")}</figcaption></figure>`;
  if (v.file) return `<figure class="cue">${tag}<img loading="lazy" src="${fileUrl(v.file)}" alt="${esc(v.title || v.kind)}"><figcaption>${esc(v.title || "")}</figcaption></figure>`;
  if (v.kind === "HEADLINE") return `<figure class="cue">${tag}<figcaption>${link(v.url, v.title || "Headline")}<br><span class="muted">No screenshot yet. Add one on the Asset board.</span></figcaption></figure>`;
  return `<figure class="cue">${tag}<figcaption>${esc(v.title || "")}<br><span class="muted">${v.blocked ? "Prompt blocked. Rewrite it as a generic scene." : "No clip yet. Add one on the Asset board."}</span></figcaption></figure>`;
}

function pinnedHtml(card) {
  if (!card.pinned.length) return `<span class="muted small">No numbers are pinned to this card.</span>`;
  return card.pinned.map((f) => `<span class="pin"><button class="small" data-insert="${esc(f.value)}" data-card="${esc(card.id)}" title="${esc(f.claim)} Click to insert at the cursor.">
    <strong>${esc(f.id)}</strong> ${esc(f.value || "(no number)")}</button><span class="small muted">${f.as_of ? `as of ${esc(f.as_of)} \u00b7 ` : ""}${link(f.source_url, f.source_name)}</span></span>`).join("");
}

function drawCards() {
  const v = cardsView;
  const p = state.project;
  const base = `/api/projects/${pid()}`;
  let html = `<div class="row spread toolbar"><div class="row">
      <span class="badge good">${v.counts.recorded} recorded</span><span class="badge warn">${v.counts.needs_another_take} need another take</span><span class="badge plain">${v.counts.unrecorded} to go</span>
    </div><div class="row">
      <button id="undo" ${v.can_undo ? "" : "disabled"} title="${esc(v.undo_label)}">Undo</button>
      <button id="redo" ${v.can_redo ? "" : "disabled"} title="${esc(v.redo_label)}">Redo</button>
      <button class="primary" id="launch-rec">Launch recording view</button>
    </div></div>
    <p class="sub small">Rewrite each card in your own voice. The numbers are pinned separately, so they stay exact and sourced however you word it. Edits save as you type.
    ${v.cues.length ? `Last take: ${v.cues.length} cues logged. Export: <a href="${base}/timeline/chapters.txt">YouTube chapters</a> \u00b7 <a href="${base}/timeline/timeline.edl">.edl</a> \u00b7 <a href="${base}/timeline/timeline.fcpxml">.fcpxml</a>` : ""}</p>`;
  v.cards.forEach((card, index) => {
    const unpinned = p.facts.filter((f) => f.value && f.status !== "verify" && !card.pinned.some((x) => x.id === f.id));
    html += `<article class="panel rcard" data-card="${esc(card.id)}">
      <div class="row spread"><div class="row"><span class="drag" draggable="true" data-drag="${esc(card.id)}" title="Drag to reorder" aria-hidden="true">\u2630</span>
        <h3 style="margin:0">${index + 1}. ${esc(card.title)}</h3>${card.edited ? '<span class="chip">edited</span>' : ""}</div>
        <div class="row"><button class="small" data-move="-1" data-card="${esc(card.id)}" ${index === 0 ? "disabled" : ""} aria-label="Move up">\u2191</button>
        <button class="small" data-move="1" data-card="${esc(card.id)}" ${index === v.cards.length - 1 ? "disabled" : ""} aria-label="Move down">\u2193</button>
        ${Object.keys(STATUS_LABEL).map((s) => `<button class="small status ${card.status === s ? "on " + STATUS_BADGE[s] : ""}" data-status="${s}" data-card="${esc(card.id)}" aria-pressed="${card.status === s}">${STATUS_LABEL[s]}</button>`).join("")}</div></div>
      ${(card.flags || []).map((f) => `<div class="notice small ${f.kind === "retake" ? "bad" : "info"}">${esc(f.text)}</div>`).join("")}
      <div class="rcard-grid"><div>
        <label for="text-${esc(card.id)}">Main point <span class="hint">In your own voice. Bullets or notes, whatever you talk from.</span></label>
        <textarea id="text-${esc(card.id)}" data-field="text" data-card="${esc(card.id)}" rows="${Math.max(4, card.text.split("\n").length + 1)}">${esc(card.text)}</textarea>
        <div class="row spread small"><span id="save-${esc(card.id)}" class="muted">Saved</span>${card.edited ? `<button class="small" data-reset="${esc(card.id)}">Restore generated wording</button>` : ""}</div>
        <div id="warn-${esc(card.id)}">${warningsHtml(card.warnings)}</div>
        <label for="pron-${esc(card.id)}">Pronunciation and delivery notes <span class="hint">Tricky names, tickers, where to pause.</span></label>
        <textarea id="pron-${esc(card.id)}" data-field="pronunciation" data-card="${esc(card.id)}" rows="2" placeholder="e.g. Pause one beat before showing the 10-year yield">${esc(card.pronunciation)}</textarea>
      </div><div>
        <label>Pinned essential numbers</label><div class="pins" id="pins-${esc(card.id)}">${pinnedHtml(card)}</div>
        ${unpinned.length ? `<select class="small" data-pin="${esc(card.id)}" aria-label="Pin another fact"><option value="">Pin another fact...</option>${unpinned.map((f) => `<option value="${esc(f.id)}">${esc(f.id)}: ${esc(f.value)} \u2014 ${esc(f.claim.slice(0, 60))}</option>`).join("")}</select>` : ""}
        <label>Visual cue</label><div class="cues">${card.visuals.length ? card.visuals.map(visualHtml).join("") : '<span class="muted small">Talking head only.</span>'}</div>
      </div></div></article>`;
  });
  document.getElementById("tab").innerHTML = html;
  bindCards();
}

function saveCardField(cardId, field, value) {
  const note = document.getElementById(`save-${cardId}`);
  if (note) note.textContent = "Saving...";
  clearTimeout(cardTimers[cardId + field]);
  cardTimers[cardId + field] = setTimeout(async () => {
    const key = cardId + field;
    try {
      cardsView = await putJson(`/api/projects/${pid()}/cards/${encodeURIComponent(cardId)}`, { [field]: value, checkpoint: !cardSessions[key] });
      cardSessions[key] = true;  // later saves in this typing session fold into the same undo step
      const card = cardsView.cards.find((c) => c.id === cardId);
      const warn = document.getElementById(`warn-${cardId}`);
      if (warn && card) warn.innerHTML = warningsHtml(card.warnings);
      if (note) note.textContent = "Saved";
      const undo = document.getElementById("undo");
      if (undo) undo.disabled = !cardsView.can_undo;
    } catch (error) { if (note) note.textContent = `Not saved: ${error.message}`; }
  }, 700);
}

function bindCards() {
  const base = `/api/projects/${pid()}`;
  const tab = document.getElementById("tab");
  const reload = (view) => { cardsView = view; drawCards(); };
  tab.querySelectorAll("textarea[data-field]").forEach((area) => {
    area.addEventListener("input", () => saveCardField(area.dataset.card, area.dataset.field, area.value));
    area.addEventListener("blur", () => { cardSessions[area.dataset.card + area.dataset.field] = false; });
  });
  tab.querySelectorAll("[data-insert]").forEach((b) => b.addEventListener("click", () => {
    const area = document.getElementById(`text-${b.dataset.card}`);
    const at = area.selectionStart ?? area.value.length;
    const before = area.value.slice(0, at);
    const gap = before && !/\s$/.test(before) ? " " : "";  // never glue a number onto the previous word
    area.value = before + gap + b.dataset.insert + area.value.slice(area.selectionEnd ?? at);
    area.focus();
    saveCardField(b.dataset.card, "text", area.value);
  }));
  tab.querySelectorAll("[data-pin]").forEach((sel) => sel.addEventListener("change", async () => {
    if (!sel.value) return;
    const card = cardsView.cards.find((c) => c.id === sel.dataset.pin);
    reload(await putJson(`${base}/cards/${encodeURIComponent(card.id)}`, { fact_ids: [...card.fact_ids, sel.value] }));
  }));
  tab.querySelectorAll("[data-status]").forEach((b) => b.addEventListener("click", async () => {
    const view = await postJson(`${base}/cards/${encodeURIComponent(b.dataset.card)}/status`, { status: b.dataset.status });
    if (view.frozen_at && b.dataset.status === "recorded") toast("Facts frozen as recorded");
    reload(view);
  }));
  tab.querySelectorAll("[data-move]").forEach((b) => b.addEventListener("click", async () => reload(await postJson(`${base}/cards/${encodeURIComponent(b.dataset.card)}/move`, { delta: Number(b.dataset.move) }))));
  tab.querySelectorAll("[data-reset]").forEach((b) => b.addEventListener("click", async () => reload(await postJson(`${base}/cards/${encodeURIComponent(b.dataset.reset)}/reset`, {}))));
  document.getElementById("undo").addEventListener("click", async () => reload(await postJson(`${base}/cards-undo`, {})));
  document.getElementById("redo").addEventListener("click", async () => reload(await postJson(`${base}/cards-redo`, {})));
  document.getElementById("launch-rec").addEventListener("click", openRecordingView);

  // drag a card by its handle and drop it on another card to reorder
  let dragged = null;
  tab.querySelectorAll("[data-drag]").forEach((handle) => {
    handle.addEventListener("dragstart", (event) => { dragged = handle.dataset.drag; event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", dragged); });
  });
  tab.querySelectorAll(".rcard").forEach((el) => {
    el.addEventListener("dragover", (event) => { if (dragged) { event.preventDefault(); el.classList.add("drop-target"); } });
    el.addEventListener("dragleave", () => el.classList.remove("drop-target"));
    el.addEventListener("drop", async (event) => {
      event.preventDefault();
      el.classList.remove("drop-target");
      if (!dragged || dragged === el.dataset.card) return;
      const order = cardsView.cards.map((c) => c.id).filter((id) => id !== dragged);
      order.splice(order.indexOf(el.dataset.card), 0, dragged);
      dragged = null;
      reload(await postJson(`${base}/cards-order`, { order }));
    });
  });
}

// ---- recording view: the active card sits at the top-centre of the screen, under the webcam
const rec = { active: false, index: 0, started: false, t0: 0, cues: [], tick: null };
const recElapsed = () => (rec.started ? (performance.now() - rec.t0) / 1000 : 0);
const clockText = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

function openRecordingView() {
  Object.assign(rec, { active: true, index: 0, started: false, cues: [] });
  const overlay = document.createElement("div");
  overlay.id = "recview";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-label", "Recording view");
  document.body.appendChild(overlay);
  document.addEventListener("keydown", recKeys);
  rec.tick = setInterval(() => { const t = document.getElementById("rec-timer"); if (t) t.textContent = clockText(recElapsed()); }, 250);
  drawRecording();
}

function drawRecording() {
  const card = cardsView.cards[rec.index];
  const last = rec.index === cardsView.cards.length - 1;
  document.getElementById("recview").innerHTML = `<div class="rec-card">
    <div class="row spread rec-top"><span><strong id="rec-timer">${clockText(recElapsed())}</strong> \u00b7 Card ${rec.index + 1} of ${cardsView.cards.length}
      ${rec.started ? '<span class="badge bad">REC LOG ON</span>' : '<span class="badge plain">Not started</span>'}</span>
      <span class="small">${rec.started ? `<kbd>Space</kbd> ${last ? "finish" : "next card"} \u00b7 <kbd>R</kbd> redo this card \u00b7 <kbd>Esc</kbd> finish` : "<kbd>Space</kbd> start when you hit record \u00b7 <kbd>Esc</kbd> close"}</span></div>
    <h2>${esc(card.title)}</h2>
    <div class="rec-text">${withMarkers(card.text).replace(/\n/g, "<br>")}</div>
    ${card.pinned.length ? `<div class="rec-pins">${card.pinned.filter((f) => f.value).map((f) => `<span><strong>${esc(f.value)}</strong> <small>${esc(f.as_of)}</small></span>`).join("")}</div>` : ""}
    ${card.pronunciation ? `<div class="rec-note">${esc(card.pronunciation)}</div>` : ""}
    ${card.visuals.length ? `<div class="rec-visuals">Visuals: ${card.visuals.map((v) => `[${esc(v.kind)} ${v.n}] ${esc(v.title || "")}`).join(" \u00b7 ")}</div>` : ""}
    <div class="row rec-buttons"><button class="primary" id="rec-next">${rec.started ? (last ? "Finish (Space)" : "Next card (Space)") : "Start (Space)"}</button>
      ${rec.started ? '<button id="rec-retake">Redo this card (R)</button>' : ""}<button id="rec-close">${rec.started ? "Finish and save (Esc)" : "Close (Esc)"}</button></div></div>`;
  document.getElementById("rec-next").addEventListener("click", recAdvance);
  document.getElementById("rec-close").addEventListener("click", recFinish);
  const retake = document.getElementById("rec-retake");
  if (retake) retake.addEventListener("click", recRetake);
}

function recKeys(event) {
  if (!rec.active || ["TEXTAREA", "INPUT", "SELECT"].includes(event.target.tagName)) return;
  if (event.code === "Space") { event.preventDefault(); recAdvance(); }
  else if (event.key === "r" || event.key === "R") { event.preventDefault(); recRetake(); }
  else if (event.key === "Escape") { event.preventDefault(); recFinish(); }
}

const recStatus = (cardId, status) => postJson(`/api/projects/${pid()}/cards/${encodeURIComponent(cardId)}/status`, { status }).then((view) => { cardsView = view; }).catch(() => {});

function recAdvance() {
  const card = cardsView.cards[rec.index];
  if (!rec.started) {
    rec.started = true;
    rec.t0 = performance.now();
    rec.cues.push({ card_id: card.id, start: 0, flagged: false });
    return drawRecording();
  }
  recStatus(card.id, "recorded");  // moving on means this take is the keeper
  if (rec.index === cardsView.cards.length - 1) return recFinish();
  rec.index += 1;
  rec.cues.push({ card_id: cardsView.cards[rec.index].id, start: recElapsed(), flagged: false });
  drawRecording();
}

function recRetake() {
  if (!rec.started) return;
  const card = cardsView.cards[rec.index];
  rec.cues[rec.cues.length - 1].flagged = true;  // that take is out; a new take of the same card starts now
  rec.cues.push({ card_id: card.id, start: recElapsed(), flagged: false });
  recStatus(card.id, "needs_another_take");
  toast("Take flagged. Go again.");
  drawRecording();
}

async function recFinish() {
  const total = recElapsed();
  rec.active = false;
  clearInterval(rec.tick);
  document.removeEventListener("keydown", recKeys);
  const overlay = document.getElementById("recview");
  if (overlay) overlay.remove();
  if (rec.started && rec.cues.length) {
    try { await postJson(`/api/projects/${pid()}/cards-cues`, { cues: rec.cues, total_seconds: total }); toast("Cues saved. Chapters and timelines are ready to export."); }
    catch (error) { toast(error.message); }
  }
  rec.started = false;
  if (state.tab === "cards") tabCards();
}

// =====================================================================================
// Visual asset board
// =====================================================================================
let boardView = null;
let libraryItems = [];
const boardState = { missingOnly: false, drawer: null };
const KIND_LABEL = { chart: "Chart", talking_head: "Talking head", headline: "Headline screenshot", broll: "B-roll" };
const SLOT_BADGE = { ready: ["good", "Ready"], missing: ["bad", "Missing"], needs_replacement: ["warn", "Needs replacement"], camera: ["plain", "On camera"] };

async function tabShots() {
  [boardView, libraryItems] = await Promise.all([api(`/api/projects/${pid()}/asset-board`), api("/api/library").then((r) => r.items)]);
  drawBoard();
}

function mediaPreview(src, media, alt) {
  return media === "video" ? `<video src="${src}" controls muted preload="metadata"></video>` : `<img loading="lazy" src="${src}" alt="${esc(alt)}">`;
}

function drawBoard() {
  const v = boardView;
  const shots = Object.fromEntries(state.project.shots.map((s) => [s.n, s]));
  const visible = v.slots.filter((s) => !boardState.missingOnly || (s.required && s.status !== "ready"));
  let html = `<div class="statusbar ${v.summary.missing ? "warn" : "good"}"><strong>${esc(v.summary.text)}</strong>
      <label class="inline"><input type="checkbox" id="missing-only" ${boardState.missingOnly ? "checked" : ""}> Missing only</label></div>
    <p class="sub small">Drag a file from your computer onto a scene, or browse for one. Charts are linked automatically. AI B-roll is always generic and labelled illustrative.</p>
    <div class="grid board">`;
  if (!visible.length) html += `<div class="notice info">Every scene visual is ready.</div>`;
  for (const slot of visible) {
    const shot = shots[slot.shot_n] || {};
    const [cls, label] = SLOT_BADGE[slot.status] || ["plain", slot.status];
    html += `<article class="panel slot" data-slot="${slot.shot_n}">
      <div class="row spread"><span><strong>Scene ${slot.shot_n}</strong> <span class="chip">${KIND_LABEL[slot.kind]}</span></span><span class="badge ${cls}">${label}</span></div>
      <div class="small muted">${esc(slot.section)}</div><div>${esc(slot.what)}</div>
      ${slot.file ? `<div class="preview">${mediaPreview(fileUrl(slot.file), slot.media, slot.what)}</div><div class="small muted">${esc(slot.original_name || slot.file)} \u00b7 ${slot.source === "pipeline" ? "made by the app from real data" : slot.source === "library" ? "from your library" : "imported"}</div>` : ""}
      ${slot.kind === "broll" ? `<div class="small"><span class="badge warn">${esc(slot.label || "ILLUSTRATIVE - AI-generated")}</span></div>${shot.blocked ? `<div class="notice bad small">${esc(shot.note || "Prompt blocked.")}</div>` : `<div class="prompt">${esc(shot.prompt || "")}</div><button class="small" data-copy="${esc(shot.prompt || "")}">Copy Higgsfield prompt</button>`}` : ""}
      ${slot.kind === "headline" && shot.url ? `<div class="small">${link(shot.url, "Open the article to screenshot")}</div>` : ""}
      ${slot.kind === "talking_head" ? "" : `<div class="dropzone" data-drop="${slot.shot_n}" tabindex="0">Drop a file here or <label class="linklike">browse<input type="file" hidden data-file="${slot.shot_n}" accept=".mp4,.mov,.webm,.png,.jpg,.jpeg,.gif"></label>
        <div class="small muted">.mp4 .mov .webm .png .jpg .gif</div></div>
        <div class="row small"><label class="inline"><input type="checkbox" data-lib="${slot.shot_n}"> Save to reusable library</label>
        <button class="small" data-pick="${slot.shot_n}">Pick from library</button>
        ${slot.file ? `<button class="small" data-toggle="${slot.shot_n}" data-next="${slot.status === "ready" ? "needs_replacement" : "ready"}">${slot.status === "ready" ? "Mark needs replacement" : "Mark ready"}</button>` : ""}
        ${slot.file && slot.source !== "pipeline" ? `<button class="small" data-clear="${slot.shot_n}">Remove</button>` : ""}</div>`}
      ${boardState.drawer === slot.shot_n ? libraryDrawer(slot.shot_n) : ""}
    </article>`;
  }
  html += `</div>`;
  document.getElementById("tab").innerHTML = html;
  bindBoard();
  bindCopy();
}

function libraryDrawer(shotN) {
  if (!libraryItems.length) return `<div class="drawer small">Your library is empty. Tick \u201cSave to reusable library\u201d when you import a clip you will use again (an intro, evergreen B-roll).</div>`;
  return `<div class="drawer"><strong class="small">Reusable library</strong><div class="lib-grid">${libraryItems.map((item) => `<button class="lib-item" data-assign="${esc(item.id)}" data-shot="${shotN}">
    ${item.media === "video" ? `<video src="/api/library/file/${encodeURIComponent(item.id)}" muted preload="metadata"></video>` : `<img loading="lazy" src="/api/library/file/${encodeURIComponent(item.id)}" alt="">`}
    <span class="small">${esc(item.name)}</span></button>`).join("")}</div></div>`;
}

async function uploadAsset(shotN, file) {
  const form = new FormData();
  form.append("file", file);
  const box = document.querySelector(`[data-lib="${shotN}"]`);
  form.append("save_to_library", box && box.checked ? "true" : "false");
  try {
    boardView = await api(`/api/projects/${pid()}/shots/${shotN}/asset`, { method: "POST", body: form });
    libraryItems = (await api("/api/library")).items;
    toast("Imported");
    drawBoard();
  } catch (error) { toast(error.message); }
}

function bindBoard() {
  const base = `/api/projects/${pid()}/shots`;
  const tab = document.getElementById("tab");
  document.getElementById("missing-only").addEventListener("change", (e) => { boardState.missingOnly = e.target.checked; drawBoard(); });
  tab.querySelectorAll("[data-drop]").forEach((zone) => {
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("over"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("over"));
    zone.addEventListener("drop", (e) => { e.preventDefault(); zone.classList.remove("over"); if (e.dataTransfer.files.length) uploadAsset(zone.dataset.drop, e.dataTransfer.files[0]); });
  });
  tab.querySelectorAll("[data-file]").forEach((input) => input.addEventListener("change", () => { if (input.files.length) uploadAsset(input.dataset.file, input.files[0]); }));
  const act = (selector, fn) => tab.querySelectorAll(selector).forEach((b) => b.addEventListener("click", async () => { try { await fn(b); drawBoard(); } catch (error) { toast(error.message); } }));
  act("[data-toggle]", async (b) => { boardView = await postJson(`${base}/${b.dataset.toggle}/asset-status`, { status: b.dataset.next }); });
  act("[data-clear]", async (b) => { boardView = await postJson(`${base}/${b.dataset.clear}/asset-clear`, {}); });
  act("[data-pick]", async (b) => { boardState.drawer = boardState.drawer === Number(b.dataset.pick) ? null : Number(b.dataset.pick); });
  act("[data-assign]", async (b) => { boardView = await postJson(`${base}/${b.dataset.shot}/asset-library`, { library_id: b.dataset.assign }); boardState.drawer = null; toast("Added from your library"); });
}

// =====================================================================================
// Thumbnail workshop
// =====================================================================================
let thumbOptions = null;
const ws = { layout: "chart_hero_right_host", theme: "dark", headline: "", chart_n: 1, background: "", host: "", fact_ids: [], title: "", preset: "" };

async function drawWorkshop() {
  thumbOptions = await api("/api/thumbnails/options");
  const p = state.project;
  if (!ws.headline) ws.headline = (p.thumbnails || [""])[0];
  if (!ws.title) ws.title = (p.titles || [""])[0];
  const facts = usableFacts();
  if (!ws.fact_ids.length) ws.fact_ids = facts.slice(0, 2).map((f) => f.id);
  const layout = thumbOptions.layouts.find((l) => l.id === ws.layout) || thumbOptions.layouts[0];
  const images = Object.values((p.asset_board || {}).slots || {}).filter((s) => s.media === "image" && s.file);
  const renders = (p.thumbnail_renders || []).slice().reverse();
  let html = `<h2>Thumbnail workshop</h2><p class="sub small">1280\u00d7720, drawn on this computer. Any number comes from the fact sheet, and each thumbnail is shown at phone size so you can judge it the way most viewers will see it.</p>
    <div class="two-col"><div class="panel">
      ${thumbOptions.presets.length ? `<label for="ws-preset">Saved preset</label><div class="row" style="flex-wrap:nowrap"><select id="ws-preset"><option value="">Choose a preset...</option>${thumbOptions.presets.map((x) => `<option ${ws.preset === x.name ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select><button class="small" id="ws-preset-delete">Delete</button></div>` : ""}
      <label>Layout</label><div class="grid layouts">${thumbOptions.layouts.map((l) => `<button class="layout ${l.id === ws.layout ? "selected" : ""}" data-layout="${l.id}" aria-pressed="${l.id === ws.layout}"><strong>${esc(l.name)}</strong><span class="small">${esc(l.about)}</span></button>`).join("")}</div>
      <label>Colour theme</label><div class="row">${thumbOptions.themes.map((t) => `<button class="swatch ${t.id === ws.theme ? "selected" : ""}" data-theme-id="${t.id}" aria-pressed="${t.id === ws.theme}"><span style="background:linear-gradient(135deg, ${esc(t.top)} 60%, ${esc(t.accent)} 60%)"></span>${esc(t.name)}</button>`).join("")}</div>
      <label for="ws-headline">Headline <span class="hint">${thumbOptions.max_words} words or fewer. Type {F1} to drop in a verified number.</span></label><input type="text" id="ws-headline" value="${esc(ws.headline)}">
      ${layout.facts ? `<label>Verified number${layout.facts > 1 ? "s" : ""} to show</label>${Array.from({ length: layout.facts }, (_, i) => `<select class="ws-fact" data-i="${i}" aria-label="Fact ${i + 1}">${factOptions(ws.fact_ids[i])}</select>`).join("")}` : ""}
      <label for="ws-chart">Chart ${layout.needs_chart ? "" : "(not used by this layout)"}</label><select id="ws-chart" ${layout.needs_chart ? "" : "disabled"}>${chartOptions(ws.chart_n)}</select>
      <label for="ws-bg">Background image <span class="hint">Optional. A chart or an image from your asset board, darkened behind the text.</span></label>
      <select id="ws-bg"><option value="">Theme colour</option>${p.charts.map((c) => `<option value="charts/${esc(c.files["1920x1080"])}" ${ws.background === "charts/" + c.files["1920x1080"] ? "selected" : ""}>Chart ${c.n} image</option>`).join("")}${images.map((s) => `<option value="${esc(s.file)}" ${ws.background === s.file ? "selected" : ""}>Scene ${s.shot_n}: ${esc(s.original_name || s.file)}</option>`).join("")}</select>
      <label for="ws-host">Presenter photo <span class="hint">A transparent PNG cutout works best.</span></label>
      <div class="row" style="flex-wrap:nowrap"><select id="ws-host"><option value="">No presenter</option>${thumbOptions.hosts.map((h) => `<option ${ws.host === h.name ? "selected" : ""}>${esc(h.name)}</option>`).join("")}</select>
        <label class="btn small">Upload<input type="file" hidden id="ws-host-file" accept=".png,.jpg,.jpeg,.webp"></label>${ws.host ? '<button class="small" id="ws-host-delete">Remove</button>' : ""}</div>
      <label for="ws-title">Title shown beside it in the phone preview</label><select id="ws-title">${p.titles.map((t) => `<option ${t === ws.title ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>
      <div class="row" style="margin-top:1rem"><button class="primary" id="ws-render">Render thumbnail</button><button id="ws-save-preset">Save layout as preset</button></div>
    </div><div><div class="grid">`;
  if (!renders.length) html += `<div class="panel muted">Rendered thumbnails appear here, full size and at phone size.</div>`;
  for (const r of renders) {
    html += `<div class="panel thumb"><img class="full" loading="lazy" src="${fileUrl(r.file)}?v=${esc(r.created)}" alt="Thumbnail ${r.n}: ${esc(r.headline)}">
      <div class="row spread small"><span>${esc(r.id)} \u00b7 ${esc(r.layout)} \u00b7 ${esc(r.theme)} ${r.stale ? '<span class="badge warn">A fact changed: re-render</span>' : ""}</span>
        <span class="row"><a class="btn small" href="${fileUrl(r.file)}?download=1">Download PNG</a><button class="small" data-thumb-delete="${r.n}">Delete</button></span></div>
      <div class="phone"><div class="small muted">Phone feed size (${r.phone.width}\u00d7${r.phone.height})</div>
        <div class="feed"><img src="${fileUrl(r.phone_file)}?v=${esc(r.created)}" width="${r.phone.width}" height="${r.phone.height}" alt="">
          <div><div class="feed-title">${esc(r.phone.title)}</div><div class="small muted">${esc(r.phone.channel || "Your channel")}</div></div></div>
        <div class="small ${r.phone.legible ? "muted" : "warn-text"}">${esc(r.phone.note)}</div></div></div>`;
  }
  html += `</div></div></div>`;
  document.getElementById("workshop").innerHTML = html;
  bindWorkshop();
}

function bindWorkshop() {
  const root = document.getElementById("workshop");
  const sync = () => {
    ws.headline = document.getElementById("ws-headline").value;
    ws.chart_n = Number(document.getElementById("ws-chart").value);
    ws.background = document.getElementById("ws-bg").value;
    ws.host = document.getElementById("ws-host").value;
    ws.title = document.getElementById("ws-title").value;
    root.querySelectorAll(".ws-fact").forEach((sel) => { ws.fact_ids[Number(sel.dataset.i)] = sel.value; });
  };
  root.querySelectorAll("[data-layout]").forEach((b) => b.addEventListener("click", () => { sync(); ws.layout = b.dataset.layout; ws.preset = ""; drawWorkshop(); }));
  root.querySelectorAll("[data-theme-id]").forEach((b) => b.addEventListener("click", () => { sync(); ws.theme = b.dataset.themeId; ws.preset = ""; drawWorkshop(); }));
  document.getElementById("ws-host").addEventListener("change", () => { sync(); drawWorkshop(); });
  const preset = document.getElementById("ws-preset");
  if (preset) {
    preset.addEventListener("change", () => {
      const chosen = thumbOptions.presets.find((x) => x.name === preset.value);
      if (!chosen) return;
      sync();
      Object.assign(ws, { layout: chosen.layout, theme: chosen.theme, host: chosen.host || "", preset: chosen.name });
      drawWorkshop();
    });
    document.getElementById("ws-preset-delete").addEventListener("click", async () => { if (preset.value) { await del(`/api/thumbnails/presets/${encodeURIComponent(preset.value)}`); ws.preset = ""; drawWorkshop(); } });
  }
  document.getElementById("ws-host-file").addEventListener("change", async (e) => {
    if (!e.target.files.length) return;
    const form = new FormData();
    form.append("file", e.target.files[0]);
    try { const r = await api("/api/assets/hosts", { method: "POST", body: form }); sync(); ws.host = r.hosts[r.hosts.length - 1].name; toast("Photo added"); drawWorkshop(); } catch (error) { toast(error.message); }
  });
  const hostDelete = document.getElementById("ws-host-delete");
  if (hostDelete) hostDelete.addEventListener("click", async () => { await del(`/api/assets/hosts/${encodeURIComponent(ws.host)}`); ws.host = ""; drawWorkshop(); });
  document.getElementById("ws-render").addEventListener("click", async (e) => {
    sync();
    e.target.disabled = true;
    try {
      await postJson(`/api/projects/${pid()}/thumbnails`, { ...ws, fact_ids: ws.fact_ids.filter(Boolean) });
      state.project = await api(`/api/projects/${pid()}`);
      drawWorkshop();
    } catch (error) { e.target.disabled = false; toast(error.message); }
  });
  document.getElementById("ws-save-preset").addEventListener("click", async () => {
    sync();
    const name = window.prompt("Name this preset (layout + colour + presenter photo):", ws.preset || "");
    if (!name) return;
    try { await postJson("/api/thumbnails/presets", { name, layout: ws.layout, theme: ws.theme, host: ws.host }); ws.preset = name.trim(); toast("Preset saved"); drawWorkshop(); } catch (error) { toast(error.message); }
  });
  root.querySelectorAll("[data-thumb-delete]").forEach((b) => b.addEventListener("click", async () => {
    await del(`/api/projects/${pid()}/thumbnails/${b.dataset.thumbDelete}`);
    state.project = await api(`/api/projects/${pid()}`);
    drawWorkshop();
  }));
}

// =====================================================================================
// Explanation graphics
// =====================================================================================
const gfx = { vertical: false };

function drawGraphics() {
  const p = state.project;
  const size = gfx.vertical ? "1080x1920" : "1920x1080";
  const items = (p.graphics || []).slice().reverse();
  let html = `<h2>Explanation graphics</h2><p class="sub small">Reusable visuals built from this project's data, in 1920\u00d71080 and 1080\u00d71920. Scale, units, date and source are kept; any number you type must be on the fact sheet.</p>
    <div class="grid builders">
      <form class="panel" data-build="reveal"><h3>Line-chart reveal</h3><p class="small sub">The line draws in left to right, then holds on the final value. 5 seconds.</p>
        <select name="chart_n" aria-label="Chart">${chartOptions(1)}</select><button class="primary">Build animation</button></form>
      <form class="panel" data-build="highlight"><h3>Highlighted date + callout</h3><p class="small sub">An event line, arrow and label on the real chart. The y-axis does not change.</p>
        <select name="chart_n" aria-label="Chart">${chartOptions(1)}</select>
        <div class="row" style="flex-wrap:nowrap"><select name="when_kind" aria-label="Which point"><option value="peak">Highest point</option><option value="trough">Lowest point</option><option value="latest">Latest value</option><option value="date">A date...</option></select><input type="date" name="when_date" aria-label="Date"></div>
        <input type="text" name="label" placeholder="Short label, e.g. Highest since the pandemic" aria-label="Label"><button class="primary">Build chart</button></form>
      <form class="panel" data-build="comparison"><h3>Side-by-side comparison</h3><p class="small sub">Two verified facts, or one chart on two dates.</p>
        <select name="mode" aria-label="Compare"><option value="facts">Two facts</option><option value="dates">One chart, two dates</option></select>
        <div data-mode="facts"><select name="fact_a" aria-label="First fact">${factOptions(usableFacts()[0]?.id)}</select><select name="fact_b" aria-label="Second fact">${factOptions(usableFacts()[1]?.id)}</select></div>
        <div data-mode="dates" hidden><select name="chart_n" aria-label="Chart">${chartOptions(1)}</select><div class="row" style="flex-wrap:nowrap"><input type="date" name="date_a" aria-label="First date"><input type="date" name="date_b" aria-label="Second date"></div><p class="small muted">Leave the second date blank for the latest value. Dates snap to the nearest earlier observation.</p></div>
        <input type="text" name="title" placeholder="Card title (optional)" aria-label="Title"><button class="primary">Build card</button></form>
      <form class="panel" data-build="flow"><h3>Mechanism flow (A \u2192 B \u2192 C)</h3><p class="small sub">3 or 4 boxes. Type {F1} to show a verified number.</p>
        <input type="text" name="s1" placeholder="e.g. 10-Year Yield {F4}" aria-label="Step 1"><input type="text" name="s2" placeholder="e.g. 30-Year Mortgage {F1}" aria-label="Step 2">
        <input type="text" name="s3" placeholder="e.g. Household payment impact" aria-label="Step 3"><input type="text" name="s4" placeholder="Step 4 (optional)" aria-label="Step 4">
        <input type="text" name="title" placeholder="Diagram title (optional)" aria-label="Title"><button class="primary">Build diagram</button></form>
    </div>`;
  if (items.length) {
    html += `<div class="row spread" style="margin-top:1rem"><h3 style="margin:0">Built graphics</h3><button id="gfx-flip">${gfx.vertical ? "Show 16:9 versions" : "Show vertical versions"}</button></div><div class="grid chart-grid">`;
    for (const g of items) {
      const src = `${fileUrl(g.files[size])}?v=${esc(g.created)}`;
      html += `<div class="panel chart-card">${g.format === "mp4" ? `<video class="${gfx.vertical ? "vertical" : ""}" src="${src}" controls autoplay loop muted playsinline></video>` : `<img class="${gfx.vertical ? "vertical" : ""}" loading="lazy" src="${src}" alt="${esc(g.title)}">`}
        <h3>${esc(g.title)} ${g.stale ? '<span class="badge warn">A fact changed: rebuild</span>' : ""}</h3>
        <p class="small sub">${esc({ reveal: "Reveal animation", highlight: "Highlighted date", comparison: "Comparison card", flow: "Flow diagram" }[g.type])} \u00b7 .${esc(g.format)}${g.fact_ids.length ? ` \u00b7 uses ${g.fact_ids.map(esc).join(", ")}` : ""}</p>
        ${g.note ? `<p class="small notice">${esc(g.note)}</p>` : ""}
        <p class="small sub">Sources: ${g.sources.length ? g.sources.map((s) => link(s.url, s.name)).join("; ") : "none (no figures shown)"}</p>
        <div class="row"><a class="btn small" href="${fileUrl(g.files["1920x1080"])}?download=1">Download 1920\u00d71080</a><a class="btn small" href="${fileUrl(g.files["1080x1920"])}?download=1">Download 1080\u00d71920</a><button class="small" data-gfx-delete="${g.n}">Delete</button></div></div>`;
    }
    html += `</div>`;
  }
  const root = document.getElementById("graphics");
  root.innerHTML = html;
  const flip = document.getElementById("gfx-flip");
  if (flip) flip.addEventListener("click", () => { gfx.vertical = !gfx.vertical; drawGraphics(); });
  const mode = root.querySelector('[name="mode"]');
  mode.addEventListener("change", () => root.querySelectorAll("[data-mode]").forEach((el) => { el.hidden = el.dataset.mode !== mode.value; }));
  root.querySelectorAll("form[data-build]").forEach((form) => form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const f = Object.fromEntries(new FormData(form).entries());
    const type = form.dataset.build;
    let body = { type };
    if (type === "reveal") body.chart_n = Number(f.chart_n);
    if (type === "highlight") body = { ...body, chart_n: Number(f.chart_n), when: f.when_kind === "date" ? f.when_date : f.when_kind, label: f.label };
    if (type === "comparison") body = f.mode === "facts" ? { ...body, title: f.title, fact_ids: [f.fact_a, f.fact_b] } : { ...body, title: f.title, chart_n: Number(f.chart_n), dates: [f.date_a, f.date_b || "latest"] };
    if (type === "flow") body = { ...body, title: f.title, steps: [f.s1, f.s2, f.s3, f.s4].filter((s) => s && s.trim()) };
    const button = form.querySelector("button");
    const label = button.textContent;
    button.disabled = true;
    button.textContent = "Building...";
    try {
      await postJson(`/api/projects/${pid()}/graphics`, body);
      state.project = await api(`/api/projects/${pid()}`);
      drawGraphics();
      toast("Graphic built");
    } catch (error) { button.disabled = false; button.textContent = label; toast(error.message); }
  }));
  root.querySelectorAll("[data-gfx-delete]").forEach((b) => b.addEventListener("click", async () => {
    await del(`/api/projects/${pid()}/graphics/${b.dataset.gfxDelete}`);
    state.project = await api(`/api/projects/${pid()}`);
    drawGraphics();
  }));
}

// =====================================================================================
// "What changed since I recorded?"
// =====================================================================================
async function drawChanges() {
  const base = `/api/projects/${pid()}`;
  const { frozen, report } = await api(`${base}/fact-changes`);
  const names = (list, fn) => list.map(fn).join(", ");
  let html = `<div class="panel changes"><div class="row spread"><div><h2 style="margin:0">What changed since I recorded?</h2>
      <p class="small sub" style="margin:.2rem 0 0">${frozen ? `Facts frozen ${esc(frozen.frozen_at.replace("T", " "))} (${esc(frozen.reason)}). ${frozen.facts} facts saved as recorded.` : "Freeze the facts when you record. Later, check whether any number has updated before you publish."}</p></div>
      <div class="row"><button id="freeze">${frozen ? "Freeze again" : "Freeze facts now"}</button><button class="primary" id="check" ${frozen ? "" : "disabled"}>Check for changes</button></div></div>`;
  if (report) {
    html += `<p><strong>${esc(report.summary)}</strong> <span class="small muted">Checked ${esc(report.checked_at.replace("T", " "))}.</span></p>`;
    const open = report.changes.filter((c) => !c.decision);
    for (const c of report.changes) {
      const a = c.affected;
      html += `<div class="change"><div class="row spread"><strong>${esc(c.fact_id)} \u00b7 ${esc(c.label)}</strong><span class="badge ${c.kind === "revised" ? "warn" : "plain"}">${c.kind === "revised" ? "Revised" : "New data"}</span></div>
        <div class="values"><span><small>As recorded</small>${esc(c.frozen_value)}<small>${esc(c.frozen_as_of)}</small></span><span class="arrow">\u2192</span><span><small>Now</small>${esc(c.live_value)}<small>${esc(c.live_as_of)}</small></span>${c.delta_text ? `<span><small>Change</small>${esc(c.delta_text)}</span>` : ""}</div>
        <div class="small sub">Used by: ${[a.cards.length ? `cards (${names(a.cards, (x) => esc(x.title))})` : "", a.charts.length ? `charts (${names(a.charts, (x) => "Chart " + x.n)})` : "", a.graphics.length ? `graphics (${names(a.graphics, (x) => esc(x.title))})` : "", a.thumbnails.length ? `thumbnails (${names(a.thumbnails, (x) => "thumb " + x.n)})` : "", a.description_lines.length ? `description lines ${names(a.description_lines, (x) => x.line)}` : ""].filter(Boolean).join(" \u00b7 ") || "nothing else in this project"}</div>
        ${c.decision ? `<div class="small"><span class="badge good">${c.decision === "keep_frozen" ? "Kept as recorded, date note added" : "New value accepted, cards flagged for retake"}</span></div>`
          : `<div class="row small choice"><label class="inline"><input type="radio" name="d-${esc(c.key)}" value="keep_frozen" data-key="${esc(c.key)}"> Keep frozen as-recorded value (add date note)</label>
             <label class="inline"><input type="radio" name="d-${esc(c.key)}" value="accept_new" data-key="${esc(c.key)}"> Accept new value and flag affected cards for retake</label></div>`}</div>`;
    }
    if (open.length) html += `<div class="row"><button class="primary" id="apply">Apply my choices</button><span class="small muted">Your card wording is never rewritten. The package as it stands is saved under versions/ first.</span></div>`;
    if (report.unavailable.length) html += `<p class="small muted">${report.unavailable.length} fact(s) could not be re-fetched and were left as recorded.</p>`;
    if (report.new_headlines.length) html += `<p class="small">New headlines on this theme: ${report.new_headlines.map((h) => link(h.url, h.title)).join("; ")}</p>`;
  }
  html += `</div>`;
  const root = document.getElementById("changes");
  root.innerHTML = html;
  const busy = async (button, text, fn) => { const old = button.textContent; button.disabled = true; button.textContent = text; try { await fn(); } catch (error) { toast(error.message); button.disabled = false; button.textContent = old; } };
  document.getElementById("freeze").addEventListener("click", (e) => busy(e.target, "Freezing...", async () => { await postJson(`${base}/freeze-facts`, {}); toast("Facts frozen"); await drawChanges(); }));
  document.getElementById("check").addEventListener("click", (e) => busy(e.target, "Re-fetching the data...", async () => { await postJson(`${base}/check-changes`, {}); await drawChanges(); }));
  const apply = document.getElementById("apply");
  if (apply) apply.addEventListener("click", (e) => busy(e.target, "Applying...", async () => {
    const decisions = {};
    root.querySelectorAll("input[type=radio]:checked").forEach((r) => { decisions[r.dataset.key] = r.value; });
    if (!Object.keys(decisions).length) throw new Error("Choose an option for at least one fact first.");
    await postJson(`${base}/resolve-changes`, { decisions });
    toast("Applied");
    await refreshProject();
  }));
}

// =====================================================================================
// Clip plan: recording, transcription, spoken fact-check, dead air, 9:16 shorts
// =====================================================================================
async function tabClips() {
  const p = state.project;
  const base = `/api/projects/${pid()}`;
  const caps = await api("/api/capabilities");
  const plan = p.clips;
  const check = p.spoken_check;
  let html = `<div class="panel"><h2 style="margin-top:0">Your recording</h2>
    <p class="sub small">Upload the recording (.mp4 .mov .mkv .wav .mp3) to transcribe it here, or upload a transcript (.srt or .txt) you already have. Everything stays on this computer.</p>
    <div class="row"><input type="file" id="media" accept=".mp4,.mov,.mkv,.wav,.mp3,.srt,.txt" aria-label="Recording or transcript"><button class="primary" id="upload">Add file</button></div>
    <div class="row" style="margin-top:.5rem;flex-wrap:nowrap"><input type="text" id="media-path" placeholder="Or paste the recording's path, e.g. D:\\Recordings\\take1.mp4 (no copying, good for big files)" aria-label="Recording path"><button id="use-path">Use this file</button></div>
    ${p.recording ? `<p class="small"><strong>Recording:</strong> ${esc(p.recording.name)} ${p.recording.duration ? `\u00b7 ${clockText(p.recording.duration)}` : ""} \u00b7 ${p.recording.has_video ? "video" : "audio only"}</p>
      <div class="row"><button id="transcribe" ${caps.faster_whisper ? "" : "disabled"}>Transcribe on this computer</button>
      <label class="inline small">Strip silences longer than <input type="text" id="silence" value="0.45" style="width:4.5rem" aria-label="Seconds"> s</label><button id="dead-air">Strip dead air</button></div>
      <p class="small muted">${esc(caps.transcribe_note)} ${esc(caps.ffmpeg_note)}</p><div id="job"></div>` : `<p class="small muted">${esc(caps.transcribe_note)}</p>`}
    ${p.dead_air ? `<div class="notice info small"><strong>Dead air:</strong> ${p.dead_air.silences} silence(s) longer than ${p.dead_air.min_silence} s, ${p.dead_air.removed_seconds} s removed of ${p.dead_air.original_seconds} s.
      ${p.dead_air.file ? `<a href="${fileUrl(p.dead_air.file)}?download=1">Download the tightened file</a> \u00b7 ` : ""}<a href="${fileUrl(p.dead_air.cut_list)}?download=1">cut list</a>. ${esc(p.dead_air.note)}</div>` : ""}
  </div>`;
  if (check) {
    html += `<div class="panel" style="margin-top:1rem"><h2 style="margin-top:0">Spoken fact-check</h2><p><strong>${esc(check.summary)}</strong></p>`;
    if (!check.flags.length) html += `<p class="small muted">Every number you said is on the fact sheet.</p>`;
    else {
      html += `<div class="table-wrap"><table><thead><tr><th>Time</th><th>You said</th><th>Check</th><th>In context</th></tr></thead><tbody>`;
      for (const f of check.flags) html += `<tr><td class="id">${esc(f.time)}</td><td><strong>${esc(f.spoken)}</strong></td><td><span class="badge ${f.status === "unverified" ? "bad" : "warn"}">${f.status === "unverified" ? "Not on fact sheet" : "Rounded"}</span><div class="note">${esc(f.note)}</div></td><td class="small">${esc(f.text)}</td></tr>`;
      html += `</tbody></table></div>`;
    }
    html += `</div>`;
  }
  if (plan) {
    html += `<h2>Clip plan</h2><p class="sub small">From <strong>${esc(plan.file || "transcript")}</strong> \u00b7 picked by ${plan.source === "llm" ? "the wording engine, validated against the transcript" : "the built-in rules"}.</p>`;
    if (plan.message) html += `<div class="notice small">${esc(plan.message)}</div>`;
    html += `<div class="grid">`;
    for (const clip of plan.clips) {
      const short = (p.shorts || []).find((s) => s.clip === clip.n);
      html += `<div class="panel"><div class="row spread"><h3 style="margin:0">Clip ${clip.n}: ${esc(clip.start)} to ${esc(clip.end)}${clip.estimated_times ? " (estimated)" : ""}</h3><span class="chip">${clip.duration_seconds} s</span></div>
        <p><strong>Caption hook:</strong> ${esc(clip.caption)} <button class="small" data-copy="${esc(clip.caption)}">Copy</button></p>
        ${clip.why ? `<p class="small sub">${esc(clip.why)}</p>` : ""}${(clip.notes || []).map((n) => `<div class="notice small">${esc(n)}</div>`).join("")}
        <blockquote>${esc(clip.text)}</blockquote>
        <div class="row small"><select data-short-chart="${clip.n}" aria-label="Chart for this short"><option value="">No chart (full-height camera)</option>${chartOptions(short ? short.chart_n : null)}</select><button data-short="${clip.n}">Export 9:16 Short (.mp4)</button></div>
        ${short ? `<div class="small" style="margin-top:.4rem">${short.file ? `<a href="${fileUrl(short.file)}?download=1">Download ${esc(short.file.split("/").pop())}</a> \u00b7 ` : ""}<a href="${fileUrl(short.captions_file)}?download=1">captions .srt</a>${short.note ? `<div class="notice small">${esc(short.note)}</div>` : ""}</div>` : ""}</div>`;
    }
    html += `</div>`;
  }
  document.getElementById("tab").innerHTML = html;

  const sendTranscript = async (file) => {
    const form = new FormData();
    form.append("file", file);
    state.project = await api(`${base}/transcript`, { method: "POST", body: form });
  };
  document.getElementById("upload").addEventListener("click", async (e) => {
    const input = document.getElementById("media");
    if (!input.files.length) return toast("Choose a file first");
    const file = input.files[0];
    e.target.disabled = true;
    e.target.textContent = "Adding...";
    try {
      if (/\.(srt|txt)$/i.test(file.name)) await sendTranscript(file);
      else { const form = new FormData(); form.append("file", file); await api(`${base}/recording`, { method: "POST", body: form }); state.project = await api(base); }
      drawProject();
    } catch (error) { e.target.disabled = false; e.target.textContent = "Add file"; toast(error.message); }
  });
  document.getElementById("use-path").addEventListener("click", async () => {
    try { await postJson(`${base}/recording-path`, { path: document.getElementById("media-path").value }); await refreshProject(); } catch (error) { toast(error.message); }
  });
  const transcribeButton = document.getElementById("transcribe");
  if (transcribeButton) transcribeButton.addEventListener("click", async () => {
    try { await postJson(`${base}/transcribe`, {}); } catch (error) { return toast(error.message); }
    transcribeButton.disabled = true;
    const job = document.getElementById("job");
    state.poll = setInterval(async () => {
      const progress = await api(`${base}/transcribe/progress`);
      job.innerHTML = `<div class="small"><span class="spinner"></span>${esc(progress.steps[progress.steps.length - 1] || "Working")}</div>`;
      if (progress.done) {
        clearInterval(state.poll);
        if (progress.error) { job.innerHTML = `<div class="notice bad small">${esc(progress.error)}</div>`; transcribeButton.disabled = false; } else refreshProject();
      }
    }, 1000);
  });
  const deadAir = document.getElementById("dead-air");
  if (deadAir) deadAir.addEventListener("click", async () => {
    deadAir.disabled = true;
    deadAir.textContent = "Scanning...";
    try { await postJson(`${base}/strip-dead-air`, { min_silence: Number(document.getElementById("silence").value) }); await refreshProject(); }
    catch (error) { deadAir.disabled = false; deadAir.textContent = "Strip dead air"; toast(error.message); }
  });
  document.querySelectorAll("[data-short]").forEach((b) => b.addEventListener("click", async () => {
    const chart = document.querySelector(`[data-short-chart="${b.dataset.short}"]`).value;
    b.disabled = true;
    b.textContent = "Exporting...";
    try { await postJson(`${base}/clips/${b.dataset.short}/short`, { chart_n: chart ? Number(chart) : null }); await refreshProject(); }
    catch (error) { b.disabled = false; b.textContent = "Export 9:16 Short (.mp4)"; toast(error.message); }
  }));
}

// =====================================================================================
// Learning log
// =====================================================================================
async function tabLearning() {
  const base = `/api/projects/${pid()}`;
  const [record, summary] = await Promise.all([api(`${base}/learning-log`), api("/api/learning-log")]);
  const num = (key, label, hint = "") => `<div><label for="ll-${key}">${label}${hint ? `<span class="hint">${hint}</span>` : ""}</label><input type="text" inputmode="decimal" id="ll-${key}" value="${record[key] ?? ""}"></div>`;
  const layouts = ["", "chart_hero_right_host", "split_comparison", "big_stat_badge", "minimal_editorial"];
  let html = `<p class="sub">What you made, how long it took and how it did. Fill in the results after publishing. Patterns below are plain counts and medians of your own episodes: there is no viral score.</p>
    <div class="panel"><h2 style="margin-top:0">This episode</h2>
      <label for="ll-hook_text">Hook as delivered</label><textarea id="ll-hook_text" rows="3">${esc(record.hook_text)}</textarea>
      <div class="form-grid">
        <div><label for="ll-final_title">Final published title</label><input type="text" id="ll-final_title" value="${esc(record.final_title)}"></div>
        <div><label for="ll-thumbnail_layout">Thumbnail layout</label><select id="ll-thumbnail_layout">${layouts.map((l) => `<option value="${l}" ${record.thumbnail_layout === l ? "selected" : ""}>${l || "Not recorded"}</option>`).join("")}</select></div>
        <div><label for="ll-thumbnail_preset">Thumbnail preset</label><input type="text" id="ll-thumbnail_preset" value="${esc(record.thumbnail_preset)}"></div>
        <div><label for="ll-topic_family">Topic family</label><input type="text" id="ll-topic_family" value="${esc(record.topic_family)}"></div>
        <div><label for="ll-published_date">Published</label><input type="date" id="ll-published_date" value="${esc(record.published_date)}"></div>
        <div><label class="inline" style="margin-top:2rem"><input type="checkbox" id="ll-open_lane" ${record.open_lane ? "checked" : ""}> Open-lane topic</label></div>
        ${num("prep_minutes", "Prep (minutes)")}${num("recording_minutes", "Recording (minutes)")}${num("editing_minutes", "Editing (minutes)")}
        ${num("views_48h", "Views after 48 hours")}${num("views_7d", "Views after 7 days")}${num("ctr_pct", "Click-through rate (%)")}${num("avg_view_duration_sec", "Average view duration (seconds)")}
      </div>
      <label for="ll-retention_notes">Retention notes</label><textarea id="ll-retention_notes" rows="2" placeholder="Where did people drop off?">${esc(record.retention_notes)}</textarea>
      <label for="ll-audience_comments_notes">Audience comments</label><textarea id="ll-audience_comments_notes" rows="2" placeholder="What did viewers ask for or push back on?">${esc(record.audience_comments_notes)}</textarea>
      <div class="row" style="margin-top:1rem"><button class="primary" id="ll-save">Save to learning log</button>${record.total_minutes != null ? `<span class="small muted">Total build time: ${record.total_minutes} minutes</span>` : ""}</div>
    </div>
    <h2>What your past episodes show</h2><p class="small sub">${esc(summary.note)}</p>`;
  if (!summary.observations.length) html += `<div class="notice info small">Log results for an episode to start seeing patterns.</div>`;
  else html += `<div class="grid cards">${summary.observations.map((o) => `<div class="panel"><div class="small"><span class="badge ${o.tentative ? "warn" : "good"}">${esc(o.label)}</span></div><h3>${esc(o.title)}</h3><p>${esc(o.text)}</p></div>`).join("")}</div>`;
  if (summary.episodes.length) {
    const cell = (v, suffix = "") => (v == null || v === "" ? '<span class="muted">\u2013</span>' : `${Number(v).toLocaleString()}${suffix}`);
    html += `<div class="panel table-wrap" style="margin-top:1rem"><table><thead><tr><th>Episode</th><th>Hook</th><th>Thumbnail</th><th>Family</th><th>Build</th><th>48 h</th><th>7 d</th><th>CTR</th><th>Avg view</th></tr></thead><tbody>
      ${summary.episodes.map((e) => `<tr><td><a href="#/project/${encodeURIComponent(e.project_id)}">${esc(e.final_title || e.topic)}</a><div class="note">${esc(e.published_date || (e.created || "").slice(0, 10))}${e.open_lane ? " \u00b7 open lane" : ""}</div></td>
        <td class="small">${esc(e.hook_structure || "")}</td><td class="small">${esc(e.thumbnail_layout || "")}</td><td class="small">${esc(e.topic_family || "")}</td>
        <td>${cell(e.total_minutes, " min")}</td><td>${cell(e.views_48h)}</td><td>${cell(e.views_7d)}</td><td>${cell(e.ctr_pct, "%")}</td><td>${cell(e.avg_view_duration_sec, " s")}</td></tr>`).join("")}</tbody></table></div>`;
  }
  document.getElementById("tab").innerHTML = html;
  document.getElementById("ll-save").addEventListener("click", async () => {
    const keys = ["hook_text", "final_title", "thumbnail_layout", "thumbnail_preset", "topic_family", "published_date", "prep_minutes", "recording_minutes", "editing_minutes", "views_48h", "views_7d", "ctr_pct", "avg_view_duration_sec", "retention_notes", "audience_comments_notes"];
    const values = Object.fromEntries(keys.map((k) => [k, document.getElementById(`ll-${k}`).value]));
    values.open_lane = document.getElementById("ll-open_lane").checked;
    try { await postJson(`${base}/learning-log`, values); toast("Saved to the learning log"); tabLearning(); } catch (error) { toast(error.message); }
  });
}
