/* Service worker: รับ push ตอนปิดแท็บ/ล็อกจอ แล้วแสดงแจ้งเตือนของระบบ · กดแล้วเปิดหน้าที่เกี่ยวข้อง
   สร้างจาก templates/notifications/firebase-messaging-sw.js (ค่าตั้งค่าใส่จากเซิร์ฟเวอร์) */
// รุ่นของไฟล์ static ชุดนี้: deploy ใหม่ -> เลขเปลี่ยน -> เบราว์เซอร์เห็นว่าไฟล์นี้เปลี่ยน -> ติดตั้ง service worker ตัวใหม่
// -> หน้าที่เปิดค้างอยู่ (จอครัว/ไรเดอร์) ขึ้นแถบ "มีเวอร์ชันใหม่" (app.js)
// assets: {{ asset_version }}

// ---- 1) หน้า "ไม่มีอินเทอร์เน็ต" ----
// หน้า HTML ทุกหน้าโหลดจากเซิร์ฟเวอร์เสมอ (ราคา/สถานะออเดอร์ต้องสดเสมอ ห้าม cache) เก็บไว้แค่หน้า offline
var OFFLINE_CACHE = 'tmpp-offline-v1';
var OFFLINE_URL = '/offline/';

// ---- 2) ไฟล์ static ที่มีเลข hash ในชื่อ (เช่น app.3f2a9c1b7d4e.js) ----
// ชื่อไฟล์เปลี่ยนทุกครั้งที่เนื้อหาเปลี่ยน (ManifestStaticFilesStorage) จึงเก็บในเครื่องได้ตลอดโดยไม่มีทางได้ของเก่า
// ไฟล์ที่ไม่มี hash (ตอนพัฒนาบนเครื่อง) ไม่เก็บ ไปเอาจากเซิร์ฟเวอร์ตามปกติ
var STATIC_CACHE = 'tmpp-static-v1';
var STATIC_MAX_FILES = 150;   // ไฟล์รุ่นเก่าที่ไม่ใช้แล้วถูกลบทิ้งเมื่อเกินจำนวนนี้ (เก่าสุดออกก่อน)
var HASHED_STATIC = /^\/static\/.+\.[0-9a-f]{12}\.[a-z0-9]+$/i;
var KEEP_CACHES = [OFFLINE_CACHE, STATIC_CACHE];

self.addEventListener('install', function (event) {
  event.waitUntil(caches.open(OFFLINE_CACHE).then(function (cache) {
    return cache.addAll([OFFLINE_URL, '{{ offline_icon }}']);
  }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener('activate', function (event) {
  event.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k.indexOf('tmpp-') === 0 && KEEP_CACHES.indexOf(k) === -1; })
      .map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

function trimStaticCache(cache) {
  return cache.keys().then(function (keys) {
    var extra = keys.length - STATIC_MAX_FILES;
    return Promise.all(keys.slice(0, Math.max(0, extra)).map(function (req) { return cache.delete(req); }));
  });
}

self.addEventListener('fetch', function (event) {
  var request = event.request;
  if (request.method !== 'GET') return;
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(function () {
      return caches.match(OFFLINE_URL, { cacheName: OFFLINE_CACHE });
    }));
    return;
  }
  var url = new URL(request.url);
  if (url.origin !== self.location.origin || !HASHED_STATIC.test(url.pathname)) return;
  event.respondWith(caches.open(STATIC_CACHE).then(function (cache) {
    return cache.match(request).then(function (hit) {
      if (hit) return hit;
      return fetch(request).then(function (response) {
        if (response.ok) {
          // เก็บหลังส่งให้หน้าเว็บแล้ว ไม่ทำให้หน้าเว็บรอ · waitUntil กัน service worker หลับก่อนเก็บเสร็จ
          var saving = cache.put(request, response.clone()).then(function () { return trimStaticCache(cache); });
          try { event.waitUntil(saving); } catch (e) { /* เบราว์เซอร์เก่า: เก็บต่อเองได้ */ }
        }
        return response;
      });
    });
  }));
});

{% if config %}
importScripts('https://www.gstatic.com/firebasejs/{{ config.sdkVersion }}/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/{{ config.sdkVersion }}/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: '{{ config.apiKey|escapejs }}',
  authDomain: '{{ config.authDomain|escapejs }}',
  projectId: '{{ config.projectId|escapejs }}',
  messagingSenderId: '{{ config.messagingSenderId|escapejs }}',
  appId: '{{ config.appId|escapejs }}',
});
// webpush.notification จากเซิร์ฟเวอร์ถูกแสดงอัตโนมัติ (มี icon + ลิงก์) ไม่ต้องสร้างซ้ำที่นี่
firebase.messaging();
{% endif %}

self.addEventListener('notificationclick', function (event) {
  var url = (event.notification.data && event.notification.data.FCM_MSG && event.notification.data.FCM_MSG.data && event.notification.data.FCM_MSG.data.url) || '/';
  event.notification.close();
  event.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].url.indexOf(self.location.origin) === 0 && 'focus' in list[i]) { list[i].navigate(url); return list[i].focus(); }
    }
    return clients.openWindow(url);
  }));
});
