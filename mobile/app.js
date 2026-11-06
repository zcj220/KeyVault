import { decryptVault, encryptVault } from "./crypto.js";
import { CATEGORIES, categoryHint, categoryLabel, t } from "./i18n.js";

const state = {
  lang: localStorage.getItem("kv-lang") || "zh",
  theme: localStorage.getItem("kv-theme") || "system",
  screen: "unlock",
  stack: [],
  vault: null,
  fileName: "",
  fileHandle: null,
  sync: "none",
  busy: false,
  error: "",
  notice: "",
  showPassword: false,
  query: "",
  category: "",
  entryId: "",
  revealed: new Set(),
  sheet: false,
  draft: null,
};

const app = document.querySelector("#app");
const fileInput = document.querySelector("#file");

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function L(key, vars) {
  return t(state.lang, key, vars);
}

function nowIso() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00");
}

function todayStr() {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
  document.documentElement.lang = state.lang === "en" ? "en" : "zh-CN";
}

function idb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open("xinzao-keyvault", 1);
    req.onupgradeneeded = () => req.result.createObjectStore("files");
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function idbGet(key) {
  const db = await idb();
  return new Promise((resolve, reject) => {
    const req = db.transaction("files").objectStore("files").get(key);
    req.onsuccess = () => resolve(req.result || null);
    req.onerror = () => reject(req.error);
  });
}

async function idbSet(key, value) {
  const db = await idb();
  return new Promise((resolve, reject) => {
    const req = db.transaction("files", "readwrite").objectStore("files").put(value, key);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

function activeEntries() {
  return (state.vault?.entries || []).filter((entry) => !entry.deleted_at);
}

function daysUntil(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const due = new Date(y, m - 1, d);
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((due - start) / 86400000);
}

function dueReminders() {
  return (state.vault?.reminders || []).filter((item) => {
    if (item.done) return false;
    const days = daysUntil(item.due_at);
    const lead = Number(item.remind_before_days ?? 3);
    return days >= 0 && days <= lead;
  });
}

function categoryNames() {
  const extra = [];
  for (const entry of activeEntries()) {
    const name = entry.category || "其他";
    if (!CATEGORIES.some((row) => row[0] === name) && !extra.includes(name)) extra.push(name);
  }
  return [...CATEGORIES.map((row) => row[0]), ...extra];
}

function countIn(name) {
  return activeEntries().filter((entry) => (entry.category || "其他") === name).length;
}

function findEntry(id) {
  return (state.vault?.entries || []).find((entry) => entry.id === id);
}

function go(screen, extra = {}) {
  state.stack.push(state.screen);
  Object.assign(state, extra, { screen, sheet: false, error: "", notice: "" });
  render();
}

function back() {
  const prev = state.stack.pop() || "home";
  state.screen = prev === "unlock" ? "home" : prev;
  state.sheet = false;
  state.error = "";
  render();
}

function nav(screen) {
  state.stack = [];
  state.screen = screen;
  state.sheet = false;
  state.error = "";
  render();
}

async function rememberBytes(bytes, name) {
  state.fileName = name || "vault.kvault";
  state.sync = "ready";
  await idbSet("vault", { name: state.fileName, bytes: bytes.slice() });
}

async function pickWithHandle() {
  const [handle] = await window.showOpenFilePicker({
    types: [{ description: "KeyVault", accept: { "application/octet-stream": [".kvault"] } }],
  });
  state.fileHandle = handle;
  const file = await handle.getFile();
  const bytes = new Uint8Array(await file.arrayBuffer());
  await rememberBytes(bytes, file.name);
}

function readChosenFile(file) {
  return file.arrayBuffer().then((buf) => rememberBytes(new Uint8Array(buf), file.name));
}

async function persist(bytes) {
  await rememberBytes(bytes, state.fileName);
  if (state.fileHandle?.createWritable) {
    const writable = await state.fileHandle.createWritable();
    await writable.write(bytes);
    await writable.close();
  }
}

async function saveVault() {
  const password = state.password;
  if (!password || !state.vault) return;
  state.vault.version = 3;
  const bytes = await encryptVault(password, state.vault);
  await persist(bytes);
  state.notice = L("saved");
}

function purgeOldTrash() {
  const now = Date.now();
  const before = state.vault.entries.length;
  state.vault.entries = state.vault.entries.filter((entry) => {
    if (!entry.deleted_at) return true;
    const deleted = Date.parse(entry.deleted_at);
    if (Number.isNaN(deleted)) return true;
    return now - deleted <= 30 * 86400000;
  });
  return state.vault.entries.length !== before;
}

async function unlock(event) {
  event.preventDefault();
  const password = new FormData(event.target).get("password");
  const stored = await idbGet("vault");
  if (!stored?.bytes) {
    state.error = L("needFile");
    render();
    return;
  }
  state.busy = true;
  state.error = "";
  render();
  try {
    const data = await decryptVault(String(password), stored.bytes);
    state.password = String(password);
    state.vault = data.version ? data : { version: 3, entries: data.entries || [], reminders: data.reminders || [] };
    state.vault.entries ||= [];
    state.vault.reminders ||= [];
    if (purgeOldTrash()) await saveVault();
    state.screen = "home";
    state.stack = [];
  } catch (err) {
    state.error = err.message === "bad-password" ? L("badPassword") : L("badFile");
  } finally {
    state.busy = false;
    render();
  }
}

function lock() {
  state.password = "";
  state.vault = null;
  state.screen = "unlock";
  state.stack = [];
  state.revealed = new Set();
  state.draft = null;
  render();
}

function blankField() {
  return { id: crypto.randomUUID().replaceAll("-", ""), key: "", value: "", purpose: "", secret: false };
}

function openAsset(entry) {
  state.draft = entry
    ? structuredClone(entry)
    : {
        id: crypto.randomUUID().replaceAll("-", ""),
        name: "",
        category: "其他",
        kind: "asset",
        summary: "",
        tags: [],
        fields: [blankField(), blankField()],
        expires_at: "",
        created_at: nowIso(),
        updated_at: nowIso(),
        deleted_at: null,
      };
  go(entry ? "edit" : "edit", { screen: "edit" });
}

function openNote() {
  state.draft = {
    id: crypto.randomUUID().replaceAll("-", ""),
    name: "",
    category: "杂记",
    kind: "note",
    summary: "",
    tags: [],
    fields: [{ ...blankField(), key: state.lang === "en" ? "Note" : "正文" }],
    expires_at: "",
    created_at: nowIso(),
    updated_at: nowIso(),
    deleted_at: null,
  };
  go("note");
}

function openReminder() {
  state.draft = {
    id: crypto.randomUUID().replaceAll("-", ""),
    title: "",
    due_at: todayStr(),
    notes: "",
    remind_before_days: 3,
    repeat: "once",
    done: false,
    created_at: nowIso(),
    updated_at: nowIso(),
  };
  go("reminder");
}

function upsertEntry(entry) {
  const list = state.vault.entries;
  const index = list.findIndex((item) => item.id === entry.id);
  entry.updated_at = nowIso();
  if (index >= 0) list[index] = entry;
  else list.push(entry);
}

async function saveEntry(event) {
  event.preventDefault();
  const form = new FormData(event.target);
  const draft = state.draft;
  draft.name = String(form.get("name") || "").trim();
  if (!draft.name) {
    state.error = L("nameRequired");
    render();
    return;
  }
  draft.category = String(form.get("category") || draft.category || "其他");
  draft.summary = String(form.get("summary") || "");
  draft.expires_at = String(form.get("expires_at") || "") || null;
  if (state.screen === "note") {
    draft.kind = "note";
    draft.fields = [{ ...(draft.fields[0] || blankField()), key: draft.fields[0]?.key || "正文", value: String(form.get("body") || ""), secret: false }];
  } else {
    const keys = form.getAll("fieldKey");
    const values = form.getAll("fieldValue");
    const purposes = form.getAll("fieldPurpose");
    draft.fields = keys
      .map((key, i) => ({
        id: draft.fields[i]?.id || crypto.randomUUID().replaceAll("-", ""),
        key: String(key || "").trim(),
        value: String(values[i] || ""),
        purpose: String(purposes[i] || ""),
        secret: Boolean(draft.fields[i]?.secret),
      }))
      .filter((field) => field.key);
  }
  upsertEntry(draft);
  await saveVault();
  state.entryId = draft.id;
  state.screen = "detail";
  render();
}

async function saveReminder(event) {
  event.preventDefault();
  const form = new FormData(event.target);
  const draft = state.draft;
  draft.title = String(form.get("title") || "").trim();
  if (!draft.title) {
    state.error = L("titleRequired");
    render();
    return;
  }
  draft.due_at = String(form.get("due_at") || todayStr());
  draft.remind_before_days = Number(form.get("lead") || 3);
  draft.repeat = String(form.get("repeat") || "once");
  draft.notes = String(form.get("notes") || "");
  draft.updated_at = nowIso();
  const list = state.vault.reminders;
  const index = list.findIndex((item) => item.id === draft.id);
  if (index >= 0) list[index] = draft;
  else list.push(draft);
  await saveVault();
  nav("home");
}

function addMonths(iso, months) {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(y, m - 1 + months, 1);
  const last = new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
  const day = Math.min(d, last);
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  return `${date.getFullYear()}-${mm}-${String(day).padStart(2, "0")}`;
}

function nextDue(item) {
  if (item.repeat === "weekly") {
    const [y, m, d] = item.due_at.split("-").map(Number);
    const date = new Date(y, m - 1, d + 7);
    const mm = String(date.getMonth() + 1).padStart(2, "0");
    return `${date.getFullYear()}-${mm}-${String(date.getDate()).padStart(2, "0")}`;
  }
  if (item.repeat === "monthly") return addMonths(item.due_at, 1);
  if (item.repeat === "quarterly") return addMonths(item.due_at, 3);
  if (item.repeat === "yearly") return addMonths(item.due_at, 12);
  return null;
}

async function completeReminder(id) {
  const item = state.vault.reminders.find((row) => row.id === id);
  if (!item) return;
  if (item.repeat !== "once") {
    let nxt = nextDue(item);
    let guard = 0;
    while (nxt && nxt <= todayStr() && guard < 48) {
      item.due_at = nxt;
      nxt = nextDue(item);
      guard += 1;
    }
    if (nxt) item.due_at = nxt;
    item.done = false;
  } else {
    item.done = true;
  }
  item.updated_at = nowIso();
  await saveVault();
  render();
}

async function deleteEntry(id) {
  const entry = findEntry(id);
  if (!entry) return;
  if (!window.confirm(L("confirmDel"))) return;
  entry.deleted_at = nowIso();
  entry.updated_at = nowIso();
  await saveVault();
  nav("home");
}

async function restoreEntry(id) {
  const entry = findEntry(id);
  if (!entry) return;
  entry.deleted_at = null;
  entry.updated_at = nowIso();
  await saveVault();
  render();
}

function entryMatches(entry, query) {
  const hay = [
    entry.name,
    entry.category,
    entry.summary,
    ...(entry.tags || []),
    ...(entry.fields || []).flatMap((field) => [field.key, field.value, field.purpose]),
  ]
    .join("\n")
    .toLowerCase();
  return hay.includes(query.toLowerCase());
}

function looksAccount(key) {
  return /账号|邮箱|email|user|username/i.test(key);
}

function looksSecret(field) {
  return field.secret || /密码|password|token|密钥|secret/i.test(field.key || "");
}

function looksUrl(field) {
  return /^https?:\/\//i.test(field.value || "") || /地址|网址|url|链接/i.test(field.key || "");
}

async function copyText(value) {
  await navigator.clipboard.writeText(value);
  state.notice = L("copied");
  render();
}

function dayLabel(iso) {
  const days = daysUntil(iso);
  if (days === 0) return L("dueToday");
  return L("daysLeft", { n: days });
}

function icon(name) {
  const paths = {
    home: "M4 11.5 12 4l8 7.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z",
    cats: "M4 4h6v6H4zm10 0h6v6h-6zM4 14h6v6H4zm10 0h6v6h-6z",
    search: "M11 6a5 5 0 1 1 0 10 5 5 0 0 1 0-10zm6.5 10.5-3-3",
    gear: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm8 4-1.6.8.2 1.8-1.7 1-1.5-1.1-1.6.6-.6 1.7-1.8-.2L12 20l-.8-1.6-1.8.2-.6-1.7-1.6-.6-1.5 1.1-1.7-1 .2-1.8L2 12l1.6-.8-.2-1.8 1.7-1 1.5 1.1 1.6-.6.6-1.7L10.6 4 12 5.6 13.4 4l1.8.2.6 1.7 1.6.6 1.5-1.1 1.7 1-.2 1.8z",
  };
  return `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7"><path d="${paths[name]}"></path></svg>`;
}

function navBar(current) {
  const items = [
    ["home", "tabHome", "home"],
    ["categories", "tabCats", "cats"],
    ["search", "tabSearch", "search"],
    ["settings", "tabSettings", "gear"],
  ];
  return `<nav class="nav">${items
    .map(
      ([screen, key, glyph]) =>
        `<button type="button" data-nav="${screen}" class="${current === screen ? "on" : ""}">${icon(glyph)}<div>${esc(L(key))}</div></button>`
    )
    .join("")}</nav>`;
}

function top(title) {
  return `<div class="topbar"><button class="text-btn" type="button" data-act="back">${esc(L("back"))}</button><h2>${esc(title)}</h2><span></span></div>`;
}

function renderUnlock() {
  const sync = state.sync === "ready" ? L("syncReady") : state.sync === "busy" ? L("syncBusy") : L("syncNone");
  return `<form class="screen unlock" data-act="unlock">
    <div class="vault-mark" aria-hidden="true">
      <svg width="92" height="92" viewBox="0 0 92 92">
        <circle cx="46" cy="46" r="40" fill="none" stroke="#8fd8b8" stroke-width="8"/>
        <circle cx="46" cy="46" r="22" fill="none" stroke="#14915f" stroke-width="6"/>
        <circle cx="46" cy="46" r="4" fill="#14915f"/>
      </svg>
    </div>
    <h1>${esc(L("appName"))}</h1>
    <p class="tagline">${esc(L("tagline"))}</p>
    <label class="password-row">
      <input name="password" type="${state.showPassword ? "text" : "password"}" placeholder="${esc(L("password"))}" autocomplete="current-password" required>
      <button class="text-btn" type="button" data-act="toggle-password">${esc(state.showPassword ? L("hide") : L("show"))}</button>
    </label>
    <p class="error">${esc(state.error)}</p>
    <button class="primary" type="submit" ${state.busy ? "disabled" : ""}>${esc(state.busy ? L("unlocking") : L("unlock"))}</button>
    <p class="sync">${esc(sync)}</p>
    ${state.sync === "ready" ? "" : `<p class="sync"><button class="text-btn" type="button" data-act="pick">${esc(L("pickFile"))}</button></p>`}
  </form>`;
}

function renderHome() {
  const dues = dueReminders();
  const names = categoryNames();
  const total = activeEntries().length;
  const cards = dues.length
    ? `<div class="hscroll">${dues
        .map(
          (item) => `<button class="rem-card" type="button" data-go="reminders"><b>${esc(item.title)}</b><span class="pill">${esc(dayLabel(item.due_at))}</span><div class="muted">${esc(L("dueOn"))} ${esc(item.due_at)}</div></button>`
        )
        .join("")}</div>`
    : `<p class="muted">${esc(L("noDue"))}</p>`;
  return `<div class="screen">
    <div class="brand-row"><div class="logo">KV</div><div><h2>${esc(L("appName"))}</h2><p>${esc(L("tagline"))}</p></div></div>
    <label class="search">${icon("search")}<input id="q" type="search" placeholder="${esc(L("searchPh"))}" value="${esc(state.query)}"></label>
    <div class="section-h"><h3>${esc(L("reminders"))}</h3><button class="linkish" type="button" data-go="reminders">${esc(L("seeAll"))}</button></div>
    ${cards}
    <div class="section-h"><h3>${esc(L("categories"))}</h3><span class="muted">${esc(L("countItems", { c: names.length, n: total }))}</span></div>
    <div class="grid3">${names
      .map(
        (name) => `<button class="cat-card" type="button" data-cat="${esc(name)}"><strong>${esc(categoryLabel(state.lang, name))}</strong><em>${esc(L("items", { n: countIn(name) }))}</em></button>`
      )
      .join("")}</div>
    <div class="add-bar"><button class="primary" type="button" data-act="sheet">${esc(L("addOne"))}</button></div>
    ${sheet()}
    ${navBar("home")}
  </div>`;
}

function sheet() {
  if (!state.sheet) return "";
  return `<div class="sheet-bg" data-act="close-sheet"><div class="sheet" data-stop>
    <button class="choice" type="button" data-act="new-asset"><b>${esc(L("sheetAsset"))}</b><span class="muted">${esc(L("sheetAssetHint"))}</span></button>
    <button class="choice" type="button" data-act="new-note"><b>${esc(L("sheetNote"))}</b><span class="muted">${esc(L("sheetNoteHint"))}</span></button>
    <button class="choice" type="button" data-act="new-rem"><b>${esc(L("sheetRem"))}</b><span class="muted">${esc(L("sheetRemHint"))}</span></button>
  </div></div>`;
}

function renderCategories() {
  const names = categoryNames();
  return `<div class="screen">
    ${top(L("catList"))}
    <div class="list">${names
      .map(
        (name) => `<button class="row-card" type="button" data-cat="${esc(name)}"><span><b>${esc(categoryLabel(state.lang, name))}</b><small>${esc(categoryHint(state.lang, name))}</small></span><b>${countIn(name)}</b></button>`
      )
      .join("")}</div>
    ${navBar("categories")}
  </div>`;
}

function renderList(title, entries) {
  const body = entries.length
    ? entries
        .map(
          (entry) => `<button class="row-card" type="button" data-entry="${esc(entry.id)}"><span><b>${esc(entry.name)}</b><small>${esc(categoryLabel(state.lang, entry.category || "其他"))}</small></span></button>`
        )
        .join("")
    : `<p class="muted">${esc(title === L("tabSearch") ? L("emptySearch") : L("emptyCat"))}</p>`;
  return `<div class="screen">${top(title)}<div class="list">${body}</div>${navBar(state.screen === "search" ? "search" : "categories")}</div>`;
}

function renderSearch() {
  const query = state.query.trim();
  const entries = query ? activeEntries().filter((entry) => entryMatches(entry, query)) : [];
  return `<div class="screen">
    ${top(L("tabSearch"))}
    <label class="search">${icon("search")}<input id="q" type="search" placeholder="${esc(L("searchPh"))}" value="${esc(state.query)}"></label>
    <div class="list">${query ? entries.map((entry) => `<button class="row-card" type="button" data-entry="${esc(entry.id)}"><span><b>${esc(entry.name)}</b><small>${esc(entry.summary || categoryLabel(state.lang, entry.category || "其他"))}</small></span></button>`).join("") || `<p class="muted">${esc(L("emptySearch"))}</p>` : ""}</div>
    ${navBar("search")}
  </div>`;
}

function renderDetail() {
  const entry = findEntry(state.entryId);
  if (!entry) return renderHome();
  const fields = entry.fields || [];
  const account = fields.find((field) => looksAccount(field.key));
  const secret = fields.find((field) => looksSecret(field));
  const link = fields.find((field) => looksUrl(field));
  const rows = fields
    .map((field) => {
      const hidden = looksSecret(field) && !state.revealed.has(field.id);
      const value = hidden ? "••••••••" : field.value;
      return `<div class="kv"><div><small class="muted">${esc(field.key)}${field.purpose ? " · " + esc(field.purpose) : ""}</small><b>${esc(value)}</b></div><span>${hidden ? `<button class="text-btn" type="button" data-reveal="${esc(field.id)}">${esc(L("show"))}</button>` : ""}${field.value ? `<button class="text-btn" type="button" data-copy="${esc(field.value)}">${esc(L("copy"))}</button>` : ""}</span></div>`;
    })
    .join("");
  return `<div class="screen">
    ${top(L("entry"))}
    <div class="detail-head"><div><h2>${esc(entry.name)}</h2><p class="muted">${esc(categoryLabel(state.lang, entry.category || "其他"))}</p></div><button class="text-btn" type="button" data-act="edit-current">${esc(L("edit"))}</button></div>
    ${entry.summary ? `<p>${esc(entry.summary)}</p>` : ""}
    ${rows}
    <p class="muted">${esc(L("created"))} ${esc(entry.created_at || "")}</p>
    <p class="muted">${esc(L("updated"))} ${esc(entry.updated_at || "")}</p>
    <p class="notice">${esc(state.notice)}</p>
    <div class="actions">
      ${account ? `<button class="ghost" type="button" data-copy="${esc(account.value)}">${esc(L("copyAccount"))}</button>` : ""}
      ${secret ? `<button class="ghost" type="button" data-copy="${esc(secret.value)}">${esc(L("copySecret"))}</button>` : ""}
      ${link ? `<a class="primary" style="text-align:center;text-decoration:none" href="${esc(link.value)}" target="_blank" rel="noreferrer">${esc(L("openLink"))}</a>` : ""}
    </div>
    <p><button class="text-btn" type="button" data-del="${esc(entry.id)}">${esc(L("del"))}</button></p>
  </div>`;
}

function categoryChips(selected) {
  const names = categoryNames();
  if (!names.includes(selected)) names.push(selected);
  return `<div class="chips">${names
    .map(
      (name) => `<button class="chip ${name === selected ? "on" : ""}" type="button" data-pick-cat="${esc(name)}">${esc(categoryLabel(state.lang, name))}</button>`
    )
    .join("")}</div><input type="hidden" name="category" value="${esc(selected)}">`;
}

function renderEdit() {
  const draft = state.draft;
  const fields = draft.fields?.length ? draft.fields : [blankField()];
  return `<form class="screen" data-act="save-entry">
    ${top(draft.created_at === draft.updated_at ? L("newAsset") : L("editAsset"))}
    <label class="field"><span>${esc(L("name"))}</span><input name="name" required value="${esc(draft.name)}"></label>
    <div class="field"><span>${esc(L("category"))}</span>${categoryChips(draft.category || "其他")}</div>
    <label class="field"><span>${esc(L("summaryLabel"))}</span><textarea name="summary">${esc(draft.summary || "")}</textarea></label>
    <label class="field"><span>${esc(L("expiry"))}</span><input name="expires_at" type="date" value="${esc(draft.expires_at || "")}"></label>
    <h3>${esc(L("fieldName"))}</h3>
    ${fields
      .map(
        (field, index) => `<div class="field-card">
          <input name="fieldKey" placeholder="${esc(L("fieldName"))}" value="${esc(field.key)}">
          <input name="fieldValue" style="margin-top:8px" type="${field.secret ? "password" : "text"}" placeholder="${esc(L("fieldValue"))}" value="${esc(field.value)}">
          <input name="fieldPurpose" style="margin-top:8px" placeholder="${esc(L("purpose"))}" value="${esc(field.purpose || "")}">
          <div class="switch" style="margin-top:8px"><span>${esc(L("secret"))}</span><input data-secret="${index}" type="checkbox" ${field.secret ? "checked" : ""}></div>
          <button class="text-btn" type="button" data-drop-field="${index}">${esc(L("remove"))}</button>
        </div>`
      )
      .join("")}
    <button class="ghost" type="button" data-act="add-field">${esc(L("addField"))}</button>
    <p class="error">${esc(state.error)}</p>
    <p class="notice">${esc(state.notice)}</p>
    <button class="primary" type="submit">${esc(L("save"))}</button>
  </form>`;
}

function renderNote() {
  const draft = state.draft;
  const body = draft.fields?.[0]?.value || "";
  return `<form class="screen" data-act="save-entry">
    ${top(L("writeNote"))}
    <label class="field"><span>${esc(L("title"))}</span><input name="name" required value="${esc(draft.name)}"></label>
    <div class="field"><span>${esc(L("category"))}</span>${categoryChips(draft.category || "杂记")}</div>
    <label class="field"><span>${esc(L("noteBody"))}</span><textarea name="body" placeholder="${esc(L("notePh"))}">${esc(body)}</textarea></label>
    <p class="error">${esc(state.error)}</p>
    <button class="primary" type="submit">${esc(L("save"))}</button>
  </form>`;
}

function renderReminder() {
  const draft = state.draft;
  const options = ["once", "weekly", "monthly", "quarterly", "yearly"]
    .map((key) => `<option value="${key}" ${draft.repeat === key ? "selected" : ""}>${esc(L(key))}</option>`)
    .join("");
  return `<form class="screen" data-act="save-rem">
    ${top(L("newReminder"))}
    <label class="field"><span>${esc(L("title"))}</span><input name="title" required value="${esc(draft.title)}"></label>
    <label class="field"><span>${esc(L("dueDate"))}</span><input name="due_at" type="date" required value="${esc(draft.due_at)}"></label>
    <label class="field"><span>${esc(L("leadDays"))}</span><input name="lead" type="number" min="0" max="90" value="${esc(draft.remind_before_days)}"></label>
    <label class="field"><span>${esc(L("repeat"))}</span><select name="repeat">${options}</select></label>
    <label class="field"><span>${esc(L("notes"))}</span><textarea name="notes">${esc(draft.notes || "")}</textarea></label>
    <p class="error">${esc(state.error)}</p>
    <button class="primary" type="submit">${esc(L("save"))}</button>
  </form>`;
}

function renderReminders() {
  const items = (state.vault.reminders || []).filter((item) => !item.done);
  return `<div class="screen">${top(L("remindersAll"))}<div class="list">${items
    .map(
      (item) => `<div class="row-card"><span><b>${esc(item.title)}</b><small>${esc(item.due_at)} · ${esc(dayLabel(item.due_at))}</small></span><button class="text-btn" type="button" data-done-rem="${esc(item.id)}">${esc(L("done"))}</button></div>`
    )
    .join("") || `<p class="muted">${esc(L("noDue"))}</p>`}</div></div>`;
}

function renderTrash() {
  const items = (state.vault.entries || []).filter((entry) => entry.deleted_at);
  return `<div class="screen">${top(L("trash"))}<p class="muted">${esc(L("trashHint"))}</p><div class="list">${items
    .map(
      (entry) => `<div class="row-card"><span><b>${esc(entry.name)}</b></span><button class="text-btn" type="button" data-restore="${esc(entry.id)}">${esc(L("restore"))}</button></div>`
    )
    .join("") || `<p class="muted">${esc(L("noTrash"))}</p>`}</div></div>`;
}

function renderSettings() {
  const themeBtn = (value, key) =>
    `<button class="chip ${state.theme === value ? "on" : ""}" type="button" data-theme="${value}">${esc(L(key))}</button>`;
  return `<div class="screen">
    ${top(L("settings"))}
    <div class="card" style="padding:14px;margin-bottom:12px"><b>${esc(L("statusOk"))}</b><p class="muted">${esc(L("statusHint"))}</p></div>
    <div class="field"><span>${esc(L("appearance"))}</span><div class="seg">${themeBtn("light", "light")}${themeBtn("dark", "dark")}${themeBtn("system", "system")}</div></div>
    <div class="field"><span>${esc(L("language"))}</span><div class="seg">
      <button class="chip ${state.lang === "zh" ? "on" : ""}" type="button" data-lang="zh">${esc(L("chinese"))}</button>
      <button class="chip ${state.lang === "en" ? "on" : ""}" type="button" data-lang="en">${esc(L("english"))}</button>
    </div></div>
    <div class="field"><span>${esc(L("data"))}</span><p class="muted">${esc(L("dataHint"))}</p>
      <button class="ghost" type="button" data-act="pick">${esc(L("pickFile"))}</button>
      <button class="ghost" type="button" data-act="export">${esc(L("exportFile"))}</button>
    </div>
    <button class="row-card" type="button" data-go="trash"><span><b>${esc(L("trash"))}</b><small>${esc(L("trashHint"))}</small></span></button>
    <p class="muted">${esc(L("aboutHint"))}</p>
    <button class="primary" type="button" data-act="lock">${esc(L("lockNow"))}</button>
    ${navBar("settings")}
  </div>`;
}

function render() {
  applyTheme();
  const screen = state.screen;
  let html = "";
  if (!state.vault && screen !== "unlock") state.screen = "unlock";
  if (state.screen === "unlock") html = renderUnlock();
  else if (state.screen === "home") html = renderHome();
  else if (state.screen === "categories") html = renderCategories();
  else if (state.screen === "category") html = renderList(categoryLabel(state.lang, state.category), activeEntries().filter((entry) => (entry.category || "其他") === state.category));
  else if (state.screen === "search") html = renderSearch();
  else if (state.screen === "detail") html = renderDetail();
  else if (state.screen === "edit") html = renderEdit();
  else if (state.screen === "note") html = renderNote();
  else if (state.screen === "reminder") html = renderReminder();
  else if (state.screen === "reminders") html = renderReminders();
  else if (state.screen === "trash") html = renderTrash();
  else if (state.screen === "settings") html = renderSettings();
  else html = renderHome();
  app.innerHTML = html;
}

async function exportFile() {
  const stored = await idbGet("vault");
  if (!stored?.bytes) return;
  const blob = new Blob([stored.bytes], { type: "application/octet-stream" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = state.fileName || "vault.kvault";
  link.click();
  URL.revokeObjectURL(link.href);
}

async function chooseFile() {
  try {
    if (window.showOpenFilePicker) await pickWithHandle();
    else {
      fileInput.click();
      return;
    }
    state.error = "";
    if (state.password) {
      const stored = await idbGet("vault");
      state.vault = await decryptVault(state.password, stored.bytes);
    }
    render();
  } catch (err) {
    if (err?.name === "AbortError") return;
    if (err?.message === "bad-password") {
      state.error = L("badPassword");
      render();
      return;
    }
    fileInput.click();
  }
}

app.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-act],[data-nav],[data-go],[data-cat],[data-entry],[data-copy],[data-reveal],[data-del],[data-restore],[data-done-rem],[data-theme],[data-lang],[data-pick-cat],[data-secret],[data-drop-field],[data-act]");
  if (!target || target.dataset.stop !== undefined && event.target !== target && target.classList.contains("sheet")) return;
  if (target.dataset.stop !== undefined) event.stopPropagation();
  if (target.dataset.nav) return nav(target.dataset.nav);
  if (target.dataset.go) return go(target.dataset.go);
  if (target.dataset.cat) return go("category", { category: target.dataset.cat });
  if (target.dataset.entry) return go("detail", { entryId: target.dataset.entry, revealed: new Set() });
  if (target.dataset.theme) {
    state.theme = target.dataset.theme;
    localStorage.setItem("kv-theme", state.theme);
    return render();
  }
  if (target.dataset.lang) {
    state.lang = target.dataset.lang;
    localStorage.setItem("kv-lang", state.lang);
    return render();
  }
  if (target.dataset.pickCat && state.draft) {
    captureDraft();
    state.draft.category = target.dataset.pickCat;
    return render();
  }
  if (target.dataset.secret != null && state.draft) {
    captureDraft();
    const index = Number(target.dataset.secret);
    state.draft.fields[index].secret = target.checked;
    return render();
  }
  if (target.dataset.dropField != null && state.draft) {
    captureDraft();
    state.draft.fields.splice(Number(target.dataset.dropField), 1);
    return render();
  }
  if (target.dataset.reveal) {
    state.revealed.add(target.dataset.reveal);
    return render();
  }
  if (target.dataset.copy) return copyText(target.dataset.copy);
  if (target.dataset.del) return deleteEntry(target.dataset.del);
  if (target.dataset.restore) return restoreEntry(target.dataset.restore);
  if (target.dataset.doneRem) return completeReminder(target.dataset.doneRem);
  const act = target.dataset.act;
  if (act === "back") return back();
  if (act === "toggle-password") {
    state.showPassword = !state.showPassword;
    return render();
  }
  if (act === "pick") return chooseFile();
  if (act === "sheet") {
    state.sheet = true;
    return render();
  }
  if (act === "close-sheet") {
    state.sheet = false;
    return render();
  }
  if (act === "new-asset") return openAsset(null);
  if (act === "new-note") return openNote();
  if (act === "new-rem") return openReminder();
  if (act === "edit-current") return openAsset(findEntry(state.entryId));
  if (act === "add-field") {
    captureDraft();
    state.draft.fields.push(blankField());
    return render();
  }
  if (act === "lock") return lock();
  if (act === "export") return exportFile();
});

app.addEventListener("submit", (event) => {
  const act = event.target.dataset.act;
  if (act === "unlock") unlock(event);
  if (act === "save-entry") saveEntry(event);
  if (act === "save-rem") saveReminder(event);
});

app.addEventListener("input", (event) => {
  if (event.target.id === "q") {
    state.query = event.target.value;
    if (state.screen === "home" && state.query.trim()) nav("search");
    else if (state.screen === "search") {
      const cursor = event.target.selectionStart;
      render();
      const box = document.querySelector("#q");
      if (box) {
        box.focus();
        box.setSelectionRange(cursor, cursor);
      }
    }
  }
});

function captureDraft() {
  const form = app.querySelector("form");
  if (!form || !state.draft) return;
  const data = new FormData(form);
  if (data.has("name")) state.draft.name = String(data.get("name") || "");
  if (data.has("summary")) state.draft.summary = String(data.get("summary") || "");
  if (data.has("expires_at")) state.draft.expires_at = String(data.get("expires_at") || "");
  if (data.has("title")) state.draft.title = String(data.get("title") || "");
  if (data.has("due_at")) state.draft.due_at = String(data.get("due_at") || "");
  if (data.has("lead")) state.draft.remind_before_days = Number(data.get("lead") || 3);
  if (data.has("repeat")) state.draft.repeat = String(data.get("repeat") || "once");
  if (data.has("notes")) state.draft.notes = String(data.get("notes") || "");
  if (data.has("body") && state.draft.fields?.[0]) state.draft.fields[0].value = String(data.get("body") || "");
  if (data.has("fieldKey")) {
    const keys = data.getAll("fieldKey");
    const values = data.getAll("fieldValue");
    const purposes = data.getAll("fieldPurpose");
    state.draft.fields = keys.map((key, i) => ({
      ...(state.draft.fields[i] || blankField()),
      key: String(key || ""),
      value: String(values[i] || ""),
      purpose: String(purposes[i] || ""),
    }));
  }
}

fileInput.addEventListener("change", async () => {
  const file = fileInput.files?.[0];
  if (!file) return;
  await readChosenFile(file);
  fileInput.value = "";
  if (state.password) {
    try {
      const stored = await idbGet("vault");
      state.vault = await decryptVault(state.password, stored.bytes);
      state.error = "";
    } catch (err) {
      state.error = err.message === "bad-password" ? L("badPassword") : L("badFile");
    }
  }
  render();
});

idbGet("vault")
  .then((stored) => {
    if (stored?.bytes) {
      state.sync = "ready";
      state.fileName = stored.name || "vault.kvault";
    }
  })
  .finally(render);
