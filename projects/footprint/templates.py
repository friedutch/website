from projects.shared_styles import BASE_CSS, THEME_JS, EARLY_THEME

FOOTPRINT_PAGE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
""" + EARLY_THEME + """
<title>Footprint — Friedutch+</title>
<style>""" + BASE_CSS + """
body { max-width:720px; margin:0 auto; padding:0 24px 100px; }

.top-bar-unified {
  position:sticky; top:0; z-index:100;
  display:flex; align-items:center; justify-content:space-between;
  padding:12px 0; margin-bottom:32px;
  backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px);
  background:rgba(15,15,26,0.6);
  border-bottom:1px solid rgba(255,255,255,0.07);
}
[data-theme="light"] .top-bar-unified {
  background:rgba(240,240,255,0.7);
  border-bottom:1px solid rgba(0,0,0,0.07);
}
.app-brand { display:flex; align-items:center; gap:10px; }
.brand-icon { width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,var(--purple),var(--blue));display:flex;align-items:center;justify-content:center;font-size:18px; }
.brand-name { font-size:15px; font-weight:900; }
.brand-sub  { font-size:10px; color:var(--text3); font-weight:600; }
.top-right  { display:flex; align-items:center; gap:8px; }
.top-icon-btn { width:36px;height:36px;border-radius:10px;border:2px solid var(--border);background:var(--surface2);display:flex;align-items:center;justify-content:center;font-size:16px;cursor:pointer;font-family:'Nunito',sans-serif;font-weight:800;color:var(--text2);transition:all 0.2s;text-decoration:none; }
.top-icon-btn:hover { border-color:var(--purple); }

h1 { font-size:36px; font-weight:900; margin-bottom:8px; }
.page-sub { font-size:14px; color:var(--text2); font-weight:600; margin-bottom:28px; }

/* Metrics */
.metrics { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:24px; }
.metric { background:var(--surface); border:2px solid var(--border); border-radius:var(--radius-sm); padding:14px 16px; }
.metric-label { font-size:10px;font-weight:800;letter-spacing:0.1em;text-transform:uppercase;color:var(--text3);margin-bottom:6px; }
.metric-val { font-size:28px; font-weight:900; }
.metric-val.danger { color:#FF4444; }
.metric-val.warn   { color:var(--orange); }
.metric-val.ok     { color:var(--green); }
.metric-val.info   { font-size:13px; color:var(--cyan); padding-top:7px; font-weight:800; }

/* Scan zone */
.scan-zone-title { font-size:12px;font-weight:900;letter-spacing:0.1em;text-transform:uppercase;color:var(--text3);margin-bottom:14px; }
.scan-row { display:flex; gap:10px; }
.scan-hint { font-size:12px;font-weight:600;color:var(--text3);margin-top:10px; }
.scan-hint span { color:var(--cyan); }

/* Tabs */
.tabs { display:flex; gap:6px; margin-bottom:20px; flex-wrap:wrap; }
.tab-btn { padding:10px 18px; border-radius:var(--radius-xs); border:2px solid var(--border); background:var(--surface2); color:var(--text2); font-family:'Nunito',sans-serif; font-size:13px; font-weight:800; cursor:pointer; transition:all 0.2s; }
.tab-btn.active { background:var(--surface); border-color:rgba(120,75,160,0.4); color:var(--text); }
.tab-count { font-size:10px;font-weight:900;padding:1px 7px;border-radius:50px;margin-left:4px;background:rgba(120,75,160,0.15);color:var(--purple); }
.tab-btn.active .tab-count { background:linear-gradient(135deg,rgba(255,60,172,0.2),rgba(120,75,160,0.2));color:var(--pink); }

/* Tab panels */
.tab-panel { display:none; }
.tab-panel.active { display:block; }

/* Filter chips */
.filter-row { display:flex; gap:8px; margin-bottom:16px; flex-wrap:wrap; align-items:center; }
.filter-chip { font-size:12px;font-weight:800;padding:6px 14px;border-radius:50px;border:2px solid var(--border);background:var(--surface2);color:var(--text2);cursor:pointer;transition:all 0.2s; }
.filter-chip.active { border-color:rgba(120,75,160,0.5);color:var(--purple);background:rgba(120,75,160,0.1); }
.filter-chip:hover  { border-color:var(--purple);color:var(--purple); }
.filter-search { flex:1;min-width:140px;background:var(--surface2);border:2px solid var(--border);border-radius:var(--radius-xs);color:var(--text);font-family:'Nunito',sans-serif;font-size:13px;font-weight:600;padding:8px 14px;outline:none;transition:all 0.2s; }
.filter-search:focus { border-color:var(--purple); }
.filter-search::placeholder { color:var(--text3); }

/* Breach cards */
.breach-card { background:var(--card);border:2px solid var(--border);border-radius:var(--radius-sm);padding:14px 16px;margin-bottom:10px;display:flex;align-items:flex-start;gap:14px;transition:all 0.2s; }
.breach-card:hover { box-shadow:0 4px 20px var(--shadow); }
.breach-card.sev-high   { border-left:3px solid #FF4444; }
.breach-card.sev-medium { border-left:3px solid var(--orange); }
.breach-card.sev-low    { border-left:3px solid var(--yellow); }
.breach-icon { width:44px;height:44px;border-radius:14px;background:linear-gradient(135deg,rgba(255,68,68,0.15),rgba(255,107,53,0.1));display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0; }
.breach-body { flex:1;min-width:0; }
.breach-top  { display:flex;align-items:center;gap:8px;margin-bottom:3px; }
.breach-site { font-size:15px;font-weight:800; }
.breach-date { font-size:11px;font-weight:700;color:var(--text3);margin-left:auto; }
.breach-email { font-size:12px;font-weight:700;color:var(--cyan);margin-bottom:8px; }
.tags { display:flex;gap:5px;flex-wrap:wrap; }
.tag { font-size:10px;font-weight:800;padding:3px 9px;border-radius:50px;letter-spacing:0.04em; }
.tag-red    { background:rgba(255,68,68,0.12);   color:#FF4444;       border:1px solid rgba(255,68,68,0.25); }
.tag-orange { background:rgba(255,107,53,0.12);  color:var(--orange); border:1px solid rgba(255,107,53,0.25); }
.tag-gray   { background:var(--surface2);         color:var(--text3);  border:1px solid var(--border); }

/* Probe cards */
.probe-card { background:var(--card);border:2px solid var(--border);border-radius:var(--radius-sm);padding:12px 16px;margin-bottom:8px;display:flex;align-items:center;gap:12px;transition:all 0.2s; }
.probe-card:hover { border-color:rgba(120,75,160,0.3); }
.probe-icon  { width:38px;height:38px;border-radius:10px;background:var(--surface2);display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0; }
.probe-info  { flex:1;min-width:0; }
.probe-site  { font-size:14px;font-weight:800;margin-bottom:2px; }
.probe-email { font-size:12px;font-weight:700;color:var(--cyan); }
.probe-status { display:flex;align-items:center;gap:6px;font-size:12px;font-weight:800;white-space:nowrap; }
.probe-status.found        { color:#FF4444; }
.probe-status.not_found    { color:var(--green); }
.probe-status.inconclusive { color:var(--text3); }
.status-dot { width:8px;height:8px;border-radius:50%;flex-shrink:0; }
.dot-found        { background:#FF4444; }
.dot-not_found    { background:var(--green); }
.dot-inconclusive { background:var(--text3); }

/* Address cards */
.addr-card { background:var(--card);border:2px solid var(--border);border-radius:var(--radius-sm);padding:14px 16px;margin-bottom:8px;display:flex;align-items:center;gap:14px; }
.addr-email { font-size:14px;font-weight:800;color:var(--cyan);flex:1; }
.addr-stat  { font-size:11px;font-weight:800;padding:3px 10px;border-radius:50px; }
.addr-breach { background:rgba(255,68,68,0.12);color:#FF4444;border:1px solid rgba(255,68,68,0.2); }
.addr-clean  { background:rgba(0,200,130,0.12);color:var(--green);border:1px solid rgba(0,200,130,0.2); }

/* Legend */
.legend { display:flex;gap:14px;margin-bottom:16px;flex-wrap:wrap; }
.legend-item { display:flex;align-items:center;gap:5px;font-size:11px;font-weight:800;color:var(--text3); }
.legend-dot  { width:10px;height:10px;border-radius:50%; }

/* Empty state */
.empty { text-align:center;padding:32px 0; }
.empty-icon { font-size:40px;margin-bottom:12px; }
.empty-text { font-size:14px;font-weight:600;color:var(--text3); }

@media (max-width:520px) {
  .metrics { grid-template-columns:repeat(2,1fr); }
}
</style>
</head>
<body>

<div class="top-bar-unified">
  <div class="app-brand">
    <div class="brand-icon">🔍</div>
    <div>
      <div class="brand-name">Footprint</div>
      <div class="brand-sub">friedutch.plus</div>
    </div>
  </div>
  <div class="top-right">
    <a class="top-icon-btn" href="/" title="Home">🏠</a>
    <a class="top-icon-btn" href="/smartlock/logout" onclick="return confirm('Log out?')" title="Log out">👋</a>
    <button class="top-icon-btn" onclick="toggleTheme(this)" id="theme-btn">🔄</button>
  </div>
</div>

<h1>🔍 Footprint</h1>
<p class="page-sub">Track every account tied to your @friedutch.plus domain</p>

<div class="metrics">
  <div class="metric">
    <div class="metric-label">Addresses</div>
    <div class="metric-val" id="m-addresses">—</div>
  </div>
  <div class="metric">
    <div class="metric-label">Breaches</div>
    <div class="metric-val danger" id="m-breaches">—</div>
  </div>
  <div class="metric">
    <div class="metric-label">Accounts found</div>
    <div class="metric-val warn" id="m-accounts">—</div>
  </div>
  <div class="metric">
    <div class="metric-label">Last scan</div>
    <div class="metric-val info" id="m-lastscan">Never</div>
  </div>
</div>

<div class="zone zone-purple">
  <div class="scan-zone-title">🔎 Run a scan</div>
  <div class="scan-row">
    <input class="app-input" type="text" id="scan-input"
           placeholder="@friedutch.plus or hello@friedutch.plus"
           value="@friedutch.plus"
           onkeydown="if(event.key==='Enter')runScan()">
    <button class="sm-btn sm-purple" onclick="runScan()" id="scan-btn">🚀 Scan</button>
  </div>
  <p class="scan-hint">
    <span>@friedutch.plus</span> scans the whole domain ·
    <span>hello@friedutch.plus</span> scans one address
  </p>
</div>

<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('breaches',this)">
    🔴 Breaches <span class="tab-count" id="tc-breaches">0</span>
  </button>
  <button class="tab-btn" onclick="switchTab('probe',this)">
    🌐 Account probe <span class="tab-count" id="tc-probe">0</span>
  </button>
  <button class="tab-btn" onclick="switchTab('addresses',this)">
    📧 Addresses <span class="tab-count" id="tc-addresses">0</span>
  </button>
</div>

<!-- BREACHES -->
<div class="tab-panel active" id="panel-breaches">
  <div class="zone zone-red">
    <div class="zone-title">
      <div class="zone-title-left"><span>🚨</span> Breach results</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;">
        <span class="filter-chip active" onclick="setBFilter('all',this)">All</span>
        <span class="filter-chip" onclick="setBFilter('high',this)">High</span>
        <span class="filter-chip" onclick="setBFilter('medium',this)">Medium</span>
        <span class="filter-chip" onclick="setBFilter('low',this)">Low</span>
      </div>
    </div>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:#FF4444"></div>Passwords / cards</div>
      <div class="legend-item"><div class="legend-dot" style="background:var(--orange)"></div>Personal data</div>
      <div class="legend-item"><div class="legend-dot" style="background:var(--yellow)"></div>Metadata</div>
    </div>
    <div id="breach-list">
      <div class="empty"><div class="empty-icon">🔐</div><div class="empty-text">Run a scan to check for breaches</div></div>
    </div>
  </div>
</div>

<!-- PROBE -->
<div class="tab-panel" id="panel-probe">
  <div class="zone zone-purple">
    <div class="zone-title">
      <div class="zone-title-left"><span>🌐</span> Account probe</div>
      <span style="font-size:11px;font-weight:700;color:var(--text3);">Top 1000 sites</span>
    </div>
    <div class="filter-row">
      <input class="filter-search" type="text" id="probe-search" placeholder="Search sites…" oninput="renderProbe()">
      <span class="filter-chip active" onclick="setPFilter('all',this)">All</span>
      <span class="filter-chip" onclick="setPFilter('found',this)">Found</span>
      <span class="filter-chip" onclick="setPFilter('not_found',this)">Clean</span>
      <span class="filter-chip" onclick="setPFilter('inconclusive',this)">Inconclusive</span>
    </div>
    <div id="probe-list">
      <div class="empty"><div class="empty-icon">🌐</div><div class="empty-text">Run a scan to probe accounts across 1000 sites</div></div>
    </div>
  </div>
</div>

<!-- ADDRESSES -->
<div class="tab-panel" id="panel-addresses">
  <div class="zone zone-cyan">
    <div class="zone-title"><div class="zone-title-left"><span>📧</span> Domain addresses</div></div>
    <div id="addr-list">
      <div class="empty"><div class="empty-icon">📭</div><div class="empty-text">Run a scan to discover active addresses</div></div>
    </div>
  </div>
</div>

<script>
""" + THEME_JS + """

// ── State ──────────────────────────────────────────────────────────────────
const S = { breaches:[], probes:[], addresses:[], bFilter:'all', pFilter:'all' };

// ── Tabs ───────────────────────────────────────────────────────────────────
function switchTab(name, btn) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('panel-'+name).classList.add('active');
  btn.classList.add('active');
}

// ── Scan ───────────────────────────────────────────────────────────────────
async function runScan() {
  const val = document.getElementById('scan-input').value.trim();
  if (!val) return;
  const btn = document.getElementById('scan-btn');
  btn.textContent = '⏳ Scanning…';
  btn.disabled = true;
  try {
    const res  = await fetch('/footprint/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRF() },
      body: JSON.stringify({ target: val })
    });
    const data = await res.json();
    S.breaches  = data.breaches  || [];
    S.probes    = data.probes    || [];
    S.addresses = data.addresses || [];
    document.getElementById('m-lastscan').textContent = data.scanned_at || 'just now';
    updateMetrics();
    renderBreaches();
    renderProbe();
    renderAddresses();
  } catch(e) {
    console.error(e);
  } finally {
    btn.textContent = '🚀 Scan';
    btn.disabled = false;
  }
}

function getCSRF() {
  const el = document.querySelector('input[name="csrf_token"]');
  return el ? el.value : '';
}

// ── Metrics ────────────────────────────────────────────────────────────────
function updateMetrics() {
  document.getElementById('m-addresses').textContent = S.addresses.length;
  document.getElementById('m-breaches').textContent  = S.breaches.length;
  document.getElementById('m-accounts').textContent  = S.probes.filter(p=>p.status==='found').length;
  document.getElementById('tc-breaches').textContent  = S.breaches.length;
  document.getElementById('tc-probe').textContent     = S.probes.length;
  document.getElementById('tc-addresses').textContent = S.addresses.length;
}

// ── Breaches ───────────────────────────────────────────────────────────────
function tagClass(t) {
  const l = t.toLowerCase();
  if (l.includes('password') || l.includes('credit')) return 'tag-red';
  if (l.includes('phone') || l.includes('birth') || l.includes('name') || l.includes('locat')) return 'tag-orange';
  return 'tag-gray';
}

function renderBreaches() {
  let items = S.breaches;
  if (S.bFilter !== 'all') items = items.filter(b => b.severity === S.bFilter);
  const el = document.getElementById('breach-list');
  if (!items.length) {
    el.innerHTML = '<div class="no-items">No breaches match this filter 🎉</div>';
    return;
  }
  el.innerHTML = items.map(b => `
    <div class="breach-card sev-${b.severity}">
      <div class="breach-icon">${b.icon}</div>
      <div class="breach-body">
        <div class="breach-top">
          <span class="breach-site">${b.site}</span>
          <span class="breach-date">${b.date}</span>
        </div>
        <div class="breach-email">${b.email}</div>
        <div class="tags">${b.tags.map(t=>`<span class="tag ${tagClass(t)}">${t}</span>`).join('')}</div>
      </div>
    </div>`).join('');
}

function setBFilter(f, el) {
  S.bFilter = f;
  document.querySelectorAll('#panel-breaches .filter-chip').forEach(c=>c.classList.remove('active'));
  el.classList.add('active');
  renderBreaches();
}

// ── Probe ──────────────────────────────────────────────────────────────────
const STATUS_LABEL = { found:'Account found', not_found:'No account', inconclusive:'Inconclusive' };

function renderProbe() {
  const search = (document.getElementById('probe-search').value||'').toLowerCase();
  let items = S.probes;
  if (S.pFilter !== 'all') items = items.filter(p => p.status === S.pFilter);
  if (search) items = items.filter(p => p.site.toLowerCase().includes(search) || p.email.toLowerCase().includes(search));
  const el = document.getElementById('probe-list');
  if (!items.length) { el.innerHTML = '<div class="no-items">No results match this filter</div>'; return; }
  el.innerHTML = items.map(p => `
    <div class="probe-card">
      <div class="probe-icon">${p.icon}</div>
      <div class="probe-info">
        <div class="probe-site">${p.site}</div>
        <div class="probe-email">${p.email}</div>
      </div>
      <div class="probe-status ${p.status}">
        <div class="status-dot dot-${p.status}"></div>
        ${STATUS_LABEL[p.status]||p.status}
      </div>
    </div>`).join('');
}

function setPFilter(f, el) {
  S.pFilter = f;
  document.querySelectorAll('#panel-probe .filter-chip').forEach(c=>c.classList.remove('active'));
  el.classList.add('active');
  renderProbe();
}

// ── Addresses ──────────────────────────────────────────────────────────────
function renderAddresses() {
  const el = document.getElementById('addr-list');
  if (!S.addresses.length) { el.innerHTML = '<div class="no-items">No addresses found</div>'; return; }
  el.innerHTML = S.addresses.map(a => `
    <div class="addr-card">
      <span style="font-size:20px;">📧</span>
      <span class="addr-email">${a.email}</span>
      ${a.breaches > 0
        ? `<span class="addr-stat addr-breach">⚠️ ${a.breaches} breach${a.breaches>1?'es':''}</span>`
        : `<span class="addr-stat addr-clean">✅ Clean</span>`}
    </div>`).join('');
}
</script>

<!-- Hidden CSRF token for fetch calls -->
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
</body>
</html>"""
