import "./style.css";

const TOKEN_KEY = "gluekettle_token";
const LABELS = { cold: "冷锅", boiling: "熬煮中", drawn: "已出胶" };
const ROLE_LABELS = { admin: "管理员", worker: "操作工" };

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
  const t = localStorage.getItem(TOKEN_KEY);
  if (t) headers.Authorization = `Bearer ${t}`;
  const res = await fetch(path, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "请求失败");
  return data;
}

const app = document.getElementById("app");
const state = {
  ready: Boolean(localStorage.getItem(TOKEN_KEY)),
  me: null,
  page: "board",
  board: null,
  picked: null,
  peak: "96",
  err: "",
  username: "admin",
  password: "123456",
  sieveKettleId: null,
  sieveTags: null,
  mesh: "40",
  hungAt: "",
};

function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

function fmtTime(iso) {
  return iso ? iso.replace("T", " ").slice(0, 19) : "—";
}

function badgeHtml(k) {
  return k.sieveMesh != null ? `<em class="badge">${k.sieveMesh}目</em>` : "";
}

async function refresh() {
  const [me, board] = await Promise.all([api("/api/auth/me"), api("/api/board")]);
  state.me = me;
  state.board = board;
  if (state.picked) {
    state.picked = state.board.kettles.find((k) => k.id === state.picked.id) || state.board.kettles[0];
  }
  if (state.page === "sieve") await loadSieveTags();
  render();
}

async function loadSieveTags() {
  const q = state.sieveKettleId ? `?kettle_id=${state.sieveKettleId}` : "";
  state.sieveTags = await api(`/api/sieve-tags${q}`);
}

function run(fn) {
  return async (...args) => {
    state.err = "";
    try {
      await fn(...args);
    } catch (ex) {
      state.err = ex.message;
      render();
    }
  };
}

function render() {
  app.innerHTML = "";
  if (!state.ready) {
    renderLogin();
    return;
  }
  if (!state.board) {
    app.append(el(`<div class="wrap">${state.err || "装载锅位…"}</div>`));
    return;
  }
  const box = el(`<div class="wrap">
    <header class="topbar">
      <h1>${state.board.workshop}</h1>
      <nav>
        <button data-page="board" class="${state.page === "board" ? "on" : ""}">锅位作业台</button>
        <button data-page="sieve" class="${state.page === "sieve" ? "on" : ""}">筛网角标</button>
      </nav>
      <span class="who">${state.me ? `${state.me.username}（${ROLE_LABELS[state.me.role] || state.me.role}）` : ""}</span>
      <button id="logout">退出</button>
    </header>
    <p class="err">${state.err}</p>
    <section class="page"></section>
  </div>`);
  box.querySelectorAll("[data-page]").forEach((b) => {
    b.onclick = run(async () => {
      state.page = b.dataset.page;
      if (state.page === "sieve") await loadSieveTags();
      render();
    });
  });
  box.querySelector("#logout").onclick = () => {
    localStorage.removeItem(TOKEN_KEY);
    state.ready = false;
    state.board = null;
    state.me = null;
    state.sieveTags = null;
    render();
  };
  const page = box.querySelector(".page");
  if (state.page === "board") renderBoard(page);
  else renderSieve(page);
  app.append(box);
}

function renderLogin() {
  const box = el(`<div class="wrap">
    <h1>骨巷熬胶坊</h1>
    <p>一排熬锅作业台，原生页面，无前端框架。</p>
    <form autocomplete="off">
      <label>用户名
        <input name="u" autocomplete="off" value="${state.username}" />
      </label>
      <label>密码
        <input name="p" type="password" autocomplete="off" value="${state.password}" />
      </label>
      <p class="hint">已预填 admin / 123456，另有 worker / 123456</p>
      <button>登录</button>
    </form>
    <p class="err">${state.err}</p>
  </div>`);
  box.querySelector("form").onsubmit = async (e) => {
    e.preventDefault();
    state.err = "";
    try {
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: box.querySelector("[name=u]").value,
          password: box.querySelector("[name=p]").value,
        }),
      });
      localStorage.setItem(TOKEN_KEY, data.access_token);
      state.ready = true;
      await refresh();
    } catch (ex) {
      state.err = ex.message;
      render();
    }
  };
  app.append(box);
}

function renderBoard(page) {
  page.innerHTML = `
    <p>${state.board.alley} · 点锅登记峰值；转熬煮中须最新未作废筛网牌为 40 或 60 目；出胶须最近峰值 ≥ 90℃</p>
    <div class="row"></div>
    <section class="drawer"></section>`;
  const row = page.querySelector(".row");
  state.board.kettles.forEach((k) => {
    const btn = el(`<button class="kettle ${k.status}">${badgeHtml(k)}<strong>${k.code}</strong><span>${LABELS[k.status]}</span></button>`);
    btn.onclick = () => {
      state.picked = k;
      render();
    };
    row.append(btn);
  });
  if (!state.picked) return;
  const d = page.querySelector(".drawer");
  d.innerHTML = `<h3>${state.picked.code} · ${LABELS[state.picked.status]}</h3>
    <p>最近峰值：${state.picked.latestPeakC ?? "无"} ℃ · ${state.picked.cookCount} 次 · 筛网：${state.picked.sieveMesh != null ? state.picked.sieveMesh + " 目" : "无未作废牌"}</p>
    <input id="peak" value="${state.peak}" />
    <button id="log">登记峰值</button>
    <div>
      <button data-s="cold">冷锅</button>
      <button data-s="boiling">熬煮中</button>
      <button data-s="drawn">已出胶</button>
    </div>`;
  d.querySelector("#log").onclick = run(async () => {
    state.peak = d.querySelector("#peak").value;
    state.picked = await api(`/api/kettles/${state.picked.id}/cooks`, {
      method: "POST",
      body: JSON.stringify({ peakTempC: Number(state.peak) }),
    });
    await refresh();
  });
  d.querySelectorAll("[data-s]").forEach((b) => {
    b.onclick = run(async () => {
      state.picked = await api(`/api/kettles/${state.picked.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status: b.dataset.s }),
      });
      await refresh();
    });
  });
}

function renderSieve(page) {
  const isAdmin = state.me && state.me.role === "admin";
  page.innerHTML = `
    <h2>筛网角标</h2>
    <p>按锅筛牌；放行以挂出时刻最晚的未作废牌为准（40 或 60 目才可转熬煮中）。挂牌、作废仅管理员，操作工只读。</p>
    <div class="row strip"></div>
    <div class="hangbox"></div>
    <div class="tagbox"></div>`;

  const strip = page.querySelector(".strip");
  const all = el(`<button class="chip ${state.sieveKettleId ? "" : "on"}">全部</button>`);
  all.onclick = run(async () => {
    state.sieveKettleId = null;
    await loadSieveTags();
    render();
  });
  strip.append(all);
  state.board.kettles.forEach((k) => {
    const btn = el(`<button class="kettle small ${k.status} ${state.sieveKettleId === k.id ? "on" : ""}">${badgeHtml(k)}<strong>${k.code}</strong></button>`);
    btn.onclick = run(async () => {
      state.sieveKettleId = k.id;
      await loadSieveTags();
      render();
    });
    strip.append(btn);
  });

  const hangbox = page.querySelector(".hangbox");
  if (isAdmin) {
    const opts = state.board.kettles
      .map((k) => `<option value="${k.id}" ${state.sieveKettleId === k.id ? "selected" : ""}>${k.code}</option>`)
      .join("");
    const form = el(`<form class="hang">
      <label>锅位 <select name="kettle">${opts}</select></label>
      <label>目数 <input name="mesh" type="number" min="1" step="1" value="${state.mesh}" required /></label>
      <label>挂出时刻（留空为现在） <input name="hungAt" type="datetime-local" step="1" value="${state.hungAt}" /></label>
      <button>挂牌</button>
    </form>`);
    form.onsubmit = async (e) => {
      e.preventDefault();
      state.mesh = form.querySelector("[name=mesh]").value;
      state.hungAt = form.querySelector("[name=hungAt]").value;
      state.err = "";
      try {
        await api(`/api/kettles/${form.querySelector("[name=kettle]").value}/sieve-tags`, {
          method: "POST",
          body: JSON.stringify({ mesh: Number(state.mesh), hungAt: state.hungAt || null }),
        });
        state.hungAt = "";
        await refresh();
      } catch (ex) {
        state.err = ex.message;
        render();
      }
    };
    hangbox.append(form);
  } else {
    hangbox.append(el(`<p class="hint">操作工只读：挂牌与作废仅管理员可操作。</p>`));
  }

  const tagbox = page.querySelector(".tagbox");
  if (!state.sieveTags) {
    tagbox.append(el(`<p>装载筛网牌…</p>`));
    return;
  }
  if (!state.sieveTags.tags.length) {
    tagbox.append(el(`<p class="hint">暂无筛网牌。</p>`));
    return;
  }
  const effective = new Set();
  const byKettle = {};
  state.sieveTags.tags.forEach((t) => {
    if (t.voidedAt) return;
    const cur = byKettle[t.kettleId];
    if (!cur || t.hungAt > cur.hungAt) byKettle[t.kettleId] = t;
  });
  Object.values(byKettle).forEach((t) => effective.add(t.id));

  const rows = state.sieveTags.tags
    .map((t) => {
      const status = t.voidedAt ? "已作废" : effective.has(t.id) ? "放行依据" : "未作废";
      const cls = t.voidedAt ? "voided" : effective.has(t.id) ? "effective" : "";
      const act = isAdmin && !t.voidedAt ? `<button data-void="${t.id}">作废</button>` : "";
      return `<tr class="${cls}">
        <td>${t.kettleCode || t.kettleId}</td><td>${t.mesh} 目</td>
        <td>${fmtTime(t.hungAt)}</td><td>${t.hungBy}</td>
        <td>${t.voidedAt ? fmtTime(t.voidedAt) : "—"}</td><td>${status}</td><td>${act}</td>
      </tr>`;
    })
    .join("");
  const table = el(`<table class="tags">
    <thead><tr><th>锅位</th><th>目数</th><th>挂出时刻</th><th>挂出人</th><th>作废时刻</th><th>状态</th><th></th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`);
  table.querySelectorAll("[data-void]").forEach((b) => {
    b.onclick = run(async () => {
      await api(`/api/sieve-tags/${b.dataset.void}/void`, { method: "POST" });
      await refresh();
    });
  });
  tagbox.append(table);
}

if (state.ready) {
  refresh().catch((e) => {
    state.err = e.message;
    render();
  });
} else {
  render();
}
