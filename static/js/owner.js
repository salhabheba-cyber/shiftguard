// ShiftGuard — Owner dashboard
var ACC = [], FIRST = null, RESET = null, CUR_ADMINS = [];

function esc(v) {
  return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}
function $(id) { return document.getElementById(id); }
function gv(id) { return ($(id).value || '').trim(); }
function when(t) { return t ? String(t).substring(0, 16) : '—'; }

async function api(url, method, body) {
  var opt = { method: method || 'GET', headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opt.body = JSON.stringify(body);
  try {
    var r = await fetch(url, opt);
    if (r.status === 401) { location.href = '/?signin=1'; return {}; }
    return await r.json();
  } catch (e) { return { success: false, message: 'Could not reach the server' }; }
}

var toastT;
function toast(msg, isErr) {
  var t = $('toast'); t.textContent = msg; t.className = 'toast show' + (isErr ? ' err' : '');
  clearTimeout(toastT); toastT = setTimeout(function () { t.className = 'toast'; }, 3500);
}
function done(d, after) {
  if (d.success) { toast(d.message || 'Done'); if (after) after(); }
  else toast(d.message || 'Something went wrong', true);
  return !!d.success;
}

function openM(id) { $(id).classList.add('open'); }
function closeM(id) { $(id).classList.remove('open'); }
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') document.querySelectorAll('.modal.open').forEach(function (m) { m.classList.remove('open'); });
});
document.querySelectorAll('.modal').forEach(function (m) {
  m.addEventListener('click', function (e) { if (e.target === m) m.classList.remove('open'); });
});

function showTab(name) {
  document.querySelectorAll('.nav-link[data-tab]').forEach(function (a) { a.classList.toggle('active', a.dataset.tab === name); });
  document.querySelectorAll('.tab-content').forEach(function (t) { t.classList.toggle('active', t.id === 'tab-' + name); });
  if (name === 'activity') loadLog();
  if (name === 'settings') loadOwner2FAStatus();
}
document.querySelectorAll('.nav-link[data-tab]').forEach(function (a) {
  a.addEventListener('click', function (e) { e.preventDefault(); showTab(a.dataset.tab); });
});

var BADGE = { active: 'b-green', suspended: 'b-red', pending: 'b-pending', rejected: 'b-gray' };
function badge(s) { return '<span class="badge ' + (BADGE[s] || 'b-gray') + '">' + esc(s.charAt(0).toUpperCase() + s.slice(1)) + '</span>'; }

var RISK_BADGE = { ok: 'b-green', medium: 'b-pending', high: 'b-red' };
function riskBadge(r) {
  if (!r || r.level === 'ok') return '<span class="badge b-green">OK</span>';
  var label = r.level === 'high' ? 'High' : 'Medium';
  return '<span class="badge ' + RISK_BADGE[r.level] + '" title="' + esc((r.reasons || []).join('; ')) + '">' + label + '</span>';
}

// ── Load everything ───────────────────────────────────────────────────────────
async function load() {
  var d = await api('/api/owner/overview');
  if (!d.success) return toast(d.message || 'Could not load', true);
  ACC = d.accounts; FIRST = d.first_account;
  var t = d.totals;
  $('t-accounts').textContent = t.accounts; $('t-active').textContent = t.active;
  $('t-pending').textContent = t.pending; $('t-employees').textContent = t.employees;
  $('t-today').textContent = t.today;
  $('req-count').textContent = t.pending; $('req-count').hidden = !t.pending;
  $('pw-banner').classList.toggle('show', d.owner.must_change);
  $('owner-name').textContent = d.owner.name || 'Owner';
  if (document.activeElement !== $('o-email')) $('o-email').value = d.owner.email;
  if (document.activeElement !== $('o-name')) $('o-name').value = d.owner.name || '';

  var live = ACC.filter(function (a) { return a.status === 'active' || a.status === 'suspended'; });
  $('ov-tbody').innerHTML = live.map(function (a) {
    return '<tr><td><span class="acc-name">' + esc(a.name) + '</span></td><td>' + badge(a.status) + '</td><td>' + a.admins + '</td><td>' + a.employees +
      '</td><td>' + a.checked_in + '</td><td>' + a.today + '</td><td style="font-size:.8rem">' + when(a.last_activity || a.last_checkin) +
      '</td><td>' + riskBadge(a.risk) + '</td></tr>';
  }).join('') || '<tr><td colspan="8" class="empty">No accounts yet</td></tr>';

  renderAccounts(); renderRequests(); loadLog(true);
}

function renderAccounts() {
  var qs = gv('acc-search').toLowerCase(), f = $('acc-filter').value;
  var rows = ACC.filter(function (a) {
    if (f && a.status !== f) return false;
    if (!qs) return true;
    return [a.name, a.contact_name, a.contact_email, a.admin_email, a.phone].join(' ').toLowerCase().indexOf(qs) >= 0;
  });
  $('acc-tbody').innerHTML = rows.map(function (a) {
    var act = '';
    if (a.status === 'active' || a.status === 'suspended') {
      act += '<button class="btn btn-primary btn-xs" onclick="openAccount(' + a.id + ')">Open ↗</button>';
      act += '<button class="btn btn-outline btn-xs" onclick="openDetail(' + a.id + ')">Manage</button>';
      act += a.status === 'active'
        ? '<button class="btn btn-warn btn-xs" onclick="act(' + a.id + ',\'suspend\')">Suspend</button>'
        : '<button class="btn btn-success btn-xs" onclick="act(' + a.id + ',\'activate\')">Activate</button>';
    } else if (a.status === 'pending') {
      act += '<button class="btn btn-success btn-xs" onclick="act(' + a.id + ',\'approve\')">Approve</button>';
      act += '<button class="btn btn-danger btn-xs" onclick="act(' + a.id + ',\'reject\')">Reject</button>';
    } else {
      act += '<button class="btn btn-outline btn-xs" onclick="openDetail(' + a.id + ')">Manage</button>';
    }
    var billing = a.free_forever
      ? '<span class="badge b-blue">Free forever</span>'
      : a.subscription_status
      ? '<span class="badge ' + (a.subscription_status === 'active' ? 'b-green' : a.subscription_status === 'trialing' ? 'b-pending' : 'b-red') + '">' + esc(a.subscription_status) + '</span>'
      : '<span style="color:var(--muted);font-size:.8rem">—</span>';
    return '<tr><td><div class="acc-name">' + esc(a.name) +
      '</div><div class="acc-sub">' + esc(a.slug) + '</div></td>' +
      '<td>' + esc(a.contact_name || '—') + '<div class="acc-sub">' + esc(a.phone || '') + '</div></td>' +
      '<td style="font-size:.84rem">' + esc(a.admin_email || a.contact_email || '—') + '</td>' +
      '<td>' + badge(a.status) + '</td><td>' + billing + '</td><td>' + a.employees + '</td>' +
      '<td style="font-size:.8rem">' + when(a.created_at) + '</td><td><div class="actions">' + act + '</div></td></tr>';
  }).join('') || '<tr><td colspan="8" class="empty">No accounts match</td></tr>';
}

function renderRequests() {
  var reqs = ACC.filter(function (a) { return a.status === 'pending'; });
  $('req-list').innerHTML = reqs.map(function (a) {
    return '<div class="req-card"><div><h4>' + esc(a.name) + '</h4><div class="req-meta">' +
      esc(a.contact_name || 'No contact name') + ' · ' + esc(a.contact_email) + (a.phone ? ' · ' + esc(a.phone) : '') +
      '<br>Requested ' + when(a.created_at) + '</div></div><div class="actions">' +
      '<button class="btn btn-success btn-sm" onclick="act(' + a.id + ',\'approve\')">✔ Approve</button>' +
      '<button class="btn btn-danger btn-sm" onclick="act(' + a.id + ',\'reject\')">✖ Reject</button></div></div>';
  }).join('') || '<div class="empty">No requests waiting. New sign-ups from the home page appear here.</div>';
}

var EVENTS = {
  login_ok: 'Account sign-in', login_fail: 'Failed sign-in', owner_login: 'Owner sign-in',
  signup_request: 'Sign-up request', account_created: 'Account created', account_approve: 'Approved',
  account_reject: 'Rejected', account_suspend: 'Suspended', account_activate: 'Activated',
  account_deleted: 'Deleted', account_updated: 'Details edited', 'account_reset-password': 'Password reset',
  'account_mark-free': 'Marked always free', 'account_mark-paid': 'Marked payable',
  owner_opened_account: 'Owner opened account', owner_profile_updated: 'Owner details changed'
};
async function loadLog(shortOnly) {
  var d = await api('/api/owner/log'); if (!d.success) return;
  function row(l, full) {
    return '<tr><td style="font-size:.8rem;white-space:nowrap">' + when(l.created_at) + '</td><td>' + esc(EVENTS[l.event] || l.event) +
      '</td><td style="font-size:.84rem">' + esc(l.actor || '—') + '</td><td>' + esc(l.account_name || '—') + '</td>' +
      (full ? '<td style="font-size:.78rem;font-family:monospace">' + esc(l.ip || '') + '</td><td style="font-size:.8rem">' + esc(l.details || '') + '</td>' : '') + '</tr>';
  }
  $('ov-log').innerHTML = d.log.slice(0, 8).map(function (l) { return row(l, false); }).join('') || '<tr><td colspan="4" class="empty">Nothing yet</td></tr>';
  if (!shortOnly) $('log-tbody').innerHTML = d.log.map(function (l) { return row(l, true); }).join('') || '<tr><td colspan="6" class="empty">Nothing yet</td></tr>';
}

// ── Actions ───────────────────────────────────────────────────────────────────
function byId(id) { return ACC.find(function (a) { return a.id === id; }); }

async function act(id, action) {
  var a = byId(id);
  var ask = { suspend: 'Suspend ' + a.name + '? Its users will not be able to sign in.',
              reject: 'Reject the request from ' + a.name + '?' }[action];
  if (ask && !confirm(ask)) return;
  done(await api('/api/owner/accounts/' + id + '/' + action, 'POST', {}), load);
}

async function openAccount(id) {
  var d = await api('/api/owner/accounts/' + id + '/open', 'POST', {});
  if (d.success) location.href = d.redirect; else toast(d.message, true);
}

function openCreate() {
  ['c-business', 'c-name', 'c-phone', 'c-email', 'c-pw'].forEach(function (i) { $(i).value = ''; });
  openM('m-create'); setTimeout(function () { $('c-business').focus(); }, 50);
}
async function createAccount() {
  var d = await api('/api/owner/accounts', 'POST', {
    business: gv('c-business'), name: gv('c-name'), phone: gv('c-phone'), email: gv('c-email'), password: $('c-pw').value
  });
  if (done(d, load)) closeM('m-create');
}

async function toggleFree(id, makeFree) {
  var d = await api('/api/owner/accounts/' + id + '/' + (makeFree ? 'mark-free' : 'mark-paid'), 'POST', {});
  if (done(d, load)) openDetail(id);
}

async function openDetail(id) {
  var a = byId(id);
  $('d-id').value = id; $('d-title').textContent = a.name; $('d-confirm').value = '';
  $('d-business').value = a.name || ''; $('d-name').value = a.contact_name || '';
  $('d-email').value = a.contact_email || ''; $('d-phone').value = a.phone || ''; $('d-notes').value = a.notes || '';
  var billingKv = a.free_forever
    ? '<span class="badge b-blue">Free forever</span> <button class="btn btn-outline btn-xs" onclick="toggleFree(' + id + ',false)">Make payable</button>'
    : '<span style="color:var(--muted);font-size:.8rem">' + esc(a.subscription_status || 'Payable') + '</span> <button class="btn btn-outline btn-xs" onclick="toggleFree(' + id + ',true)">Mark always free</button>';
  var kv = [['Status', badge(a.status)], ['Account ID', esc(a.slug)], ['Created', when(a.created_at)],
            ['Last activity', when(a.last_activity)], ['Last check-in', when(a.last_checkin)],
            ['Employees', a.employees], ['Data size', a.db_kb + ' KB'], ['Billing', billingKv]];
  $('d-kv').innerHTML = kv.map(function (p) { return '<dt>' + p[0] + '</dt><dd>' + p[1] + '</dd>'; }).join('');
  $('d-admins').innerHTML = '<tr><td colspan="5" class="empty">Loading…</td></tr>';
  openM('m-detail');
  var d = await api('/api/owner/accounts/' + id + '/admins');
  CUR_ADMINS = d.admins || [];
  $('d-admins').innerHTML = CUR_ADMINS.map(function (u) {
    return '<tr><td><strong>' + esc(u.username) + '</strong></td><td>' + esc(u.email || '—') + '</td><td>' + esc(u.role) +
      '</td><td style="font-size:.8rem">' + when(u.last_login) + '</td><td><button class="btn btn-outline btn-xs" ' +
      'onclick="openEditAdmin(' + id + ',' + u.id + ')">Edit</button></td></tr>';
  }).join('') || '<tr><td colspan="5" class="empty">No admin users</td></tr>';
}
async function saveDetail() {
  var id = +$('d-id').value;
  var d = await api('/api/owner/accounts/' + id, 'PUT', {
    business: gv('d-business'), name: gv('d-name'), email: gv('d-email'), phone: gv('d-phone'), notes: $('d-notes').value
  });
  if (done(d, load)) $('d-title').textContent = gv('d-business');
}
async function deleteAccount() {
  var id = +$('d-id').value, a = byId(id);
  if (!confirm('Delete ' + a.name + '? This cannot be undone from the dashboard.')) return;
  var d = await api('/api/owner/accounts/' + id, 'DELETE', { confirm: $('d-confirm').value });
  if (done(d, load)) closeM('m-detail');
}

function openEditAdmin(accId, adminId) {
  var u = CUR_ADMINS.find(function (x) { return x.id === adminId; });
  if (!u) return;
  RESET = { id: accId, adminId: adminId, username: u.username };
  $('r-user').textContent = u.username; $('r-acc').textContent = byId(accId).name;
  $('r-email').value = u.email || ''; $('r-pw').value = '';
  openM('m-reset'); setTimeout(function () { $('r-email').focus(); }, 50);
}
async function saveAdminEdit() {
  var body = { email: gv('r-email') };
  var pw = $('r-pw').value;
  if (pw) body.password = pw;
  var d = await api('/api/owner/accounts/' + RESET.id + '/admins/' + RESET.adminId, 'PUT', body);
  if (done(d)) { closeM('m-reset'); openDetail(RESET.id); }
}

async function saveProfile() {
  var nw = $('o-new').value, cf = $('o-cfm').value;
  if (nw && nw !== cf) return toast('New passwords do not match', true);
  var d = await api('/api/owner/profile', 'POST', {
    name: gv('o-name'), email: gv('o-email'), current_password: $('o-cur').value, new_password: nw
  });
  if (done(d, load)) { ['o-new', 'o-cfm', 'o-cur'].forEach(function (i) { $(i).value = ''; }); }
}

async function loadOwner2FAStatus() {
  var d = await api('/api/owner/2fa/status');
  var on = !!d.enabled;
  $('o-tfa-status').textContent = on ? 'Two-factor authentication is ON for your account.' : 'Two-factor authentication is OFF. Turn it on to require a code from your phone at sign-in.';
  $('o-tfa-off').style.display = on ? 'none' : '';
  $('o-tfa-on').style.display = on ? '' : 'none';
  $('o-tfa-setup').style.display = 'none';
  $('o-tfa-backup-codes').style.display = 'none';
}
async function startOwner2FASetup() {
  var d = await api('/api/owner/2fa/setup', 'POST', {});
  if (!d.success) return toast(d.message || 'Could not start setup', true);
  $('o-tfa-off').style.display = 'none';
  $('o-tfa-setup').style.display = '';
  $('o-tfa-secret').textContent = d.secret;
  var qr = $('o-tfa-qr'); qr.innerHTML = '';
  new QRCode(qr, { text: d.otpauth_url, width: 180, height: 180 });
  $('o-tfa-code').value = '';
}
function cancelOwner2FASetup() {
  $('o-tfa-setup').style.display = 'none';
  $('o-tfa-off').style.display = '';
}
async function verifyOwner2FASetup() {
  var d = await api('/api/owner/2fa/verify', 'POST', { code: gv('o-tfa-code') });
  if (!d.success) return toast(d.message || 'Invalid code', true);
  $('o-tfa-setup').style.display = 'none';
  $('o-tfa-backup-codes').style.display = '';
  $('o-tfa-codes-list').innerHTML = (d.backup_codes || []).map(function (c) { return '<div>' + esc(c) + '</div>'; }).join('');
  toast('Two-factor authentication enabled');
}
function closeOwnerTfaBackupCodes() {
  $('o-tfa-backup-codes').style.display = 'none';
  loadOwner2FAStatus();
}
async function disableOwner2FA() {
  var pw = $('o-tfa-disable-pw').value;
  if (!pw) return toast('Enter your current password', true);
  var d = await api('/api/owner/2fa/disable', 'POST', { password: pw });
  if (done(d)) { $('o-tfa-disable-pw').value = ''; loadOwner2FAStatus(); }
}

async function doLogout() {
  await api('/admin/logout', 'POST', {});
  location.href = '/';
}

load();
setInterval(load, 60000);
