/*! cursor-zh-inline — Cursor 自研界面中文化（静态注入版）
 *  词典来源：https://github.com/Ver3ce/cursor-zh (MIT)
 *  原理：遍历 DOM 文本节点与常见属性，按本地词典做精确/正则替换；MutationObserver 跟踪增量渲染。
 *  不翻译：Monaco 编辑器、终端、输入框、Markdown 正文、AI 回复、代码块。
 */
(function () {
  'use strict';
  if (window.__cursorZhInline) { return; }
  window.__cursorZhInline = 1;

  var DICT = __DICT__;

  var EXACT = DICT.exact || {};
  var PATTERNS = (DICT.patterns || []).map(function (p) {
    try { return { re: new RegExp(p.match), to: p.replace }; } catch (e) { return null; }
  }).filter(Boolean);
  var SUFFIXES = (DICT.suffixes || []).map(function (p) {
    try { return { re: new RegExp(p.match), to: p.replace }; } catch (e) { return null; }
  }).filter(Boolean);
  var ATTRS = DICT.attributes || ['title', 'aria-label', 'placeholder'];
  var SKIP = (DICT.skipSelectors || []).join(',');
  var SEP = (DICT.segmentSeparators && DICT.segmentSeparators[0]) || ', ';
  var JOIN = DICT.segmentJoiner || '，';

  var LOWER = Object.create(null);
  for (var k in EXACT) {
    var lk = k.toLowerCase();
    if (!(lk in LOWER)) { LOWER[lk] = EXACT[k]; }
    else if (LOWER[lk] !== EXACT[k]) { LOWER[lk] = null; }
  }

  var ZW = /[\u200b\u200c\u200d\u2060\ufeff]/g;
  var CJK = /[\u4e00-\u9fa5\u3000-\u303f\uff00-\uffef]/;
  var LATIN = /[A-Za-z]/;

  function strip(s) { return s.replace(ZW, '').replace(/^[\s\u00a0]+|[\s\u00a0]+$/g, ''); }

  function lookup(s) {
    if (!s) { return null; }
    var v = EXACT[s];
    return typeof v === 'string' ? v : null;
  }

  function core(s) {
    var v = lookup(s);
    if (v !== null) { return v; }

    var t = s.replace(/[.…:：\u2026]+$/, '');
    t = strip(t);
    if (t && t !== s) {
      v = lookup(t);
      if (v !== null) { return v; }
    }

    for (var i = 0; i < PATTERNS.length; i++) {
      if (PATTERNS[i].re.test(s)) { return s.replace(PATTERNS[i].re, PATTERNS[i].to); }
    }

    for (var j = 0; j < SUFFIXES.length; j++) {
      var m = SUFFIXES[j].re.exec(s);
      if (m && m.index > 0) {
        var head = strip(s.slice(0, m.index));
        var h = lookup(head);
        if (h !== null) { return h + m[0].replace(SUFFIXES[j].re, SUFFIXES[j].to); }
      }
    }

    if (s.indexOf(SEP) > 0) {
      var parts = s.split(SEP);
      var out = [];
      var ok = true;
      for (var p = 0; p < parts.length; p++) {
        var q = strip(parts[p]);
        var qv = lookup(q);
        if (qv === null) { ok = false; break; }
        out.push(qv);
      }
      if (ok) { return out.join(JOIN); }
    }

    var lv = LOWER[s.toLowerCase()];
    if (typeof lv === 'string') { return lv; }
    return null;
  }

  function skipped(el) {
    if (!el || !el.closest) { return false; }
    try { return !!el.closest(SKIP); } catch (e) { return false; }
  }

  function doText(node) {
    var raw = node.nodeValue;
    if (!raw || raw.length > 400) { return; }
    if (!LATIN.test(raw) || CJK.test(raw)) { return; }
    var lead = raw.match(/^[\s\u00a0\u200b\u200c\u200d\u2060\ufeff]*/)[0];
    var tail = raw.match(/[\s\u00a0\u200b\u200c\u200d\u2060\ufeff]*$/)[0];
    var body = strip(raw);
    if (!body) { return; }
    var out = core(body);
    if (out !== null && out !== body) { node.nodeValue = lead + out + tail; }
  }

  function doAttrs(el) {
    if (!el.getAttribute) { return; }
    for (var i = 0; i < ATTRS.length; i++) {
      var a = ATTRS[i];
      var v = el.getAttribute(a);
      if (!v || !LATIN.test(v) || CJK.test(v)) { continue; }
      var out = core(strip(v));
      if (out !== null) { try { el.setAttribute(a, out); } catch (e) { /* noop */ } }
    }
  }

  function walk(root) {
    if (!root) { return; }
    if (root.nodeType === 3) { if (!skipped(root.parentElement)) { doText(root); } return; }
    if (root.nodeType !== 1 && root.nodeType !== 9 && root.nodeType !== 11) { return; }
    if (root.nodeType === 1) {
      // 即使元素被 skip（如 contenteditable 输入框），也翻译其属性（placeholder/title 等），
      // 但不深入其文本内容，避免翻译用户输入。
      doAttrs(root);
      if (skipped(root)) { return; }
    }

    var tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    var n;
    while ((n = tw.nextNode())) {
      if (!skipped(n.parentElement)) { doText(n); }
    }

    if (root.querySelectorAll) {
      var all = root.querySelectorAll('*');
      for (var i = 0; i < all.length; i++) {
        var el = all[i];
        doAttrs(el);
        if (skipped(el)) { continue; }
        if (el.shadowRoot && !el.shadowRoot.__cz) {
          el.shadowRoot.__cz = 1;
          observe(el.shadowRoot);
          walk(el.shadowRoot);
        }
      }
    }
  }

  var queue = [];
  var scheduled = false;

  function flush() {
    scheduled = false;
    var batch = queue;
    queue = [];
    for (var i = 0; i < batch.length; i++) {
      var r = batch[i];
      try {
        if (r.type === 'characterData') { walk(r.target); }
        else if (r.type === 'attributes') { if (!skipped(r.target)) { doAttrs(r.target); } }
        else {
          for (var j = 0; j < r.addedNodes.length; j++) { walk(r.addedNodes[j]); }
        }
      } catch (e) { /* noop */ }
    }
  }

  var observer = new MutationObserver(function (records) {
    for (var i = 0; i < records.length; i++) { queue.push(records[i]); }
    if (!scheduled) {
      scheduled = true;
      if (typeof requestAnimationFrame === 'function') { requestAnimationFrame(flush); }
      else { setTimeout(flush, 16); }
    }
  });

  function observe(target) {
    observer.observe(target, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ATTRS
    });
  }

  function boot() {
    if (!document.body) { return setTimeout(boot, 100); }
    walk(document.body);
    observe(document.body);
    window.__cursorZhWalk = function () { walk(document.body); };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
