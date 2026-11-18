/* เสียงแจ้งเตือน (ไฟล์เดียวกับระบบเดิม static/sounds/bell-*.mp3) — ใช้ร่วมกันทุกหน้า
   - เบราว์เซอร์ไม่ให้เล่นเสียงจนกว่าผู้ใช้จะแตะหน้าจอ: แตะตรงไหนก็ได้ 1 ครั้ง = ปลดล็อกเสียง
   - [data-sound-banner] แถบเตือน "แตะเพื่อเปิดเสียง" แสดงจนกว่าเสียงจะพร้อม (ครัว/ไรเดอร์)
     (เหมือนระบบเดิม) ปุ่ม "เปิดเสียง" ยังมีไว้ให้กดเปิด/ปิดเองได้
   - play(type, {loop}) เล่นครั้งเดียวหรือวนจนกว่าจะ stop(type) เช่น ไรเดอร์มีงานใหม่ดังวนจนกดรับ
   - ปิดเสียงเองแล้วจำไว้ในเครื่อง (localStorage) เปิดหน้าใหม่ไม่ดังขึ้นมาเอง */
(function () {
  var PATHS = { order: '/static/sounds/bell-order.mp3', rider: '/static/sounds/bell-rider.mp3', customer: '/static/sounds/bell-customer.mp3' };
  var cache = {};
  var unlocked = false;
  var listeners = [];
  var MUTE_KEY = 'tmpp-sound-muted';

  function readMuted() { try { return localStorage.getItem(MUTE_KEY) === '1'; } catch (e) { return false; } }
  var muted = readMuted();

  function audio(type) {
    if (!cache[type]) {
      // ใช้ไฟล์จาก <audio data-sound="..."> ในหน้าถ้ามี (ได้ชื่อไฟล์แบบมี hash จาก collectstatic)
      var el = document.querySelector('audio[data-sound="' + type + '"]');
      cache[type] = el || new Audio(PATHS[type]);
      cache[type].preload = 'auto';
    }
    return cache[type];
  }

  function notify() { listeners.forEach(function (fn) { fn(api.enabled()); }); }

  // iPhone (Safari/แอปบนหน้าจอโฮม) ปลดล็อกเสียง "ทีละไฟล์" และต้องเล่นแบบไม่ปิดเสียง ภายในการแตะจริงเท่านั้น
  // (เล่นแบบ muted เบราว์เซอร์ยอมเสมอ จึงไม่ได้ปลดล็อกอะไร = สาเหตุที่ครัว/ไรเดอร์ไม่ได้ยินในรอบแรก)
  // ต้องเรียก play() แบบ synchronous ในตัวจัดการ click/touchend/keydown ห้ามรอ promise อื่นก่อน
  function unlock() {
    if (unlocked) return Promise.resolve(true);
    var elements = Array.prototype.slice.call(document.querySelectorAll('audio[data-sound]'));
    if (!elements.length) elements = [audio('order')];
    var attempts = elements.map(function (el) {
      cache[el.dataset.sound || 'order'] = el;
      el.muted = false;
      var result;
      try { result = el.play(); } catch (e) { return Promise.resolve(false); }
      return Promise.resolve(result).then(function () { el.pause(); el.currentTime = 0; return true; })
        .catch(function () { return false; });
    });
    return Promise.all(attempts).then(function (results) {
      unlocked = results.every(Boolean);
      notify();
      return unlocked;
    });
  }

  // pointerdown/touchstart บนมือถือไม่นับเป็น "การกด" สำหรับเสียง ต้องเป็น click / touchend / keydown
  var UNLOCK_EVENTS = ['click', 'touchend', 'keydown'];
  function onFirstInteraction() {
    unlock().then(function (ok) {
      if (!ok) return;
      UNLOCK_EVENTS.forEach(function (name) { document.removeEventListener(name, onFirstInteraction, true); });
    });
  }
  UNLOCK_EVENTS.forEach(function (name) { document.addEventListener(name, onFirstInteraction, true); });

  var api = {
    enabled: function () { return unlocked && !muted; },
    play: function (type, opts) {
      if (!api.enabled()) return Promise.resolve(false);
      var a = audio(type);
      a.loop = !!(opts && opts.loop);
      a.currentTime = 0;
      return a.play().then(function () { return true; }).catch(function () { return false; });
    },
    stop: function (type) {
      var a = cache[type];
      if (a) { a.pause(); a.currentTime = 0; a.loop = false; }
    },
    stopAll: function () { Object.keys(cache).forEach(api.stop); },
    setMuted: function (value) {
      muted = value;
      try { localStorage.setItem(MUTE_KEY, value ? '1' : '0'); } catch (e) { /* โหมดส่วนตัว: ไม่จำก็ได้ */ }
      if (value) api.stopAll();
      notify();
    },
    // ปุ่มเปิด/ปิดเสียง: ยังไม่ปลดล็อก -> ปลดล็อก · ปลดล็อกแล้ว -> สลับปิด/เปิด
    toggle: function () {
      if (!unlocked) { muted = false; api.setMuted(false); return unlock(); }
      api.setMuted(!muted);
      return Promise.resolve(api.enabled());
    },
    onChange: function (fn) { listeners.push(fn); fn(api.enabled()); },
  };

  // ปุ่ม [data-sound-toggle] ทุกหน้าใช้ร่วมกัน
  function bindButtons() {
    var buttons = document.querySelectorAll('[data-sound-toggle]');
    buttons.forEach(function (btn) {
      btn.addEventListener('click', function () { api.toggle(); });
    });
    var banners = document.querySelectorAll('[data-sound-banner]');
    banners.forEach(function (b) { b.addEventListener('click', function () { muted = false; api.setMuted(false); unlock(); }); });
    api.onChange(function (on) {
      banners.forEach(function (b) { b.classList.toggle('d-none', on); });
      buttons.forEach(function (btn) {
        btn.setAttribute('aria-pressed', on ? 'true' : 'false');
        btn.setAttribute('aria-label', on ? 'เสียงเปิดอยู่ (กดเพื่อปิด)' : 'เปิดเสียง');
        btn.title = on ? 'เสียงเปิดอยู่ (กดเพื่อปิด)' : 'เปิดเสียง';
        btn.classList.toggle('btn-primary', !on);
        btn.classList.toggle('btn-outline-ink', on);
        var icon = btn.querySelector('i');
        var label = btn.querySelector('[data-sound-label]');
        if (icon) icon.className = on ? 'bi bi-volume-up' : 'bi bi-volume-mute';
        if (label) label.textContent = on ? 'เสียงเปิดอยู่' : 'เปิดเสียง';
      });
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bindButtons); else bindButtons();

  window.TmppSound = api;
})();
