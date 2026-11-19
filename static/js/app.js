/* ค่าเริ่มต้นของ HTMX ที่ใช้ทั้งเว็บ */
document.addEventListener('DOMContentLoaded', function () {
  if (!window.htmx) {
    // ยังไม่ได้รัน scripts/fetch_vendor.sh
    console.warn('HTMX ยังไม่ถูกโหลด: รัน bash scripts/fetch_vendor.sh');
    return;
  }
  // ให้ HTMX แสดงหน้า error ของเซิร์ฟเวอร์ (422 ฟอร์มไม่ผ่าน) แทนที่จะเงียบ
  htmx.config.responseHandling = [
    { code: '204', swap: false },
    { code: '[23]..', swap: true },
    { code: '422', swap: true },
    { code: '[45]..', swap: false, error: true },
  ];
  htmx.config.defaultSwapStyle = 'outerHTML';
});

/* toast แจ้งผล: server ส่ง HX-Trigger {"tmpp:toast": {"message", "level"}} */
document.addEventListener('tmpp:toast', function (event) {
  var detail = event.detail || {};
  var toastEl = document.getElementById('tm-toast');
  if (!toastEl || !window.bootstrap) return;
  toastEl.classList.remove('text-bg-success', 'text-bg-warning', 'text-bg-dark');
  toastEl.classList.add(detail.level === 'warning' ? 'text-bg-warning' : 'text-bg-dark');
  document.getElementById('tm-toast-body').textContent = detail.message || '';
  bootstrap.Toast.getOrCreateInstance(toastEl, { delay: 2500 }).show();
  // เพิ่มลงตะกร้าเสร็จ -> ปิด modal เลือกตัวเลือก
  var sheet = document.getElementById('item-sheet');
  if (sheet && detail.level !== 'warning') bootstrap.Modal.getOrCreateInstance(sheet).hide();
});

/* โหลดเนื้อหา modal เมนูเสร็จ -> เปิด modal */
document.addEventListener('htmx:afterSwap', function (event) {
  if (event.detail.target && event.detail.target.id === 'item-sheet-body' && window.bootstrap) {
    bootstrap.Modal.getOrCreateInstance(document.getElementById('item-sheet')).show();
  }
});

/* หยุด polling ของ HTMX เมื่อแท็บถูกซ่อน ลดภาระเซิร์ฟเวอร์และแบตมือถือ
   ใช้คู่กับ hx-trigger="every 5s [document.visibilityState === 'visible']" */
function tmppRefreshVisible() {
  if (document.visibilityState !== 'visible' || !window.htmx) return;
  document.querySelectorAll('[data-refresh-on-visible]').forEach(function (el) { htmx.trigger(el, 'refresh'); });
}
document.addEventListener('visibilitychange', tmppRefreshVisible);
// แอปบนหน้าจอโฮม (iPhone) กลับมาจากพื้นหลังด้วยหน้าเก่าในหน่วยความจำ (bfcache) โดยไม่ยิง visibilitychange
window.addEventListener('pageshow', function (event) { if (event.persisted) tmppRefreshVisible(); });
window.addEventListener('focus', tmppRefreshVisible);

/* หน้าเลือกอาหาร (orders/_item_sheet.html): กติกากลุ่มตัวเลือก + ยอดรวมสด
   ครบจำนวนสูงสุดแล้ว ตัวเลือกอื่นในกลุ่มจะเป็นสีเทา (ต้องเอาอันเดิมออกก่อน) · ต้องเลือกครบถึงกดเพิ่มได้ */
window.tmppItemSheet = function (config) {
  var priceOf = {};
  config.groups.forEach(function (g) { g.options.forEach(function (o) { priceOf[o.id] = o.price; }); });
  return {
    base: config.base,
    qty: config.qty || 1,
    groups: config.groups,
    selected: config.selected.slice(),
    isChecked: function (id) { return this.selected.indexOf(id) !== -1; },
    count: function (g) {
      var self = this;
      return g.options.filter(function (o) { return self.isChecked(o.id); }).length;
    },
    isDisabled: function (g, id) { return !this.isChecked(id) && this.count(g) >= g.max; },
    toggle: function (g, id) {
      if (this.isChecked(id)) { this.selected = this.selected.filter(function (x) { return x !== id; }); return; }
      if (this.count(g) < g.max) this.selected = this.selected.concat([id]);
    },
    get valid() {
      var self = this;
      return this.groups.every(function (g) { return self.count(g) >= g.min; });
    },
    get missingText() {
      var self = this;
      var g = this.groups.find(function (x) { return self.count(x) < x.min; });
      return g ? 'เลือกตัวเลือกที่ต้องระบุให้ครบก่อน' : '';
    },
    get total() {
      var extras = this.selected.reduce(function (sum, id) { return sum + (priceOf[id] || 0); }, 0);
      return (this.base + extras) * this.qty;
    },
  };
};

/* หน้าตะกร้า: แก้ไข/เพิ่มรายการจากหน้าเลือกอาหารแล้ว ให้โหลดรายการใหม่ */
document.addEventListener('tmpp:cart-changed', function () {
  var body = document.getElementById('cart-body');
  if (body && window.htmx) htmx.ajax('GET', body.dataset.refreshUrl, { target: '#cart-body', swap: 'outerHTML' });
});

/* ---------------------------------------------------------------- แบบแอป (PWA) */
(function () {
  var standalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  if (standalone) document.documentElement.classList.add('is-standalone');

  // service worker: หน้า "ไม่มีอินเทอร์เน็ต" + เก็บไฟล์ static + รับแจ้งเตือน (ไฟล์เดียวกับ Firebase ต้องอยู่ที่ root)
  if ('serviceWorker' in navigator) {
    // ตอนเปิดหน้ามี service worker คุมอยู่แล้ว = ถ้าเปลี่ยนตัวคุมทีหลัง แปลว่า deploy ใหม่
    // (เปิดครั้งแรกสุดยังไม่มีตัวคุม การเปลี่ยนครั้งแรกนั้นไม่ใช่เวอร์ชันใหม่ ไม่ต้องเตือน)
    var hadController = !!navigator.serviceWorker.controller;
    navigator.serviceWorker.addEventListener('controllerchange', function () {
      if (!hadController) { hadController = true; return; }
      var updateBar = document.getElementById('tm-update');
      if (updateBar) updateBar.classList.remove('d-none');
    });
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/firebase-messaging-sw.js', { scope: '/' }).then(function (registration) {
        // จอครัว/ไรเดอร์เปิดค้างทั้งวันโดยไม่เปลี่ยนหน้า เบราว์เซอร์จึงไม่เช็คเวอร์ชันเอง -> เช็คทุก 30 นาที
        setInterval(function () {
          if (document.visibilityState === 'visible') registration.update().catch(function () { /* เน็ตหลุด รอบหน้าค่อยเช็ค */ });
        }, 30 * 60 * 1000);
      }).catch(function () { /* ไม่รองรับก็ใช้เว็บได้ปกติ */ });
    });
  }
  document.addEventListener('click', function (event) {
    if (!event.target.closest('[data-app-update]')) return;
    // ไรเดอร์กำลังถ่ายรูปส่งของ: โหลดใหม่แล้วรูปหาย ต้องถามก่อน
    if (document.querySelector('[data-busy]') && !window.confirm('รูปที่ถ่ายไว้จะหาย โหลดเวอร์ชันใหม่เลยไหม')) return;
    window.location.reload();
  });

  // ปุ่มย้อนกลับบนหัวแอป (components/_app_back.html): แอปที่ติดตั้งแล้วไม่มีปุ่ม back ของเบราว์เซอร์
  document.addEventListener('DOMContentLoaded', function () {
    var back = document.querySelector('[data-app-back]');
    if (!back) return;
    var roots = (back.dataset.roots || '').split(/\s+/).filter(Boolean);
    if (roots.indexOf(window.location.pathname) === -1) back.classList.add('is-shown');
    back.addEventListener('click', function () {
      // มาจากหน้าอื่นในเว็บเรา -> ย้อนกลับจริง · เปิดมาจากแจ้งเตือน/ลิงก์ภายนอก -> ไปหน้าหลัก
      var cameFromHere = document.referrer.indexOf(window.location.origin + '/') === 0;
      if (cameFromHere && window.history.length > 1) window.history.back();
      else window.location.href = back.dataset.fallback || '/';
    });
  });

  // ตัวเลขบนไอคอนแอป (Android/คอม ที่ติดตั้งแล้ว · iPhone ไม่รองรับ)
  // ใช้ [data-app-badge] ของหน้านั้นก่อน (ครัว = ออเดอร์ใหม่, ไรเดอร์ = งานใหม่) ไม่มีก็ใช้แจ้งเตือนที่ยังไม่อ่าน
  function syncAppBadge() {
    if (!('setAppBadge' in navigator)) return;
    var source = document.querySelector('[data-app-badge]');
    var count = source ? source.dataset.appBadge : (document.querySelector('[data-app-badge-fallback]') || { dataset: {} }).dataset.appBadgeFallback;
    count = parseInt(count || '0', 10) || 0;
    (count > 0 ? navigator.setAppBadge(count) : navigator.clearAppBadge()).catch(function () { /* ไม่ได้ติดตั้งแอป */ });
  }
  document.addEventListener('DOMContentLoaded', syncAppBadge);
  document.addEventListener('htmx:afterSettle', syncAppBadge);

  // หน้าเลือกอาหาร: แตะเมนูแล้วเปิดหน้าต่างพร้อมโครงร่างทันที ไม่ต้องรอเน็ต (เหมือนแอป)
  document.addEventListener('htmx:beforeRequest', function (event) {
    var target = event.detail.target;
    var skeleton = document.getElementById('item-sheet-skeleton');
    if (!target || target.id !== 'item-sheet-body' || !skeleton || !window.bootstrap) return;
    target.innerHTML = skeleton.innerHTML;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('item-sheet')).show();
  });
  document.addEventListener('htmx:afterRequest', function (event) {
    var target = event.detail.target;
    if (!target || target.id !== 'item-sheet-body' || event.detail.successful || !window.bootstrap) return;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('item-sheet')).hide();
    document.dispatchEvent(new CustomEvent('tmpp:toast', { detail: { message: 'โหลดเมนูไม่สำเร็จ ลองแตะอีกครั้ง', level: 'warning' } }));
  });

  // ดึงลงเพื่อโหลดใหม่: เฉพาะแอปที่ติดตั้งแล้วบนจอสัมผัส (เบราว์เซอร์ปกติมีของตัวเองอยู่แล้ว)
  // ถ้าหน้ามีส่วนที่โหลดเองได้ ([data-refresh-on-visible] เช่น บอร์ดครัว/งานไรเดอร์) โหลดแค่ส่วนนั้น ไม่โหลดทั้งหน้า
  // ไม่โหลดทั้งหน้าเมื่อพิมพ์ฟอร์มค้างไว้หรือกำลังถ่ายรูปส่งของ ([data-busy]) ของที่กรอกจะได้ไม่หาย
  (function () {
    if (!standalone || !('ontouchstart' in window)) return;
    var PULL_READY = 64;       // px ที่ต้องดึง (หลังหน่วงครึ่งหนึ่ง) ถึงจะโหลด
    var indicator = null, startY = null, pulled = 0, formDirty = false;
    document.addEventListener('input', function (e) { if (e.target.closest('form')) formDirty = true; });

    function scrolledParent(node) {
      for (; node && node !== document.body; node = node.parentElement) {
        if (node.scrollTop > 0) return true;
      }
      return false;
    }
    function blocked(target) {
      return document.body.classList.contains('modal-open') ||
        !!target.closest('[data-no-ptr], .modal, .gm-style, input, textarea, select, .offcanvas') || scrolledParent(target);
    }
    function reset() {
      startY = null; pulled = 0;
      if (indicator) { indicator.style.transform = ''; indicator.classList.remove('is-pulling', 'is-ready'); }
    }
    function refresh() {
      var parts = document.querySelectorAll('[data-refresh-on-visible]');
      if (parts.length && window.htmx) {
        indicator.classList.add('is-loading');
        parts.forEach(function (el) { htmx.trigger(el, 'refresh'); });
        setTimeout(function () { indicator.classList.remove('is-loading'); }, 700);
        return;
      }
      if (formDirty || document.querySelector('[data-busy]')) {
        document.dispatchEvent(new CustomEvent('tmpp:toast', { detail: { message: 'มีข้อมูลที่กรอกค้างไว้ จึงไม่โหลดหน้าใหม่', level: 'warning' } }));
        return;
      }
      indicator.classList.add('is-loading');
      window.location.reload();
    }
    document.addEventListener('touchstart', function (e) {
      indicator = indicator || document.getElementById('tm-ptr');
      if (!indicator || window.scrollY > 0 || e.touches.length !== 1 || blocked(e.target)) { startY = null; return; }
      startY = e.touches[0].clientY;
    }, { passive: true });
    document.addEventListener('touchmove', function (e) {
      if (startY === null) return;
      var distance = e.touches[0].clientY - startY;
      if (distance <= 0 || window.scrollY > 0) { reset(); return; }
      pulled = Math.min(distance / 2, 96);
      indicator.classList.add('is-pulling');
      indicator.classList.toggle('is-ready', pulled >= PULL_READY);
      indicator.style.transform = 'translate(-50%, ' + pulled + 'px) rotate(' + (pulled * 4) + 'deg)';
    }, { passive: true });
    document.addEventListener('touchend', function () {
      if (startY === null) return;
      var ready = pulled >= PULL_READY;
      reset();
      if (ready) refresh();
    });
    document.addEventListener('touchcancel', reset);
  })();

  // แถบโหลดด้านบน: เปลี่ยนหน้า (ลิงก์/ฟอร์ม) และ HTMX ที่ใช้เวลานานเกิน 150ms
  var bar = document.getElementById('tm-progress');
  var timer = null, pending = 0;
  function start() { pending++; clearTimeout(timer); timer = setTimeout(function () { if (bar) bar.classList.add('is-active'); }, 150); }
  function done() { pending = Math.max(0, pending - 1); if (pending) return; clearTimeout(timer); if (bar) bar.classList.remove('is-active'); }
  document.addEventListener('htmx:beforeRequest', function (e) {
    // polling ทุก 5 วิ ไม่ต้องโชว์แถบ (ไม่ได้เกิดจากการกด)
    var trig = e.detail.requestConfig && e.detail.requestConfig.triggeringEvent;
    if (trig) start();
  });
  document.addEventListener('htmx:afterRequest', function (e) {
    var trig = e.detail.requestConfig && e.detail.requestConfig.triggeringEvent;
    if (trig) done();
  });
  window.addEventListener('beforeunload', function () { if (bar) bar.classList.add('is-active'); });
  window.addEventListener('pageshow', function () { pending = 0; if (bar) bar.classList.remove('is-active'); });

  // ชวนติดตั้งแอป
  var KEY = 'tmpp-install-dismissed';
  function dismissedRecently() {
    try { var t = parseInt(localStorage.getItem(KEY) || '0', 10); return Date.now() - t < 14 * 86400000; } catch (e) { return false; }
  }
  document.addEventListener('DOMContentLoaded', function () {
    var banner = document.querySelector('[data-install-banner]');
    if (!banner || standalone || dismissedRecently()) return;
    var accept = banner.querySelector('[data-install-accept]');
    var text = banner.querySelector('[data-install-text]');
    banner.querySelector('[data-install-dismiss]').addEventListener('click', function () {
      banner.classList.add('d-none');
      try { localStorage.setItem(KEY, String(Date.now())); } catch (e) { /* ไม่จำก็ได้ */ }
    });
    var isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent) && !window.MSStream;
    if (isIOS) {
      text.innerHTML = 'กด <i class="bi bi-box-arrow-up"></i> แชร์ แล้วเลือก "เพิ่มไปยังหน้าจอโฮม"';
      banner.classList.remove('d-none');
      return;
    }
    window.addEventListener('beforeinstallprompt', function (event) {
      event.preventDefault();
      var promptEvent = event;
      accept.classList.remove('d-none');
      banner.classList.remove('d-none');
      accept.onclick = function () {
        promptEvent.prompt();
        promptEvent.userChoice.finally(function () { banner.classList.add('d-none'); });
      };
    });
  });
  window.addEventListener('appinstalled', function () {
    var banner = document.querySelector('[data-install-banner]');
    if (banner) banner.classList.add('d-none');
  });
})();