/* GovFood SPA - buyers, riders (GPS), admin. No framework. */
"use strict";
const state = { token: localStorage.getItem("gf_token") || "", user: null, products: [], cart: {}, riderWatch: null, map: null, mapTimer: null };
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const GHS = n => "GH₵" + Number(n || 0).toLocaleString("en-GH", { maximumFractionDigits: 2 });
const kg = n => Number(n || 0).toLocaleString("en-GH", { maximumFractionDigits: 1 });

function toast(msg, kind = "") { const t = document.createElement("div"); t.className = "toast " + kind; t.textContent = msg; $("#toast-root").appendChild(t); setTimeout(() => t.remove(), 4500); }
async function api(path, opts = {}) {
  const res = await fetch(path, { method: opts.method || "GET",
    headers: { ...(opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
               ...(state.token ? { Authorization: "Bearer " + state.token } : {}) },
    body: opts.body ? (opts.body instanceof FormData ? opts.body : JSON.stringify(opts.body)) : undefined });
  if (res.status === 401 && !path.startsWith("/auth/")) { openAuthModal("Sign in to continue"); throw new Error("Sign in to continue"); }
  let data = null; try { data = await res.json(); } catch {}
  if (!res.ok) { const d = data && data.detail; throw new Error(Array.isArray(d) ? d.map(x => x.msg).join("; ") : (d || `Request failed (${res.status})`)); }
  return data;
}
function openModal(html) { const root = $("#modal-root"); $("#modal-card").innerHTML = `<button class="modal-close" id="modal-close">✕</button>` + html; root.hidden = false; root.style.display = "flex"; $("#modal-close").onclick = closeModal; }
function closeModal() { const root = $("#modal-root"); root.hidden = true; root.style.display = "none"; }
$("#modal-backdrop").addEventListener("click", closeModal);
const loading = (m = "Loading…") => `<div class="empty-state"><div class="spinner"></div>${esc(m)}</div>`;
const emptyState = (t, c = "") => `<div class="empty-state"><p>${esc(t)}</p>${c}</div>`;
const statusPill = s => ({ pending_payment: '<span class="pill warn">Awaiting payment</span>',
  paid: '<span class="pill ok">Paid · assigning</span>', assigned: '<span class="pill info">Rider assigned</span>',
  picked: '<span class="pill info">Picked up</span>', delivering: '<span class="pill warn">On the way</span>',
  delivered: '<span class="pill ok">Delivered</span>', cancelled: '<span class="pill bad">Cancelled</span>' }[s] || s);

/* ---------------- auth ---------------- */
function renderChrome() {
  const loggedIn = !!state.user;
  $("#btn-auth").hidden = loggedIn; $("#user-chip").hidden = !loggedIn;
  $("#nav-admin").hidden = !(loggedIn && state.user.role === "admin");
  $("#menu-admin").hidden = !(loggedIn && state.user.role === "admin");
  $("#nav-rider").hidden = !(loggedIn && state.user.role === "rider");
  $("#menu-rider").hidden = !(loggedIn && state.user.role === "rider");
  if (loggedIn) { $("#user-avatar").textContent = (state.user.full_name || "G")[0].toUpperCase(); $("#user-menu-name").textContent = `${state.user.full_name} · ${state.user.role}`; }
}
function openAuthModal(note = "") {
  openModal(`<h3 class="mb">${esc(note) || "Welcome to GovFood"}</h3>
    <div class="auth-tabs"><button id="tab-login" class="active">Sign in</button><button id="tab-reg">Create account</button></div>
    <form id="auth-form" class="grid" style="gap:.8rem">
      <div class="field" id="f-name" hidden><label>Full name</label><input name="full_name" minlength="2"></div>
      <div class="field"><label>Email</label><input name="email" type="email" required></div>
      <div class="field" id="f-phone" hidden><label>Phone</label><input name="phone" minlength="7"></div>
      <div class="field" id="f-role" hidden><label>I am a</label><select name="role"><option value="user">Government worker (buyer)</option><option value="rider">Delivery rider</option></select></div>
      <div class="field"><label>Password</label><input name="password" type="password" required minlength="6"></div>
      <button class="btn btn-primary btn-block" id="auth-submit">Sign in</button>
    </form>
    <p class="muted small mt">Buyers: verify your work ID + bank to unlock GH₵500 monthly credit. Riders: register, upload DL + photo, get verified, start earning.</p>`);
  let mode = "login";
  const swap = m => { mode = m;
    $("#tab-login").classList.toggle("active", m === "login"); $("#tab-reg").classList.toggle("active", m === "register");
    $("#f-name").hidden = $("#f-phone").hidden = $("#f-role").hidden = m === "login";
    $("#auth-submit").textContent = m === "login" ? "Sign in" : "Create account"; };
  $("#tab-login").onclick = () => swap("login"); $("#tab-reg").onclick = () => swap("register");
  $("#auth-form").onsubmit = async e => { e.preventDefault();
    const body = Object.fromEntries(new FormData(e.target).entries());
    if (mode === "register" && (!body.full_name || !body.phone)) return toast("Fill all fields", "error");
    const btn = $("#auth-submit"); btn.disabled = true;
    try { const r = await api("/auth/" + (mode === "login" ? "login" : "register"), { method: "POST", body });
      state.token = r.access_token; localStorage.setItem("gf_token", r.access_token); state.user = r.user;
      closeModal(); renderChrome(); toast(`Welcome${mode === "login" ? " back" : ""}, ${r.user.full_name.split(" ")[0]}!`, "success"); route();
    } catch (err) { toast(err.message, "error"); }
    btn.disabled = false; };
}
$("#btn-auth").onclick = () => openAuthModal();
$("#user-avatar").onclick = e => { e.stopPropagation(); $("#user-menu").hidden = !$("#user-menu").hidden; };
document.addEventListener("click", () => { const m = $("#user-menu"); if (m) m.hidden = true; });
$("#user-menu").addEventListener("click", e => e.stopPropagation());
$("#btn-logout").onclick = () => { state.token = ""; state.user = null; localStorage.removeItem("gf_token");
  stopRiderWatch(); renderChrome(); location.hash = "#/"; route(); toast("Signed out"); };

/* ---------------- shop ---------------- */
async function loadProducts() { state.products = await api("/products"); }
function viewHome() {
  const app = $("#app");
  const credit = state.user ? `<div class="card card-pad" style="background:var(--gold-soft);border:1px dashed var(--gold)">
      <b>Your credit:</b> ${GHS(state.user.credit_available)} available of ${GHS(state.user.credit_limit)} · repayable in 1 month @ 15% fee
      ${state.user.verified ? "" : ' · <a href="#/profile"><b>Verify to activate →</b></a>'}</div>` : "";
  app.innerHTML = `<section class="hero"><div class="hero-inner">
    <h1>Quality foodstuffs for government workers — priced per kilo, delivered to your door</h1>
    <p>Rice, beans, plantain, fish, meat, vegetables and more at fair KG prices. Verified workers shop with GH₵500 monthly credit or pay instantly by MoMo/card. Live rider tracking on every order.</p>
    <div class="stat-strip"><div class="card-pad"><b>26+</b> staples & fresh foods</div>
    <div class="card-pad"><b>GH₵500</b> monthly credit</div>
    <div class="card-pad"><b>Live GPS</b> rider tracking</div></div></div></section>
  <div class="wrap"><div class="mt">${credit}</div>
    <div id="shop" class="mt">${loading("Loading market…")}</div></div>`;
  renderShop();
}
function renderShop() {
  const cats = [...new Set(state.products.map(p => p.category))];
  $("#shop").innerHTML = cats.map(cat => `<h3 class="section-title mt" style="font-size:1.1rem">${esc(cat)}</h3>
    <div class="grid grid-3">${state.products.filter(p => p.category === cat).map(p => `
      <div class="prod"><span class="cat">${esc(p.category)}</span><b>${esc(p.name)}</b>
        <div class="price">${GHS(p.price)} <small>/ kg</small></div>
        <div class="muted small">${kg(p.stock)} kg in stock</div>
        <div class="qty-row mt"><input type="number" min="0.5" max="${p.stock}" step="0.5" value="1" id="q${p.id}">
        <button class="btn btn-primary btn-sm" data-add="${p.id}" ${p.stock < 0.5 ? "disabled" : ""}>Add to cart</button></div>
      </div>`).join("")}</div>`).join("");
  $$("#shop [data-add]").forEach(b => b.onclick = () => {
    const p = state.products.find(x => x.id == b.dataset.add);
    const qty = Math.max(0.5, parseFloat($("#q" + p.id).value) || 1);
    if (qty > p.stock) return toast(`Only ${kg(p.stock)}kg available`, "error");
    state.cart[p.id] = (state.cart[p.id] || 0) + qty;
    toast(`${p.name} × ${kg(qty)}kg added to cart`, "success"); renderCartBar(); });
  renderCartBar();
}
function renderCartBar() {
  let bar = $("#cart-bar");
  const items = Object.entries(state.cart);
  if (!items.length) { if (bar) bar.remove(); return; }
  const total = items.reduce((s, [id, q]) => s + (state.products.find(p => p.id == id)?.price || 0) * q, 0);
  const kgTotal = items.reduce((s, [, q]) => s + q, 0);
  if (!bar) { bar = document.createElement("div"); bar.id = "cart-bar";
    bar.style.cssText = "position:fixed;left:50%;transform:translateX(-50%);bottom:1.2rem;z-index:80;background:var(--navy);color:#fff;border-radius:999px;padding:.7rem 1.4rem;display:flex;gap:1rem;align-items:center;box-shadow:var(--shadow)";
    document.body.appendChild(bar); }
  bar.innerHTML = `<b>${items.length} item(s) · ${kg(kgTotal)}kg · ${GHS(total)}</b>
    <button class="btn btn-gold btn-sm" onclick="location.hash='#/cart'">Checkout →</button>
    <button class="btn btn-ghost btn-sm" id="cart-clear">Clear</button>`;
  $("#cart-clear").onclick = () => { state.cart = {}; renderCartBar(); };
}
function viewCart() {
  const items = Object.entries(state.cart).map(([id, qty]) => ({ ...state.products.find(p => p.id == id), qty }));
  if (!items.length) { $("#app").innerHTML = `<div class="wrap">${emptyState("Your cart is empty", '<a class="btn btn-primary mt" href="#/">Go shopping</a>')}</div>`; return; }
  const total = items.reduce((s, i) => s + i.price * i.qty, 0);
  const kgT = items.reduce((s, i) => s + i.qty, 0);
  const fee = Math.round(total * 0.15 * 100) / 100;
  let delivery = 10; // fallback flat fee; updated by live quote below
  const grand = () => total + delivery;
  const creditOk = state.user && state.user.verified && state.user.credit_available >= total;
  $("#app").innerHTML = `<div class="wrap" style="max-width:760px">
    <h2 class="section-title">Your cart</h2>
    <div class="card table-scroll mb"><table class="table"><tr><th>Item</th><th>Qty (kg)</th><th>Price/kg</th><th>Line</th><th></th></tr>
      ${items.map(i => `<tr><td>${esc(i.name)}</td><td>${kg(i.qty)}</td><td>${GHS(i.price)}</td><td>${GHS(i.price * i.qty)}</td>
        <td><button class="btn btn-danger btn-sm" data-del="${i.id}">✕</button></td></tr>`).join("")}
      <tr><td colspan="3"><b>Total (${kg(kgT)}kg)</b></td><td><b>${GHS(total)}</b></td><td></td></tr></table></div>
    <div class="card card-pad mb"><h3 class="mb">Delivery details</h3>
      <form id="checkout-form" class="grid" style="gap:.8rem">
        <div class="field"><label>Delivery address</label><textarea name="address" rows="2" required placeholder="House no, street, area, city"></textarea></div>
        <div class="row"><button type="button" class="btn btn-outline btn-sm" id="use-gps">📍 Use my current location (GPS)</button><span class="muted small" id="gps-note"></span></div>
        <input type="hidden" name="lat" id="lat"><input type="hidden" name="lng" id="lng">
        <label class="row small" style="gap:.4rem"><input type="checkbox" name="bulk" value="1"> <span><b>Ministry bulk order</b> — one combined delivery for my office (appears on the ministry invoice)</span></label>
        <div class="field"><label>Bulk order note (optional)</label><input name="note" maxlength="200" placeholder="e.g. For Agric Dept staff canteen - 40 beneficiaries"></div>
        <div class="field"><label>Payment</label>
          <select name="payment_method">
            ${creditOk ? `<option value="credit">Monthly credit (repay in 1 month + 15% fee) — ${GHS(state.user.credit_available)} available</option>` : ""}
            <option value="instant">Instant payment (MoMo / card)</option>
          </select></div>
        ${!creditOk && state.user ? `<p class="muted small">Credit unavailable (need ${GHS(total)}${state.user.verified ? "" : " + verification"}). Instant payment selected.</p>` : ""}
        <div class="sum-row spread"><span>Subtotal (${kg(kgT)}kg)</span><span>${GHS(total)}</span></div>
        <div class="sum-row spread"><span>Delivery fee</span><span id="delivery-row">${GHS(delivery)}</span></div>
        <div class="sum-row spread"><b>Total</b><b id="grand-row" style="color:var(--green);font-size:1.2rem">${GHS(grand())}</b></div>
        <p class="muted small">Platform fee on this sale (15%): ${GHS(fee)} · included in settlement to GovFood</p>
        <button class="btn btn-primary btn-block" id="pay-btn">Place order · ${GHS(grand())}</button>
      </form></div></div>`;
  $$("[data-del]").forEach(b => b.onclick = () => { delete state.cart[b.dataset.del]; viewCart(); renderCartBar(); });
  const quoteDelivery = async () => {
    const lat = $("#lat").value, lng = $("#lng").value;
    try { const q = await api(`/delivery-quote?lat=${lat || ""}&lng=${lng || ""}`);
      delivery = q.fee;
      $("#delivery-row").textContent = GHS(q.fee) + (q.km != null ? ` (${q.km}km · ${q.tier} zone)` : " (flat)");
      $("#grand-row").textContent = GHS(grand());
      $("#pay-btn").textContent = `Place order · ${GHS(grand())}`;
    } catch {}
  };
  $("#use-gps").onclick = () => navigator.geolocation?.getCurrentPosition(async pos => {
    $("#lat").value = pos.coords.latitude; $("#lng").value = pos.coords.longitude;
    $("#gps-note").textContent = "Location captured ✓"; await quoteDelivery(); }, () => toast("Could not get GPS location", "error"));
  quoteDelivery();
  $("#checkout-form").onsubmit = async e => { e.preventDefault();
    const fd = new FormData(e.target);
    const body = { items: Object.entries(state.cart).map(([product_id, qty]) => ({ product_id: +product_id, qty })),
      address: fd.get("address"), lat: fd.get("lat") || null, lng: fd.get("lng") || null,
      payment_method: fd.get("payment_method"), bulk: fd.get("bulk") === "1", note: fd.get("note") || "" };
    const btn = $("#pay-btn"); btn.disabled = true; btn.textContent = "Placing order…";
    try { const r = await api("/orders", { method: "POST", body });
      state.cart = {}; renderCartBar();
      if (r.status === "pending_payment") {
        const p = await api("/payments/initialize", { method: "POST", body: { reference: r.reference } });
        if (p.authorization_url) { location.href = p.authorization_url; return; }
        location.hash = `#/pay/${r.reference}`;
      } else {
        toast(`Order ${r.reference} placed!`, "success");
        location.hash = `#/order/${r.reference}`;
      }
    } catch (err) { toast(err.message, "error"); btn.disabled = false; btn.textContent = "Place order"; } };
}

/* ---------------- orders + tracking + chat ---------------- */
async function viewOrders() {
  if (!state.user) { openAuthModal("Sign in to see your orders"); $("#app").innerHTML = emptyState("Sign in to view orders"); return; }
  $("#app").innerHTML = `<div class="wrap"><h2 class="section-title">My orders</h2><div id="olist">${loading()}</div></div>`;
  const list = await api("/orders/mine");
  $("#olist").innerHTML = list.length ? `<div class="grid" style="gap:.7rem">${list.map(o => `
    <a class="card card-pad spread" href="#/order/${o.reference}" style="color:inherit">
      <div><b>${o.reference}</b> ${statusPill(o.status)}<div class="muted small">${kg(o.total_kg)}kg · ${o.items.map(i => esc(i.name)).join(", ").slice(0, 60)}</div></div>
      <div class="right"><b>${GHS(o.amount)}</b><div class="muted small">${o.created_at.slice(0, 16)}</div></div>
    </a>`).join("")}</div>` : emptyState("No orders yet — go grab some foodstuffs!", '<a class="btn btn-primary mt" href="#/">Shop now</a>');
}
function stopOrderPolling() { if (state.mapTimer) { clearInterval(state.mapTimer); state.mapTimer = null; } if (state.map) { state.map.remove(); state.map = null; } }
async function viewOrder(ref) {
  stopOrderPolling();
  $("#app").innerHTML = `<div class="wrap">${loading("Loading order…")}</div>`;
  let o; try { o = await api("/orders/" + ref); } catch (e) { $("#app").innerHTML = emptyState(e.message); return; }
  const canChat = state.user && (state.user.role === "admin" || o.rider || o.status !== "delivered");
  $("#app").innerHTML = `<div class="wrap" style="max-width:860px">
    <div class="spread mb"><h2 class="section-title" style="margin:0">${o.reference} ${statusPill(o.status)}</h2>
      <b style="font-size:1.2rem">${GHS(o.amount)}</b></div>
    <div class="grid" style="grid-template-columns:1.4fr 1fr;align-items:start" id="order-grid">
      <div>
        <div class="card table-scroll mb"><table class="table"><tr><th>Item</th><th>kg</th><th>Line</th></tr>
          ${o.items.map(i => `<tr><td>${esc(i.name)}</td><td>${kg(i.qty)}</td><td>${GHS(i.line)}</td></tr>`).join("")}
          <tr><td colspan="2"><b>Total</b></td><td><b>${GHS(o.amount)}</b></td></tr></table></div>
        <div class="card card-pad mb"><b>Delivery address:</b><br>${esc(o.address)}<br>
          <span class="muted small">Paid via ${o.payment_method}${o.credit_applied ? ` · credit ${GHS(o.credit_applied)}` : ""}</span></div>
        <div class="card card-pad"><h4 class="mb">Live tracking</h4><div id="map" class="map">Map loading…</div>
          <div id="map-note" class="muted small mt"></div></div>
      </div>
      <div>
        ${o.rider ? `<div class="card card-pad mb"><div class="row">
          ${o.rider.photo ? `<img class="rider-photo" src="${o.rider.photo}" alt="${esc(o.rider.name)}">` : ""}
          <div><b>${esc(o.rider.name)}</b><div class="muted small">🚗 ${esc(o.rider.plate || "")} · ⭐ verified rider</div>
          <a class="small" href="tel:${o.rider.phone}">📞 ${o.rider.phone}</a></div></div></div>` :
          `<div class="card card-pad mb muted">Assigning a rider… you will be notified.</div>`}
        <div class="card card-pad"><h4 class="mb">Chat ${state.user.role === "admin" ? "(admin monitor)" : ""}</h4>
          <div class="chat-box mb" id="chat-box">${loading("Chat…")}</div>
          <form id="chat-form" class="row"><input class="field" style="flex:1" name="text" required maxlength="500" placeholder="Message…">
          <button class="btn btn-primary btn-sm">Send</button></form></div>
      </div>
    </div>
    <style>@media(max-width:800px){#order-grid{grid-template-columns:1fr!important}}</style>
  </div>`;
  initOrderMap(o);
  loadChat(ref);
  $("#chat-form").onsubmit = async e => { e.preventDefault();
    try { await api(`/orders/${ref}/messages`, { method: "POST", body: { text: new FormData(e.target).get("text") } });
      e.target.reset(); loadChat(ref); } catch (err) { toast(err.message, "error"); } };
  state.mapTimer = setInterval(async () => { try { const fresh = await api("/orders/" + ref); updateMap(fresh); } catch {} }, 15000);
}
async function loadChat(ref) {
  try { const msgs = await api(`/orders/${ref}/messages`);
    $("#chat-box").innerHTML = msgs.length ? msgs.map(m =>
      `<div class="chat-msg ${m.role === state.user.role ? "mine" : ""}"><b class="small">${esc(m.sender)}</b> ${esc(m.text)}<small>${m.created_at.slice(11, 16)}</small></div>`).join("")
      : `<div class="muted small">No messages yet — say hello to ${state.user.role === "user" ? "your rider" : "the buyer"}.</div>`;
    $("#chat-box").scrollTop = 1e6;
  } catch {}
}
function initOrderMap(o) {
  if (typeof L === "undefined") { $("#map").textContent = "Map unavailable (offline)"; return; }
  const center = o.lat ? [o.lat, o.lng] : [5.6037, -0.1870];
  state.map = L.map("map").setView(center, 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(state.map);
  updateMap(o);
}
function updateMap(o) {
  if (!state.map) return;
  if (state._markers) state._markers.forEach(m => m.remove());
  state._markers = [];
  if (o.lat) state._markers.push(L.marker([o.lat, o.lng]).addTo(state.map).bindPopup("Delivery address"));
  if (o.rider && o.rider.lat) {
    const rm = L.marker([o.rider.lat, o.rider.lng]).addTo(state.map).bindPopup(`🛵 ${esc(o.rider.name)}`).openPopup();
    state._markers.push(rm);
    if (o.status === "delivering") state.map.setView([o.rider.lat, o.rider.lng], 14);
  }
  $("#map-note").textContent = o.rider && o.rider.lat
    ? `Rider last seen: ${o.rider.last_seen || "now"} · ${o.status}`
    : (o.rider ? "Waiting for rider location…" : "Rider location appears once assigned.");
}

/* ---------------- profile / verification ---------------- */
async function viewProfile() {
  if (!state.user) { openAuthModal(); return; }
  const fresh = await api("/auth/me"); state.user = fresh;
  $("#app").innerHTML = `<div class="wrap" style="max-width:640px">
    <h2 class="section-title">My profile & credit</h2>
    <div class="grid grid-2">
      <div class="card card-pad"><h4 class="mb">Verification ${fresh.verified ? '<span class="pill ok">Approved</span>' : '<span class="pill warn">Pending / not submitted</span>'}</h4>
        ${fresh.verified ? `<p class="small">Employer: ${esc(fresh.employer)} · Work ID: ${esc(fresh.work_id)}</p>
          <p class="small muted">Bank linked: your account ending ${esc((fresh.bank_acct || "****").slice(-4))}</p>` :
        `<form id="verify-form" class="grid" style="gap:.8rem">
          <div class="field"><label>Employer / Ministry</label><input name="employer" required placeholder="e.g. Ministry of Agriculture"></div>
          <div class="field"><label>Work ID number</label><input name="work_id" required placeholder="Staff ID"></div>
          <div class="field-row">
            <div class="field"><label>Bank name</label><input name="bank_name" required placeholder="e.g. Ecobank"></div>
            <div class="field"><label>Account number (for credit deduction)</label><input name="bank_acct" required minlength="6" placeholder="0123456789"></div>
          </div>
          <button class="btn btn-primary btn-block">Submit for verification</button>
          <p class="muted small">Admin reviews your work ID, then approves your account + GH₵500 credit.</p>
        </form>`}
      </div>
      <div class="card card-pad" style="background:var(--gold-soft)"><h4 class="mb">Monthly credit</h4>
        <div class="sum-row spread"><span>Limit</span><b>${GHS(fresh.credit_limit)}</b></div>
        <div class="sum-row spread"><span>Used</span><b>${GHS(fresh.credit_used)}</b></div>
        <div class="sum-row spread"><span>Available</span><b style="color:var(--green);font-size:1.2rem">${GHS(fresh.credit_available)}</b></div>
        <p class="muted small mt">Credit orders repay automatically after 1 month from your linked account, plus a 15% service fee.</p></div>
    </div></div>`;
  const vf = $("#verify-form");
  if (vf) vf.onsubmit = async e => { e.preventDefault();
    try { await api("/auth/verify", { method: "POST", body: Object.fromEntries(new FormData(e.target).entries()) });
      toast("Verification submitted — admin will review", "success"); viewProfile(); } catch (err) { toast(err.message, "error"); } };
}

/* ---------------- rider app ---------------- */
function stopRiderWatch() { if (state.riderWatch) { navigator.geolocation?.clearWatch(state.riderWatch); state.riderWatch = null; } }
async function viewRider() {
  if (!state.user) { openAuthModal("Sign in as a rider"); return; }
  if (state.user.role !== "rider") { $("#app").innerHTML = emptyState("This area is for rider accounts."); return; }
  const prof = await api("/rider/me");
  if (!prof.registered || !prof.dl_number) {
    $("#app").innerHTML = `<div class="wrap" style="max-width:560px"><h2 class="section-title">Rider registration</h2>
      <div class="card card-pad"><form id="rider-form" class="grid" style="gap:.8rem">
        <div class="field"><label>Driving licence number</label><input name="dl_number" required minlength="4"></div>
        <div class="field"><label>Bike / vehicle plate</label><input name="plate" required></div>
        <div class="field"><label>Your photo (buyers see this as your profile)</label><input name="photo" type="file" accept="image/*" required></div>
        <button class="btn btn-primary btn-block">Submit for verification</button>
        <p class="muted small">Admin verifies your DL + photo. Once approved you appear on the dispatch board and start receiving orders.</p>
      </form></div></div>`;
    $("#rider-form").onsubmit = async e => { e.preventDefault();
      const fd = new FormData(e.target);
      try { await api("/rider/profile", { method: "POST", body: fd });
        toast("Profile submitted — await admin verification", "success"); viewRider(); } catch (err) { toast(err.message, "error"); } };
    return;
  }
  $("#app").innerHTML = `<div class="wrap"><div class="spread mb"><h2 class="section-title" style="margin:0">Rider dashboard ${prof.verified ? '<span class="pill ok">Verified</span>' : '<span class="pill warn">Awaiting verification</span>'}</h2>
      <label class="row small"><input type="checkbox" id="duty" ${state.riderWatch ? "checked" : ""}> Share my location (GPS) for dispatch</label></div>
    <div class="card card-pad mb">${prof.photo ? `<img class="rider-photo" src="${prof.photo}">` : ""} <b>${esc(state.user.full_name)}</b> · 🚗 ${esc(prof.plate)} · DL ${esc(prof.dl_number)}</div>
    <div id="rmap" class="map mb" style="display:none"></div>
    <h3 class="section-title" style="font-size:1.1rem">Assigned orders</h3><div id="rorders">${loading()}</div></div>`;
  $("#duty").onchange = e => {
    if (e.target.checked) {
      if (!navigator.geolocation) return toast("GPS not available on this device", "error");
      $("#rmap").style.display = "";
      if (!state.map2 && typeof L !== "undefined") {
        state.map2 = L.map("rmap").setView([5.6037, -0.187], 12);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19 }).addTo(state.map2);
      }
      state.riderWatch = navigator.geolocation.watchPosition(async pos => {
        const { latitude: lat, longitude: lng } = pos.coords;
        try { await api("/rider/location", { method: "POST", body: { lat, lng } }); } catch {}
        if (state.map2) { if (state._me) state._me.remove(); state._me = L.marker([lat, lng]).addTo(state.map2); state.map2.setView([lat, lng], 14); }
      }, () => toast("GPS error — enable location permission", "error"), { enableHighAccuracy: true, maximumAge: 10000 });
      toast("Location sharing ON — admin can now dispatch you", "success");
    } else stopRiderWatch();
  };
  const orders = await api("/rider/orders");
  $("#rorders").innerHTML = orders.length ? `<div class="grid" style="gap:.7rem">${orders.map(o => `
    <div class="card card-pad"><div class="spread"><div><b>${o.reference}</b> ${statusPill(o.status)}</div><b>${GHS(o.amount)}</b></div>
      <div class="muted small mt">${kg(o.total_kg)}kg · ${esc(o.address)}</div>
      <div class="row mt"><span>Buyer: <a href="tel:${o.buyer.phone}">${esc(o.buyer.name)} 📞</a></span>
      ${o.status === "assigned" ? `<button class="btn btn-primary btn-sm" data-st="picked" data-ref="${o.reference}">Picked up</button>` : ""}
      ${o.status === "picked" ? `<button class="btn btn-gold btn-sm" data-st="delivering" data-ref="${o.reference}">Start delivery</button>` : ""}
      ${o.status === "delivering" ? `<button class="btn btn-primary btn-sm" data-st="delivered" data-ref="${o.reference}">Mark delivered</button>` : ""}
      <a class="btn btn-outline btn-sm" href="#/order/${o.reference}">Open (map+chat)</a></div></div>`).join("")}</div>`
    : emptyState("No active deliveries. Turn on location sharing and wait for admin to assign orders.");
  $$("#rorders [data-st]").forEach(b => b.onclick = async () => {
    try { await api(`/rider/orders/${b.dataset.ref}/status`, { method: "POST", body: { status: b.dataset.st } });
      toast(`Status: ${b.dataset.st}`, "success"); viewRider(); } catch (err) { toast(err.message, "error"); } });
}

/* ---------------- admin ---------------- */
async function viewAdmin(tab = "orders") {
  if (!state.user || state.user.role !== "admin") { $("#app").innerHTML = emptyState("Admin access required"); return; }
  $("#app").innerHTML = `<div class="wrap"><h2 class="section-title">GovFood Admin</h2>
    <div class="row mb">${["orders", "users", "riders", "products", "messages", "fees", "ministry"].map(t =>
      `<button class="btn btn-sm ${t === tab ? "btn-primary" : "btn-outline"}" data-tab="${t}">${t[0].toUpperCase() + t.slice(1)}</button>`).join("")}</div>
    <div id="admin-body">${loading()}</div></div>`;
  $$("[data-tab]").forEach(b => b.onclick = () => viewAdmin(b.dataset.tab));
  const body = $("#admin-body");
  if (tab === "orders") {
    const [orders, riders] = [await api("/admin/orders"), await api("/admin/riders")];
    const avail = riders.filter(r => r.verified && r.active);
    body.innerHTML = `<div class="card table-scroll"><table class="table"><tr><th>Ref</th><th>Status</th><th>Items</th><th>kg</th><th>Amount</th><th>Fee(15%)</th><th>Pay</th><th>Buyer</th><th>Rider / assign</th></tr>
      ${orders.map(o => `<tr><td><b>${o.reference}</b></td><td>${statusPill(o.status)}</td>
        <td class="small">${o.items.map(i => esc(i.name) + " " + kg(i.qty) + "kg").join(", ")}</td>
        <td>${kg(o.total_kg)}</td><td>${GHS(o.amount)}</td><td>${GHS(o.sales_fee)}</td><td>${o.payment_method}</td>
        <td class="small">${esc(o.buyer.name)}<br>${o.buyer.phone}</td>
        <td>${o.rider ? esc(o.rider.name) : (o.status === "pending_payment" ? '<span class="pill warn">awaiting payment</span>' : (["paid"].includes(o.status) ?
          `<select data-assign="${o.reference}"><option value="">Assign rider…</option>${avail.map(r => `<option value="${r.id}">${esc(r.name)}</option>`).join("")}</select>` : "—"))}</td></tr>`).join("")}</table></div>`;
    $$("[data-assign]").forEach(sel => sel.onchange = async () => {
      if (!sel.value) return;
      try { const r = await api(`/admin/orders/${sel.dataset.assign}/assign`, { method: "POST", body: { rider_id: +sel.value } });
        toast(`Assigned to ${r.rider}`, "success"); viewAdmin("orders"); } catch (err) { toast(err.message, "error"); } });
  }
  if (tab === "users") {
    const users = await api("/admin/users");
    body.innerHTML = `<div class="card table-scroll"><table class="table"><tr><th>Name</th><th>Email</th><th>Phone</th><th>Employer</th><th>Work ID</th><th>Status</th><th>Credit (limit/used)</th><th>Actions</th></tr>
      ${users.map(u => `<tr><td>${esc(u.full_name)}</td><td>${esc(u.email)}</td><td>${u.phone}</td><td>${esc(u.employer)}</td><td>${esc(u.work_id)}</td>
        <td>${u.verified ? '<span class="pill ok">verified</span>' : '<span class="pill warn">unverified</span>'}</td>
        <td>${GHS(u.credit_limit)} / ${GHS(u.credit_used)}</td>
        <td class="row">${u.verified ? "" : `<button class="btn btn-primary btn-sm" data-verify="${u.id}">Verify + GH₵500</button>`}
          <button class="btn btn-outline btn-sm" data-credit="${u.id}" data-name="${esc(u.full_name)}">Set credit</button></td></tr>`).join("")}</table></div>`;
    $$("[data-verify]").forEach(b => b.onclick = async () => { try { await api(`/admin/users/${b.dataset.verify}/verify`, { method: "POST" }); toast("Verified + credit granted", "success"); viewAdmin("users"); } catch (e) { toast(e.message, "error"); } });
    $$("[data-credit]").forEach(b => b.onclick = () => { const v = prompt(`Credit limit for ${b.dataset.name}:`, "500");
      if (v) api(`/admin/credit`, { method: "POST", body: { user_id: +b.dataset.credit, limit: +v } }).then(() => { toast("Credit updated"); viewAdmin("users"); }).catch(e => toast(e.message, "error")); });
  }
  if (tab === "riders") {
    const riders = await api("/admin/riders");
    body.innerHTML = `<div class="card table-scroll"><table class="table"><tr><th>Photo</th><th>Name</th><th>Phone</th><th>DL</th><th>Plate</th><th>Status</th><th>Actions</th></tr>
      ${riders.map(r => `<tr><td>${r.photo ? `<img class="rider-photo" src="${r.photo}">` : "—"}</td><td>${esc(r.name)}</td><td>${r.phone}</td>
        <td>${esc(r.dl_number)}</td><td>${esc(r.plate)}</td><td>${r.verified ? '<span class="pill ok">verified</span>' : '<span class="pill warn">pending</span>'} ${r.active ? "" : '<span class="pill bad">off</span>'}</td>
        <td class="row">${r.verified ? "" : `<button class="btn btn-primary btn-sm" data-rverify="${r.id}">Verify</button>`}
        <button class="btn btn-outline btn-sm" data-rtoggle="${r.id}">${r.active ? "Deactivate" : "Activate"}</button></td></tr>`).join("")}</table></div>`;
    $$("[data-rverify]").forEach(b => b.onclick = async () => { try { await api(`/admin/riders/${b.dataset.rverify}/verify`, { method: "POST" }); toast("Rider verified", "success"); viewAdmin("riders"); } catch (e) { toast(e.message, "error"); } });
    $$("[data-rtoggle]").forEach(b => b.onclick = async () => { await api(`/admin/riders/${b.dataset.rtoggle}/toggle`, { method: "POST" }); viewAdmin("riders"); });
  }
  if (tab === "products") {
    const prods = await api("/products");
    body.innerHTML = `<div class="card card-pad mb"><h4 class="mb">Add / update item (price per kg)</h4>
      <form id="prod-form" class="form-grid"><input type="hidden" name="product_id">
      <div class="field"><label>Name</label><input name="name" required></div>
      <div class="field"><label>Category</label><input name="category" value="Staples"></div>
      <div class="field"><label>Price GH₵/kg</label><input name="price" type="number" step="0.5" min="0.5" required></div>
      <div class="field"><label>Stock (kg)</label><input name="stock" type="number" step="1" min="0" required></div>
      <button class="btn btn-primary">Save item</button></form></div>
      <div class="card table-scroll"><table class="table"><tr><th>Name</th><th>Category</th><th>GH₵/kg</th><th>Stock</th><th></th></tr>
      ${prods.map(p => `<tr><td>${esc(p.name)}</td><td>${esc(p.category)}</td><td>${GHS(p.price)}</td><td>${kg(p.stock)}</td>
        <td class="row"><button class="btn btn-outline btn-sm" data-edit='${JSON.stringify(p)}'>Edit</button></td></tr>`).join("")}</table></div>`;
    $("#prod-form").onsubmit = async e => { e.preventDefault(); const fd = new FormData(e.target);
      const pid = fd.get("product_id");
      try { await api("/admin/products" + (pid ? "?product_id=" + pid : ""), { method: "POST",
          body: { name: fd.get("name"), category: fd.get("category"), price: +fd.get("price"), stock: +fd.get("stock") } });
        toast("Item saved", "success"); loadProducts().then(() => viewAdmin("products")); } catch (err) { toast(err.message, "error"); } };
    $$("[data-edit]").forEach(b => b.onclick = () => { const p = JSON.parse(b.dataset.edit); const f = $("#prod-form");
      f.product_id.value = p.id; f.name.value = p.name; f.category.value = p.category; f.price.value = p.price; f.stock.value = p.stock;
      f.scrollIntoView({ behavior: "smooth" }); });
  }
  if (tab === "messages") {
    const msgs = await api("/admin/messages");
    body.innerHTML = `<p class="muted small mb">All buyer↔rider communications (admin monitor)</p>
      <div class="chat-box" style="max-height:400px">${msgs.length ? msgs.map(m =>
        `<div class="chat-msg"><b class="small">${esc(m.sender)}</b> <span class="pill ${m.role === "user" ? "info" : "warn"}">${m.role}</span> ${esc(m.text)}<small>${esc(m.order)} · ${m.created_at.slice(5, 16)}</small></div>`).join("") : "No messages yet"}</div>`;
  }
  if (tab === "ministry") {
    const rep = await api("/admin/ministry-report");
    body.innerHTML = `<p class="muted small mb">Weekly invoice report per employer — week starting <b>${rep.week_start}</b> (for Ministry of Agriculture reconciliation & billing)</p>
      ${rep.rows.length ? rep.rows.map(r => `<div class="card card-pad mb"><div class="spread"><h4 style="margin:0">${esc(r.employer)}</h4><b>${GHS(r.amount)}</b></div>
        <div class="row small muted mt">${r.workers} worker(s) · ${r.orders} order(s) · ${kg(r.kg)}kg · fees ${GHS(r.fees)}</div>
        <div class="row small mt">${Object.entries(r.items).map(([n, q]) => `<span class="pill info">${esc(n)} ${kg(q)}kg</span>`).join("")}</div></div>`).join("") : emptyState("No orders this week yet")}`;
  }
  if (tab === "fees") {
    const st = await api("/admin/stats");
    body.innerHTML = `<div class="grid grid-3">
      <div class="card card-pad"><div class="small muted">Sales volume</div><b style="font-size:1.4rem">${GHS(st.gmv)}</b></div>
      <div class="card card-pad"><div class="small muted">Sales fees (15%)</div><b style="font-size:1.4rem;color:var(--green)">${GHS(st.sales_fees)}</b></div>
      <div class="card card-pad"><div class="small muted">Credit outstanding</div><b style="font-size:1.4rem;color:var(--red)">${GHS(st.credit_outstanding)}</b></div>
      <div class="card card-pad"><div class="small muted">Est. credit fees (15%)</div><b style="font-size:1.4rem;color:var(--green)">${GHS(st.credit_fees_est)}</b></div>
      <div class="card card-pad"><div class="small muted">Workers</div><b style="font-size:1.4rem">${st.users} (${st.verified_users} verified)</b></div>
      <div class="card card-pad"><div class="small muted">Riders</div><b style="font-size:1.4rem">${st.riders} (${st.verified_riders} verified)</b></div></div>
      <div class="card card-pad mt"><div class="spread"><div><b>Monthly credit settlement</b><div class="muted small">Deducts all outstanding credit for the month + records the 15% fee. Bank = linked account charge; Payroll = Ministry salary deduction.</div></div>
      <div class="row"><button class="btn btn-gold btn-sm" id="settle-btn">Settle (bank)</button>
      <button class="btn btn-navy btn-sm" id="settle-payroll-btn">Settle (payroll)</button></div></div></div>
      <div class="card card-pad mt"><div class="spread"><div><b>Ministry payroll export</b><div class="muted small">CSV deduction schedule for Ministry HR (worker, work ID, amounts).</div></div>
      <button class="btn btn-outline btn-sm" id="payroll-export-btn">Download CSV</button></div><pre id="payroll-out" class="small mt" style="white-space:pre-wrap;background:var(--bg);padding:.8rem;border-radius:10px;max-height:260px;overflow:auto;display:none"></pre></div>`;
    $("#settle-btn").onclick = async () => { if (!confirm("Deduct all outstanding credit + fees for this month from linked bank accounts?")) return;
      try { const r = await api("/admin/settle", { method: "POST" }); toast(`Settled ${r.settlements} workers: ${GHS(r.total)} + ${GHS(r.fees)} fees`, "success"); viewAdmin("fees"); } catch (e) { toast(e.message, "error"); } };
    $("#settle-payroll-btn").onclick = async () => { if (!confirm("Mark this month's credit for MINISTRY PAYROLL deduction (salary)?")) return;
      try { const r = await api("/admin/settle?channel=payroll", { method: "POST" }); toast(`Payroll settlement: ${r.settlements} workers`, "success"); viewAdmin("fees"); } catch (e) { toast(e.message, "error"); } };
    $("#payroll-export-btn").onclick = async () => {
      try { const r = await api("/admin/payroll-export"); const out = $("#payroll-out");
        out.style.display = ""; out.textContent = r.csv;
        const blob = new Blob([r.csv], { type: "text/csv" }); const a = document.createElement("a");
        a.href = URL.createObjectURL(blob); a.download = `payroll-${r.month}.csv`; a.click(); } catch (e) { toast(e.message, "error"); } };
  }
}

/* ---------------- instant payment (mock gateway) ---------------- */
async function viewPay(ref) {
  $("#app").innerHTML = loading("Preparing checkout…");
  let o; try { o = await api("/orders/" + ref); } catch (e) { $("#app").innerHTML = emptyState(e.message); return; }
  if (o.status === "paid") { location.hash = `#/order/${ref}`; return; }
  $("#app").innerHTML = `<div class="wrap" style="max-width:480px"><div class="card card-pad mt">
    <h3 class="section-title" style="font-size:1.2rem">GovFood Secure Checkout</h3>
    <div class="spread mt mb"><span class="muted">Amount payable</span><b style="font-size:1.5rem;color:var(--green)">${GHS(o.amount)}</b></div>
    <div class="card card-pad mb" style="box-shadow:none;border:1px solid var(--line)">
      ${o.bulk ? `<span class="pill info">Ministry bulk order</span>${o.note ? `<div class="muted small">${esc(o.note)}</div>` : ""}` : ""}
      ${o.items.map(i => `<div class="sum-row"><span>${esc(i.name)} × ${kg(i.qty)}kg</span><span>${GHS(i.line)}</span></div>`).join("")}
      <div class="sum-row"><span>Delivery fee</span><span>${GHS(o.delivery_fee || 0)}</span></div>
      <div class="sum-row total"><span>Total</span><span>${GHS(o.total ?? o.amount)}</span></div></div>
    <div class="pay-methods" id="pay-methods">
      <div class="pay-method sel" data-m="momo"><div><b>MoMo</b><div class="muted small">MTN · Telecel · AT — approve with PIN</div></div></div>
      <div class="pay-method" data-m="card"><div><b>Card</b><div class="muted small">Visa · Mastercard</div></div></div>
    </div>
    <button class="btn btn-primary btn-block mt" id="pay-btn">Pay ${GHS(o.amount)}</button>
    <button class="btn btn-outline btn-block mt" id="pay-cancel">Cancel order</button>
    <p class="muted small center mt">Demo gateway — add PAYSTACK_SECRET_KEY for live MoMo/card.</p></div></div>`;
  let method = "momo";
  $$("#pay-methods .pay-method").forEach(m => m.onclick = () => { method = m.dataset.m;
    $$("#pay-methods .pay-method").forEach(x => x.classList.toggle("sel", x === m)); });
  $("#pay-btn").onclick = async () => { const b = $("#pay-btn"); b.disabled = true; b.textContent = "Processing…";
    try { await api("/payments/confirm", { method: "POST", body: { reference: ref, method } });
      toast("Payment confirmed!", "success"); location.hash = `#/order/${ref}`; route();
    } catch (e) { toast(e.message, "error"); b.disabled = false; b.textContent = `Pay ${GHS(o.amount)}`; } };
  $("#pay-cancel").onclick = async () => { if (!confirm("Cancel this unpaid order? Stock is released.")) return;
    try { await api(`/orders/${ref}/cancel`, { method: "POST" }); toast("Order cancelled"); location.hash = "#/orders"; }
    catch (e) { toast(e.message, "error"); } };
}

/* ---------------- notifications ---------------- */
async function viewNotifications() {
  const list = await api("/notifications").catch(() => []);
  $("#app").innerHTML = `<div class="wrap" style="max-width:640px"><h2 class="section-title">Notifications</h2>
    <div class="grid" style="gap:.6rem">${list.length ? list.map(n => `<div class="card card-pad"><b>${esc(n.title)}</b><p class="small">${esc(n.body)}</p><div class="muted small">${n.created_at}</div></div>`).join("") : emptyState("No notifications yet")}</div></div>`;
}

/* ---------------- router ---------------- */
function setActiveNav(seg) { $$("#mainnav a").forEach(a => a.classList.toggle("active", a.dataset.nav === seg)); }
function route() {
  stopOrderPolling();
  const raw = (location.hash || "#/").slice(1);
  const [path] = raw.split("?");
  const seg = path.split("/")[1] || "home";
  setActiveNav(seg);
  window.scrollTo(0, 0);
  if (seg === "home" || seg === "") viewHome();
  else if (seg === "cart") viewCart();
  else if (seg === "orders") viewOrders();
  else if (seg === "order") viewOrder(path.split("/")[2]);
  else if (seg === "profile") viewProfile();
  else if (seg === "rider") viewRider();
  else if (seg === "admin") viewAdmin(path.split("/")[2] || "orders");
  else if (seg === "pay") viewPay(path.split("/")[2]);
  else if (seg === "notifications") viewNotifications();
  else $("#app").innerHTML = emptyState("Page not found");
}
(async function boot() {
  try {
    if (state.token) state.user = await api("/auth/me");
    await loadProducts();
  } catch { state.token = ""; localStorage.removeItem("gf_token"); }
  renderChrome(); route();
})();
window.addEventListener("hashchange", route);
