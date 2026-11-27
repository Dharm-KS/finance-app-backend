/* Finance Twin web app: uses only the public /api/v1 APIs (the same calls the mobile app makes). */
(() => {
  "use strict";

  const API = "/api/v1";
  const $ = (id) => document.getElementById(id);
  const store = {
    get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
    set: (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } },
  };

  const state = { token: store.get("ft_token"), user: null, flow: "login", clientToken: null, clientExp: 0, currency: "INR", polling: null };

  // ---- helpers ---------------------------------------------------------------------------------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const money = (v, cur = state.currency) => {
    if (v == null) return "–";
    try { return new Intl.NumberFormat(cur === "INR" ? "en-IN" : undefined, { style: "currency", currency: cur, maximumFractionDigits: 0 }).format(v); }
    catch { return `${cur} ${Math.round(v).toLocaleString()}`; }
  };
  const fmtMetric = (m) => {
    if (m.value == null) return "–";
    if (/^[A-Z]{3}$/.test(m.unit || "")) return money(m.value, m.unit);
    if (m.unit === "%") return `${Number(m.value).toFixed(1)}%`;
    if (m.unit === "months") return `${m.value} mo`;
    return String(m.value);
  };
  const ACRONYMS = { RSU: "RSU" };
  const label = (s) => ACRONYMS[s] || String(s || "").replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
  const show = (el, on = true) => el.classList.toggle("hidden", !on);
  let toastTimer;
  const toast = (msg) => { const t = $("toast"); t.textContent = msg; show(t); clearTimeout(toastTimer); toastTimer = setTimeout(() => show(t, false), 2600); };

  class ApiError extends Error {
    constructor(body, status) { super(body?.message || `Request failed (${status})`); this.code = body?.error_code; this.status = status; }
  }

  async function clientToken() {
    if (state.clientToken && Date.now() < state.clientExp - 60_000) return state.clientToken;
    const body = { client_id: $("client-id").value.trim(), client_secret: $("client-secret").value };
    store.set("ft_client_id", body.client_id); store.set("ft_client_secret", body.client_secret);
    const data = await call("POST", "/auth/token", body, { auth: false });
    state.clientToken = data.access_token; state.clientExp = Date.parse(data.expires_at);
    return state.clientToken;
  }

  async function call(method, path, body, { auth = "user" } = {}) {
    const headers = { "Content-Type": "application/json" };
    if (auth === "client") headers.Authorization = `Bearer ${await clientToken()}`;
    else if (auth === "user" && state.token) headers.Authorization = `Bearer ${state.token}`;
    const res = await fetch(API + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
    let json = null;
    try { json = await res.json(); } catch { /* empty body */ }
    if (!res.ok || !json?.success) {
      if (res.status === 401 && auth === "user") { logout(true); }
      throw new ApiError(json, res.status);
    }
    return json.data;
  }

  // ---- sign in ---------------------------------------------------------------------------------
  function showLogin() {
    show($("login-view")); show($("app-view"), false); show($("onboard-view"), false); show($("logout-btn"), false);
    $("user-label").textContent = "";
    $("client-id").value = store.get("ft_client_id") || "finance-mobile-app";
    $("client-secret").value = store.get("ft_client_secret") || "";
    if (!$("client-secret").value) $("login-view").querySelector("details").open = true;
  }

  function loginMsg(text, error = false) { const m = $("login-msg"); m.textContent = text; m.classList.toggle("error", error); }

  $("send-otp-btn").onclick = async () => {
    const mobile = $("mobile").value.trim();
    if (!mobile) return loginMsg("Enter your mobile number.", true);
    $("send-otp-btn").disabled = true;
    try {
      try {
        await call("POST", "/auth/login/request-otp", { mobile }, { auth: "client" });
        state.flow = "login";
      } catch (e) {
        if (e.code !== "MOBILE_NOT_REGISTERED") throw e;
        await call("POST", "/auth/register/request-otp", { mobile }, { auth: "client" });
        state.flow = "register";
      }
      show($("otp-row")); show($("name-row"), state.flow === "register"); show($("verify-otp-btn"));
      $("send-otp-btn").textContent = "Resend OTP";
      loginMsg(state.flow === "register" ? "New here. OTP sent; add your name too." : "OTP sent.");
      $("otp").focus();
    } catch (e) { loginMsg(e.message, true); }
    finally { $("send-otp-btn").disabled = false; }
  };

  $("verify-otp-btn").onclick = async () => {
    const body = { mobile: $("mobile").value.trim(), otp: $("otp").value.trim() };
    if (state.flow === "register" && $("name").value.trim()) body.name = $("name").value.trim();
    $("verify-otp-btn").disabled = true;
    try {
      const data = await call("POST", `/auth/${state.flow}/verify-otp`, body, { auth: "client" });
      state.token = data.access_token; store.set("ft_token", state.token);
      loginMsg(""); enterApp();
    } catch (e) { loginMsg(e.message, true); }
    finally { $("verify-otp-btn").disabled = false; }
  };

  async function logout(expired = false) {
    if (!expired && state.token) { try { await call("POST", "/auth/logout"); } catch { /* already invalid */ } }
    state.token = null; store.set("ft_token", null); stopPolling();
    showLogin();
    if (expired) loginMsg("Your session ended. Please sign in again.", true);
  }
  $("logout-btn").onclick = () => logout();

  // ---- app shell -------------------------------------------------------------------------------
  async function enterApp() {
    show($("login-view"), false); show($("logout-btn"));
    try {
      state.user = await call("GET", "/auth/me");
      $("user-label").textContent = state.user.name || state.user.mobile;
      const ob = await call("GET", "/onboarding/status");
      if (!ob.onboarding_completed) return showOnboarding(ob);
    } catch { return; }
    show($("onboard-view"), false); show($("app-view"));
    switchTab("plan");
  }

  document.querySelectorAll(".tab").forEach((b) => (b.onclick = () => switchTab(b.dataset.tab)));
  function switchTab(tab) {
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
    document.querySelectorAll(".tab-panel").forEach((p) => show(p, p.id === `tab-${tab}`));
    ({ plan: loadPlan, agents: loadAgents, chat: loadChat, data: loadData })[tab]();
  }

  // ---- analysis status / polling ---------------------------------------------------------------
  function stopPolling() { clearTimeout(state.polling); state.polling = null; show($("run-pill"), false); }

  async function pollStatus() {
    stopPolling();
    let s, o;
    try { [s, o] = await Promise.all([call("GET", "/advisor/status"), call("GET", "/advisor/overview")]); } catch { return; }
    const pill = $("run-pill");
    if (s.running) {
      pill.textContent = `Analysing… ${s.progress.completed}/${s.progress.total}`; show(pill);
      if (!o.ready) renderProgress(s, o);  // first analysis: show progress + early suggestions
      state.polling = setTimeout(pollStatus, 1500);
    } else {
      loadPlan();
      if (s.last_run?.status === "COMPLETED") toast(`Analysis updated: ${s.last_run.agents_regenerated.length ? s.last_run.agents_regenerated.map(label).join(", ") : "nothing changed"}`);
    }
  }

  function renderProgress(s, o) {
    show($("progress-card")); show($("plan-content"), false); show($("connect-empty"), false);
    const { completed, total } = s.progress;
    $("progress-fill").style.width = `${Math.round((completed / total) * 100)}%`;
    $("progress-text").textContent = completed < total - 1
      ? `${completed} of ${total - 1} specialists done` : "Chief agent is combining everything into your plan…";
    $("progress-agents").innerHTML = s.agents.map((a) => `<span class="chip status-${esc(a.status)}">${esc(label(a.key))} · ${esc(label(a.status))}</span>`).join("");
    const preview = o?.preview_steps || [];
    show($("preview-wrap"), preview.length > 0);
    $("preview-steps").innerHTML = preview.map((r, i) => previewHtml(r, i + 1)).join("");
  }

  function previewHtml(r, num) {
    const amount = r.amount ? `<span class="step-amount">${esc(money(r.amount))}</span>` : "";
    return `<li class="step preview"><div class="step-num">${num}</div><div class="step-body">
      <div class="step-head"><span class="step-title">${esc(r.title)}</span>${amount}</div>
      <p class="step-why">${esc(r.why)}</p>
      <div class="chips"><span class="chip">Impact ${esc(label(r.impact))}</span>${r.agents.map((a) => `<span class="chip gold">${esc(label(a))}</span>`).join("")}</div>
      </div></li>`;
  }

  // ---- plan ------------------------------------------------------------------------------------
  async function loadPlan() {
    let o, s;
    try { [o, s] = await Promise.all([call("GET", "/advisor/overview"), call("GET", "/advisor/status")]); } catch { return; }
    if (s.phase === "WAITING_FOR_ONBOARDING") return enterApp();
    if (s.running && !o.ready) { renderProgress(s, o); if (!state.polling) state.polling = setTimeout(pollStatus, 1500); return; }
    if (s.running && !state.polling) state.polling = setTimeout(pollStatus, 1500);  // re-run: keep showing the current plan
    show($("progress-card"), false); show($("preview-wrap"), false);
    if (!o.ready) {
      if (!state.autoRefreshed) {
        state.autoRefreshed = true;  // only once per page load, so a failing analysis can't loop
        await call("POST", "/advisor/refresh", {}).catch(() => {});
        return pollStatus();
      }
      show($("connect-empty")); show($("plan-content"), false); return;
    }
    show($("connect-empty"), false); show($("plan-content"));
    state.currency = o.currency || state.currency;
    if (s.stale && !state.autoRefreshed) {
      // Data, settings or logic changed since this analysis was saved: refresh it once, automatically.
      state.autoRefreshed = true;
      call("POST", "/advisor/refresh", {}).then(pollStatus).catch(() => {});
    }

    const badge = $("health-badge");
    badge.className = `badge ${o.health}`; badge.textContent = label(o.health);
    const fx = Object.entries(o.fx_rates || {}).map(([c, r]) => `1 ${c} = ${money(r)}`).join(", ");
    $("plan-meta").textContent = `Updated ${new Date(o.generated_at).toLocaleString()} · ${o.provider === "claude" ? "Claude" : "rule engine"}`
      + (fx ? ` · converted at ${fx}` : "");
    $("headline").textContent = o.headline || "";
    $("summary").textContent = o.summary || "";
    show($("stale-note"), s.stale);

    const bs = o.balance_sheet || {};
    $("balance-tiles").innerHTML = [["Net worth", bs.net_worth], ["Liquid net worth", bs.liquid_net_worth], ["Investments", bs.investments],
      ["Pension", bs.pension], ["Property", bs.property], ["Debts", bs.total_liabilities]]
      .map(([k, v]) => `<div class="tile"><div class="k">${esc(k)}</div><div class="v">${esc(money(v))}</div></div>`).join("");

    show($("conflicts"), o.conflicts.length > 0);
    $("conflict-list").innerHTML = o.conflicts.map((c) => `
      <div class="card conflict"><b>${esc(c.title)}</b>
        <p class="muted small">${esc(c.detail)}</p><p>${esc(c.resolution)}</p>
        <div class="chips">${c.agents.map((a) => `<span class="chip">${esc(label(a))}</span>`).join("")}</div></div>`).join("");

    $("steps").innerHTML = o.steps.map((r) => stepHtml(r, r.step)).join("") || `<p class="muted">Nothing to do right now.</p>`;
    show($("completed-wrap"), o.completed.length > 0);
    $("completed-count").textContent = o.completed.length;
    $("completed").innerHTML = o.completed.map((r) => stepHtml(r, r.status === "DONE" ? "✓" : "–", true)).join("");
  }

  function stepHtml(r, num, compact = false) {
    const amount = r.amount ? `<span class="step-amount">${esc(money(r.amount, r.currency || state.currency))}</span>` : "";
    const buttons = compact
      ? `<button class="btn ghost small" data-rec="${r.id}" data-status="OPEN">Reopen</button>`
      : `${r.status === "IN_PROGRESS" ? "" : `<button class="btn ghost small" data-rec="${r.id}" data-status="IN_PROGRESS">Start</button>`}
         <button class="btn primary small" data-rec="${r.id}" data-status="DONE">Mark done</button>
         <button class="btn ghost small" data-rec="${r.id}" data-status="DISMISSED">Dismiss</button>`;
    return `<li class="step ${esc(r.status)}">
      <div class="step-num">${esc(num)}</div>
      <div class="step-body">
        <div class="step-head" data-toggle><span class="step-title">${esc(r.title)}</span>${amount}</div>
        ${compact ? "" : `<p class="step-why">${esc(r.why)}</p>`}
        <div class="chips">
          ${r.status === "IN_PROGRESS" ? `<span class="chip gold">In progress</span>` : ""}
          ${compact ? `<span class="chip">${esc(label(r.status))}</span>` : `<span class="chip">Impact ${esc(label(r.impact))}</span><span class="chip">Risk if ignored ${esc(label(r.risk))}</span><span class="chip">Effort ${esc(label(r.effort))}</span><span class="chip">${esc(label(r.timeframe))}</span>`}
          ${r.agents.map((a) => `<span class="chip gold">${esc(label(a))}</span>`).join("")}
        </div>
        <div class="step-detail ${compact ? "hidden" : ""}">
          ${compact ? "" : `<ul>${r.action_steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>`}
          <div class="row">${buttons}</div>
        </div>
      </div></li>`;
  }

  document.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-rec]");
    if (btn) {
      btn.disabled = true;
      try { await call("PATCH", `/advisor/recommendations/${btn.dataset.rec}`, { status: btn.dataset.status }); toast("Saved"); loadPlan(); }
      catch (e) { toast(e.message); btn.disabled = false; }
      return;
    }
    const head = ev.target.closest(".steps.compact [data-toggle]");
    if (head) head.closest(".step-body").querySelector(".step-detail").classList.toggle("hidden");
  });

  $("run-analysis-btn").onclick = async () => {
    try { await call("POST", "/advisor/refresh", {}); pollStatus(); } catch (e) { toast(e.message); }
  };

  $("refresh-btn").onclick = async () => {
    try { await call("POST", "/advisor/refresh", { force: false }); pollStatus(); } catch (e) { toast(e.message); }
  };

  // ---- connect bank ----------------------------------------------------------------------------
  let pendingConnection = null;
  async function startConnect() {
    try {
      const data = await call("POST", "/aggregator/connections");
      pendingConnection = data.connection.id;
      $("agg-otp").value = ""; $("agg-msg").textContent = ""; show($("connect-modal")); $("agg-otp").focus();
    } catch (e) { toast(e.message); }
  }
  document.querySelectorAll(".connect-btn").forEach((b) => (b.onclick = startConnect));
  $("agg-cancel").onclick = () => show($("connect-modal"), false);
  $("agg-verify").onclick = async () => {
    $("agg-verify").disabled = true;
    try {
      const data = await call("POST", `/aggregator/connections/${pendingConnection}/verify-otp`, { otp: $("agg-otp").value.trim() });
      show($("connect-modal"), false);
      toast(`Imported ${data.reports.length} report(s)`);
      if (state.onboarding) return nextOnboardingStep();
      switchTab("plan"); pollStatus();
    } catch (e) { $("agg-msg").textContent = e.message; $("agg-msg").classList.add("error"); }
    finally { $("agg-verify").disabled = false; }
  };


  // ---- onboarding wizard (bank first, then the 5 screens; the analysis starts after the last one) ---
  const OB_STEPS = [["BANK_CONNECT", "Bank"], ["FINANCIAL_PROFILE", "Money"], ["EQUITY", "Equity"], ["RISK", "Risk"],
    ["GOALS", "Goals"], ["PREFERENCES", "Preferences"]];
  const num = (id) => { const v = $(id)?.value.trim(); return v === "" || v == null ? null : Number(v); };
  const field = (id, text, value = "", attrs = 'inputmode="decimal"') =>
    `<label>${esc(text)}<input id="${id}" ${attrs} value="${esc(value ?? "")}"></label>`;
  const select = (id, text, options, value) =>
    `<label>${esc(text)}<select id="${id}">${options.map(([v, t]) => `<option value="${v}" ${v === value ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></label>`;
  const obMsg = () => `<p id="ob-msg" class="msg"></p>`;
  const obError = (e) => { const m = $("ob-msg"); if (m) { m.textContent = e.message; m.classList.add("error"); } };

  async function nextOnboardingStep() {
    try { showOnboarding(await call("GET", "/onboarding/status")); } catch (e) { toast(e.message); }
  }

  async function showOnboarding(ob) {
    stopPolling();
    if (ob.onboarding_completed) {
      state.onboarding = false; state.autoRefreshed = true;
      show($("onboard-view"), false); show($("app-view")); switchTab("plan"); pollStatus();
      return;
    }
    state.onboarding = true;
    show($("app-view"), false); show($("onboard-view"));
    const idx = OB_STEPS.findIndex(([k]) => k === ob.current_step);
    $("ob-stepper").innerHTML = OB_STEPS.map(([, t], i) => `<span class="${i < idx ? "done" : i === idx ? "current" : ""}">${i + 1}. ${esc(t)}</span>`).join("");
    const card = $("ob-card");
    const step = ob.current_step;

    if (step === "BANK_CONNECT") {
      card.innerHTML = `<h1>Connect your bank accounts</h1>
        <p class="muted">We read your accounts, investments, loans, cards and property so your plan uses real numbers. Test OTP: <b>123456</b>.</p>
        <div class="row"><button class="btn primary connect-btn" id="ob-connect">Connect bank accounts</button>
        <button class="btn ghost" id="ob-skip">Skip for now</button></div>${obMsg()}`;
      $("ob-connect").onclick = startConnect;
      $("ob-skip").onclick = () => call("POST", "/onboarding/skip", { step: "BANK_CONNECT" }).then(showOnboarding).catch(obError);
    } else if (step === "FINANCIAL_PROFILE") {
      const fp = (await call("GET", "/financial-profile")).profile || {};
      card.innerHTML = `<h1>Your money</h1><p class="muted">Amounts in ₹.</p><div class="form-grid">
        ${field("fp-income", "Annual income", fp.annual_income)}${field("fp-spend", "Monthly spend", fp.monthly_spend)}
        ${field("fp-cash", "Cash reserve", fp.cash_reserve)}${field("fp-emi", "Monthly EMI (optional)", fp.monthly_emi)}
        ${field("fp-debt", "Total debt (optional)", fp.total_debt)}${field("fp-inv", "Investments (optional)", fp.investments)}
        ${field("fp-age", "Age (optional)", fp.age, 'inputmode="numeric"')}${field("fp-dep", "Dependents (optional)", fp.dependents, 'inputmode="numeric"')}
        ${field("fp-ins", "Life insurance cover (optional)", fp.insurance_cover)}</div>
        <button class="btn primary" id="ob-save">Continue</button>${obMsg()}`;
      $("ob-save").onclick = () => call("PUT", "/financial-profile", {
        annual_income: num("fp-income"), monthly_spend: num("fp-spend"), cash_reserve: num("fp-cash"), currency: "INR",
        monthly_emi: num("fp-emi"), total_debt: num("fp-debt"), investments: num("fp-inv"), age: num("fp-age"),
        dependents: num("fp-dep"), insurance_cover: num("fp-ins"),
      }).then(nextOnboardingStep).catch(obError);
    } else if (step === "EQUITY") {
      card.innerHTML = `<h1>Employer stock</h1><p class="muted">RSUs or ESOPs from your employer, if you have any.</p><div class="form-grid">
        ${field("eq-name", "Employer", "", "")}${field("eq-vested", "Vested value (₹)")}
        ${field("eq-unvested", "Unvested value (₹)")}${field("eq-date", "Next vest date", "", 'type="date"')}</div>
        <div class="row"><button class="btn primary" id="ob-save">Save &amp; continue</button>
        <button class="btn ghost" id="ob-skip">I don't have employer stock</button></div>${obMsg()}`;
      $("ob-save").onclick = () => call("POST", "/equity", {
        employer_name: $("eq-name").value.trim(), vested_value: num("eq-vested"), unvested_value: num("eq-unvested") ?? 0,
        next_vest_date: $("eq-date").value || null, currency: "INR",
      }).then(nextOnboardingStep).catch(obError);
      $("ob-skip").onclick = () => call("POST", "/onboarding/skip", { step: "EQUITY" }).then(showOnboarding).catch(obError);
    } else if (step === "RISK") {
      card.innerHTML = `<h1>Risk</h1><div class="form-grid">
        ${select("rk-tol", "How do you like to invest?", [["STEADY", "Steady"], ["BALANCED", "Balanced"], ["GROWTH", "Growth"]], "BALANCED")}
        ${field("rk-dd", "Largest fall you can live with (%)", 20)}${field("rk-ss", "Max in any single stock (%)", 10)}
        ${field("rk-h", "Planning horizon (years)", 10, 'inputmode="numeric"')}</div>
        <button class="btn primary" id="ob-save">Continue</button>${obMsg()}`;
      $("ob-save").onclick = () => call("PUT", "/risk-profile", {
        risk_tolerance: $("rk-tol").value, max_drawdown_percent: num("rk-dd"), single_stock_limit_percent: num("rk-ss"),
        planning_horizon_years: num("rk-h"),
      }).then(nextOnboardingStep).catch(obError);
    } else if (step === "GOALS") {
      const cards = await call("GET", "/goals/suggestions");
      card.innerHTML = `<h1>Your goals</h1><p class="muted">Pick what matters to you.</p>
        ${cards.map((g) => `<div class="goal-opt"><label class="check"><input type="checkbox" data-goal="${esc(g.goal_type)}" ${g.already_added ? "checked" : ""}>
          <b>${esc(g.name)}</b>${g.calculation.suggested_target_amount ? ` <span class="step-amount">${esc(money(g.calculation.suggested_target_amount))}</span>` : ""}</label>
          <p class="muted small">${esc(g.description)}</p>
          ${(g.calculation.required_inputs || []).map((f) => field(`gi-${g.goal_type}-${f}`, label(f))).join("")}</div>`).join("")}
        <button class="btn primary" id="ob-save">Continue</button>${obMsg()}`;
      $("ob-save").onclick = () => {
        const goals = [...document.querySelectorAll("[data-goal]:checked")].map((c) => {
          const g = cards.find((x) => x.goal_type === c.dataset.goal);
          const inputs = Object.fromEntries((g.calculation.required_inputs || []).map((f) => [f, num(`gi-${g.goal_type}-${f}`)]));
          return Object.keys(inputs).length ? { goal_type: g.goal_type, inputs } : { goal_type: g.goal_type };
        });
        if (!goals.length) return obError(new Error("Pick at least one goal."));
        call("PUT", "/goals/selection", { goals }).then(nextOnboardingStep).catch(obError);
      };
    } else if (step === "PREFERENCES") {
      const pr = await call("GET", "/preferences");
      card.innerHTML = `<h1>Preferences</h1>
        ${select("pr-tone", "How detailed should insights be?", [["CONCISE", "Concise"], ["BALANCED", "Balanced"], ["DETAILED", "Detailed"]], pr.insight_tone)}
        <label class="check"><input type="checkbox" id="pr-vest" ${pr.vesting_alerts ? "checked" : ""}> Vesting alerts</label>
        <label class="check"><input type="checkbox" id="pr-tax" ${pr.tax_deadline_alerts ? "checked" : ""}> Tax deadline alerts</label>
        <label class="check"><input type="checkbox" id="pr-week" ${pr.weekly_digest ? "checked" : ""}> Weekly digest</label>
        <p class="muted small">When you finish, your AI agents start building your plan from your bank data and these answers.</p>
        <button class="btn primary" id="ob-save">Finish &amp; build my plan</button>${obMsg()}`;
      $("ob-save").onclick = () => call("PUT", "/preferences", {
        insight_tone: $("pr-tone").value, vesting_alerts: $("pr-vest").checked, tax_deadline_alerts: $("pr-tax").checked,
        weekly_digest: $("pr-week").checked,
      }).then(nextOnboardingStep).catch(obError);
    }
  }

  // ---- agents ----------------------------------------------------------------------------------
  async function loadAgents() {
    let agents;
    try { agents = await call("GET", "/advisor/agents"); } catch { return; }
    $("agent-grid").innerHTML = agents.map((a) => `
      <div class="card agent-card" data-agent="${esc(a.key)}">
        <div class="row space"><b>${esc(a.name)}</b>${a.health ? `<span class="badge ${esc(a.health)}">${esc(label(a.health))}</span>` : `<span class="chip">${esc(label(a.status))}</span>`}</div>
        <p class="muted small">${esc(a.summary || a.description)}</p>
        <div class="metrics">${a.metrics.slice(0, 4).map((m) => `<div class="m"><div class="k">${esc(m.label)}</div><div class="v">${esc(fmtMetric(m))}</div></div>`).join("")}</div>
        <span class="muted small">${a.recommendations_count} recommendation(s) · v${a.version}</span>
      </div>`).join("");
    document.querySelectorAll("[data-agent]").forEach((c) => (c.onclick = () => openAgent(c.dataset.agent)));
  }

  async function openAgent(key) {
    let a;
    try { a = await call("GET", `/advisor/agents/${key}`); } catch (e) { return toast(e.message); }
    $("drawer-body").innerHTML = `
      <h1>${esc(a.name)}</h1>
      <p class="muted">${esc(a.description)}</p>
      ${a.health ? `<span class="badge ${esc(a.health)}">${esc(label(a.health))}</span>` : ""}
      <p style="margin-top:10px">${esc(a.summary || "")}</p>
      <div class="tiles">${a.metrics.map((m) => `<div class="tile"><div class="k">${esc(m.label)}</div><div class="v">${esc(fmtMetric(m))}</div></div>`).join("")}</div>
      <h2 class="section-title">Findings</h2>
      ${a.findings.map((f) => `<div class="finding ${esc(f.severity)}"><b>${esc(f.title)}</b><p class="muted">${esc(f.detail)}</p></div>`).join("") || `<p class="muted">None.</p>`}
      <h2 class="section-title">Recommendations</h2>
      ${a.recommendations.map((r) => `<div class="card"><b>${esc(r.title)}</b>${r.amount ? ` <span class="step-amount">${esc(money(r.amount))}</span>` : ""}
          <p class="muted">${esc(r.why)}</p><ul>${r.action_steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ul></div>`).join("") || `<p class="muted">None.</p>`}
      ${a.data_gaps.length ? `<h2 class="section-title">What would improve this analysis</h2><ul>${a.data_gaps.map((g) => `<li class="muted">${esc(g)}</li>`).join("")}</ul>` : ""}
      <details><summary class="section-title">Facts the agent used</summary><pre class="facts">${esc(JSON.stringify(a.facts, null, 2))}</pre></details>
      <p class="muted small">Version ${a.version} · ${esc(a.provider || "–")} · ${a.generated_at ? esc(new Date(a.generated_at).toLocaleString()) : ""}</p>`;
    show($("drawer")); $("drawer").setAttribute("aria-hidden", "false");
  }
  $("drawer-close").onclick = () => { show($("drawer"), false); $("drawer").setAttribute("aria-hidden", "true"); };
  $("drawer").onclick = (e) => { if (e.target.id === "drawer") $("drawer-close").onclick(); };

  // ---- chat ------------------------------------------------------------------------------------
  const SUGGESTIONS = ["What should I do first?", "Should I prepay my mortgage?", "Am I too concentrated in one stock?",
    "Do I have enough insurance?", "How much cash should I keep?"];

  function bubble(m) {
    const who = m.role === "assistant" && m.agents?.length ? `<div class="who">${m.agents.map(label).map(esc).join(" · ")}</div>` : "";
    return `<div class="bubble ${esc(m.role)}">${esc(m.content)}${who}</div>`;
  }

  async function loadChat() {
    let data;
    try { data = await call("GET", "/advisor/chat?limit=100"); } catch { return; }
    $("chat-log").innerHTML = data.messages.map(bubble).join("") ||
      `<p class="muted">Ask anything about your finances. Answers use your saved analysis.</p>`;
    $("chat-suggestions").innerHTML = SUGGESTIONS.map((s) => `<span class="chip clickable">${esc(s)}</span>`).join("");
    $("chat-suggestions").querySelectorAll(".chip").forEach((c) => (c.onclick = () => { $("chat-input").value = c.textContent; $("chat-form").requestSubmit(); }));
    $("chat-log").scrollTop = $("chat-log").scrollHeight;
  }

  $("chat-form").onsubmit = async (ev) => {
    ev.preventDefault();
    const text = $("chat-input").value.trim();
    if (!text) return;
    $("chat-input").value = "";
    const log = $("chat-log");
    if (log.querySelector("p.muted")) log.innerHTML = "";
    log.insertAdjacentHTML("beforeend", bubble({ role: "user", content: text }) + `<div class="bubble assistant" id="typing">…</div>`);
    log.scrollTop = log.scrollHeight;
    try {
      const data = await call("POST", "/advisor/chat", { message: text });
      $("typing").outerHTML = bubble(data.answer);
    } catch (e) { $("typing").outerHTML = bubble({ role: "assistant", content: e.message }); }
    log.scrollTop = log.scrollHeight;
  };

  // ---- data ------------------------------------------------------------------------------------
  async function loadData() {
    let conns, data;
    try { [conns, data] = await Promise.all([call("GET", "/aggregator/connections"), call("GET", "/aggregator/data")]); } catch { return; }
    $("connections").innerHTML = conns.length ? `<div class="table-wrap"><table><tr><th>#</th><th>Provider</th><th>Status</th><th>Last sync</th><th></th></tr>
      ${conns.map((c) => `<tr><td>${c.id}</td><td>${esc(c.provider)}</td><td>${esc(label(c.status))}</td>
        <td>${c.last_synced_at ? esc(new Date(c.last_synced_at).toLocaleString()) : "–"}</td>
        <td>${c.status === "ACTIVE" ? `<button class="btn ghost small" data-sync="${c.id}">Refresh</button>` : ""}</td></tr>`).join("")}</table></div>`
      : `<p class="muted">No accounts connected yet.</p>`;
    document.querySelectorAll("[data-sync]").forEach((b) => (b.onclick = async () => {
      b.disabled = true;
      try {
        const r = await call("POST", `/aggregator/connections/${b.dataset.sync}/refresh`);
        toast(r.data_changed ? "New data imported; updating analysis" : "No changes since last sync");
        if (r.data_changed) pollStatus();
        loadData();
      } catch (e) { toast(e.message); b.disabled = false; }
    }));
    $("data-counts").innerHTML = Object.entries(data.counts).map(([k, v]) => `<span class="chip">${esc(label(k))}: ${v}</span>`).join("");
    const table = (title, cols, rows) => rows.length ? `<div class="card"><h2>${esc(title)}</h2><div class="table-wrap"><table>
      <tr>${cols.map(([h, , num]) => `<th class="${num ? "num" : ""}">${esc(h)}</th>`).join("")}</tr>
      ${rows.map((r) => `<tr>${cols.map(([, f, num]) => `<td class="${num ? "num" : ""}">${esc(f(r))}</td>`).join("")}</tr>`).join("")}</table></div></div>` : "";
    $("data-tables").innerHTML =
      table("Accounts", [["Name", (r) => r.name], ["Type", (r) => label(r.subtype)], ["Balance", (r) => money(r.balance, r.currency), 1]], data.accounts) +
      table("Investments", [["Name", (r) => r.name], ["Type", (r) => label(r.subtype)], ["Return", (r) => r.weighted_return != null ? `${r.weighted_return}%` : "–", 1], ["Value", (r) => money(r.total_value, r.currency), 1]], data.portfolios) +
      table("Loans", [["Type", (r) => label(r.loan_type)], ["Rate", (r) => `${r.interest_rate}%`, 1], ["Instalment", (r) => money(r.next_installment, r.currency), 1], ["Outstanding", (r) => money(r.pending_amount, r.currency), 1]], data.loans) +
      table("Deposits", [["Name", (r) => r.name], ["Rate", (r) => `${r.nominal_interest_rate}%`, 1], ["Matures", (r) => r.maturity_date], ["Principal", (r) => money(r.principal, r.currency), 1]], data.deposits);
  }

  $("extra-save").onclick = async () => {
    const data = { has_will: $("x-will").checked, pension_beneficiaries_named: $("x-benef").checked, has_power_of_attorney: $("x-poa").checked };
    try { await call("POST", "/advisor/extra-data", { category: "ESTATE", data }); $("extra-msg").textContent = "Saved. Updating your analysis…"; pollStatus(); }
    catch (e) { $("extra-msg").textContent = e.message; }
  };

  // ---- start -----------------------------------------------------------------------------------
  if (state.token) enterApp(); else showLogin();
})();
