import "./style.css";

const TOKEN_KEY = "gluekettle_token";
const LABELS = { cold: "冷锅", boiling: "熬煮中", drawn: "已出胶" };

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
  const t = localStorage.getItem(TOKEN_KEY);
  if (t) headers.Authorization = `Bearer ${t}`;
  const res = await fetch(path, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.detail || "请求失败"), { status: res.status });
  return data;
}

const app = document.getElementById("app");
const state = {
  ready: Boolean(localStorage.getItem(TOKEN_KEY)),
  me: null,
  view: "board",
  board: null,
  picked: null,
  screens: null,
  peak: "96",
  mesh: "40",
  err: "",
  username: "admin",
  password: "123456",
};

function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { hour12: false });
}

async function refreshBoard() {
  state.board = await api("/api/board");
  if (state.picked) {
    state.picked = state.board.kettles.find((k) => k.id === state.picked.id) || state.board.kettles[0];
  }
}

async function refreshScreens() {
  const kettle = state.picked || state.board.kettles[0];
  state.picked = kettle;
  state.screens = await api(`/api/kettles/${kettle.id}/screens`);
}

async function refresh() {
  await refreshBoard();
  if (state.view === "screens") await refreshScreens();
  render();
}

function logout() {
  localStorage.removeItem(TOKEN_KEY);
  state.ready = false;
  state.me = null;
  state.board = null;
  state.picked = null;
  render();
}

function kettleButton(k, onclick) {
  const badge =
    k.latestScreen && k.latestScreen.active
      ? `<span class="badge mesh-${k.latestScreen.mesh}">${k.latestScreen.mesh}目</span>`
      : "";
  const btn = el(`<button class="kettle ${k.status}">${badge}<strong>${k.code}</strong><span>${LABELS[k.status]}</span></button>`);
  btn.onclick = onclick;
  return btn;
}

function topBar() {
  const bar = el(`<header class="topbar">
    <div class="brand">${state.board.workshop}</div>
    <nav>
      <button data-v="board" class="tab ${state.view === "board" ? "on" : ""}">锅位作业台</button>
      <button data-v="screens" class="tab ${state.view === "screens" ? "on" : ""}">筛网角标</button>
    </nav>
    <div class="who">${state.me.username} · ${state.me.role === "admin" ? "管理员" : "操作工"}
      <button id="logout">退出</button>
    </div>
  </header>`);
  bar.querySelectorAll(".tab").forEach((b) => {
    b.onclick = async () => {
      state.view = b.dataset.v;
      state.err = "";
      if (state.view === "screens" && state.screens == null) {
        try {
          state.picked = state.picked || state.board.kettles[0];
          await refreshScreens();
        } catch (ex) {
          state.err = ex.message;
        }
      }
      render();
    };
  });
  bar.querySelector("#logout").onclick = logout;
  return bar;
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
      state.me = data.user;
      state.ready = true;
      state.view = "board";
      state.screens = null;
      await refresh();
    } catch (ex) {
      state.err = ex.message;
      render();
    }
  };
  app.append(box);
}

function renderBoard(box) {
  box.append(el(`<p>${state.board.alley} · 点锅登记峰值；改熬煮中须挂 40/60 目有效筛网牌；出胶只看最近峰值 ≥ 90℃</p>`));
  const row = el(`<div class="row"></div>`);
  state.board.kettles.forEach((k) => {
    row.append(
      kettleButton(k, () => {
        state.picked = k;
        render();
      })
    );
  });
  box.append(row);

  const d = el(`<section class="drawer"></section>`);
  if (state.picked) {
    const scr = state.picked.latestScreen;
    const scrText = scr && scr.active
      ? `当前筛网：<strong>${scr.mesh} 目</strong>（${fmtTime(scr.postedAt)} 挂出，${scr.postedBy}）`
      : "当前筛网：无未作废牌";
    d.innerHTML = `<h3>${state.picked.code} · ${LABELS[state.picked.status]}</h3>
      <p>最近峰值：${state.picked.latestPeakC ?? "无"} ℃ · ${state.picked.cookCount} 次</p>
      <p class="screen-line ${scr && scr.active ? "" : "none"}">${scrText}</p>
      <input id="peak" value="${state.peak}" />
      <button id="log">登记峰值</button>
      <div>
        <button data-s="cold">冷锅</button>
        <button data-s="boiling">熬煮中</button>
        <button data-s="drawn">已出胶</button>
      </div>`;
    d.querySelector("#log").onclick = async () => {
      state.err = "";
      state.peak = d.querySelector("#peak").value;
      try {
        state.picked = await api(`/api/kettles/${state.picked.id}/cooks`, {
          method: "POST",
          body: JSON.stringify({ peakTempC: Number(state.peak) }),
        });
        await refresh();
      } catch (ex) {
        state.err = ex.message;
        render();
      }
    };
    d.querySelectorAll("[data-s]").forEach((b) => {
      b.onclick = async () => {
        state.err = "";
        try {
          state.picked = await api(`/api/kettles/${state.picked.id}/status`, {
            method: "POST",
            body: JSON.stringify({ status: b.dataset.s }),
          });
          await refresh();
        } catch (ex) {
          // 后端中文门槛（如 80 目 / 无牌改熬煮中被挡）原样显示
          state.err = ex.message;
          render();
        }
      };
    });
  }
  box.append(d);
}

function renderScreens(box) {
  box.append(el(`<p>筛网角标页：按锅查看筛网牌。放行以挂出时刻最晚的一张未作废牌为准；改熬煮中只认 40 / 60 目。</p>`));
  const row = el(`<div class="row"></div>`);
  state.board.kettles.forEach((k) => {
    row.append(
      kettleButton(k, async () => {
        state.err = "";
        state.picked = k;
        try {
          await refreshScreens();
          render();
        } catch (ex) {
          state.err = ex.message;
          render();
        }
      })
    );
  });
  box.append(row);

  if (!state.screens) return;
  const canManage = Boolean(state.screens.canManage);
  const panel = el(`<section class="drawer screen-panel"></section>`);
  panel.append(el(`<h3>${state.picked.code} · 筛网牌</h3>`));

  if (canManage) {
    const form = el(`<form class="screen-form">
      <label>目数
        <input id="mesh" type="number" min="1" max="1000" value="${state.mesh}" />
      </label>
      <button>挂牌</button>
      <span class="hint">挂出时刻取当前时刻；只放行 40 / 60 目</span>
    </form>`);
    form.onsubmit = async (e) => {
      e.preventDefault();
      state.err = "";
      state.mesh = form.querySelector("#mesh").value;
      try {
        await api(`/api/kettles/${state.picked.id}/screens`, {
          method: "POST",
          body: JSON.stringify({ mesh: Number(state.mesh) }),
        });
        await refreshScreens();
        render();
      } catch (ex) {
        state.err = ex.message;
        render();
      }
    };
    panel.append(form);
  } else {
    panel.append(el(`<p class="hint">操作工只读：只有管理员能挂牌和作废。</p>`));
  }

  const list = el(`<ul class="tag-list"></ul>`);
  if (state.screens.tags.length === 0) {
    list.append(el(`<li class="tag-none">该锅还没有筛网牌</li>`));
  }
  state.screens.tags.forEach((t) => {
    const li = el(`<li class="tag-row ${t.active ? "active" : "revoked"}"></li>`);
    const head = el(`<span class="tag-head"><b class="mesh-${t.mesh}">${t.mesh} 目</b></span>`);
    const meta = el(
      `<span class="tag-meta">挂出 ${fmtTime(t.postedAt)} · ${t.postedBy} · ${
        t.active ? "未作废" : `已作废 ${fmtTime(t.revokedAt)} · ${t.revokedBy}`
      }</span>`
    );
    li.append(head, meta);
    if (t.active && canManage) {
      const btn = el(`<button class="revoke">作废</button>`);
      btn.onclick = async () => {
        state.err = "";
        try {
          await api(`/api/screens/${t.id}/revoke`, { method: "POST" });
          await refresh();
        } catch (ex) {
          state.err = ex.message;
          render();
        }
      };
      li.append(btn);
    }
    list.append(li);
  });
  panel.append(list);
  box.append(panel);
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
  app.append(topBar());
  const box = el(`<div class="wrap"></div>`);
  if (state.view === "screens") renderScreens(box);
  else renderBoard(box);
  if (state.err) box.append(el(`<p class="err">${state.err}</p>`));
  app.append(box);
}

async function boot() {
  try {
    state.me = await api("/api/auth/me");
    await refresh();
  } catch (e) {
    if (e.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      state.ready = false;
    } else {
      state.err = e.message;
    }
    render();
  }
}

if (state.ready) {
  boot();
} else {
  render();
}
