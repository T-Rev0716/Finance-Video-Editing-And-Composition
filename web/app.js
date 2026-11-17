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
  let html = `<h1>Pick today's topic</h1>`;

  const missing = [];
  if (!keys.fred) missing.push("FRED key (release dates will be left blank; the data itself still loads)");
  if (!keys.llm) missing.push("LLM key (wording will use the built-in templates)");
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

const TABS = [["facts", "Fact sheet"], ["charts", "Charts"], ["outline", "Outline"], ["shots", "Shot list"], ["titles", "Titles & thumbnails"], ["clips", "Clip plan"], ["compliance", "Compliance"], ["description", "Description"]];

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
  ({ facts: tabFacts, charts: tabCharts, outline: tabOutline, shots: tabShots, titles: tabTitles, clips: tabClips, compliance: tabCompliance, description: tabDescription })[state.tab]();
  app.querySelectorAll("[data-copy]").forEach((b) => b.addEventListener("click", () => copyText(b.dataset.copy)));
}

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
  document.getElementById("tab").innerHTML = html;
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
      <p class="small sub">Data through ${esc(chart.data_through)}. Sources: ${chart.series.map((s) => link(s.source_url, s.source_name)).join("; ")}</p>
      <div class="row"><a class="btn small" href="${base}${esc(chart.files["1920x1080"])}?download=1">Download 1920x1080</a>
      <a class="btn small" href="${base}${esc(chart.files["1080x1920"])}?download=1">Download 1080x1920</a></div></div>`;
  }
  html += `</div>`;
  document.getElementById("tab").innerHTML = html;
  document.getElementById("flip").addEventListener("click", () => { state.verticalCharts = !state.verticalCharts; drawProject(); });
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

function tabShots() {
  const p = state.project;
  let html = `<p class="sub">Scene by scene. AI B-roll is always generic and labelled illustrative: never a real person, never a re-creation of a real event.</p>
    <div class="panel table-wrap"><table><thead><tr><th>#</th><th>Shot</th><th>What</th></tr></thead><tbody>`;
  let section = null;
  for (const shot of p.shots) {
    if (shot.section !== section) { section = shot.section; html += `<tr class="group-row"><td colspan="3">${esc(section)}</td></tr>`; }
    const cls = shot.type.startsWith("CHART") ? "good" : shot.type.startsWith("B-ROLL") ? "warn" : "plain";
    let detail = `<div>${esc(shot.what)}</div>`;
    if (shot.file) detail += `<div class="note">File: charts/${esc(shot.file)}</div>`;
    if (shot.url) detail += `<div class="note">${link(shot.url, "Open the article to screenshot")}</div>`;
    if (shot.type === "B-ROLL (AI)") {
      detail += `<div class="note"><span class="badge warn">${esc(shot.label)}</span></div>`;
      detail += shot.blocked ? "" : `<div class="prompt">${esc(shot.prompt)}</div><button class="small" data-copy="${esc(shot.prompt)}">Copy Higgsfield prompt</button>`;
    }
    if (shot.note) detail += `<div class="note">${esc(shot.note)}</div>`;
    html += `<tr><td class="id">${shot.n}</td><td><span class="badge ${cls}">${esc(shot.type)}</span></td><td>${detail}</td></tr>`;
  }
  html += `</tbody></table></div>`;
  document.getElementById("tab").innerHTML = html;
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
  html += `</div></div>`;
  document.getElementById("tab").innerHTML = html;
}

function tabClips() {
  const p = state.project;
  const plan = p.clips;
  let html = `<div class="panel"><h2 style="margin-top:0">Upload your recorded video's transcript</h2>
    <p class="sub small">A .srt gives exact timestamps. A .txt works too; without timestamps the times are estimated.</p>
    <div class="row"><input type="file" id="transcript" accept=".srt,.txt" aria-label="Transcript file"><button class="primary" id="upload">Suggest clips</button></div></div>`;
  if (plan) {
    html += `<p class="sub small" style="margin-top:1rem">From <strong>${esc(plan.file || "transcript")}</strong> · picked by ${plan.source === "llm" ? "the LLM, validated against the transcript" : "the built-in rules"}.</p>`;
    if (plan.message) html += `<div class="notice small">${esc(plan.message)}</div>`;
    html += `<div class="grid">`;
    for (const clip of plan.clips) {
      html += `<div class="panel"><div class="row spread"><h3 style="margin:0">Clip ${clip.n}: ${esc(clip.start)} to ${esc(clip.end)}${clip.estimated_times ? " (estimated)" : ""}</h3><span class="chip">${clip.duration_seconds} s</span></div>
        <p><strong>Caption hook:</strong> ${esc(clip.caption)} <button class="small" data-copy="${esc(clip.caption)}">Copy</button></p>
        ${clip.why ? `<p class="small sub">${esc(clip.why)}</p>` : ""}
        ${(clip.notes || []).map((n) => `<div class="notice small">${esc(n)}</div>`).join("")}
        <blockquote>${esc(clip.text)}</blockquote></div>`;
    }
    html += `</div>`;
  }
  document.getElementById("tab").innerHTML = html;
  document.getElementById("upload").addEventListener("click", async () => {
    const input = document.getElementById("transcript");
    if (!input.files.length) return toast("Choose a .srt or .txt file first");
    const form = new FormData();
    form.append("file", input.files[0]);
    const button = document.getElementById("upload");
    button.disabled = true;
    button.textContent = "Reading transcript...";
    try {
      state.project = await api(`/api/projects/${encodeURIComponent(p.id)}/transcript`, { method: "POST", body: form });
      drawProject();
    } catch (error) {
      button.disabled = false;
      button.textContent = "Suggest clips";
      toast(error.message);
    }
  });
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
  ["CHANNEL_NAME", "Channel name", "Optional. Added to the description and the subscribe line."],
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
  html += `<label for="CHART_THEME">Chart style<span class="hint">Dark suits most video edits.</span></label>
    <select id="CHART_THEME"><option value="dark" ${settings.CHART_THEME.value === "dark" ? "selected" : ""}>Dark</option><option value="light" ${settings.CHART_THEME.value === "light" ? "selected" : ""}>Light</option></select>
    <label for="DISCLAIMER">Disclaimer<span class="hint">Goes at the end of every description. Keep the words "education" and "not investment advice".</span></label>
    <textarea id="DISCLAIMER">${esc(settings.DISCLAIMER.value)}</textarea>
    <div class="row" style="margin-top:1rem"><button class="primary" id="save">Save settings</button><button id="test-fred">Test FRED connection</button><span id="test-result" class="small"></span></div></div>`;
  app.innerHTML = html;

  document.getElementById("save").addEventListener("click", async () => {
    const values = {};
    [...FIELDS.map((f) => f[0]), "CHART_THEME", "DISCLAIMER"].forEach((key) => { values[key] = document.getElementById(key).value; });
    try { await postJson("/api/settings", { values }); toast("Settings saved"); renderSettings(); } catch (error) { toast(error.message); }
  });
  app.querySelectorAll("[data-clear]").forEach((b) => b.addEventListener("click", async () => {
    await postJson("/api/settings", { values: {}, clear: [b.dataset.clear] });
    toast("Key removed");
    renderSettings();
  }));
  document.getElementById("test-fred").addEventListener("click", async () => {
    const out = document.getElementById("test-result");
    out.textContent = "Testing...";
    try { const r = await postJson("/api/settings/test-fred", {}); out.textContent = r.message; } catch (error) { out.textContent = error.message; }
  });
}
