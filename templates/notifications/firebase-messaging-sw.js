/* Service worker: รับ push ตอนปิดแท็บ/ล็อกจอ แล้วแสดงแจ้งเตือนของระบบ · กดแล้วเปิดหน้าที่เกี่ยวข้อง
   สร้างจาก templates/notifications/firebase-messaging-sw.js (ค่าตั้งค่าใส่จากเซิร์ฟเวอร์) */
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
