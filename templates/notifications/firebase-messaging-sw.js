/* Service worker: รับ push ตอนปิดแท็บ/ล็อกจอ แล้วแสดงแจ้งเตือนของระบบ · กดแล้วเปิดหน้าที่เกี่ยวข้อง
   สร้างจาก templates/notifications/firebase-messaging-sw.js (ค่าตั้งค่าใส่จากเซิร์ฟเวอร์) */
// ---- แอปบนหน้าจอโฮม: หน้า "ไม่มีอินเทอร์เน็ต" ----
// เก็บไว้แค่หน้า offline + ไอคอน · หน้าอื่นโหลดจากเซิร์ฟเวอร์เสมอ (ราคา/สถานะออเดอร์ต้องสดเสมอ ห้าม cache)
var OFFLINE_CACHE = 'tmpp-offline-v1';
var OFFLINE_URL = '/offline/';
self.addEventListener('install', function (event) {
  event.waitUntil(caches.open(OFFLINE_CACHE).then(function (cache) {
    return cache.addAll([OFFLINE_URL, '{{ offline_icon }}']);
  }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener('activate', function (event) {
  event.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k.indexOf('tmpp-offline-') === 0 && k !== OFFLINE_CACHE; })
      .map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});
self.addEventListener('fetch', function (event) {
  if (event.request.mode !== 'navigate') return;
  event.respondWith(fetch(event.request).catch(function () {
    return caches.match(OFFLINE_URL, { cacheName: OFFLINE_CACHE });
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
