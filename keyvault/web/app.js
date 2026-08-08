const $ = (id) => document.getElementById(id);

let state = {
  unlocked: false,
  entries: [],
  current: null,
  categories: [],
  reminders: [],
  due: [],
};

async function api(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `请求失败 ${res.status}`);
  return data;
}

function parseFieldsText(text) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line.split("|").map((x) => x.trim());
      const [key, value = "", purpose = "", secretFlag = ""] = parts;
      const secret =
        ["1", "true", "yes", "secret", "敏感"].includes(secretFlag.toLowerCase()) ||
        /token|secret|password|密码|密钥|key/i.test(key);
      return { key, value, purpose, secret };
    })
    .filter((f) => f.key);
}

async function bootstrap() {
  const data = await api("/api/bootstrap");
  $("vaultPath").value = data.vault_path;
  $("syncHint").textContent = data.sync_hint;
  state.categories = data.suggested_categories || [];
  const list = $("catList");
  const filter = $("filterCategory");
  list.innerHTML = "";
  filter.innerHTML = '<option value="">全部分类</option>';
  state.categories.forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c;
    list.appendChild(opt);
    const opt2 = document.createElement("option");
    opt2.value = c;
    opt2.textContent = c;
    filter.appendChild(opt2);
  });
  try {
    const status = await api("/api/status");
    if (status.unlocked) await enterApp(status);
  } catch (_) {}
}

async function enterApp(status) {
  state.unlocked = true;
  $("gate").classList.add("hidden");
  $("app").classList.remove("hidden");
  $("pathLabel").textContent = status.vault_path || "";
  $("statsBar").textContent = `资产 ${status.count ?? "—"} · 已解锁`;
  await Promise.all([refreshList(), refreshReminders()]);
  if ((status.reminders_due || []).length) {
    state.due = status.reminders_due;
    renderAlertBar();
  }
}

async function unlock(create) {
  $("gateError").textContent = "";
  const body = {
    path: $("vaultPath").value.trim(),
    password: $("masterPassword").value,
  };
  try {
    const data = create
      ? await api("/api/init", { method: "POST", body: JSON.stringify(body) })
      : await api("/api/unlock", { method: "POST", body: JSON.stringify(body) });
    await enterApp(data);
  } catch (err) {
    $("gateError").textContent = err.message;
  }
}

function renderAlertBar() {
  const bar = $("alertBar");
  const due = state.due || [];
  const expiring = (state.entries || []).filter(
    (e) => e.expiry_status === "expired" || e.expiry_status === "expiring_soon"
  );
  if (!due.length && !expiring.length) {
    bar.classList.add("hidden");
    bar.innerHTML = "";
    return;
  }
  bar.classList.remove("hidden");
  const parts = [];
  if (due.length) {
    parts.push(`<div class="title">⚠ 待办提醒 · ${due.length} 条</div>`);
    parts.push(
      due
        .map((r) => {
          const label =
            r.alert_level === "overdue"
              ? `已过期 ${Math.abs(r.days_until_due)} 天`
              : r.days_until_due === 0
                ? "今天到期"
                : `${r.days_until_due} 天后到期`;
          return `<div class="alert-item">· ${escapeHtml(r.title)}（${label}）${r.notes ? " — " + escapeHtml(r.notes) : ""}</div>`;
        })
        .join("")
    );
  }
  if (expiring.length) {
    parts.push(`<div class="title" style="margin-top:8px">⚠ 资产密钥快到期 · ${expiring.length} 条</div>`);
    parts.push(
      expiring
        .slice(0, 8)
        .map((e) => {
          const label =
            e.expiry_status === "expired"
              ? "已过期"
              : `还剩 ${e.days_until_expiry} 天`;
          return `<div class="alert-item">· ${escapeHtml(e.name)}（${escapeHtml(e.expires_at)} · ${label}）</div>`;
        })
        .join("")
    );
  }
  bar.innerHTML = parts.join("");
}

async function refreshReminders() {
  state.reminders = await api("/api/reminders?include_done=1");
  state.due = state.reminders.filter((r) => r.should_alert);
  $("dueBadge").textContent = String(state.due.length);
  renderAlertBar();
  renderReminderPanel();
}

function renderReminderPanel() {
  const box = $("reminderPanel");
  const items = state.reminders.filter((r) => !r.done).concat(state.reminders.filter((r) => r.done).slice(0, 5));
  if (!items.length) {
    box.innerHTML = '<p class="muted" style="padding:12px">暂无提醒。可点「+ 提醒」或让 AI 帮你写入。</p>';
    return;
  }
  box.innerHTML = items
    .map((r) => {
      const level = r.alert_level;
      const when =
        level === "done"
          ? "已完成"
          : level === "overdue"
            ? `过期 ${Math.abs(r.days_until_due)} 天`
            : r.days_until_due === 0
              ? "今天"
              : `${r.days_until_due} 天后`;
      return `<div class="reminder-card ${level}">
        <div class="t">${escapeHtml(r.title)}</div>
          <div class="d">${escapeHtml(r.due_at)} · ${escapeHtml(r.repeat_label || "仅一次")} · 提前${r.remind_before_days}天 · ${when}</div>
        ${r.notes ? `<div class="purpose">${escapeHtml(r.notes)}</div>` : ""}
        <div class="actions">
          ${
            r.done
              ? `<button data-undone="${escapeAttr(r.id)}">恢复</button>`
              : `<button class="primary" data-done="${escapeAttr(r.id)}">完成</button>`
          }
          <button class="danger" data-del-rem="${escapeAttr(r.id)}">删除</button>
        </div>
      </div>`;
    })
    .join("");

  box.querySelectorAll("[data-done]").forEach((btn) => {
    btn.onclick = async () => {
      await api(`/api/reminders/${encodeURIComponent(btn.dataset.done)}/complete`, {
        method: "POST",
        body: JSON.stringify({ done: true }),
      });
      await refreshReminders();
    };
  });
  box.querySelectorAll("[data-undone]").forEach((btn) => {
    btn.onclick = async () => {
      await api(`/api/reminders/${encodeURIComponent(btn.dataset.undone)}/complete`, {
        method: "POST",
        body: JSON.stringify({ done: false }),
      });
      await refreshReminders();
    };
  });
  box.querySelectorAll("[data-del-rem]").forEach((btn) => {
    btn.onclick = async () => {
      if (!confirm("删除这条提醒？")) return;
      await api(`/api/reminders/${encodeURIComponent(btn.dataset.delRem)}`, { method: "DELETE" });
      await refreshReminders();
    };
  });
}

async function refreshList() {
  const q = $("search").value.trim();
  const category = $("filterCategory").value;
  const qs = new URLSearchParams();
  if (q) qs.set("q", q);
  if (category) qs.set("category", category);
  state.entries = await api(`/api/entries?${qs}`);
  $("statsBar").textContent = `资产 ${state.entries.length} · 已解锁`;
  renderList();
  renderAlertBar();
  if (state.current) {
    const still = state.entries.find((e) => e.id === state.current.id || e.name === state.current.name);
    if (still) await openEntry(still.name);
    else {
      state.current = null;
      $("detail").innerHTML = '<p class="muted">选择左侧条目，或新建资产 / 提醒。</p>';
    }
  }
}

function renderList() {
  const box = $("list");
  if (!state.entries.length) {
    box.innerHTML = '<p class="muted" style="padding:12px">暂无条目</p>';
    return;
  }
  box.innerHTML = state.entries
    .map((e) => {
      const active = state.current && (state.current.id === e.id || state.current.name === e.name);
      const keys = (e.fields || []).map((f) => f.key).slice(0, 4).join(" · ") || "无字段";
      return `<div class="item ${active ? "active" : ""}" data-name="${escapeAttr(e.name)}">
        <div class="name">${escapeHtml(e.name)}</div>
        <div class="meta">${escapeHtml(e.category)} · ${escapeHtml(keys)}</div>
      </div>`;
    })
    .join("");
  box.querySelectorAll(".item").forEach((el) => {
    el.addEventListener("click", () => openEntry(el.dataset.name));
  });
}

async function openEntry(name) {
  const item = await api(`/api/entries/${encodeURIComponent(name)}?show_secret=0`);
  state.current = item;
  renderList();
  const fields = (item.fields || [])
    .map(
      (f) => `<div class="field">
        <div>
          <strong>${escapeHtml(f.key)}</strong>
          ${f.secret ? '<div class="chip">敏感</div>' : ""}
          <div class="purpose">${escapeHtml(f.purpose || "")}</div>
        </div>
        <div>
          <code>${escapeHtml(f.value)}</code>
          ${f.secret ? `<div><button data-reveal="${escapeAttr(item.name)}" data-key="${escapeAttr(f.key)}">显示明文</button></div>` : ""}
        </div>
        <div><button class="danger" data-rm-field="${escapeAttr(f.key)}">删除</button></div>
      </div>`
    )
    .join("");

  $("detail").innerHTML = `
    <div class="row" style="justify-content:space-between;align-items:center">
      <div>
        <h2 style="margin:0;font-family:var(--display);letter-spacing:.06em;font-size:20px">${escapeHtml(item.name)}</h2>
        <div class="muted">${escapeHtml(item.category)} / ${escapeHtml(item.kind)}</div>
      </div>
      <div class="row">
        <button id="btnEditMeta" class="ghost">编辑</button>
        <button id="btnAddField" class="ghost">加字段</button>
        <button class="danger" id="btnDelete">删除</button>
      </div>
    </div>
    <p>${escapeHtml(item.summary || "（无整体用途说明）")}</p>
    <p class="muted">过期：${escapeHtml(item.expires_at || "无")} · ${escapeHtml(item.expiry_status)}</p>
    <div class="fields">${fields || '<p class="muted">还没有字段</p>'}</div>
  `;

  $("btnEditMeta").onclick = () => openEditDialog(item);
  $("btnAddField").onclick = () => addFieldFlow(item.name);
  $("btnDelete").onclick = async () => {
    if (!confirm(`确认删除「${item.name}」？`)) return;
    await api(`/api/entries/${encodeURIComponent(item.name)}`, { method: "DELETE" });
    state.current = null;
    await refreshList();
  };
  $("detail").querySelectorAll("[data-rm-field]").forEach((btn) => {
    btn.onclick = async () => {
      if (!confirm(`删除字段 ${btn.dataset.rmField}？`)) return;
      await api(
        `/api/entries/${encodeURIComponent(item.name)}/fields/${encodeURIComponent(btn.dataset.rmField)}`,
        { method: "DELETE" }
      );
      await openEntry(item.name);
      await refreshList();
    };
  });
  $("detail").querySelectorAll("[data-reveal]").forEach((btn) => {
    btn.onclick = async () => {
      const full = await api(`/api/entries/${encodeURIComponent(btn.dataset.reveal)}?show_secret=1`);
      const field = (full.fields || []).find((f) => f.key === btn.dataset.key);
      if (field) alert(`${field.key}:\n${field.value}`);
    };
  });
}

function openEditDialog(item) {
  const form = $("editForm");
  $("editTitle").textContent = item ? "编辑条目" : "新建条目";
  form.name.value = item?.name || "";
  form.category.value = item?.category || "其他";
  form.kind.value = item?.kind || "asset";
  form.summary.value = item?.summary || "";
  form.expires_at.value = item?.expires_at || "";
  form.fieldsText.value = item ? "" : "账号 | \n密码 |  | 登录密码 | secret";
  $("editError").textContent = "";
  $("editDialog").showModal();
}

async function saveEntry(ev) {
  ev.preventDefault();
  $("editError").textContent = "";
  const form = $("editForm");
  const payload = {
    name: form.name.value.trim(),
    category: form.category.value.trim() || "其他",
    kind: form.kind.value.trim() || "asset",
    summary: form.summary.value.trim(),
    expires_at: form.expires_at.value || "",
    fields: parseFieldsText(form.fieldsText.value),
  };
  try {
    if ($("editTitle").textContent.startsWith("编辑") && state.current) {
      await api(`/api/entries/${encodeURIComponent(state.current.name)}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      await openEntry(payload.name || state.current.name);
    } else {
      const created = await api("/api/entries", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.current = created.item;
      await openEntry(created.item.name);
    }
    $("editDialog").close();
    await refreshList();
  } catch (err) {
    $("editError").textContent = err.message;
  }
}

async function saveReminder(ev) {
  ev.preventDefault();
  $("reminderError").textContent = "";
  const form = $("reminderForm");
  try {
    await api("/api/reminders", {
      method: "POST",
      body: JSON.stringify({
        title: form.title.value.trim(),
        due_at: form.due_at.value,
        notes: form.notes.value.trim(),
        remind_before_days: Number(form.remind_before_days.value || 3),
        repeat: form.repeat.value || "once",
      }),
    });
    $("reminderDialog").close();
    form.reset();
    form.remind_before_days.value = 3;
    form.repeat.value = "once";
    await refreshReminders();
  } catch (err) {
    $("reminderError").textContent = err.message;
  }
}

async function addFieldFlow(name) {
  const key = prompt("字段名（Token / KEY / AccessKeyId…）");
  if (!key) return;
  const value = prompt("字段值");
  if (value === null) return;
  const purpose = prompt("这个字段干什么用？") || "";
  const secret = confirm("是否敏感？");
  await api(`/api/entries/${encodeURIComponent(name)}/fields`, {
    method: "POST",
    body: JSON.stringify({ key, value, purpose, secret }),
  });
  await openEntry(name);
  await refreshList();
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
function escapeAttr(s) {
  return escapeHtml(s).replaceAll("`", "&#96;");
}
function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

$("btnUnlock").onclick = () => unlock(false);
$("btnInit").onclick = () => unlock(true);
$("btnLock").onclick = async () => {
  await api("/api/lock", { method: "POST", body: "{}" });
  location.reload();
};
$("btnNew").onclick = () => openEditDialog(null);
$("btnNewReminder").onclick = () => {
  $("reminderError").textContent = "";
  const form = $("reminderForm");
  form.reset();
  form.remind_before_days.value = 3;
  form.repeat.value = "once";
  $("reminderDialog").showModal();
};
$("search").oninput = debounce(refreshList, 250);
$("filterCategory").onchange = refreshList;
$("editForm").addEventListener("submit", saveEntry);
$("reminderForm").addEventListener("submit", saveReminder);
document.querySelectorAll("[data-close-dialog]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const id = btn.getAttribute("data-close-dialog");
    const dlg = $(id);
    if (dlg?.open) dlg.close();
  });
});
$("btnMcp").onclick = async () => {
  try {
    const data = await api("/api/write-mcp", { method: "POST", body: "{}" });
    alert(`已写入 Cursor 配置：\n${data.path}\n\n请到 Cursor → Settings → MCP 重载后使用。\n之后在 Cursor 里写软件时，AI 也会提醒快到期的待办。`);
  } catch (err) {
    alert(err.message);
  }
};

bootstrap();
