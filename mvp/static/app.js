const appRoot = document.querySelector("#app");
const mainNav = document.querySelector("#mainNav");
const accountButton = document.querySelector("#accountButton");
const authDialog = document.querySelector("#authDialog");
const alipayDialog = document.querySelector("#alipayDialog");
const toastEl = document.querySelector("#toast");

const state = {
  me: null,
  health: null,
  view: "tasks",
  pendingClaim: null,
  afterBind: null,
  countdownTimer: null,
};

const statusLabels = {
  ACTIVE: "保护期内",
  EXPIRED: "保护期已结束",
  VERIFIED_LOCKED: "奖励已锁定",
  VERIFIED_NO_REWARD: "完成但无奖励",
  PAYOUT_PENDING: "待人工支付",
  PAYOUT_RETRY: "支付待处理",
  PAID: "已支付",
  ORDER_EXPIRED: "订单已结束",
  PENDING: "待核验",
  CONFIRMED: "已核验",
  REJECTED: "核验未通过",
  AWAITING_INVITE: "待填写邀请码",
  CLOSED: "已关闭",
};

const orderStatusLabels = {
  ACTIVE: "进行中",
  AWAITING_INVITE: "待填写邀请码",
  CLOSED: "已关闭",
  REFUNDED: "已退款",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatTime(timestamp) {
  if (!timestamp) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false,
  }).format(new Date(timestamp * 1000));
}

function formatRemaining(seconds) {
  const safe = Math.max(0, Math.floor(seconds));
  const minutes = String(Math.floor(safe / 60)).padStart(2, "0");
  const secs = String(safe % 60).padStart(2, "0");
  return `${minutes}:${secs}`;
}

function statusClass(status) {
  if (["PAID", "PAYOUT_PENDING", "VERIFIED_LOCKED", "CONFIRMED"].includes(status)) return "green";
  if (["ACTIVE", "EXPIRED", "AWAITING_INVITE", "PENDING"].includes(status)) return "amber";
  if (["CLOSED", "ORDER_EXPIRED", "VERIFIED_NO_REWARD", "REJECTED"].includes(status)) return "red";
  return "";
}

function toast(message) {
  toastEl.textContent = message;
  toastEl.classList.add("show");
  window.setTimeout(() => toastEl.classList.remove("show"), 2600);
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("X-MVP-Request", "1");
  if (options.body && typeof options.body !== "string") {
    headers.set("Content-Type", "application/json");
    options.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = data?.error?.message || data?.detail || "请求失败";
    const error = new Error(message);
    error.status = response.status;
    error.code = data?.error?.code;
    throw error;
  }
  return data;
}

async function apiAdmin(path, options = {}) {
  const key = sessionStorage.getItem("mvp_admin_key") || "";
  options.headers = { ...(options.headers || {}), "X-Admin-Key": key };
  return api(path, options);
}

async function loadMe() {
  try {
    state.me = await api("/api/me");
  } catch (error) {
    if (error.status !== 401) throw error;
    state.me = null;
  }
  accountButton.textContent = state.me ? state.me.phone : "手机号登录";
  return state.me;
}

function setNavVisible(visible) {
  mainNav.style.display = visible ? "" : "none";
}

async function copyText(value) {
  try {
    await navigator.clipboard.writeText(value);
  } catch (_) {
    const input = document.createElement("textarea");
    input.value = value;
    input.setAttribute("readonly", "");
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.appendChild(input);
    input.select();
    document.execCommand("copy");
    input.remove();
  }
  toast("已复制");
}

function bindCopyButtons() {
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", () => copyText(button.dataset.copy));
  });
}

function openLogin() {
  authDialog.showModal();
  document.querySelector("#loginPhone").focus();
}

function openAlipay(afterBind = null) {
  state.afterBind = afterBind;
  alipayDialog.showModal();
  document.querySelector("#alipayAccount").focus();
}

async function claimAfterAccount(slug) {
  if (!state.me) {
    state.pendingClaim = slug;
    openLogin();
    return;
  }
  if (!state.me.alipay_bound) {
    state.pendingClaim = slug;
    openAlipay(() => performClaim(slug));
    return;
  }
  await performClaim(slug);
}

async function performClaim(slug) {
  try {
    await api(`/api/tasks/${encodeURIComponent(slug)}/claim`, { method: "POST" });
    toast("抢单成功，30 分钟保护期已开始");
    state.pendingClaim = null;
    await renderTask(slug);
  } catch (error) {
    toast(error.message);
  }
}

function pageHeading(eyebrow, title, subtitle) {
  return `
    <div class="page-head">
      <div>
        <p class="eyebrow">${escapeHtml(eyebrow)}</p>
        <h1>${escapeHtml(title)}</h1>
        <p>${escapeHtml(subtitle)}</p>
      </div>
    </div>`;
}

async function renderTasks() {
  const data = await api("/api/tasks");
  const total = data.tasks.length;
  const available = data.tasks.reduce((sum, task) => sum + task.available, 0);
  const locked = data.tasks.reduce((sum, task) => sum + task.counts.locked, 0);
  appRoot.innerHTML = `
    ${pageHeading("公开任务", "任务大厅", "先完成本站手机号登录和支付宝登记，再领取任务名额。")}
    <div class="summary-strip">
      <div class="metric"><span>进行中任务</span><strong>${total}</strong></div>
      <div class="metric"><span>当前可抢名额</span><strong>${available}</strong></div>
      <div class="metric"><span>已完成认证</span><strong>${locked}</strong></div>
      <div class="metric"><span>单次奖励</span><strong>¥5</strong></div>
    </div>
    <section class="section">
      <div class="section-head"><h2>可领取任务</h2><p>名额以服务器实时结果为准</p></div>
      ${total ? `<div class="task-list">${data.tasks.map((task) => `
        <div class="task-row">
          <div class="task-name"><strong>SiliconFlow 新用户认证</strong><span>领取后显示专属邀请链接</span></div>
          <div><span class="cell-label">目标</span><span class="cell-value">${task.target} 人</span></div>
          <div><span class="cell-label">已完成</span><span class="cell-value">${task.counts.locked} 人</span></div>
          <div><span class="cell-label">保护中</span><span class="cell-value">${task.counts.active} 人</span></div>
          <div><span class="cell-label">剩余</span><span class="cell-value">${task.available} 人</span></div>
          <a class="button secondary" href="${task.task_url}">查看任务</a>
        </div>`).join("")}</div>` : `<div class="empty">当前没有开放中的任务</div>`}
    </section>`;
}

async function renderMine() {
  if (!state.me) {
    appRoot.innerHTML = `${pageHeading("个人中心", "我的任务", "登录后查看抢单记录、倒计时、认证和奖励状态。")}
      <div class="empty"><p>尚未登录</p><button id="mineLogin" class="button primary">手机号登录</button></div>`;
    document.querySelector("#mineLogin").addEventListener("click", openLogin);
    return;
  }
  const [assignmentData, notificationData] = await Promise.all([
    api("/api/me/assignments"), api("/api/me/notifications"),
  ]);
  const assignments = assignmentData.assignments;
  appRoot.innerHTML = `
    ${pageHeading("个人中心", "我的任务", `${state.me.phone} · ${state.me.alipay_bound ? `支付宝 ${state.me.alipay}` : "尚未登记支付宝"}`)}
    ${!state.me.alipay_bound ? `<div class="notice warning"><button id="bindFromMine" class="button secondary">登记支付宝收款信息</button></div>` : ""}
    <section class="section">
      <div class="section-head"><h2>抢单记录</h2><p>${assignments.length} 条</p></div>
      ${assignments.length ? `<div class="task-list">${assignments.map((item) => `
        <div class="task-row">
          <div class="task-name"><strong>SiliconFlow 新用户认证</strong><span>${formatTime(item.claimed_at)} 领取</span></div>
          <div><span class="cell-label">状态</span><span class="status ${statusClass(item.status)}">${statusLabels[item.status] || item.status}</span></div>
          <div><span class="cell-label">奖励</span><span class="cell-value">${item.reward_status === "PAID" ? "已支付" : item.reward_id ? "¥5 待支付" : "-"}</span></div>
          <div><span class="cell-label">注册</span><span class="cell-value">${item.registered_at ? "已完成" : "待完成"}</span></div>
          <div><span class="cell-label">订单截止</span><span class="cell-value">${formatTime(item.order_expires_at)}</span></div>
          <a class="button secondary" href="/t/${item.public_slug}">打开</a>
        </div>`).join("")}</div>` : `<div class="empty">还没有领取过任务</div>`}
    </section>
    <section class="section">
      <div class="section-head"><h2>站内通知</h2></div>
      <div class="panel">${notificationData.notifications.length ? notificationData.notifications.map((item) => `
        <div class="admin-order"><strong>${escapeHtml(item.message)}</strong><p class="muted">${formatTime(item.created_at)}</p></div>`).join("") : `<p class="muted">暂无通知</p>`}</div>
    </section>`;
  document.querySelector("#bindFromMine")?.addEventListener("click", () => openAlipay(() => showView("mine")));
}

function adminLoginPanel(error = "") {
  appRoot.innerHTML = `
    ${pageHeading("运营工作台", "订单管理", "按淘宝付款订单创建 1 人、5 人或 10 人任务。")}
    <div class="panel">
      <h2>管理员验证</h2>
      ${error ? `<div class="notice error">${escapeHtml(error)}</div>` : ""}
      <div class="admin-controls">
        <input id="adminKey" type="password" autocomplete="off" placeholder="管理员密钥">
        <button id="adminLogin" class="button primary">进入管理台</button>
      </div>
    </div>`;
  document.querySelector("#adminLogin").addEventListener("click", async () => {
    sessionStorage.setItem("mvp_admin_key", document.querySelector("#adminKey").value);
    await renderAdmin();
  });
}

async function renderAdmin() {
  if (!sessionStorage.getItem("mvp_admin_key")) {
    adminLoginPanel();
    return;
  }
  let data;
  try {
    data = await apiAdmin("/api/admin/summary");
  } catch (error) {
    sessionStorage.removeItem("mvp_admin_key");
    adminLoginPanel(error.message);
    return;
  }
  appRoot.innerHTML = `
    ${pageHeading("运营工作台", "订单管理", "付款订单建单、人工审核和支付宝转账登记。")}
    <div id="createdOrder"></div>
    <section class="panel">
      <h2>创建付款订单</h2>
      <form id="orderForm" class="form-stack">
        <div class="form-grid">
          <label>淘宝订单号<input id="taobaoTid" required value="T${Date.now()}" maxlength="64"></label>
          <label>SKU
            <select id="orderSku"><option value="SF_INVITE_1">1 人</option><option value="SF_INVITE_5">5 人</option><option value="SF_INVITE_10">10 人</option></select>
          </label>
          <label>购买数量<input id="orderQuantity" type="number" min="1" max="100" value="1"></label>
          <label>SiliconFlow 模式
            <select id="siliconMode"><option value="mock">本地代理登录演示</option><option value="manual">人工邀请码</option><option value="live-disabled">真实调用禁用</option></select>
          </label>
        </div>
        <button class="button primary" type="submit">生成订单链接</button>
      </form>
    </section>
    <section class="section">
      <div class="section-head"><h2>订单</h2><p>${data.orders.length} 个</p></div>
      <div class="panel">${data.orders.map((order) => `
        <div class="admin-order">
          <div class="admin-order-head">
            <div><h3>${escapeHtml(order.taobao_tid)}</h3><p class="muted">${order.sku} × ${order.quantity} · 目标 ${order.target} 人 · ${escapeHtml(order.silicon_mode)}</p></div>
            <span class="status ${statusClass(order.status)}">${orderStatusLabels[order.status] || order.status}</span>
          </div>
          <p>已完成 ${order.counts.locked} · 保护中 ${order.counts.active} · 剩余 ${order.available}</p>
          ${order.assignments.length ? `<table class="assignment-table"><thead><tr><th>用户</th><th>状态</th><th>SF ID</th><th>注册</th><th>奖励</th><th>操作</th></tr></thead><tbody>${order.assignments.map((item) => `
            <tr><td>${escapeHtml(item.phone_mask)}</td><td>${statusLabels[item.status] || item.status}</td><td>${item.upstream_claim ? `${escapeHtml(item.upstream_claim.account_id_mask)} · ${escapeHtml(item.upstream_claim.status)}` : "未提交"}</td><td>${item.registered_at ? "已注册" : "待注册"}</td><td>${item.reward_status ? statusLabels[item.reward_status] || item.reward_status : "-"}</td><td>${["ACTIVE", "EXPIRED"].includes(item.status) ? `<button class="button secondary admin-verify" data-id="${item.id}" data-mask="${escapeHtml(item.upstream_claim?.account_id_mask || "")}">人工确认</button>` : "-"}</td></tr>`).join("")}</tbody></table>` : `<p class="muted">暂无抢单记录</p>`}
        </div>`).join("")}</div>
    </section>
    <section class="section">
      <div class="section-head"><h2>待支付奖励</h2><p>${data.rewards.filter((item) => item.status !== "PAID").length} 笔</p></div>
      <div class="panel">${data.rewards.length ? data.rewards.map((reward) => `
        <div class="admin-order admin-order-head">
          <div><strong>${escapeHtml(reward.phone_mask)} · ${escapeHtml(reward.alipay_mask)}</strong><p class="muted">奖励 ¥${(reward.amount_cents / 100).toFixed(2)} · ${statusLabels[reward.status] || reward.status}</p></div>
          ${reward.status === "PAID" ? `<span class="status green">已支付</span>` : `<button class="button primary pay-reward" data-id="${reward.id}">登记已支付</button>`}
        </div>`).join("") : `<p class="muted">暂无奖励记录</p>`}</div>
    </section>`;

  document.querySelector("#orderForm").addEventListener("submit", createAdminOrder);
  document.querySelectorAll(".admin-verify").forEach((button) => button.addEventListener("click", () => adminVerify(button.dataset.id, button.dataset.mask)));
  document.querySelectorAll(".pay-reward").forEach((button) => button.addEventListener("click", () => payReward(button.dataset.id)));
}

async function createAdminOrder(event) {
  event.preventDefault();
  try {
    const order = await apiAdmin("/api/admin/orders", {
      method: "POST",
      body: {
        taobao_tid: document.querySelector("#taobaoTid").value,
        outer_sku_id: document.querySelector("#orderSku").value,
        quantity: Number(document.querySelector("#orderQuantity").value),
        silicon_mode: document.querySelector("#siliconMode").value,
      },
    });
    const customerUrl = location.origin + order.customer_url;
    const taskUrl = location.origin + order.task_url;
    document.querySelector("#createdOrder").innerHTML = `
      <div class="panel"><h2>订单链接已生成</h2>
        <p class="muted">淘宝聊天自动发送权限未启用，请人工发送客户订单链接。</p>
        <label>客户订单链接<div class="copy-field"><input readonly value="${escapeHtml(customerUrl)}"><button class="button secondary" data-copy="${escapeHtml(customerUrl)}">复制</button></div></label>
        <label>任务链接<div class="copy-field"><input readonly value="${escapeHtml(taskUrl)}"><button class="button secondary" data-copy="${escapeHtml(taskUrl)}">复制</button></div></label>
      </div>`;
    bindCopyButtons();
    toast("订单创建成功");
  } catch (error) {
    toast(error.message);
  }
}

async function adminVerify(assignmentId, submittedMask = "") {
  const hint = submittedMask ? `，抢单人提交值为 ${submittedMask}` : "";
  const upstream = prompt(`请输入从官方邀请记录核实的 SiliconFlow 用户 ID${hint}`);
  if (!upstream) return;
  try {
    await apiAdmin(`/api/admin/assignments/${assignmentId}/verify`, {
      method: "POST", body: { upstream_account_id: upstream, valid_authentication: true },
    });
    toast("已确认有效认证并锁定奖励");
    await renderAdmin();
  } catch (error) {
    toast(error.message);
  }
}

async function payReward(rewardId) {
  const reference = prompt("请输入支付宝转账流水号");
  if (!reference) return;
  try {
    await apiAdmin(`/api/admin/rewards/${rewardId}/pay`, { method: "POST", body: { payout_reference: reference } });
    toast("支付状态已登记");
    await renderAdmin();
  } catch (error) {
    toast(error.message);
  }
}

async function renderCustomer(rawToken) {
  setNavVisible(false);
  let order;
  try {
    order = await api(`/api/customer/${encodeURIComponent(rawToken)}`);
  } catch (error) {
    appRoot.innerHTML = `${pageHeading("订单", "无法打开订单", error.message)}<div class="notice error">${escapeHtml(error.message)}</div>`;
    return;
  }
  const active = order.status === "ACTIVE" && order.invitation_code;
  const taskUrl = location.origin + order.task_url;
  appRoot.innerHTML = `
    <div class="detail-title"><p class="eyebrow">淘宝订单 ${escapeHtml(order.taobao_tid)}</p><h1>配置邀请任务</h1><p>目标 ${order.target} 人 · 订单截止 ${formatTime(order.expires_at)}</p></div>
    <div class="detail-layout">
      <div class="detail-main">
        ${active ? `<div class="panel">
          <span class="status green">邀请码已确认</span><h2>任务已开放</h2>
          <dl class="key-value"><dt>8 位邀请码</dt><dd>${escapeHtml(order.invitation_code)}</dd><dt>邀请链接</dt><dd>${escapeHtml(order.invitation_url)}</dd><dt>任务链接</dt><dd>${escapeHtml(taskUrl)}</dd></dl>
          <div class="button-row"><button class="button primary" data-copy="${escapeHtml(taskUrl)}">复制任务链接</button><a class="button secondary" href="${order.task_url}">打开任务页</a></div>
        </div>` : `<div class="panel">
          <div class="tabs" role="tablist"><button id="proxyTab" class="active" role="tab" aria-selected="true" aria-controls="proxyPane">手机安全登录</button><button id="manualTab" role="tab" aria-selected="false" aria-controls="manualPane">手动填写</button></div>
          <div id="proxyPane">
            <form id="handoffForm" class="form-stack">
              <label class="checkbox"><input id="handoffConsent" type="checkbox" required><span>我授权本站启动一次性浏览器会话并读取邀请码；该授权不代表 SiliconFlow 官方接入许可。</span></label>
              <button class="button primary" type="submit" ${order.browser_handoff?.enabled ? "" : "disabled"}>开始手机安全登录</button>
              <p id="handoffStatus" class="form-hint" role="status">${order.browser_handoff?.enabled ? "会话最长保留 5 分钟未操作时间" : "远程浏览器网关尚未配置，请使用手动填写"}</p>
            </form>
            ${order.adapter.proxy_login ? `<div class="development-block"><p class="eyebrow">本地开发演示</p><form id="proxyForm" class="form-stack">
              <label>SiliconFlow 注册手机号<input id="sfPhone" type="tel" inputmode="numeric" required placeholder="请输入邀请人手机号"></label>
              <div class="code-row"><label>SiliconFlow 验证码<input id="sfOtp" inputmode="numeric" maxlength="6" required placeholder="6 位验证码"></label><button id="sendSfCode" type="button" class="button secondary">获取验证码</button></div>
              <p id="sfCodeHint" class="form-hint"></p>
              <label class="checkbox"><input id="sfConsent" type="checkbox" required><span>我授权本站代为提交登录信息、读取邀请码，并将会话令牌加密保存最长 24 小时。</span></label>
              <button class="button primary" type="submit">获取邀请码</button>
            </form></div>` : ""}
          </div>
          <div id="manualPane" hidden>
            <form id="manualForm" class="form-stack">
              <label>邀请码或完整邀请链接<input id="manualInvitation" required placeholder="8 位邀请码或 https://cloud.siliconflow.cn/i/..."></label>
              <label class="checkbox"><input id="manualConsent" type="checkbox" required><span>我确认提交的是该订单邀请人的邀请码，并同意用于任务履约。</span></label>
              <button class="button primary" type="submit">确认邀请码</button>
            </form>
          </div>
        </div>`}
      </div>
      <aside class="detail-side">
        <div class="panel"><h2>订单状态</h2><dl class="key-value"><dt>SKU</dt><dd>${escapeHtml(order.sku)}</dd><dt>目标人数</dt><dd>${order.target}</dd><dt>有效期</dt><dd>24 小时</dd><dt>适配器</dt><dd>${escapeHtml(order.silicon_mode)}</dd></dl></div>
        <div class="panel"><h2>数据处理</h2><p class="muted">验证码不写入数据库或日志。会话仅保存在服务端密文中，到期或订单结束后失效。</p></div>
      </aside>
    </div>`;
  bindCopyButtons();
  if (!active) bindCustomerForms(rawToken, order);
}

function bindCustomerForms(rawToken, order) {
  const proxyPane = document.querySelector("#proxyPane");
  const manualPane = document.querySelector("#manualPane");
  document.querySelector("#proxyTab").addEventListener("click", (event) => {
    event.currentTarget.classList.add("active"); document.querySelector("#manualTab").classList.remove("active");
    event.currentTarget.setAttribute("aria-selected", "true"); document.querySelector("#manualTab").setAttribute("aria-selected", "false");
    proxyPane.hidden = false; manualPane.hidden = true;
  });
  document.querySelector("#manualTab").addEventListener("click", (event) => {
    event.currentTarget.classList.add("active"); document.querySelector("#proxyTab").classList.remove("active");
    event.currentTarget.setAttribute("aria-selected", "true"); document.querySelector("#proxyTab").setAttribute("aria-selected", "false");
    proxyPane.hidden = true; manualPane.hidden = false;
  });
  document.querySelector("#handoffForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = document.querySelector("#handoffStatus");
    try {
      status.textContent = "正在创建安全会话...";
      const data = await api(`/api/customer/${encodeURIComponent(rawToken)}/silicon/handoffs`, {
        method: "POST", body: { consent: document.querySelector("#handoffConsent").checked },
      });
      location.assign(data.viewer_url);
    } catch (error) {
      status.textContent = error.message;
    }
  });
  document.querySelector("#sendSfCode")?.addEventListener("click", async () => {
    try {
      const data = await api(`/api/customer/${encodeURIComponent(rawToken)}/silicon/send-code`, {
        method: "POST", body: { phone: document.querySelector("#sfPhone").value },
      });
      document.querySelector("#sfCodeHint").textContent = data.debug_code ? `本地演示验证码：${data.debug_code}` : "验证码已发送";
    } catch (error) { toast(error.message); }
  });
  document.querySelector("#proxyForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api(`/api/customer/${encodeURIComponent(rawToken)}/silicon/login`, {
        method: "POST", body: {
          phone: document.querySelector("#sfPhone").value,
          otp: document.querySelector("#sfOtp").value,
          consent: document.querySelector("#sfConsent").checked,
        },
      });
      toast("邀请码获取成功，会话已加密保存");
      await renderCustomer(rawToken);
    } catch (error) { toast(error.message); }
  });
  document.querySelector("#manualForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api(`/api/customer/${encodeURIComponent(rawToken)}/manual-invitation`, {
        method: "POST", body: {
          invitation: document.querySelector("#manualInvitation").value,
          consent: document.querySelector("#manualConsent").checked,
        },
      });
      toast("邀请码已确认");
      await renderCustomer(rawToken);
    } catch (error) { toast(error.message); }
  });
}

async function renderTask(slug) {
  setNavVisible(false);
  clearInterval(state.countdownTimer);
  let task;
  try {
    task = await api(`/api/tasks/${encodeURIComponent(slug)}`);
  } catch (error) {
    appRoot.innerHTML = `${pageHeading("任务", "无法打开任务", error.message)}<div class="notice error">${escapeHtml(error.message)}</div>`;
    return;
  }
  let assignment = null;
  if (state.me) {
    const data = await api("/api/me/assignments");
    assignment = data.assignments.find((item) => item.public_slug === slug) || null;
  }
  const completion = Math.min(100, task.target ? task.counts.locked / task.target * 100 : 0);
  appRoot.innerHTML = `
    <div class="detail-title"><p class="eyebrow">公开任务</p><h1>SiliconFlow 新用户注册与认证</h1><p>使用指定邀请码完成注册和首次有效实名认证，奖励 5 元。</p></div>
    <div class="detail-layout">
      <div class="detail-main">
        <div class="panel">
          <h2>任务要求</h2>
          <dl class="key-value"><dt>邀请信息</dt><dd>抢单成功后向本人显示</dd><dt>完成条件</dt><dd>新用户注册 + 填写邀请码 + 首次有效实名认证</dd><dt>任务截止</dt><dd>${formatTime(task.expires_at)}</dd></dl>
        </div>
        <div class="panel">
          <h2>我的进度</h2>
          ${assignment ? assignmentPanel(assignment) : `<p class="muted">领取后将锁定 30 分钟名额。领取前须完成本站手机号登录和支付宝收款信息登记。</p><button id="claimTask" class="button primary" ${task.available <= 0 ? "disabled" : ""}>${task.available <= 0 ? "当前名额已满" : "立即抢单"}</button>`}
        </div>
      </div>
      <aside class="detail-side">
        <div class="panel"><span class="status ${task.available ? "green" : "amber"}">${task.available ? "可抢单" : "名额已占用"}</span><h2>${task.counts.locked} / ${task.target} 已完成</h2><div class="progress"><span style="width:${completion}%"></span></div><p class="muted">保护中 ${task.counts.active} 人 · 剩余 ${task.available} 人</p></div>
        <div class="panel"><h2>规则</h2><p>30 分钟后释放保护名额；订单 24 小时内补做成功且尚有容量，仍可获得奖励。订单已满后不再奖励。</p></div>
      </aside>
    </div>`;
  document.querySelector("#claimTask")?.addEventListener("click", () => claimAfterAccount(slug));
  bindCopyButtons();
  if (assignment) bindAssignmentActions(assignment, slug);
}

function assignmentPanel(item) {
  const active = item.status === "ACTIVE";
  const canComplete = ["ACTIVE", "EXPIRED"].includes(item.status);
  return `
    <div class="button-row"><span class="status ${statusClass(item.status)}">${statusLabels[item.status] || item.status}</span>${item.reward_status ? `<span class="status ${statusClass(item.reward_status)}">奖励：${statusLabels[item.reward_status] || item.reward_status}</span>` : ""}</div>
    ${active ? `<h3>保护期剩余</h3><div id="countdown" class="countdown" data-expires="${item.reservation_expires_at}">${formatRemaining(item.reservation_expires_at - Date.now() / 1000)}</div>` : ""}
    <dl class="key-value"><dt>领取时间</dt><dd>${formatTime(item.claimed_at)}</dd><dt>注册状态</dt><dd>${item.registered_at ? "已登记完成" : "待完成"}</dd><dt>认证状态</dt><dd>${item.verified_at ? "已确认" : "待确认"}</dd></dl>
    ${canComplete && item.invitation_url ? `<div class="official-actions"><a class="button primary" href="${escapeHtml(item.invitation_url)}" target="_blank" rel="noopener noreferrer">前往 SiliconFlow 注册</a><button type="button" class="button secondary" data-copy="${escapeHtml(item.invitation_url)}">复制邀请链接</button></div>` : ""}
    ${canComplete ? `<form id="siliconAccountForm" class="form-stack upstream-form">
      <label>SiliconFlow 用户 ID<input id="siliconAccountId" autocomplete="off" autocapitalize="off" spellcheck="false" maxlength="128" required placeholder="完成后填写用户 ID"></label>
      <button class="button secondary" type="submit">${item.upstream_claim ? "更新并等待核验" : "提交并等待核验"}</button>
      <p id="upstreamClaimStatus" class="form-hint" role="status">${item.upstream_claim ? `已提交 ${escapeHtml(item.upstream_claim.account_id_mask)} · ${item.upstream_claim.status === "PENDING" ? "等待核验" : statusLabels[item.upstream_claim.status] || item.upstream_claim.status}` : "提交不会直接认定注册或认证成功"}</p>
    </form>` : ""}
    ${canComplete && state.health?.environment === "development" ? `<div class="button-row"><button id="mockRegister" class="button secondary">模拟完成注册</button><button id="mockVerify" class="button primary">模拟完成有效认证</button></div>` : ""}
    ${item.status === "EXPIRED" ? `<div class="notice warning">30 分钟保护期已结束。订单未满且仍在 24 小时内时，补做成功仍可锁定奖励。</div>` : ""}`;
}

function bindAssignmentActions(item, slug) {
  const countdown = document.querySelector("#countdown");
  if (countdown) {
    state.countdownTimer = window.setInterval(() => {
      const remaining = Number(countdown.dataset.expires) - Date.now() / 1000;
      countdown.textContent = formatRemaining(remaining);
      if (remaining <= 0) {
        clearInterval(state.countdownTimer);
        window.setTimeout(() => renderTask(slug), 600);
      }
    }, 1000);
  }
  document.querySelector("#siliconAccountForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = document.querySelector("#upstreamClaimStatus");
    try {
      status.textContent = "正在提交...";
      await api(`/api/assignments/${item.id}/silicon-account`, {
        method: "PUT", body: { account_id: document.querySelector("#siliconAccountId").value },
      });
      toast("用户 ID 已提交，等待核验");
      await renderTask(slug);
    } catch (error) {
      status.textContent = error.message;
    }
  });
  document.querySelector("#mockRegister")?.addEventListener("click", async () => {
    try { await api(`/api/assignments/${item.id}/mock-register`, { method: "POST" }); toast("注册状态已更新"); await renderTask(slug); }
    catch (error) { toast(error.message); }
  });
  document.querySelector("#mockVerify")?.addEventListener("click", async () => {
    try { await api(`/api/assignments/${item.id}/mock-verify`, { method: "POST" }); toast("有效认证已确认，奖励已锁定"); await renderTask(slug); }
    catch (error) { toast(error.message); }
  });
}

async function showView(view) {
  setNavVisible(true);
  clearInterval(state.countdownTimer);
  state.view = view;
  mainNav.querySelectorAll("button").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  appRoot.innerHTML = `<div class="loading">正在加载...</div>`;
  try {
    if (view === "mine") await renderMine();
    else if (view === "admin") await renderAdmin();
    else await renderTasks();
  } catch (error) {
    appRoot.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
  }
}

document.querySelector("#sendSiteCode").addEventListener("click", async () => {
  try {
    const data = await api("/api/auth/send-code", { method: "POST", body: { phone: document.querySelector("#loginPhone").value } });
    document.querySelector("#siteCodeHint").textContent = data.debug_code ? `本地演示验证码：${data.debug_code}` : "验证码已发送";
  } catch (error) { toast(error.message); }
});

document.querySelector("#authForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/auth/verify", { method: "POST", body: { phone: document.querySelector("#loginPhone").value, code: document.querySelector("#loginCode").value } });
    await loadMe();
    authDialog.close();
    toast("登录成功");
    if (state.pendingClaim) await claimAfterAccount(state.pendingClaim);
    else if (location.pathname === "/") await showView(state.view);
  } catch (error) { toast(error.message); }
});

document.querySelector("#alipayForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/me/alipay", { method: "PUT", body: { account: document.querySelector("#alipayAccount").value, real_name: document.querySelector("#alipayName").value } });
    await loadMe();
    alipayDialog.close();
    toast("支付宝收款信息已登记");
    const callback = state.afterBind;
    state.afterBind = null;
    if (callback) await callback();
  } catch (error) { toast(error.message); }
});

accountButton.addEventListener("click", async () => {
  if (!state.me) { openLogin(); return; }
  if (!confirm("退出当前本站账号？")) return;
  await api("/api/auth/logout", { method: "POST" });
  await loadMe();
  if (location.pathname === "/") await showView(state.view);
  else location.reload();
});

mainNav.querySelectorAll("button").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));

async function init() {
  state.health = await api("/api/health");
  await loadMe();
  const customerMatch = location.pathname.match(/^\/o\/([^/]+)$/);
  const taskMatch = location.pathname.match(/^\/t\/([^/]+)$/);
  if (customerMatch) await renderCustomer(decodeURIComponent(customerMatch[1]));
  else if (taskMatch) await renderTask(decodeURIComponent(taskMatch[1]));
  else await showView("tasks");
}

init().catch((error) => {
  appRoot.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
});
