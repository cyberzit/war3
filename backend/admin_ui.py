"""Single-page Mongolian Web Admin Dashboard for MongolRanger (/admin)."""

ADMIN_HTML = """<!DOCTYPE html>
<html lang="mn">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MongolRanger Admin — Сервер Удирдлагын Самбар</title>
<style>
:root {
  --bg: #0b0f17;
  --panel: #131b2e;
  --panel2: #19233c;
  --border: #263554;
  --accent: #10b981;
  --accent-hover: #059669;
  --blue: #3b82f6;
  --danger: #ef4444;
  --warn: #f59e0b;
  --text: #f1f5f9;
  --muted: #94a3b8;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
}
.topbar {
  background: var(--panel);
  border-bottom: 1px solid var(--border);
  padding: 14px 28px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 18px;
  font-weight: 700;
}
.brand-badge {
  background: rgba(16, 185, 129, 0.15);
  color: var(--accent);
  border: 1px solid rgba(16, 185, 129, 0.4);
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
}
.container {
  max-width: 1240px;
  margin: 24px auto;
  padding: 0 20px;
}
.login-box {
  max-width: 420px;
  margin: 80px auto;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 28px;
}
.login-box h2 { margin-bottom: 8px; font-size: 20px; }
.login-box p { color: var(--muted); font-size: 13px; margin-bottom: 20px; }
.field { margin-bottom: 14px; }
.field label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 6px; }
.field input[type="text"], .field input[type="password"], .field input[type="file"] {
  width: 100%;
  padding: 10px 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 8px;
  font-size: 14px;
}
.btn {
  cursor: pointer;
  border: none;
  border-radius: 8px;
  padding: 10px 16px;
  font-weight: 600;
  font-size: 13px;
  transition: 0.15s;
}
.btn-primary { background: var(--accent); color: #04130d; }
.btn-primary:hover { background: var(--accent-hover); color: #fff; }
.btn-blue { background: var(--blue); color: #fff; }
.btn-danger { background: rgba(239,68,68,0.18); color: #fca5a5; border: 1px solid rgba(239,68,68,0.4); padding: 6px 12px; }
.btn-danger:hover { background: var(--danger); color: #fff; }
.btn-sm { padding: 6px 12px; font-size: 12px; }
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}
.stat-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px 20px;
}
.stat-card .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
.stat-card .val { font-size: 26px; font-weight: 700; margin-top: 6px; }
.tabs {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 12px;
}
.tab-btn {
  background: var(--panel);
  color: var(--muted);
  border: 1px solid var(--border);
  padding: 9px 18px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
}
.tab-btn.active {
  background: var(--blue);
  color: #fff;
  border-color: var(--blue);
}
.card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
}
.card h3 { font-size: 16px; margin-bottom: 6px; }
.card .sub { color: var(--muted); font-size: 13px; margin-bottom: 16px; }
.check-row {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  margin: 12px 0 16px;
}
.check-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  cursor: pointer;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
th, td {
  text-align: left;
  padding: 11px 12px;
  border-bottom: 1px solid var(--border);
}
th { color: var(--muted); font-weight: 600; font-size: 12px; text-transform: uppercase; }
.badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
}
.badge-green { background: rgba(16,185,129,0.16); color: #34d399; border: 1px solid rgba(16,185,129,0.35); }
.badge-blue { background: rgba(59,130,246,0.16); color: #60a5fa; border: 1px solid rgba(59,130,246,0.35); }
.badge-warn { background: rgba(245,158,11,0.16); color: #fbbf24; border: 1px solid rgba(245,158,11,0.35); }
.alert {
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  margin-bottom: 14px;
  display: none;
}
.alert-ok { background: rgba(16,185,129,0.15); border: 1px solid var(--accent); color: #6ee7b7; }
.alert-err { background: rgba(239,68,68,0.15); border: 1px solid var(--danger); color: #fca5a5; }
.progress-wrap {
  width: 100%;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  height: 10px;
  overflow: hidden;
  margin-top: 10px;
  display: none;
}
.progress-bar {
  height: 100%;
  background: var(--accent);
  width: 0%;
  transition: width 0.2s;
}
.dl-slot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 18px;
}
.dl-slot-card {
  background: var(--panel2);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px;
}
.dl-slot-card h4 { font-size: 15px; margin-bottom: 4px; }
.dl-slot-meta { font-size: 12px; color: var(--muted); margin-bottom: 12px; line-height: 1.5; }
.hidden { display: none !important; }
</style>
</head>
<body>

<div class="topbar">
  <div class="brand">
    <a href="/" style="display:flex;align-items:center;gap:10px;color:var(--text);text-decoration:none;">
      <svg width="32" height="32" viewBox="0 0 64 64" fill="none">
        <defs>
          <linearGradient id="ag" x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stop-color="#10b981"/>
            <stop offset="100%" stop-color="#2563eb"/>
          </linearGradient>
        </defs>
        <path d="M32 4L56 14V32C56 47 45 57 32 61C19 57 8 47 8 32V14L32 4Z" fill="url(#ag)" stroke="#f59e0b" stroke-width="2.5"/>
        <path d="M18 42V22L26 32L32 23L38 32L46 22V42H41V31L35 38H29L23 31V42H18Z" fill="#fff"/>
      </svg>
      <span>MongolRanger Admin</span>
    </a>
    <span class="brand-badge" id="srvVersion">v0.4.0 • W3GS 8051</span>
  </div>
  <div id="topActions" class="hidden" style="display:flex;gap:8px;align-items:center;">
    <a class="btn btn-sm" href="/" target="_blank" style="background:var(--panel2);color:var(--text);border:1px solid var(--border);text-decoration:none;">🌐 Вэбсайт харах</a>
    <button class="btn btn-sm btn-blue" onclick="refreshAll()">🔄 Шинэчлэх</button>
    <button class="btn btn-sm btn-danger" onclick="logoutAdmin()">Гарах</button>
  </div>
</div>

<!-- LOGIN VIEW -->
<div id="loginView" class="login-box">
  <h2>Админ Нэвтрэх</h2>
  <p>MongolRanger серверийн Татах файлууд, Газрын зураг (Map), Өрөө болон Тоглогчдын удирдлага</p>
  <div id="loginAlert" class="alert alert-err"></div>
  <form onsubmit="doAdminLogin(event)">
    <div class="field">
      <label>Нэвтрэх нэр</label>
      <input type="text" id="admUser" value="admin" required>
    </div>
    <div class="field">
      <label>Нууц үг</label>
      <input type="password" id="admPass" placeholder="Админ нууц үг..." required>
    </div>
    <button type="submit" class="btn btn-primary" style="width:100%">Нэвтрэх</button>
  </form>
</div>

<!-- DASHBOARD VIEW -->
<div id="dashView" class="container hidden">
  <div class="stats-grid">
    <div class="stat-card">
      <div class="label">Серверийн Төлөв</div>
      <div class="val" style="color:var(--accent)" id="stStatus">ONLINE</div>
    </div>
    <div class="stat-card">
      <div class="label">Татах Програм / Багц</div>
      <div class="val" id="stDownloads">0</div>
    </div>
    <div class="stat-card">
      <div class="label">Албан ёсны Map-ууд</div>
      <div class="val" id="stMaps">0</div>
    </div>
    <div class="stat-card">
      <div class="label">Идэвхтэй Өрөө (W3GS)</div>
      <div class="val" id="stRooms">0</div>
    </div>
    <div class="stat-card">
      <div class="label">Бүртгэлтэй Хэрэглэгч</div>
      <div class="val" id="stUsers">0</div>
    </div>
  </div>

  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('downloads', this)">📥 Татах Файлууд & Холбоос (Client / War3)</button>
    <button class="tab-btn" onclick="switchTab('maps', this)">🗺️ Газрын зураг (Maps & Auto-Patcher)</button>
    <button class="tab-btn" onclick="switchTab('rooms', this)">⚔️ Идэвхтэй Өрөөнүүд</button>
    <button class="tab-btn" onclick="switchTab('users', this)">👥 Хэрэглэгчид</button>
    <button class="tab-btn" onclick="switchTab('settings', this)">⚙️ Админ Тохиргоо</button>
  </div>

  <div id="globalAlert" class="alert"></div>

  <!-- TAB 0: DOWNLOADS MANAGER -->
  <div id="tab-downloads">
    <div class="card">
      <h3>📥 Нүүр Хуудасны Татах Товчнуудын Удирдлага (mongolranger.com)</h3>
      <div class="sub">
        Та эндээс <b>MongolRanger Client (Windows x86/x64)</b>, <b>macOS Client</b> болон <b>Warcraft III 1.26a + DotA Багц</b>-ийн
        файлыг сервер рүү шууд <b>Upload</b> хийх эсвэл <b>Гадны татах линк (Google Drive, Mega, MediaFire, Direct CDN)</b> холбох боломжтой.
        Хадгалмагц нүүр хуудасны татах товчнууд автоматаар шинэчлэгдэнэ!
      </div>
      <div class="dl-slot-grid" id="downloadsAdminGrid"></div>
    </div>
  </div>

  <!-- TAB 1: MAPS -->
  <div id="tab-maps" class="hidden">
    <div class="card">
      <h3>➕ Шинэ Map Оруулах & Автоматаар Хөрвүүлэх (.w3x / .w3m)</h3>
      <div class="sub">
        Та <b>DotA 6.74c LoD</b>, <b>DotA 6.83d</b>, <b>DotA 6.85m LoD</b> зэрэг ямар ч map оруулахад сервер автоматаар
        <b>-cam / -zoom</b> камер холдуулах команд болон <b>Crash Reconnect</b> дэмжлэг нэмж, W3GS CRC/SHA1 тооцоолоод
        өндөр хурдны HTTPS татах санд байршуулна (тоглогчид 20-30 минут хүлээхгүй, 2-3 секундэд татна).
      </div>
      <form onsubmit="uploadMap(event)">
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 14px;">
          <div class="field">
            <label>Map файл сонгох (.w3x / .w3m)</label>
            <input type="file" id="mapFile" accept=".w3x,.w3m" required>
          </div>
          <div class="field">
            <label>Харагдах нэр (хоосон орхивол файлын нэрээр)</label>
            <input type="text" id="mapTitle" placeholder="Жнь: DotA v6.74c LoD (-cam)">
          </div>
        </div>
        <div class="check-row">
          <label class="check-label">
            <input type="checkbox" id="chkCam" checked>
            <span><b>-cam / -zoom</b> камер холдуулах команд автоматаар нэмэх (6.74c зэрэг map-д)</span>
          </label>
          <label class="check-label">
            <input type="checkbox" id="chkRec" checked>
            <span><b>Crash Reconnect & Save-Game</b> дэмжлэг автоматаар идэвхжүүлэх</span>
          </label>
          <label class="check-label">
            <input type="checkbox" id="chkDefault">
            <span>Үндсэн (Default) Map болгох</span>
          </label>
        </div>
        <button type="submit" class="btn btn-primary" id="btnUpload">🚀 Map Оруулах & Автоматаар Хөрвүүлэх</button>
        <div class="progress-wrap" id="upProgWrap"><div class="progress-bar" id="upProgBar"></div></div>
      </form>
    </div>

    <div class="card">
      <h3>📦 Сервер дээрх Албан ёсны Map-ууд (HTTPS Хурдан Татах Сан)</h3>
      <div class="sub">Тоглогчийн MongolRanger програм тоглоом эхлэхээс өмнө эндээс map-аа 2 секундэд автоматаар татаж авна.</div>
      <table>
        <thead>
          <tr>
            <th>Нэр / Гарчиг</th>
            <th>Файлын нэр (Maps\\Download\\)</th>
            <th>Хэмжээ</th>
            <th>Онцлог</th>
            <th>W3GS CRC / SHA1</th>
            <th>Үйлдэл</th>
          </tr>
        </thead>
        <tbody id="mapsTableBody"></tbody>
      </table>
    </div>
  </div>

  <!-- TAB 2: ROOMS -->
  <div id="tab-rooms" class="hidden">
    <div class="card">
      <h3>⚔️ Одоо Ажиллаж Байгаа Өрөөнүүд (W3GS Port 8051)</h3>
      <div class="sub">Ямар ч тоглогч (Host ороод) гацаж гарсан үед сервер тоглоомыг унагахгүйгээр WAITING горимд шилжүүлж буцааж оруулна.</div>
      <table>
        <thead>
          <tr>
            <th>Өрөөний нэр</th>
            <th>Host</th>
            <th>Map</th>
            <th>Төлөв (Phase)</th>
            <th>Тоглогчид (W3GS)</th>
            <th>Үйлдэл</th>
          </tr>
        </thead>
        <tbody id="roomsTableBody"></tbody>
      </table>
    </div>
  </div>

  <!-- TAB 3: USERS -->
  <div id="tab-users" class="hidden">
    <div class="card">
      <h3>👥 Бүртгэлтэй Тоглогчид</h3>
      <div class="sub">Тоглогч бүр өөрийн бүртгүүлсэн нэрээрээ (zev, zevb гэх мэт түгжээгүй) тоглоом болон Reconnect системд оролцоно.</div>
      <table>
        <thead>
          <tr>
            <th>Хэрэглэгчийн нэр</th>
            <th>Бүртгүүлсэн огноо</th>
            <th>Одоогийн өрөө</th>
            <th>Үйлдэл</th>
          </tr>
        </thead>
        <tbody id="usersTableBody"></tbody>
      </table>
    </div>
  </div>

  <!-- TAB 4: SETTINGS -->
  <div id="tab-settings" class="hidden">
    <div class="card" style="max-width:520px;">
      <h3>🔑 Админ Нууц Үг Солих</h3>
      <div class="sub">mongolranger.com/admin удирдлагын самбарын нэвтрэх нууц үгийг шинэчлэх</div>
      <form onsubmit="changeAdminPassword(event)">
        <div class="field">
          <label>Шинэ нууц үг (хамгийн багадаа 8 тэмдэгт)</label>
          <input type="password" id="newAdmPass" minlength="8" required>
        </div>
        <button type="submit" class="btn btn-primary">Нууц үг хадгалах</button>
      </form>
    </div>
  </div>
</div>

<script>
let adminToken = localStorage.getItem('mr_admin_token') || '';

function showAlert(msg, isErr=false) {
  const el = document.getElementById('globalAlert');
  el.className = 'alert ' + (isErr ? 'alert-err' : 'alert-ok');
  el.textContent = msg;
  el.style.display = 'block';
  setTimeout(() => { el.style.display = 'none'; }, 6000);
}

async function apiFetch(path, opts={}) {
  const headers = opts.headers || {};
  if (adminToken) headers['Authorization'] = 'Bearer ' + adminToken;
  const res = await fetch(path, { ...opts, headers });
  if (res.status === 401) {
    logoutAdmin();
    throw new Error('Нэвтрэх эрх дууссан байна.');
  }
  return res;
}

async function doAdminLogin(e) {
  e.preventDefault();
  const username = document.getElementById('admUser').value.trim();
  const password = document.getElementById('admPass').value;
  const alertEl = document.getElementById('loginAlert');
  alertEl.style.display = 'none';
  try {
    const res = await fetch('/api/admin/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username, password})
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Нэвтрэхэд алдаа гарлаа');
    adminToken = data.token;
    localStorage.setItem('mr_admin_token', adminToken);
    document.getElementById('admPass').value = '';
    enterDashboard();
  } catch (err) {
    alertEl.textContent = err.message;
    alertEl.style.display = 'block';
  }
}

function logoutAdmin() {
  adminToken = '';
  localStorage.removeItem('mr_admin_token');
  document.getElementById('dashView').classList.add('hidden');
  document.getElementById('topActions').classList.add('hidden');
  document.getElementById('loginView').classList.remove('hidden');
}

function switchTab(name, btn) {
  ['downloads', 'maps', 'rooms', 'users', 'settings'].forEach(t => {
    document.getElementById('tab-' + t).classList.toggle('hidden', t !== name);
  });
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

async function enterDashboard() {
  document.getElementById('loginView').classList.add('hidden');
  document.getElementById('dashView').classList.remove('hidden');
  document.getElementById('topActions').classList.remove('hidden');
  await refreshAll();
}

async function refreshAll() {
  try {
    const res = await apiFetch('/api/admin/overview');
    const data = await res.json();
    const dls = data.downloads || [];
    document.getElementById('stDownloads').textContent = dls.filter(d => d.ready).length + '/' + dls.length;
    document.getElementById('stMaps').textContent = data.maps.length;
    document.getElementById('stRooms').textContent = data.rooms.length;
    document.getElementById('stUsers').textContent = data.users.length;
    document.getElementById('srvVersion').textContent = `v${data.version} • W3GS ${data.w3gs_port}`;

    // Render Downloads Slots
    const dg = document.getElementById('downloadsAdminGrid');
    dg.innerHTML = '';
    dls.forEach(d => {
      const card = document.createElement('div');
      card.className = 'dl-slot-card';
      const statusBadge = d.ready
        ? (d.is_r2
            ? '<span class="badge badge-green">☁️ Cloudflare R2 CDN Идэвхтэй</span>'
            : (d.is_external
                ? '<span class="badge badge-blue">🔗 Гадны Линк Идэвхтэй</span>'
                : '<span class="badge badge-green">✅ Сервер Файл Бэлэн</span>'))
        : '<span class="badge badge-warn">⏳ Тохируулаагүй</span>';
      card.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:6px;">
          <h4>${esc(d.title)}</h4>
          ${statusBadge}
        </div>
        <div class="dl-slot-meta">
          Платформ: <b>${esc(d.platform)}</b> • Slot ID: <code>${esc(d.slot)}</code><br>
          Одоогийн татах зам: <a href="${esc(d.download_url)}" target="_blank" style="color:var(--accent);word-break:break-all;">${esc(d.download_url)}</a>
          (${esc(d.size_label)})
        </div>

        <div style="border-top:1px solid var(--border);padding-top:12px;margin-top:8px;">
          <div style="font-size:12px;font-weight:700;color:var(--accent);margin-bottom:8px;">1️⃣ СОНГОЛТ А: Файл шууд Upload хийх (Cloudflare R2 эсвэл Монгол Сервер)</div>
          <input type="file" id="dlFile_${esc(d.slot)}" style="width:100%;font-size:12px;background:var(--bg);padding:6px;border:1px solid var(--border);border-radius:6px;color:var(--text);margin-bottom:8px;">
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
            <button type="button" class="btn btn-sm btn-primary" style="flex:1;" id="dlBtnR2_${esc(d.slot)}" onclick="uploadDownloadSlotR2('${esc(d.slot)}')">☁️ Cloudflare R2 руу Upload (Том файл 1GB+)</button>
            <button type="button" class="btn btn-sm btn-blue" id="dlBtnUp_${esc(d.slot)}" onclick="uploadDownloadSlot('${esc(d.slot)}')">⬆️ Монгол Серверт (Жижиг файл)</button>
          </div>
          <div class="progress-wrap" id="dlProgWrap_${esc(d.slot)}"><div class="progress-bar" id="dlProgBar_${esc(d.slot)}"></div></div>
        </div>

        <div style="border-top:1px solid var(--border);padding-top:12px;margin-top:12px;">
          <div style="font-size:12px;font-weight:700;color:#60a5fa;margin-bottom:8px;">2️⃣ СОНГОЛТ Б: Татах зам (r2:// эсвэл Гадны линк) & Мэдээлэл засах</div>
          <div class="field" style="margin-bottom:8px;">
            <label style="font-size:11px;">Cloudflare R2 зам (r2://...) эсвэл Гадны URL (хоосон бол Монгол сервер дээрх файлыг ашиглана)</label>
            <input type="text" id="dlUrl_${esc(d.slot)}" value="${esc(d.external_url || '')}" placeholder="r2://mongolranger/downloads/... эсвэл https://...">
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:10px;">
            <div class="field" style="margin-bottom:0;">
              <label style="font-size:11px;">Хувилбар</label>
              <input type="text" id="dlVer_${esc(d.slot)}" value="${esc(d.version || 'v1.0')}">
            </div>
            <div class="field" style="margin-bottom:0;">
              <label style="font-size:11px;">Хэмжээ</label>
              <input type="text" id="dlSize_${esc(d.slot)}" value="${esc(d.size_label || '')}" placeholder="Жнь: 1.2 GB">
            </div>
            <div class="field" style="margin-bottom:0;">
              <label style="font-size:11px;">Товчны бичиг</label>
              <input type="text" id="dlBtnTxt_${esc(d.slot)}" value="${esc(d.button_text || 'Татах')}">
            </div>
          </div>
          <button type="button" class="btn btn-sm btn-blue" style="width:100%" onclick="saveDownloadLink('${esc(d.slot)}')">💾 Линк & Мэдээлэл Хадгалах (Товч Автоматаар Холбогдоно)</button>
        </div>
      `;
      dg.appendChild(card);
    });

    // Render Maps
    const mb = document.getElementById('mapsTableBody');
    mb.innerHTML = '';
    data.maps.forEach(m => {
      const tr = document.createElement('tr');
      const mbSize = (m.file_size / (1024 * 1024)).toFixed(2) + ' MB';
      const badges = [];
      if (m.is_default) badges.push('<span class="badge badge-warn">⭐ Default</span>');
      if (m.has_cam) badges.push('<span class="badge badge-green">✅ -cam / -zoom</span>');
      if (m.has_reconnect) badges.push('<span class="badge badge-blue">✅ Reconnect</span>');
      tr.innerHTML = `
        <td><b>${esc(m.title)}</b></td>
        <td><code>${esc(m.filename)}</code></td>
        <td>${mbSize}</td>
        <td>${badges.join(' ')}</td>
        <td><code style="font-size:11px;color:var(--muted)">CRC: ${esc(m.crc_hex)}<br>SHA1: ${esc(m.sha1_hex.slice(0, 16))}...</code></td>
        <td style="display:flex;gap:6px;">
          <a class="btn btn-sm btn-blue" href="/api/maps/${m.id}/download" style="text-decoration:none;">⬇️ Татах</a>
          ${!m.is_default ? `<button class="btn btn-sm btn-primary" onclick="setDefaultMap('${m.id}')">Default</button>` : ''}
          <button class="btn btn-sm btn-danger" onclick="deleteMap('${m.id}', '${esc(m.filename)}')">Устгах</button>
        </td>
      `;
      mb.appendChild(tr);
    });

    // Render Rooms
    const rb = document.getElementById('roomsTableBody');
    rb.innerHTML = '';
    if (data.rooms.length === 0) {
      rb.innerHTML = '<tr><td colspan="6" style="color:var(--muted);text-align:center;">Одоогоор идэвхтэй өрөө алга байна.</td></tr>';
    } else {
      data.rooms.forEach(r => {
        const tr = document.createElement('tr');
        const pList = (r.w3gs_players || []).map(p => `${esc(p.name)} (pid:${p.pid}${p.connected ? '🟢' : '🔴'})`).join(', ') || `${r.players}/${r.capacity}`;
        tr.innerHTML = `
          <td><b>${esc(r.name)}</b></td>
          <td>${esc(r.host)}</td>
          <td><code>${esc(r.map_name)}</code></td>
          <td><span class="badge badge-blue">${esc(r.phase)}</span></td>
          <td>${pList}</td>
          <td><button class="btn btn-sm btn-danger" onclick="closeRoom('${r.id}')">Өрөө хаах</button></td>
        `;
        rb.appendChild(tr);
      });
    }

    // Render Users
    const ub = document.getElementById('usersTableBody');
    ub.innerHTML = '';
    data.users.forEach(u => {
      const tr = document.createElement('tr');
      const dt = new Date(u.created * 1000).toLocaleString();
      tr.innerHTML = `
        <td><b>${esc(u.name)}</b></td>
        <td>${dt}</td>
        <td>${u.room_name ? `<span class="badge badge-green">${esc(u.room_name)}</span>` : '<span style="color:var(--muted)">-</span>'}</td>
        <td><button class="btn btn-sm btn-danger" onclick="deleteUser('${u.id}', '${esc(u.name)}')">Устгах</button></td>
      `;
      ub.appendChild(tr);
    });
  } catch (err) {
    console.error(err);
  }
}

async function uploadDownloadSlotR2(slot) {
  const fIn = document.getElementById('dlFile_' + slot);
  if (!fIn || !fIn.files.length) {
    showAlert('Cloudflare R2 руу Upload хийх файлаа эхлээд сонгоно уу!', true);
    return;
  }
  const file = fIn.files[0];
  const ver = (document.getElementById('dlVer_' + slot)?.value || '').trim();
  const btn = document.getElementById('dlBtnR2_' + slot);
  const progWrap = document.getElementById('dlProgWrap_' + slot);
  const progBar = document.getElementById('dlProgBar_' + slot);
  btn.disabled = true;
  btn.textContent = '⏳ R2 бэлтгэж байна...';
  progWrap.style.display = 'block';
  progBar.style.width = '5%';

  try {
    const ctype = file.type || 'application/octet-stream';
    const preRes = await apiFetch(`/api/admin/downloads/${encodeURIComponent(slot)}/r2-presign`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ filename: file.name, content_type: ctype })
    });
    const ticket = await preRes.json();
    if (!preRes.ok || !ticket.upload_url) throw new Error(ticket.detail || 'R2 Presign алдаа гарлаа');

    await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('PUT', ticket.upload_url);
      xhr.setRequestHeader('Content-Type', ctype);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const pct = Math.max(5, Math.round((e.loaded / e.total) * 100));
          progBar.style.width = pct + '%';
          btn.textContent = `☁️ R2 Upload: ${pct}%`;
        }
      };
      xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error('R2 PUT HTTP ' + xhr.status)));
      xhr.onerror = () => reject(new Error('R2 сүлжээний алдаа'));
      xhr.send(file);
    });

    const finRes = await apiFetch(`/api/admin/downloads/${encodeURIComponent(slot)}/r2-complete`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        r2_key: ticket.r2_key,
        filename: ticket.filename,
        size_bytes: file.size,
        version: ver
      })
    });
    const data = await finRes.json();
    if (!finRes.ok) throw new Error(data.detail || 'R2 бүртгэхэд алдаа гарлаа');
    progBar.style.width = '100%';
    showAlert(`✅ "${data.download.title}" Cloudflare R2 CDN рүү шууд амжилттай хуулагдаж, татах товч холбогдлоо!`);
    fIn.value = '';
    await refreshAll();
  } catch (err) {
    showAlert(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = '☁️ Cloudflare R2 руу Upload (Том файл 1GB+)';
    setTimeout(() => { progWrap.style.display = 'none'; progBar.style.width = '0%'; }, 1000);
  }
}

async function uploadDownloadSlot(slot) {
  const fIn = document.getElementById('dlFile_' + slot);
  if (!fIn || !fIn.files.length) {
    showAlert('Upload хийх файлаа эхлээд сонгоно уу!', true);
    return;
  }
  const file = fIn.files[0];
  const ver = (document.getElementById('dlVer_' + slot)?.value || '').trim();
  const btn = document.getElementById('dlBtnUp_' + slot);
  const progWrap = document.getElementById('dlProgWrap_' + slot);
  const progBar = document.getElementById('dlProgBar_' + slot);
  btn.disabled = true;
  btn.textContent = '⏳ Хуулж байна...';
  progWrap.style.display = 'block';
  progBar.style.width = '40%';

  try {
    const qs = new URLSearchParams({ filename: file.name, version: ver });
    const buf = await file.arrayBuffer();
    progBar.style.width = '80%';
    const res = await apiFetch(`/api/admin/downloads/${encodeURIComponent(slot)}/upload?` + qs.toString(), {
      method: 'POST',
      headers: {'Content-Type': 'application/octet-stream'},
      body: buf
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Файл оруулахад алдаа гарлаа');
    progBar.style.width = '100%';
    showAlert(`✅ "${data.download.title}" файл Монгол серверт амжилттай хуулагдаж, нүүр хуудасны татах товч автоматаар холбогдлоо!`);
    fIn.value = '';
    await refreshAll();
  } catch (err) {
    showAlert(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = '⬆️ Монгол Серверт (Жижиг файл)';
    setTimeout(() => { progWrap.style.display = 'none'; progBar.style.width = '0%'; }, 800);
  }
}

async function saveDownloadLink(slot) {
  const external_url = (document.getElementById('dlUrl_' + slot)?.value || '').trim();
  const version = (document.getElementById('dlVer_' + slot)?.value || '').trim();
  const size_label = (document.getElementById('dlSize_' + slot)?.value || '').trim();
  const button_text = (document.getElementById('dlBtnTxt_' + slot)?.value || '').trim();
  try {
    const res = await apiFetch(`/api/admin/downloads/${encodeURIComponent(slot)}/link`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ external_url, version, size_label, button_text })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Хадгалахад алдаа гарлаа');
    showAlert(`✅ "${data.download.title}" татах товчны холбоос болон мэдээлэл амжилттай шинэчлэгдлээ!`);
    await refreshAll();
  } catch (err) {
    showAlert(err.message, true);
  }
}

async function uploadMap(e) {
  e.preventDefault();
  const fileInput = document.getElementById('mapFile');
  if (!fileInput.files.length) return;
  const file = fileInput.files[0];
  const title = document.getElementById('mapTitle').value.trim();
  const enableCam = document.getElementById('chkCam').checked ? '1' : '0';
  const enableRec = document.getElementById('chkRec').checked ? '1' : '0';
  const isDefault = document.getElementById('chkDefault').checked ? '1' : '0';

  const btn = document.getElementById('btnUpload');
  const progWrap = document.getElementById('upProgWrap');
  const progBar = document.getElementById('upProgBar');
  btn.disabled = true;
  btn.textContent = '⏳ Хөрвүүлж, сервер рүү хуулж байна...';
  progWrap.style.display = 'block';
  progBar.style.width = '35%';

  try {
    const qs = new URLSearchParams({
      filename: file.name,
      title: title,
      enable_cam: enableCam,
      enable_reconnect: enableRec,
      is_default: isDefault
    });
    const buf = await file.arrayBuffer();
    progBar.style.width = '75%';
    const res = await apiFetch('/api/admin/maps?' + qs.toString(), {
      method: 'POST',
      headers: {'Content-Type': 'application/octet-stream'},
      body: buf
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Map оруулахад алдаа гарлаа');
    progBar.style.width = '100%';
    showAlert(`✅ "${data.map.title}" (${data.map.filename}) амжилттай хөрвүүлэгдэж серверт нэмэгдлээ! (-cam: ${data.map.has_cam ? 'Тийм' : 'Үгүй'})`);
    fileInput.value = '';
    document.getElementById('mapTitle').value = '';
    await refreshAll();
  } catch (err) {
    showAlert(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = '🚀 Map Оруулах & Автоматаар Хөрвүүлэх';
    setTimeout(() => { progWrap.style.display = 'none'; progBar.style.width = '0%'; }, 800);
  }
}

async function setDefaultMap(id) {
  const res = await apiFetch(`/api/admin/maps/${id}/default`, {method: 'POST'});
  if (res.ok) {
    showAlert('Үндсэн (Default) Map шинэчлэгдлээ.');
    await refreshAll();
  }
}

async function deleteMap(id, name) {
  if (!confirm(`"${name}" газрын зургийг серверээс устгах уу?`)) return;
  const res = await apiFetch(`/api/admin/maps/${id}`, {method: 'DELETE'});
  if (res.ok) {
    showAlert(`"${name}" устгагдлаа.`);
    await refreshAll();
  } else {
    const d = await res.json();
    showAlert(d.detail || 'Устгаж чадсангүй', true);
  }
}

async function closeRoom(rid) {
  if (!confirm('Энэ өрөөг албадан хаах уу?')) return;
  const res = await apiFetch(`/api/admin/rooms/${rid}`, {method: 'DELETE'});
  if (res.ok) {
    showAlert('Өрөө хаагдлаа.');
    await refreshAll();
  }
}

async function deleteUser(uid, name) {
  if (!confirm(`"${name}" хэрэглэгчийг устгах уу?`)) return;
  const res = await apiFetch(`/api/admin/users/${uid}`, {method: 'DELETE'});
  if (res.ok) {
    showAlert(`"${name}" хэрэглэгч устгагдлаа.`);
    await refreshAll();
  }
}

async function changeAdminPassword(e) {
  e.preventDefault();
  const newPass = document.getElementById('newAdmPass').value;
  const res = await apiFetch('/api/admin/password', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({password: newPass})
  });
  const data = await res.json();
  if (res.ok) {
    document.getElementById('newAdmPass').value = '';
    showAlert('✅ Админ нууц үг амжилттай солигдлоо!');
  } else {
    showAlert(data.detail || 'Алдаа гарлаа', true);
  }
}

function esc(s) {
  return String(s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

if (adminToken) {
  enterDashboard();
}
</script>
</body>
</html>
"""
