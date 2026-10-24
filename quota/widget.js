/*! cursor-quota-widget — 标题栏中间的实时额度显示
 *  数据来源：本机 127.0.0.1:47821（quota/server.py 读 Cursor 登录态后转发的官方接口）
 *  不写 innerHTML（workbench 开了 Trusted Types），全部 createElement。
 */
(function () {
  'use strict';
  if (window.__cursorQuotaWidget) { return; }
  window.__cursorQuotaWidget = 1;

  var ENDPOINT = 'http://127.0.0.1:47821/usage';
  var POLL_MS = 60000;
  var R = 5.5;
  var CIRC = 2 * Math.PI * R;

  window.addEventListener('error', function (ev) {
    try {
      if (!/^QUOTA_/.test(document.title)) {
        document.title = 'QUOTA_ERR ' + String(ev.message || 'unknown').slice(0, 60);
      }
    } catch (e) { /* noop */ }
  });

  var root = null;
  var arc = null;
  var label = null;
  var tip = null;
  var lastFetch = 0;
  var busy = false;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text != null) { n.textContent = text; }
    return n;
  }

  function color(used) {
    if (used >= 99.5) { return '#f14c4c'; }
    if (used >= 80) { return '#e8a33d'; }
    return '#3fb950'; // 这里的红/绿是「用超了/还宽裕」，与股市涨跌配色无关
  }

  function fmtReset(ms) {
    if (!ms) { return '未知'; }
    var d = new Date(ms);
    var p = function (n) { return n < 10 ? '0' + n : '' + n; };
    return (d.getMonth() + 1) + '月' + d.getDate() + '日 ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function build() {
    var style = el('style');
    style.textContent = [
      '#cz-quota{position:fixed;top:6px;left:50%;transform:translateX(-50%);z-index:2147483000;',
      'display:flex;align-items:center;gap:6px;height:22px;padding:0 9px 0 7px;border-radius:11px;',
      'border:1px solid rgba(255,255,255,.10);background:rgba(28,28,30,.62);',
      'font:11px/1 -apple-system,"Segoe UI",system-ui,sans-serif;color:rgba(255,255,255,.78);',
      'cursor:pointer;user-select:none;-webkit-app-region:no-drag;letter-spacing:.2px;',
      'transition:background .15s,border-color .15s}',
      '#cz-quota:hover{background:rgba(45,45,48,.85);border-color:rgba(255,255,255,.20)}',
      '#cz-quota.cz-busy{opacity:.55}',
      '#cz-tip{position:fixed;top:32px;left:50%;transform:translateX(-50%);z-index:2147483000;',
      'min-width:170px;padding:8px 10px;border-radius:8px;border:1px solid rgba(255,255,255,.12);',
      'background:rgba(24,24,26,.94);box-shadow:0 6px 20px rgba(0,0,0,.45);display:none;',
      'font:11px/1.65 -apple-system,"Segoe UI",system-ui,sans-serif;color:rgba(255,255,255,.82)}',
      '#cz-tip .row{display:flex;justify-content:space-between;gap:16px}',
      '#cz-tip .k{color:rgba(255,255,255,.50)}',
      '#cz-tip .msg{margin-top:5px;padding-top:5px;border-top:1px solid rgba(255,255,255,.10);',
      'color:#e8a33d;max-width:220px;white-space:normal;line-height:1.5}'
    ].join('');
    document.head.appendChild(style);

    var svgns = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(svgns, 'svg');
    svg.setAttribute('width', '14');
    svg.setAttribute('height', '14');
    svg.setAttribute('viewBox', '0 0 14 14');
    var track = document.createElementNS(svgns, 'circle');
    track.setAttribute('cx', '7');
    track.setAttribute('cy', '7');
    track.setAttribute('r', String(R));
    track.setAttribute('fill', 'none');
    track.setAttribute('stroke', 'rgba(255,255,255,.16)');
    track.setAttribute('stroke-width', '1.8');
    arc = document.createElementNS(svgns, 'circle');
    arc.setAttribute('cx', '7');
    arc.setAttribute('cy', '7');
    arc.setAttribute('r', String(R));
    arc.setAttribute('fill', 'none');
    arc.setAttribute('stroke', 'rgba(255,255,255,.35)');
    arc.setAttribute('stroke-width', '1.8');
    arc.setAttribute('stroke-linecap', 'round');
    arc.setAttribute('stroke-dasharray', '0 ' + CIRC.toFixed(2));
    arc.setAttribute('transform', 'rotate(-90 7 7)');
    svg.appendChild(track);
    svg.appendChild(arc);

    root = el('div');
    root.id = 'cz-quota';
    root.title = '';
    label = el('span', null, '额度 …');
    root.appendChild(svg);
    root.appendChild(label);

    tip = el('div');
    tip.id = 'cz-tip';

    root.addEventListener('mouseenter', function () { tip.style.display = 'block'; });
    root.addEventListener('mouseleave', function () { tip.style.display = 'none'; });
    root.addEventListener('click', function () { refresh(true); });

    document.body.appendChild(root);
    document.body.appendChild(tip);
  }

  function row(k, v, cls) {
    var r = el('div', 'row');
    r.appendChild(el('span', 'k', k));
    var val = el('span', cls || null, v);
    r.appendChild(val);
    return r;
  }

  function render(d) {
    if (!d || !d.ok) {
      label.textContent = '额度 —';
      arc.setAttribute('stroke', 'rgba(255,255,255,.28)');
      arc.setAttribute('stroke-dasharray', '0 ' + CIRC.toFixed(2));
      tip.textContent = '';
      tip.appendChild(row('状态', '未连接额度服务'));
      tip.appendChild(row('解决', '运行 quota/server.py'));
      return;
    }

    var used = Math.max(0, Math.min(100, d.used || 0));
    var left = Math.round(100 - used);
    var c = color(used);
    arc.setAttribute('stroke', c);
    arc.setAttribute('stroke-dasharray', (CIRC * used / 100).toFixed(2) + ' ' + CIRC.toFixed(2));
    label.textContent = '剩余 ' + left + '%';
    label.style.color = used >= 99.5 ? c : 'rgba(255,255,255,.78)';

    tip.textContent = '';
    if (typeof d.autoUsed === 'number') { tip.appendChild(row('自动模型', d.autoUsed + '%')); }
    if (typeof d.apiUsed === 'number') { tip.appendChild(row('API 用量', d.apiUsed + '%')); }
    tip.appendChild(row('总额度已用', used + '%'));
    tip.appendChild(row('下次重置', fmtReset(d.resetAt)));
    if (d.message) {
      var m = el('div', 'msg', d.message === "You've hit your usage limit" ? '已达用量上限，充值或等待重置' : d.message);
      tip.appendChild(m);
    }
  }

  var timerId = null;

  function schedule(ms) {
    if (timerId) { clearTimeout(timerId); }
    timerId = setTimeout(function () { refresh(false); }, ms);
  }

  function refresh(force) {
    if (busy) { return; }
    busy = true;
    if (root) { root.classList.add('cz-busy'); }
    var url = ENDPOINT + (force ? '?refresh=1' : '');
    var ctrl = typeof AbortController === 'function' ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctrl) { ctrl.abort(); } }, 12000);
    fetch(url, { cache: 'no-store', signal: ctrl ? ctrl.signal : undefined })
      .then(function (r) { return r.json(); })
      .then(function (d) { lastFetch = Date.now(); render(d); schedule(60000); })
      .catch(function () { render({ ok: false }); schedule(10000); })
      .then(function () {
        clearTimeout(timer);
        busy = false;
        if (root) { root.classList.remove('cz-busy'); }
      });
  }

  function attach() {
    if (!document.body) { return; }
    if (root && !root.isConnected) { document.body.appendChild(root); }
    if (tip && !tip.isConnected) { document.body.appendChild(tip); }
  }

  function boot() {
    if (!document.body) { return setTimeout(boot, 200); }
    try {
      build();
    } catch (e) {
      document.title = 'QUOTA_ERR ' + String(e && e.message || e).slice(0, 60);
      return;
    }
    attach();
    // workbench 启动阶段可能重建 body，节点会被摘掉，这里持续兜住
    setInterval(attach, 1500);
    var until = Date.now() + 30000;
    (function tick() {
      attach();
      if (Date.now() < until) { requestAnimationFrame(tick); }
    })();

    render({ ok: false });
    refresh(false);
    window.addEventListener('focus', function () {
      if (Date.now() - lastFetch > 30000) { refresh(false); }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
