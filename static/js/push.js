/* เปิดแจ้งเตือน (FCM) ในเบราว์เซอร์
   - ปุ่ม [data-push-enable]: ขออนุญาต -> ลงทะเบียน service worker -> ขอ token -> ส่งให้เซิร์ฟเวอร์เก็บ
   - เคยอนุญาตแล้ว: ต่ออายุ token เงียบๆ ทุกครั้งที่เปิดเว็บ (token เปลี่ยนได้)
   - เปิดเว็บอยู่ (foreground): แสดงเป็น toast แทนแจ้งเตือนของระบบ
   iPhone: ต้อง "เพิ่มไปยังหน้าจอโฮม" ก่อน (iOS 16.4+) ถึงจะรับแจ้งเตือนได้ */
(function () {
  var configEl = document.getElementById('push-config');
  if (!configEl) return;
  var config = JSON.parse(configEl.textContent);
  var csrf = JSON.parse(document.body.getAttribute('hx-headers') || '{}')['X-CSRFToken'];
  var buttons = document.querySelectorAll('[data-push-enable]');
  var supported = 'Notification' in window && 'serviceWorker' in navigator && 'PushManager' in window;

  function setButtons(state, text) {
    buttons.forEach(function (btn) {
      btn.dataset.state = state;
      var label = btn.querySelector('[data-push-label]');
      if (label) label.textContent = text;
      btn.title = text; btn.setAttribute('aria-label', text);
      btn.disabled = state === 'on' || state === 'busy' || state === 'unsupported';
      btn.classList.toggle('btn-primary', state === 'off');
      btn.classList.toggle('btn-outline-ink', state !== 'off');
    });
  }

  async function firebaseMessaging() {
    var base = 'https://www.gstatic.com/firebasejs/' + config.sdkVersion + '/';
    var app = await import(base + 'firebase-app.js');
    var msg = await import(base + 'firebase-messaging.js');
    if (!(await msg.isSupported())) throw new Error('unsupported');
    var firebaseApp = app.initializeApp({
      apiKey: config.apiKey, authDomain: config.authDomain, projectId: config.projectId,
      messagingSenderId: config.messagingSenderId, appId: config.appId,
    });
    return { messaging: msg.getMessaging(firebaseApp), getToken: msg.getToken, onMessage: msg.onMessage };
  }

  async function registerToken() {
    var fb = await firebaseMessaging();
    var registration = await navigator.serviceWorker.register('/firebase-messaging-sw.js', { scope: '/' });
    var token = await fb.getToken(fb.messaging, { vapidKey: config.vapidKey, serviceWorkerRegistration: registration });
    if (!token) throw new Error('no token');
    var res = await fetch('/notifications/devices/', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify({ token: token }),
    });
    if (!res.ok) throw new Error('register failed');
    // เปิดเว็บอยู่: แสดง toast (เบราว์เซอร์ไม่แสดงแจ้งเตือนของระบบตอนแท็บเปิด)
    fb.onMessage(fb.messaging, function (payload) {
      var data = payload.data || {};
      document.dispatchEvent(new CustomEvent('tmpp:toast', { detail: { message: (data.title || '') + ' · ' + (data.body || ''), level: 'success' } }));
    });
    setButtons('on', 'แจ้งเตือนเปิดอยู่');
  }

  if (!supported) {
    var isIOS = /iPhone|iPad/.test(navigator.userAgent);
    setButtons('unsupported', isIOS ? 'iPhone: เพิ่มเว็บไปที่หน้าจอโฮมก่อน' : 'เบราว์เซอร์นี้ไม่รองรับแจ้งเตือน');
    return;
  }
  if (Notification.permission === 'denied') {
    setButtons('unsupported', 'ถูกปิดแจ้งเตือนไว้: เปิดในตั้งค่าเบราว์เซอร์');
    return;
  }
  if (Notification.permission === 'granted') {
    registerToken().catch(function () { setButtons('off', 'เปิดการแจ้งเตือน'); });
  } else {
    setButtons('off', 'เปิดการแจ้งเตือน');
  }

  buttons.forEach(function (btn) {
    btn.addEventListener('click', async function () {
      setButtons('busy', 'กำลังเปิด...');
      try {
        var permission = await Notification.requestPermission();
        if (permission !== 'granted') { setButtons('unsupported', 'ไม่ได้อนุญาตแจ้งเตือน'); return; }
        await registerToken();
      } catch (e) {
        setButtons('off', 'เปิดไม่สำเร็จ ลองใหม่');
      }
    });
  });
})();
