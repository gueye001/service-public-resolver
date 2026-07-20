const state = {
  history: [],
  filter: "all",
  stats: null,
};

const el = (id) => document.getElementById(id);

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function fmtTime(iso) {
  const d = new Date(iso);
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

// ---------- Navigation ----------
document.querySelectorAll(".nav-item").forEach((item) => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((i) => i.classList.remove("active"));
    item.classList.add("active");
    const view = item.dataset.view;
    document.querySelectorAll(".view").forEach((v) => (v.hidden = true));
    el(`view-${view}`).hidden = false;
  });
});

// ---------- Tabs (filter) ----------
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    state.filter = tab.dataset.filter;
    renderList();
  });
});

// ---------- Stats ----------
async function loadStats() {
  const res = await fetch("/api/stats");
  const s = await res.json();
  state.stats = s;

  el("stat-grid").innerHTML = `
    <div class="stat-tile"><div class="value">${(s.macro_f1 * 100).toFixed(0)}%</div><div class="label">Précision globale</div></div>
    <div class="stat-tile"><div class="value">${(s.f1_known * 100).toFixed(0)}%</div><div class="label">Précision sur les questions déjà connues</div></div>
    <div class="stat-tile"><div class="value">${(s.f1_novel * 100).toFixed(0)}%</div><div class="label">Précision sur les questions nouvelles</div></div>
    <div class="stat-tile"><div class="value">${(s.recall_at_k * 100).toFixed(0)}%</div><div class="label">Bonne réponse trouvée dans le top ${s.k}</div></div>
    <div class="stat-tile"><div class="value">${s.n_test.toLocaleString("fr-FR")}</div><div class="label">Questions testées</div></div>
  `;

  el("mini-stats").innerHTML = `
    <div class="mini-stat"><span class="k">Précision globale</span><span class="v">${(s.macro_f1 * 100).toFixed(0)}%</span></div>
    <div class="mini-stat"><span class="k">Top ${s.k} correct</span><span class="v">${(s.recall_at_k * 100).toFixed(0)}%</span></div>
  `;

  el("ask-hint").textContent = "Réponse instantanée si une question officielle proche existe déjà.";
}

// ---------- Resolve ----------
el("ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = el("question-input");
  const question = input.value.trim();
  if (!question) return;

  const btn = el("ask-btn");
  btn.disabled = true;
  btn.querySelector(".btn-label").textContent = "Analyse en cours…";
  btn.querySelector(".spinner").hidden = false;

  try {
    const res = await fetch("/api/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    state.history.unshift(data);
    renderResult(data);
    renderList();
    renderActivity();
    input.value = "";
  } catch (err) {
    el("result-slot").innerHTML = `<div class="result-card">Erreur : impossible de contacter l'agent.</div>`;
  } finally {
    btn.disabled = false;
    btn.querySelector(".btn-label").textContent = "Diagnostiquer";
    btn.querySelector(".spinner").hidden = true;
  }
});

function renderResult(data) {
  const known = data.status === "known";
  const pill = known
    ? `<span class="pill pill-known">Connu</span>`
    : `<span class="pill pill-novel">Nouveau</span>`;
  const themePill = data.theme ? `<span class="pill pill-theme">${escapeHtml(data.theme)}</span>` : "";

  const answer = known
    ? `<p class="result-answer">${escapeHtml(data.reponse)}</p>`
    : `<p class="result-answer novel">Aucune réponse officielle suffisamment proche n'a été trouvée. Ce cas doit être transmis à un agent humain.</p>`;

  const candidates = data.candidates.map((c, i) => `
    <div class="candidate-row">
      <div class="cq">${i + 1}. ${escapeHtml(c.question)}</div>
      <div class="cmeta">${escapeHtml(c.theme)}</div>
    </div>
  `).join("");

  el("result-slot").innerHTML = `
    <div class="result-card">
      <div class="result-head">
        ${pill}
        ${themePill}
        <span class="conf">fiabilité : ${(data.confidence * 100).toFixed(0)}%</span>
      </div>
      ${answer}
      <button class="candidates-toggle" id="toggle-candidates">Voir des questions similaires déjà traitées</button>
      <div class="candidates-list" id="candidates-list">${candidates}</div>
    </div>
  `;
  el("toggle-candidates").addEventListener("click", () => {
    el("candidates-list").classList.toggle("open");
  });
}

function renderList() {
  const listEl = el("ticket-list");
  const items = state.history.filter((h) => state.filter === "all" || h.status === state.filter);

  if (items.length === 0) {
    listEl.innerHTML = `
      <div class="empty-state">
        <svg viewBox="0 0 48 48" fill="none"><rect x="8" y="10" width="32" height="28" rx="3" stroke="currentColor" stroke-width="1.6"/><path d="M15 18h18M15 24h18M15 30h11" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
        <p>Aucune question ${state.filter !== "all" ? "dans cette catégorie" : "posée pour l'instant"}.</p>
      </div>`;
    return;
  }

  listEl.innerHTML = items.map((h) => {
    const pill = h.status === "known"
      ? `<span class="pill pill-known">Connu</span>`
      : `<span class="pill pill-novel">Nouveau</span>`;
    const themePill = h.theme ? `<span class="pill pill-theme">${escapeHtml(h.theme)}</span>` : "";
    const answerPreview = h.status === "known"
      ? escapeHtml((h.reponse || "").slice(0, 140)) + ((h.reponse || "").length > 140 ? "…" : "")
      : "Escaladé vers un agent humain.";
    return `
      <div class="ticket-card">
        <div class="ticket-top">${pill}${themePill}</div>
        <p class="ticket-question">${escapeHtml(h.question)}</p>
        <p class="ticket-answer">${answerPreview}</p>
        <div class="ticket-meta">fiabilité ${(h.confidence * 100).toFixed(0)}% · ${fmtTime(h.timestamp)}</div>
      </div>`;
  }).join("");
}

function renderActivity() {
  const listEl = el("activity-list");
  const items = state.history.slice(0, 6);
  if (items.length === 0) {
    listEl.innerHTML = `<p class="muted-empty">Rien à afficher.</p>`;
    return;
  }
  listEl.innerHTML = items.map((h) => `
    <div class="activity-item">
      <div class="aq">${escapeHtml((h.question || "").slice(0, 60))}${(h.question || "").length > 60 ? "…" : ""}</div>
      <div class="at">${h.status === "known" ? "Connu" : "Nouveau"} · ${fmtTime(h.timestamp)}</div>
    </div>
  `).join("");
}

loadStats();
