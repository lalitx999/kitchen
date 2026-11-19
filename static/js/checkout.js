/* หน้า checkout: หาพิกัดจัดส่ง (GPS / ที่อยู่เดิม / แผนที่) แล้วให้ HTMX คิดค่าส่ง
   ไม่มีพิกัดสำรอง: ถ้าหาตำแหน่งไม่ได้ แสดงวิธีแก้ ไม่เดาตำแหน่งให้

   แผนที่: หมุดอยู่กลางจอเสมอ ลูกค้าเลื่อนแผนที่ (นิ้วเดียว) ให้หมุดตรงบ้าน ปล่อยมือแล้วใช้จุดกลางจอ
   GPS: ฟังต่อเนื่องไม่เกิน 10 วินาที เลือกค่าที่แม่นที่สุด (ค่าแรกมักมาจาก Wi-Fi/เสาสัญญาณ คลาดเป็นร้อยเมตร) */
(function () {
  var GPS_WINDOW_MS = 10000;   // ฟัง GPS นานสุด
  var GPS_GOOD_M = 25;         // แม่นพอแล้ว หยุดฟังทันที
  var GPS_WARN_M = 150;        // คลาดมากกว่านี้ บอกให้เลื่อนแผนที่ปรับเอง
  var MAP_TIMEOUT_MS = 10000;  // แผนที่ยังไม่ขึ้น -> บอกทางอื่น

  var latInput = document.getElementById('id_latitude');
  var lngInput = document.getElementById('id_longitude');
  var statusEl = document.getElementById('location-status');
  var wrap = document.getElementById('pin-map');
  var map = null, accuracyCircle = null, userDragging = false, mapReady = false;
  var watchId = null, watchTimer = null, best = null;

  function setStatus(html) { statusEl.innerHTML = html; }
  function esc(n) { return Math.round(n); }

  function setLocation(lat, lng, source, opts) {
    latInput.value = Number(lat).toFixed(7);
    lngInput.value = Number(lng).toFixed(7);
    setStatus('<span class="text-action"><i class="bi bi-check-circle me-1"></i>ปักหมุดแล้ว' + (source ? ' (' + source + ')' : '') + '</span>');
    if (map && !(opts && opts.fromMap)) map.panTo({ lat: Number(lat), lng: Number(lng) });
    if (wrap) wrap.classList.add('has-pin');
    // ค่าส่งคิดหลังหยุดขยับ 350ms (hx-trigger delay) ไม่ยิงซ้ำทุกครั้งที่ลาก
    document.body.dispatchEvent(new CustomEvent('tmpp:location'));
  }

  // ---------------------------------------------------------------- GPS
  function stopGps() {
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    clearTimeout(watchTimer);
    watchId = null;
    document.querySelectorAll('[data-locating]').forEach(function (el) { el.classList.add('d-none'); });
    document.querySelectorAll('#use-my-location, #map-locate').forEach(function (b) { b.disabled = false; });
  }

  function showAccuracy(pos) {
    if (!map || !window.google) return;
    var center = { lat: pos.coords.latitude, lng: pos.coords.longitude };
    if (!accuracyCircle) {
      var brand = getComputedStyle(document.documentElement).getPropertyValue('--tm-brand').trim();
      accuracyCircle = new google.maps.Circle({ map: map, strokeColor: brand, strokeOpacity: .5, strokeWeight: 1,
        fillColor: brand, fillOpacity: .08, clickable: false });
    }
    accuracyCircle.setCenter(center);
    accuracyCircle.setRadius(pos.coords.accuracy);
  }

  function finishGps() {
    stopGps();
    if (!best) return;
    var acc = best.coords.accuracy;
    setLocation(best.coords.latitude, best.coords.longitude, 'GPS ±' + esc(acc) + ' ม.');
    if (acc > GPS_WARN_M) {
      setStatus('<span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>ตำแหน่งคลาดเคลื่อนประมาณ ' + esc(acc) +
        ' ม. เลื่อนแผนที่ให้หมุดตรงบ้าน หรือออกไปที่โล่งแล้วกดใหม่</span>');
    }
  }

  function locate() {
    if (!navigator.geolocation) {
      setStatus('<span class="text-danger">เบราว์เซอร์นี้หาตำแหน่งไม่ได้ ลองเปิดด้วย Chrome หรือ Safari หรือเลื่อนแผนที่ปักเอง</span>');
      return;
    }
    stopGps();
    best = null;
    document.querySelectorAll('[data-locating]').forEach(function (el) { el.classList.remove('d-none'); });
    document.querySelectorAll('#use-my-location, #map-locate').forEach(function (b) { b.disabled = true; });
    setStatus('<span class="text-muted-tm">กำลังหาตำแหน่ง... (ไม่เกิน 10 วินาที)</span>');
    watchId = navigator.geolocation.watchPosition(function (pos) {
      if (!best || pos.coords.accuracy < best.coords.accuracy) {
        best = pos;
        showAccuracy(pos);
        // เลื่อนแผนที่ตามค่าที่ดีขึ้น ระหว่างรอ (ถ้าลูกค้าไม่ได้กำลังลากอยู่)
        if (map && !userDragging) map.panTo({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setStatus('<span class="text-muted-tm">กำลังหาตำแหน่ง... ตอนนี้คลาด ±' + esc(pos.coords.accuracy) + ' ม.</span>');
      }
      if (best.coords.accuracy <= GPS_GOOD_M) finishGps();
    }, function (err) {
      stopGps();
      if (best) { finishGps(); return; }
      var msg = err.code === 1
        ? 'ยังไม่ได้อนุญาตให้ใช้ตำแหน่ง: เปิด "ตำแหน่ง" ให้เว็บนี้ในตั้งค่าเบราว์เซอร์ แล้วกดใหม่ (หรือเลื่อนแผนที่ปักเอง)'
        : 'หาตำแหน่งไม่สำเร็จ ลองเปิด GPS ของมือถือแล้วกดใหม่ หรือเลื่อนแผนที่ปักเอง';
      setStatus('<span class="text-danger">' + msg + '</span>');
    }, { enableHighAccuracy: true, timeout: GPS_WINDOW_MS, maximumAge: 0 });
    watchTimer = setTimeout(finishGps, GPS_WINDOW_MS);
  }

  document.getElementById('use-my-location').addEventListener('click', locate);
  var mapLocate = document.getElementById('map-locate');
  if (mapLocate) mapLocate.addEventListener('click', locate);

  document.querySelectorAll('[data-saved-address]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.getElementById('id_address_text').value = btn.dataset.text;
      var note = document.getElementById('id_address_note');
      if (note) note.value = btn.dataset.note || '';
      stopGps();
      setLocation(btn.dataset.lat, btn.dataset.lng, 'ที่อยู่เดิม');
    });
  });

  // กลับมาหน้านี้หลังฟอร์มไม่ผ่าน: มีพิกัดอยู่แล้ว -> คิดค่าส่งให้เลย
  document.addEventListener('DOMContentLoaded', function () {
    if (latInput.value && lngInput.value) {
      if (wrap) wrap.classList.add('has-pin');
      document.body.dispatchEvent(new CustomEvent('tmpp:location'));
    }
  });

  // ---------------------------------------------------------------- แผนที่เต็มจอ
  // ปุ่มย้อนกลับของมือถือ = ปิดเต็มจอ (ไม่ออกจากหน้าชำระเงิน)
  function setFullscreen(on) {
    if (!wrap) return;
    var isOn = wrap.classList.contains('is-fullscreen');
    if (on === isOn) return;
    wrap.classList.toggle('is-fullscreen', on);
    document.body.classList.toggle('pin-map-open', on);
    if (on) history.pushState({ tmppMap: true }, '');
    else if (history.state && history.state.tmppMap) history.back();
  }
  window.addEventListener('popstate', function () {
    if (wrap && wrap.classList.contains('is-fullscreen')) {
      wrap.classList.remove('is-fullscreen');
      document.body.classList.remove('pin-map-open');
    }
  });
  if (wrap) {
    document.getElementById('map-expand').addEventListener('click', function () { setFullscreen(!wrap.classList.contains('is-fullscreen')); });
    document.getElementById('map-confirm-btn').addEventListener('click', function () {
      if (map) {
        var c = map.getCenter();
        setLocation(c.lat(), c.lng(), 'หมุดบนแผนที่', { fromMap: true });
      }
      setFullscreen(false);
    });
  }

  // ---------------------------------------------------------------- Google Maps (มีเฉพาะเมื่อตั้ง GOOGLE_MAPS_API_KEY)
  function mapMessage(text) {
    var el = document.getElementById('map-msg');
    if (!el) return;
    el.textContent = text;
    el.classList.remove('d-none');
  }
  // คีย์ใช้ไม่ได้/โดเมนไม่ได้รับอนุญาต: Google เรียกฟังก์ชันนี้เอง
  window.gm_authFailure = function () {
    mapMessage('แผนที่ใช้ไม่ได้ตอนนี้ ใช้ปุ่ม "ใช้ตำแหน่งปัจจุบัน" หรือที่อยู่ที่เคยใช้แทนได้');
  };
  if (wrap) {
    setTimeout(function () {
      if (!mapReady) mapMessage('แผนที่โหลดช้า (เน็ตช้า?) ใช้ปุ่ม "ใช้ตำแหน่งปัจจุบัน" แทนได้');
    }, MAP_TIMEOUT_MS);
  }

  window.tmppInitAddressMap = async function () {
    var el = document.getElementById('address-map');
    if (!el || !window.google) return;
    var { Map } = await google.maps.importLibrary('maps');
    var start = latInput.value ? { lat: Number(latInput.value), lng: Number(lngInput.value) } : window.TMPP_SHOP;
    if (!start) { mapMessage('ร้านยังไม่ได้ตั้งพิกัด'); return; }
    map = new Map(el, {
      center: start, zoom: latInput.value ? 18 : 16, mapId: window.TMPP_MAP_ID || 'DEMO_MAP_ID',
      // นิ้วเดียวเลื่อนแผนที่ได้ (ไม่ต้องสองนิ้ว) · แผนที่อยู่ใน data-no-ptr จึงไม่ชนกับดึงเพื่อโหลดใหม่
      gestureHandling: 'greedy', clickableIcons: false,
      streetViewControl: false, mapTypeControl: false, fullscreenControl: false, zoomControl: false,
      keyboardShortcuts: false,
    });
    mapReady = true;
    var msg = document.getElementById('map-msg');
    if (msg) msg.classList.add('d-none');

    // ลูกค้าเลื่อนแผนที่เอง -> พอหยุด (idle) ใช้จุดกลางจอ · การเลื่อนจากโค้ด (GPS/ที่อยู่เดิม) ไม่นับ
    function userStarts() {
      userDragging = true;
      stopGps();
      if (accuracyCircle) { accuracyCircle.setMap(null); accuracyCircle = null; }
    }
    // นิ้วแตะแผนที่ (รวมถ่างสองนิ้วซูม ซึ่งไม่มี dragstart) = ลูกค้ากำลังปรับเอง
    el.addEventListener('pointerdown', userStarts);
    map.addListener('dragstart', function () { userStarts(); wrap.classList.add('is-dragging'); });
    map.addListener('dragend', function () { wrap.classList.remove('is-dragging'); });
    map.addListener('idle', function () {
      if (!userDragging) return;
      userDragging = false;
      // เต็มจอ: รอกด "ยืนยันตำแหน่งนี้" · แผนที่เล็ก: ใช้ทันที
      if (wrap.classList.contains('is-fullscreen')) return;
      var c = map.getCenter();
      // แตะเฉยๆ ไม่ได้เลื่อน (กลางจอยังเป็นจุดเดิม) -> ไม่ต้องคิดค่าส่งใหม่
      if (latInput.value && Math.abs(c.lat() - Number(latInput.value)) < 1e-6 && Math.abs(c.lng() - Number(lngInput.value)) < 1e-6) return;
      setLocation(c.lat(), c.lng(), 'หมุดบนแผนที่', { fromMap: true });
    });
  };
})();
