/* ShiftGuard AI chat widget.
   <script src="/static/js/assistant.js" data-endpoint="/api/assistant/public"
           data-title="ShiftGuard AI" data-greeting="Hi! ..." data-suggestions="A|B|C"></script>
   window.ShiftGuardAI.open() opens it from any button. */
(function () {
  var me = document.currentScript;
  var cfg = {
    endpoint: me.dataset.endpoint || '/api/assistant/public',
    title: me.dataset.title || 'ShiftGuard AI',
    subtitle: me.dataset.subtitle || 'Ask me anything',
    greeting: me.dataset.greeting || 'Hi! How can I help?',
    suggestions: (me.dataset.suggestions || '').split('|').filter(Boolean),
    storeKey: 'sg-ai-' + (me.dataset.endpoint || 'public')
  };
  var history = [];
  try { history = JSON.parse(sessionStorage.getItem(cfg.storeKey) || '[]'); } catch (e) { history = []; }

  var ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9z"/><path d="M19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/></svg>';

  var root = document.createElement('div');
  root.className = 'sgai';
  root.innerHTML =
    '<button class="sgai-fab" type="button" aria-label="Open ' + esc(cfg.title) + '" aria-expanded="false">' + ICON + '<span>AI</span></button>' +
    '<section class="sgai-panel" role="dialog" aria-label="' + esc(cfg.title) + '" hidden>' +
      '<header class="sgai-head"><div class="sgai-av">' + ICON + '</div><div><b>' + esc(cfg.title) + '</b><small>' + esc(cfg.subtitle) + '</small></div>' +
      '<button class="sgai-x" type="button" aria-label="New conversation" title="New conversation">↺</button>' +
      '<button class="sgai-x sgai-close" type="button" aria-label="Close">×</button></header>' +
      '<div class="sgai-log" aria-live="polite"></div>' +
      '<div class="sgai-sugs"></div>' +
      '<form class="sgai-form"><textarea rows="1" maxlength="2000" placeholder="Type your question…" aria-label="Message"></textarea>' +
      '<button type="submit" aria-label="Send">➤</button></form>' +
      '<p class="sgai-foot">AI can make mistakes. Check important numbers.</p>' +
    '</section>';
  document.body.appendChild(root);

  var fab = root.querySelector('.sgai-fab'), panel = root.querySelector('.sgai-panel');
  var log = root.querySelector('.sgai-log'), sugs = root.querySelector('.sgai-sugs');
  var form = root.querySelector('.sgai-form'), input = form.querySelector('textarea'), send = form.querySelector('button');
  var busy = false;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  // Tiny, safe formatter: escape first, then **bold** and "- " bullets.
  function fmt(t) {
    var lines = esc(t).split('\n'), out = '', inList = false;
    lines.forEach(function (l) {
      l = l.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      var m = l.match(/^\s*[-•]\s+(.*)/);
      if (m) { if (!inList) { out += '<ul>'; inList = true; } out += '<li>' + m[1] + '</li>'; return; }
      if (inList) { out += '</ul>'; inList = false; }
      out += l.trim() ? '<p>' + l + '</p>' : '';
    });
    if (inList) out += '</ul>';
    return out;
  }
  function bubble(role, text, extra) {
    var d = document.createElement('div');
    d.className = 'sgai-msg ' + role + (extra ? ' ' + extra : '');
    d.innerHTML = role === 'user' ? '<p>' + esc(text) + '</p>' : fmt(text);
    log.appendChild(d); log.scrollTop = log.scrollHeight;
    return d;
  }
  function render() {
    log.innerHTML = '';
    bubble('bot', cfg.greeting);
    history.forEach(function (m) { bubble(m.role === 'user' ? 'user' : 'bot', m.content); });
    sugs.innerHTML = history.length ? '' : cfg.suggestions.map(function (s) {
      return '<button type="button">' + esc(s) + '</button>';
    }).join('');
  }
  function save() { try { sessionStorage.setItem(cfg.storeKey, JSON.stringify(history.slice(-20))); } catch (e) {} }

  async function ask(text) {
    text = (text || '').trim();
    if (!text || busy) return;
    busy = true; send.disabled = true; sugs.innerHTML = '';
    history.push({ role: 'user', content: text }); save();
    bubble('user', text);
    var wait = bubble('bot', '', 'typing'); wait.innerHTML = '<span></span><span></span><span></span>';
    var reply;
    try {
      var r = await fetch(cfg.endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: history }) });
      if (r.status === 401) { reply = 'Please sign in again to use the assistant.'; }
      else { var d = await r.json(); reply = d.success ? d.reply : (d.message || 'Something went wrong.'); if (!d.success) history.pop(); }
    } catch (e) { reply = 'Could not reach the assistant. Check your connection.'; history.pop(); }
    wait.remove();
    if (history.length && history[history.length - 1].role === 'user') { history.push({ role: 'assistant', content: reply }); save(); }
    bubble('bot', reply);
    busy = false; send.disabled = false; input.focus();
  }

  function open() { panel.hidden = false; fab.setAttribute('aria-expanded', 'true'); root.classList.add('open'); render(); setTimeout(function () { input.focus(); }, 60); }
  function close() { panel.hidden = true; fab.setAttribute('aria-expanded', 'false'); root.classList.remove('open'); fab.focus(); }
  fab.addEventListener('click', function () { panel.hidden ? open() : close(); });
  root.querySelector('.sgai-close').addEventListener('click', close);
  root.querySelector('.sgai-x:not(.sgai-close)').addEventListener('click', function () { history = []; save(); render(); input.focus(); });
  panel.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
  sugs.addEventListener('click', function (e) { if (e.target.tagName === 'BUTTON') ask(e.target.textContent); });
  form.addEventListener('submit', function (e) { e.preventDefault(); var t = input.value; input.value = ''; input.style.height = ''; ask(t); });
  input.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  input.addEventListener('input', function () { input.style.height = ''; input.style.height = Math.min(input.scrollHeight, 120) + 'px'; });

  window.ShiftGuardAI = { open: open, close: close, ask: function (t) { open(); ask(t); } };
})();
