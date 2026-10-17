/* AI Coding Desktop — Code-Web chrome, one UI, tab = engine module */
(function () {
  const TOKEN = window.ACD_TOKEN || "";
  const MODULES = [
    { id: "kimi", zh: "Kimi", en: "Kimi" },
    { id: "xai", zh: "xAI", en: "xAI" },
    { id: "codex", zh: "Codex", en: "Codex" },
    { id: "claude", zh: "Claude", en: "Claude" },
    { id: "qwen", zh: "Qwen Code", en: "Qwen Code" },
    { id: "deepseek", zh: "DeepSeek", en: "DeepSeek" },
  ];
  const I18N = {
    zh: {
      newChat: "新建聊天", openTerm: "打开终端", settings: "设置", history: "聊天记录",
      send: "发送", cancel: "取消", ph: "发给当前模组…",
      setHint: "CLI 路径与 API 绑定分行。打开 = 可见终端。密钥只存本机，不进日志。",
      apiBlock: "API 绑定", workspace: "工作区", verify: "验证连接",
      openLogs: "打开日志", openImportant: "打开 IMPORTANT", close: "关闭",
      browse: "浏览", open: "打开", sendTip: "发送", stopTip: "停止（取消当前任务）",
      langTip: "English",
      closeWin: "关窗", closeTray: "到托盘", closeQuit: "直接关",
      closeWinTip: "点击窗口关闭按钮时：最小化到托盘，或直接退出",
      kimiEngine: "Kimi 引擎", kimiEngineKap: "API", kimiEngineAcp: "ACP",
      kimiEngineTip: "API = 挂 Kimi 自带的本地服务（推荐：删除对话由 Kimi 自己处理）；ACP = 旧 kimi acp 通道。切换后重开 Kimi 页签生效。",
      delSession: "删除会话", cacheUnk: "命中未知",
      manageSessions: "管理会话", manageDone: "完成",
      selectAll: "全选", selectNone: "全不选", deleteSelected: "删除所选",
      ctxDeleteSession: "删除该会话", confirmDeleteTitle: "确认删除",
      confirmDeleteYes: "删除", cancelDlg: "取消",
      confirmDeleteMsg: "将永久删除 {n} 个会话，此操作不可恢复。确定继续？",
      confirmDeleteOne: "将永久删除会话「{title}」，此操作不可恢复。确定继续？",
      noSelection: "请先勾选要删除的会话。",
      deleting: "正在删除…", deleteDone: "已删除 {n} 个会话。",
      deleteFailed: "删除失败：{err}", noSessions: "暂无历史会话",
      untitledSession: "（无标题）",
      currentSessionDeleted: "当前会话已删除；发送消息或点「新建聊天」后才会创建。",
      tabErr: "错误",
      claude_no_acp: "Claude Code 没有 ACP 入口（--acp 不是合法选项）。请点右上角「打开终端」用官方 CLI。",
      engine_not_acp: "当前模组未连上 ACP，请打开终端或检查设置里的 CLI。",
      not_qwen_code: "Qwen Tab 只接 Qwen Code（qwen），不接 QwenCloud CLI（qwencloud）。请把 CLI 指到 %LOCALAPPDATA%\\qwen-code\\bin\\qwen.cmd。",
      dsh_host_timeout: "DeepSeek 引擎启动超时。请确认已安装 dsh，且未弹出需手动关闭的终端。",
      kimi_kap_unavailable: "Kimi 本地服务连不上，也起不来。请先打开 Kimi Code 桌面端，或在设置里把 Kimi 引擎切到 ACP。",
      kimi_kap_unreachable: "Kimi 本地服务已断开（进程没了）。重开 Kimi 页签可重新挂接。",
      model_not_configured: "Kimi 会话没有选定模型。请在模型条里选一个再发。",
    },
    en: {
      newChat: "New chat", openTerm: "Open terminal", settings: "Settings", history: "History",
      send: "Send", cancel: "Stop", ph: "Message this module…",
      setHint: "CLI path and API binding are separate rows. Open = visible terminal. Keys stay local, never logged.",
      apiBlock: "API binding", workspace: "Workspace", verify: "Verify",
      openLogs: "Open logs", openImportant: "Open IMPORTANT", close: "Close",
      browse: "Browse", open: "Open", sendTip: "Send", stopTip: "Stop (cancel current task)",
      langTip: "简体中文",
      closeWin: "Close", closeTray: "To tray", closeQuit: "Quit",
      closeWinTip: "Window close button: minimize to tray, or quit",
      kimiEngine: "Kimi engine", kimiEngineKap: "API", kimiEngineAcp: "ACP",
      kimiEngineTip: "API = attach to Kimi's own local service (recommended: Kimi deletes chats itself); ACP = legacy kimi acp channel. Reopen the Kimi tab after switching.",
      delSession: "Delete session", cacheUnk: "hit unknown",
      manageSessions: "Manage sessions", manageDone: "Done",
      selectAll: "Select all", selectNone: "Select none", deleteSelected: "Delete selected",
      ctxDeleteSession: "Delete this session", confirmDeleteTitle: "Confirm delete",
      confirmDeleteYes: "Delete", cancelDlg: "Cancel",
      confirmDeleteMsg: "Permanently delete {n} session(s)? This cannot be undone.",
      confirmDeleteOne: "Permanently delete session “{title}”? This cannot be undone.",
      noSelection: "Select at least one session to delete.",
      deleting: "Deleting…", deleteDone: "Deleted {n} session(s).",
      deleteFailed: "Delete failed: {err}", noSessions: "No past sessions",
      untitledSession: "(untitled)",
      currentSessionDeleted: "Current session was deleted. Send a message or choose New chat to create one.",
      tabErr: "Error",
      claude_no_acp: "Claude Code has no ACP flag (--acp is invalid). Use Open terminal for the official CLI.",
      engine_not_acp: "This module is not on ACP. Open the terminal or check the CLI path in Settings.",
      not_qwen_code: "The Qwen tab is Qwen Code only (qwen), not QwenCloud CLI (qwencloud). Point CLI at %LOCALAPPDATA%\\qwen-code\\bin\\qwen.cmd.",
      dsh_host_timeout: "DeepSeek engine timed out. Confirm dsh is installed and no extra terminal was left open.",
      kimi_kap_unavailable: "Kimi's local service is unreachable and could not be started. Open the Kimi Code app, or switch Kimi engine to ACP in Settings.",
      kimi_kap_unreachable: "Kimi's local service went away (process gone). Reopen the Kimi tab to attach again.",
      model_not_configured: "This Kimi session has no model selected. Pick one in the model bar and send again.",
    },
  };
  const MONO_LOGOS = { xai: true, codex: true };
  const ICON_OPEN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/></svg>';
  const ICON_BROWSE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9L9.2 3.9A2 2 0 0 0 7.5 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"/><path d="M8 14h.01M12 14h.01M16 14h.01"/></svg>';
  const ICON_DEL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/></svg>';
  const ICON_MARK_OFF = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="3"/></svg>';
  const ICON_MARK_ON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="3"/><path d="m8 12 3 3 5-6"/></svg>';
  let lang = localStorage.getItem("acd-lang") || "zh";
  let active = "kimi";
  let since = 0;
  const drafts = {};
  const conn = {};
  let sessionsCache = [];
  let manageMode = false;
  const selectedSessions = new Set();
  let deletingSessions = false;
  let currentSessionId = null;
  let ctxSession = null;
  const API_FIELDS = [
    ["moonshot", "Kimi / Moonshot"],
    ["xai", "Grok / xAI"],
    ["openai", "Codex / OpenAI"],
    ["anthropic", "Claude / Anthropic"],
    ["deepseek", "DeepSeek"],
    ["qwen", "Qwen Code API"],
    ["qwen_base_url", "Qwen Code Base URL"],
  ];

  function t(k) { return (I18N[lang] || I18N.zh)[k] || k; }
  function tf(k, vars) {
    let s = t(k);
    Object.keys(vars || {}).forEach((key) => {
      s = s.split("{" + key + "}").join(String(vars[key]));
    });
    return s;
  }
  function applyI18n() {
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = t(el.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-tip]").forEach((el) => {
      const label = t(el.getAttribute("data-tip"));
      el.title = label;
      el.setAttribute("aria-label", label);
    });
    const ph = document.getElementById("input");
    if (ph) ph.placeholder = t("ph");
    const send = document.getElementById("btnSend");
    const stop = document.getElementById("btnCancel");
    if (send) { send.title = t("sendTip"); send.setAttribute("aria-label", t("sendTip")); }
    if (stop) { stop.title = t("stopTip"); stop.setAttribute("aria-label", t("stopTip")); }
    syncManageUi();
  }

  async function api(path, opts) {
    const headers = { "X-ACD-Token": TOKEN, "Content-Type": "application/json" };
    const ctrl = new AbortController();
    const tmo = setTimeout(() => ctrl.abort(), (opts && opts.timeout) || 20000);
    try {
      const res = await fetch(path, { ...opts, headers, signal: ctrl.signal });
      return await res.json();
    } finally {
      clearTimeout(tmo);
    }
  }

  function renderTabs() {
    const nav = document.getElementById("tabs");
    nav.innerHTML = "";
    MODULES.forEach((m) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tab" + (m.id === active ? " active" : "");
      const name = lang === "zh" ? m.zh : m.en;
      b.title = name;
      b.setAttribute("aria-label", name);
      const mono = MONO_LOGOS[m.id] ? " mono" : "";
      b.innerHTML = '<img class="tab-logo' + mono + '" src="/logos/' + m.id + '.svg" alt="">'
        + '<span class="dot" data-dot="' + m.id + '"></span>';
      b.onclick = () => switchTab(m.id);
      nav.appendChild(b);
    });
    applyConnDots();
  }

  function applyConnDots() {
    MODULES.forEach((m) => {
      const el = document.querySelector('[data-dot="' + m.id + '"]');
      if (!el) return;
      el.classList.remove("ok", "bad");
      if (conn[m.id] === true) el.classList.add("ok");
      if (conn[m.id] === false) el.classList.add("bad");
    });
  }

  function addMsg(role, text) {
    const box = document.getElementById("msgs");
    const d = document.createElement("div");
    d.className = "msg " + role;
    d.textContent = text;
    box.appendChild(d);
    box.scrollTop = box.scrollHeight;
    return d;
  }

  function setStatus(s) { document.getElementById("status").textContent = s || ""; }

  function statusIsBusy() {
    const cur = (document.getElementById("status") && document.getElementById("status").textContent) || "";
    return cur.indexOf("生成") >= 0 || cur.indexOf("Running") >= 0;
  }

  function applyEngineStatus(st) {
    if (!st || statusIsBusy()) return;
    if (st.state === "starting") {
      setStatus(lang === "zh" ? "连接中…" : "Connecting…");
      return;
    }
    if (st.state === "ready") {
      setStatus("ready" + (st.model ? " · " + st.model : ""));
      return;
    }
    if (st.state) setStatus(st.state + (st.model ? " · " + st.model : ""));
  }

  function moduleLabel(id) {
    const m = MODULES.find((x) => x.id === id);
    if (!m) return id;
    return lang === "zh" ? m.zh : m.en;
  }

  function translateErr(code) {
    if (!code) return "";
    const mapped = t(code);
    if (mapped && mapped !== code) return mapped;
    // kap error codes are dotted (model.not_configured); i18n keys use "_".
    const key = String(code).replace(/[.\-]/g, "_");
    const alt = t(key);
    if (alt && alt !== key) return alt;
    return String(code);
  }

  function renderTabAlert(st) {
    const el = document.getElementById("tabAlert");
    if (!el) return;
    const err = (st && st.error) || "";
    const tail = (st && st.stderr_tail && st.stderr_tail[0]) || "";
    if (!err && !tail) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    const name = moduleLabel(active);
    const body = translateErr(err) || tail;
    const extra = (tail && body.indexOf(tail) < 0) ? "\n" + tail : "";
    el.hidden = false;
    el.textContent = name + " · " + body + extra;
  }

  function renderCache(hit) {
    const st = document.getElementById("status");
    if (!st) return;
    const base = st.textContent.replace(/\s*·\s*cache[^\s]*/i, "").replace(/\s*·\s*命中[^\s]*/i, "");
    if (!hit) { st.textContent = base; return; }
    const pct = hit.hit_pct;
    const label = (pct === null || pct === undefined) ? t("cacheUnk") : ("cache " + pct + "%");
    st.textContent = (base ? base + " · " : "") + label;
  }

  function renderModelBar(st) {
    const bar = document.getElementById("modelBar");
    if (!bar) return;
    const opts = (st && st.config_options) || [];
    bar.innerHTML = "";
    opts.forEach((opt) => {
      const cid = opt.id || opt.configId || "";
      if (!cid) return;
      const sel = document.createElement("select");
      sel.title = cid;
      const values = opt.options || opt.choices || opt.values || [];
      const cur = String(opt.value || opt.current || "");
      (Array.isArray(values) ? values : []).forEach((v) => {
        const o = document.createElement("option");
        o.value = typeof v === "string" ? v : String(v.value || v.id || "");
        o.textContent = typeof v === "string" ? v : String(v.label || v.name || o.value);
        if (o.value === cur) o.selected = true;
        sel.appendChild(o);
      });
      if (!sel.options.length) return;
      sel.onchange = () => api("/api/config", { method: "POST", body: JSON.stringify({ configId: cid, value: sel.value }) });
      bar.appendChild(sel);
    });
  }

  async function switchTab(id) {
    drafts[active] = document.getElementById("input").value;
    active = id;
    since = 0;
    currentSessionId = null;
    setManageMode(false);
    document.getElementById("msgs").innerHTML = "";
    document.getElementById("input").value = drafts[id] || "";
    renderTabAlert({});
    renderTabs();
    await api("/api/tab", { method: "POST", body: JSON.stringify({ module: id }) });
    await startActive();
    await loadSessions();
    await pollEvents(true);
  }

  async function startActive() {
    setStatus(lang === "zh" ? "连接中…" : "Connecting…");
    try {
      const r = await api("/api/start", { method: "POST", body: JSON.stringify({ module: active }), timeout: 20000 });
      const st = Object.assign({}, (r && r.state) || {});
      if (!st.error && r && r.error) st.error = r.error;
      applyEngineStatus(st);
      renderTabAlert(st);
      renderModelBar(st);
      renderCache(st.cache_hit);
    } catch (e) {
      setStatus(String(e));
      renderTabAlert({ error: String(e) });
    }
  }

  function syncManageUi() {
    const bar = document.getElementById("sessionToolbar");
    const btn = document.getElementById("btnManageSessions");
    const del = document.getElementById("btnDeleteSelected");
    if (bar) bar.hidden = !manageMode;
    if (btn) {
      btn.classList.toggle("active", manageMode);
      btn.title = t("manageSessions");
      btn.setAttribute("aria-label", t("manageSessions"));
    }
    if (!del) return;
    del.disabled = deletingSessions || selectedSessions.size === 0;
    del.textContent = deletingSessions
      ? t("deleting")
      : t("deleteSelected") + (selectedSessions.size ? " (" + selectedSessions.size + ")" : "");
  }

  function setManageMode(next) {
    manageMode = !!next;
    if (!manageMode) selectedSessions.clear();
    closeCtxMenu();
    renderSessionList();
  }

  function toggleMark(sid) {
    if (selectedSessions.has(sid)) selectedSessions.delete(sid);
    else selectedSessions.add(sid);
    renderSessionList();
  }

  function renderSessionList() {
    const box = document.getElementById("sessions");
    const empty = document.getElementById("sessionEmpty");
    if (!box) return;
    box.innerHTML = "";
    const alive = new Set(sessionsCache.map((s) => String(s.sessionId || s.id || "")));
    Array.from(selectedSessions).forEach((id) => { if (!alive.has(id)) selectedSessions.delete(id); });
    if (empty) {
      empty.hidden = sessionsCache.length > 0;
      empty.textContent = t("noSessions");
    }
    sessionsCache.forEach((s) => {
      const id = String(s.sessionId || s.id || "");
      if (!id) return;
      const el = document.createElement("div");
      const marked = selectedSessions.has(id);
      el.className = "sess"
        + (id === String(currentSessionId || "") ? " current" : "")
        + (manageMode && marked ? " marked" : "");
      el.dataset.sid = id;
      if (manageMode) {
        const mark = document.createElement("button");
        mark.type = "button";
        mark.className = "sess-mark" + (marked ? " on" : "");
        mark.title = t("selectAll");
        mark.setAttribute("aria-pressed", marked ? "true" : "false");
        mark.innerHTML = marked ? ICON_MARK_ON : ICON_MARK_OFF;
        mark.onclick = (ev) => { ev.stopPropagation(); toggleMark(id); };
        el.appendChild(mark);
      }
      const lab = document.createElement("span");
      lab.className = "sess-title";
      lab.textContent = s.title || t("untitledSession") || id.slice(0, 16);
      lab.title = s.title || id;
      el.appendChild(lab);
      if (!manageMode) {
        const del = document.createElement("button");
        del.type = "button";
        del.className = "icon-btn sm sess-del";
        del.title = t("delSession");
        del.setAttribute("aria-label", t("delSession"));
        del.innerHTML = ICON_DEL;
        del.onclick = (ev) => { ev.stopPropagation(); deleteOneFlow(s); };
        el.appendChild(del);
      }
      el.onclick = () => {
        if (manageMode) toggleMark(id);
        else loadOneSession(s);
      };
      el.oncontextmenu = (ev) => {
        ev.preventDefault();
        openCtxMenu(ev.clientX, ev.clientY, s);
      };
      box.appendChild(el);
    });
    syncManageUi();
  }

  async function loadOneSession(s) {
    const id = String(s.sessionId || s.id || "");
    currentSessionId = id;
    await api("/api/session/load", { method: "POST", body: JSON.stringify({ sessionId: id }) });
    document.getElementById("msgs").innerHTML = "";
    since = 0;
    await pollEvents(true);
    renderSessionList();
  }

  async function loadSessions() {
    try {
      const r = await api("/api/sessions");
      sessionsCache = r.sessions || [];
    } catch (_) {
      sessionsCache = [];
    }
    renderSessionList();
  }

  function openCtxMenu(x, y, session) {
    ctxSession = session;
    const menu = document.getElementById("ctxMenu");
    if (!menu) return;
    menu.hidden = false;
    const mw = menu.offsetWidth || 150;
    const mh = menu.offsetHeight || 40;
    menu.style.left = Math.min(x, window.innerWidth - mw - 8) + "px";
    menu.style.top = Math.min(y, window.innerHeight - mh - 8) + "px";
  }

  function closeCtxMenu() {
    const menu = document.getElementById("ctxMenu");
    if (menu) menu.hidden = true;
    ctxSession = null;
  }

  function confirmDialog(msg) {
    return new Promise((resolve) => {
      const modal = document.getElementById("confirmModal");
      const text = document.getElementById("confirmMsg");
      if (text) text.textContent = msg;
      modal.classList.add("show");
      const yes = document.getElementById("btnConfirmYes");
      const no = document.getElementById("btnConfirmNo");
      function done(v) {
        modal.classList.remove("show");
        yes.onclick = null;
        no.onclick = null;
        resolve(v);
      }
      yes.onclick = () => done(true);
      no.onclick = () => done(false);
    });
  }

  async function deleteSessions(ids) {
    if (deletingSessions || !ids.length) return;
    deletingSessions = true;
    syncManageUi();
    try {
      const r = await api("/api/sessions/delete", {
        method: "POST",
        body: JSON.stringify({ sessionIds: ids }),
        timeout: 120000,
      });
      const n = (r && r.deleted_count) || 0;
      if (n > 0) addMsg("tool", tf("deleteDone", { n: n }));
      if (r && r.failed && r.failed.length) {
        addMsg("tool", tf("deleteFailed", { err: r.failed.map((e) => e.error).join("; ") }));
      } else if (r && r.ok === false && n === 0) {
        addMsg("tool", tf("deleteFailed", { err: r.error || "error" }));
      }
      ids.forEach((id) => selectedSessions.delete(String(id)));
      if (ids.map(String).indexOf(String(currentSessionId || "")) !== -1) {
        currentSessionId = null;
        document.getElementById("msgs").innerHTML = "";
        since = 0;
        addMsg("tool", t("currentSessionDeleted"));
      }
    } catch (e) {
      addMsg("tool", tf("deleteFailed", { err: String(e) }));
    } finally {
      deletingSessions = false;
      await loadSessions();
    }
  }

  async function deleteSelectedFlow() {
    const ids = Array.from(selectedSessions);
    if (!ids.length) {
      addMsg("tool", t("noSelection"));
      return;
    }
    const ok = await confirmDialog(tf("confirmDeleteMsg", { n: ids.length }));
    if (!ok) return;
    await deleteSessions(ids);
  }

  async function deleteOneFlow(session) {
    if (!session) return;
    const title = session.title || t("untitledSession");
    const ok = await confirmDialog(tf("confirmDeleteOne", { title: title }));
    if (!ok) return;
    await deleteSessions([String(session.sessionId || session.id || "")]);
  }

  function renderEvent(ev) {
    if (!ev) return;
    if (ev.type === "user") addMsg("user", ev.text || "");
    if (ev.type === "assistant") addMsg("assistant", ev.text || "");
    if (ev.type === "info") addMsg("tool", ev.text || "");
    if (ev.type === "engine_error") {
      const code = ev.code || ev.text || "";
      renderTabAlert({ error: code, stderr_tail: ev.stderr || [] });
      addMsg("tool", moduleLabel(active) + " · " + translateErr(code));
    }
    if (ev.type === "engine_ready") {
      applyEngineStatus({ state: "ready" });
    }
    if (ev.type === "cache") renderCache(ev.cache_hit);
    if (ev.type === "session_update") {
      const u = (ev.params || {}).update || {};
      const kind = u.sessionUpdate || "";
      if (kind === "agent_message_chunk") {
        const t = ((u.content || {}).text) || u.text || "";
        if (t) {
          const last = document.getElementById("msgs").lastElementChild;
          if (last && last.classList.contains("assistant")) last.textContent += t;
          else addMsg("assistant", t);
        }
      } else if (kind === "tool_call" || kind === "tool_call_update") {
        addMsg("tool", (u.title || u.kind || "tool") + " " + (u.status || ""));
      }
    }
  }

  async function pollEvents(reset) {
    if (reset) since = 0;
    try {
      const r = await api("/api/events?since=" + since);
      (r.events || []).forEach(renderEvent);
      if (typeof r.seq === "number") since = r.seq;
      if (r.state) renderTabAlert(r.state);
    } catch (_) { /* ignore poll */ }
  }

  async function pollHealth() {
    try {
      const r = await api("/api/health");
      const bar = document.getElementById("alertBar");
      const st = (r.modules && r.modules[active]) || {};
      renderTabAlert(st);
      applyEngineStatus(st);
      const global = r.alert || "";
      const mine = (active + " · ").toLowerCase();
      bar.textContent = (global && global.toLowerCase().indexOf(mine) !== 0) ? global : "";
      if (st && st.cache_hit) renderCache(st.cache_hit);
    } catch (_) { /* */ }
  }

  async function send() {
    const input = document.getElementById("input");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    addMsg("user", text);
    setStatus(lang === "zh" ? "生成中…" : "Running…");
    try {
      await api("/api/prompt", { method: "POST", body: JSON.stringify({ text }), timeout: 310000 });
    } catch (e) {
      addMsg("tool", String(e));
    }
    setStatus("");
  }

  function openSettings() {
    document.getElementById("modal").classList.add("show");
    api("/api/settings").then((r) => {
      const cfg = (r && r.config) || {};
      const resolved = (r && r.resolved) || {};
      const cliBox = document.getElementById("cliRows");
      cliBox.innerHTML = "";
      MODULES.forEach((m) => {
        const row = document.createElement("div");
        row.className = "row";
        row.innerHTML = `<label>${m.zh}</label><input data-cli="${m.id}" /><span class="mark" data-mark="${m.id}"></span><button class="icon-btn" data-browse="${m.id}" title="${t("browse")}" aria-label="${t("browse")}">${ICON_BROWSE}</button><button class="icon-btn" data-open="${m.id}" title="${t("open")}" aria-label="${t("open")}">${ICON_OPEN}</button>`;
        cliBox.appendChild(row);
        row.querySelector("input").value = (cfg.cli && cfg.cli[m.id]) || resolved[m.id] || "";
        row.querySelector("[data-browse]").onclick = async () => {
          const br = await api("/api/browse", { method: "POST", body: "{}" });
          if (br && br.path) row.querySelector("input").value = br.path;
        };
        row.querySelector("[data-open]").onclick = () => {
          api("/api/tab", { method: "POST", body: JSON.stringify({ module: m.id }) });
          api("/api/terminal", { method: "POST", body: JSON.stringify({ module: m.id }) });
        };
      });
      const apiBox = document.getElementById("apiRows");
      apiBox.innerHTML = "";
      API_FIELDS.forEach(([key, label]) => {
        const row = document.createElement("div");
        row.className = "row";
        const type = key.indexOf("url") >= 0 ? "text" : "password";
        row.innerHTML = `<label>${label}</label><input data-api="${key}" type="${type}" />`;
        apiBox.appendChild(row);
        row.querySelector("input").value = (cfg.api && cfg.api[key]) || "";
      });
      document.getElementById("workspace").value = cfg.workspace || "";
      const ca = cfg.close_action === "tray" ? "tray" : "quit";
      document.querySelectorAll('input[name="closeAction"]').forEach((el) => {
        el.checked = el.value === ca;
      });
      const ke = cfg.kimi_engine === "acp" ? "acp" : "kap";
      document.querySelectorAll('input[name="kimiEngine"]').forEach((el) => {
        el.checked = el.value === ke;
      });
    });
  }

  function saveSettings() {
    const cli = {};
    document.querySelectorAll("[data-cli]").forEach((el) => { cli[el.getAttribute("data-cli")] = el.value.trim(); });
    const ap = {};
    document.querySelectorAll("[data-api]").forEach((el) => { ap[el.getAttribute("data-api")] = el.value.trim(); });
    const picked = document.querySelector('input[name="closeAction"]:checked');
    const close_action = picked && picked.value === "tray" ? "tray" : "quit";
    const engine = document.querySelector('input[name="kimiEngine"]:checked');
    const kimi_engine = engine && engine.value === "acp" ? "acp" : "kap";
    return api("/api/settings", {
      method: "POST",
      body: JSON.stringify({
        cli, api: ap,
        workspace: document.getElementById("workspace").value.trim(),
        close_action,
        kimi_engine,
      }),
    });
  }

  document.getElementById("btnLang").onclick = () => {
    lang = lang === "zh" ? "en" : "zh";
    localStorage.setItem("acd-lang", lang);
    applyI18n();
    renderTabs();
    renderSessionList();
  };
  document.getElementById("btnNew").onclick = () => api("/api/session/new", { method: "POST", body: "{}" }).then((r) => {
    currentSessionId = (r && (r.session_id || r.sessionId)) || null;
    document.getElementById("msgs").innerHTML = "";
    since = 0;
    loadSessions();
  });
  document.getElementById("btnManageSessions").onclick = () => setManageMode(!manageMode);
  document.getElementById("btnManageDone").onclick = () => setManageMode(false);
  document.getElementById("btnSelectAll").onclick = () => {
    sessionsCache.forEach((s) => selectedSessions.add(String(s.sessionId || s.id || "")));
    renderSessionList();
  };
  document.getElementById("btnSelectNone").onclick = () => {
    selectedSessions.clear();
    renderSessionList();
  };
  document.getElementById("btnDeleteSelected").onclick = deleteSelectedFlow;
  document.getElementById("ctxDelete").onclick = () => {
    const s = ctxSession;
    closeCtxMenu();
    deleteOneFlow(s);
  };
  document.addEventListener("click", (ev) => {
    const menu = document.getElementById("ctxMenu");
    if (menu && !menu.hidden && !menu.contains(ev.target)) closeCtxMenu();
  });
  document.getElementById("btnTerm").onclick = () => api("/api/terminal", { method: "POST", body: JSON.stringify({ module: active }) });
  document.getElementById("btnSet").onclick = openSettings;
  document.getElementById("btnCloseSet").onclick = () => {
    saveSettings();
    document.getElementById("modal").classList.remove("show");
  };
  document.querySelectorAll('input[name="closeAction"]').forEach((el) => {
    el.addEventListener("change", () => { saveSettings(); });
  });
  document.querySelectorAll('input[name="kimiEngine"]').forEach((el) => {
    el.addEventListener("change", () => { saveSettings(); });
  });
  async function runVerify() {
    const r = await api("/api/verify", { method: "POST", body: "{}", timeout: 90000 });
    const lines = Object.entries(r.rows || {}).map(([k, v]) => {
      conn[k] = !!(v && v.cli);
      return k + " " + ((v && v.mark) || "") + " " + ((v && v.version) || v.path || "");
    });
    const out = document.getElementById("verifyOut");
    if (out) out.textContent = lines.join(" · ");
    document.querySelectorAll("[data-mark]").forEach((el) => {
      const id = el.getAttribute("data-mark");
      el.textContent = (r.rows && r.rows[id] && r.rows[id].mark) || "";
    });
    applyConnDots();
    return r;
  }
  document.getElementById("btnVerify").onclick = async () => {
    await saveSettings();
    await runVerify();
  };
  document.getElementById("btnLogs").onclick = () => api("/api/logs/open", { method: "POST", body: JSON.stringify({ which: "dir" }) });
  document.getElementById("btnImp").onclick = () => api("/api/logs/open", { method: "POST", body: JSON.stringify({ which: "important" }) });
  document.getElementById("alertBar").onclick = () => api("/api/logs/open", { method: "POST", body: JSON.stringify({ which: "important" }) });
  document.getElementById("btnSend").onclick = send;
  document.getElementById("btnCancel").onclick = () => api("/api/cancel", { method: "POST", body: "{}" });
  document.getElementById("input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });

  applyI18n();
  renderTabs();
  switchTab("kimi");
  runVerify().catch(function () { /* first paint without dots is fine */ });
  setInterval(pollEvents, 700);
  setInterval(pollHealth, 4000);
})();
