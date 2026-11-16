# TMPP — แผนสร้างระบบสั่งอาหารและส่งอาหารใหม่

> วันที่: 17/11/2569 · สถานะ: M0-M9 เสร็จ · M10 ขั้นที่ 1 ออนไลน์ที่ http://177.202.247.183:8080 · เหลือโดเมน + HTTPS
> ของเดิม: `~/Documents/food` (Django 5 + DRF + Next.js 15) · ของใหม่: `~/Documents/foodnes`

---

## 1. สิ่งที่เปลี่ยนจากระบบเดิม

| เรื่อง | ระบบเดิม | ระบบใหม่ |
|---|---|---|
| หน้าเว็บ | Next.js บน Vercel แยกจาก API | Django Templates + HTMX + Alpine.js + Bootstrap 5.3.8 (self-hosted) |
| โดเมน | 2 ที่ (Vercel + `api.tmth-th.com`) ต้องเปิด CORS | โดเมนเดียว ไม่มี CORS |
| ล็อกอิน | JWT เก็บฝั่ง client + refresh | Django session cookie (HttpOnly, Secure) |
| รูปแบบธุรกิจ | เริ่มจาก marketplace แล้วค่อยปิดด้วย setting | ร้านเดียว เจ้าของคนเดียว (เพิ่มสาขาได้ในอนาคต) ไม่มีโค้ด marketplace ติดมา |
| ตรวจสลิป | เรียก EasySlip ระหว่าง request | ส่งให้ Celery ทำเบื้องหลัง หน้าเว็บถามผลด้วย HTMX |
| ตั้งค่า | `settings.py` ไฟล์เดียว | `settings/base.py`, `local.py`, `production.py` |
| หลังบ้าน | หน้า admin ใน Next.js + API | Console ของเจ้าของร้าน (Django Template + Bootstrap) ไม่ใช้ Django Admin กับผู้ใช้ทั่วไป |

**ของเดิมที่ยกมาใช้ (เขียนใหม่ให้เข้าโครงสร้าง services/selectors):**
- สูตรค่าส่ง + ระยะทางด้วย PostGIS (`orders/services.py`: `compute_delivery_fee`, `calculate_order_quote`, `transition_order`)
- ตรวจสลิป EasySlip V2 (เช็คชื่อผู้รับ + บัญชี + ยอด + สลิปซ้ำ) และคิวให้แอดมินตรวจเอง (`payments/services.py`)
- QR พร้อมเพย์ (`payments/promptpay.py`)
- พิกัดไรเดอร์แบบสดใน Redis (`riders/live_location.py`)
- FCM (`notifications/fcm.py`) และ service worker
- บันทึกการแก้ไขของแอดมิน (`backoffice/audit.py`)
- Deploy บน VPS ด้วย Caddy (HTTPS อัตโนมัติ) + docker compose (`backend/deploy/`)

**ของเดิมที่ไม่ยกมา:** ใบสมัครร้าน/ไรเดอร์, OnboardingIntent, RoleChangeRequest, GP ของร้าน, คำขอเปลี่ยนบัญชีร้าน, ส่วนแบ่งแพลตฟอร์ม, LINE webhook ที่ค้างอยู่, Tailwind, sweetalert2

---

## 2. โครงสร้างระบบ

```
ผู้ใช้ทุกบทบาท (มือถือ / คอม)
        │ HTTPS โดเมนเดียว
        ▼
     Caddy  ── เสิร์ฟ /static/ และ /media/ เอง
        │      /media/private/ (สลิป, หลักฐานส่ง) ส่งผ่าน Django ตรวจสิทธิ์ก่อน
        ▼
     Django (gunicorn)  ── หน้าเว็บ (Templates + HTMX) และ API เล็กน้อยสำหรับ JS
        │
        ├── PostgreSQL 16 + PostGIS   ข้อมูลหลัก ระยะทาง
        ├── Redis                     cache, พิกัดไรเดอร์ล่าสุด, broker ของ Celery
        └── Celery worker + beat      ตรวจสลิป, ส่ง FCM, งานตามเวลา
```

**เรียลไทม์:** ใช้ HTMX ถามซ้ำ (polling) ทุก 5 วินาทีเฉพาะหน้าที่ต้องการ และหยุดเมื่อแท็บถูกซ่อน
เหตุผล: มีไรเดอร์ 1 คนและครัว 1 จอ polling เพียงพอและดูแลง่ายที่สุด ถ้าวันหน้ามีหลายสาขาหลายไรเดอร์ ค่อยเพิ่ม Django Channels เฉพาะจุด

**URL ใต้โดเมนเดียว**

| Path | ใคร | หน้าที่ |
|---|---|---|
| `/` | ทุกคน | หน้าร้าน ดูเมนู |
| `/cart/`, `/checkout/` | ลูกค้า | ตะกร้า ปักหมุดที่อยู่ ทวนออเดอร์ |
| `/orders/<id>/` | ลูกค้า | จ่ายเงิน (QR + แนบสลิป) ติดตามสถานะ แผนที่ไรเดอร์ |
| `/account/` | ลูกค้า | โปรไฟล์ ที่อยู่ ประวัติออเดอร์ |
| `/kitchen/` | ครัว | จอ KDS รับออเดอร์ เปลี่ยนสถานะ เปิด/ปิดร้าน |
| `/rider/` | ไรเดอร์ | แผนที่เต็มจอ การ์ดงาน นำทาง ถ่ายหลักฐานส่ง |
| `/console/` | เจ้าของร้าน | ภาพรวม ออเดอร์ สลิป เมนู ผู้ใช้ สาขา บันทึกการแก้ไข |
| `/auth/` | ทุกคน | ล็อกอิน สมัคร Google |
| `/api/v1/` | JS ในหน้าเว็บ | ส่งพิกัดไรเดอร์, ลงทะเบียน FCM token, ดึงพิกัดติดตาม |
| `/django-admin/` | นักพัฒนา | Django Admin ปิดใน production หรือจำกัด IP |

---

## 3. ข้อตัดสินใจ (ตอบแล้ว 16/11/2569)

| ข้อ | เลือก | ผลต่อการออกแบบ |
|---|---|---|
| D1 ข้อมูลเดิม | **เริ่มใหม่ทั้งหมด** | ฐานข้อมูลใหม่ volume ใหม่ ไม่แตะฐานข้อมูลของระบบเดิม ไม่มีคำสั่ง import |
| D2 ล็อกอินลูกค้า | **Google + อีเมล/รหัสผ่าน** | ไม่ทำ LINE Login และไม่ทำสั่งแบบไม่สมัคร |
| D3 เงินไรเดอร์ | **บันทึกค่าส่งส่วนของไรเดอร์ในระบบ** | `Order.rider_fee` + หน้าสรุปใน Console เจ้าของร้านตัดสินใจจ่ายเอง (ระบบไม่โอนเงิน) |
| D4 โดเมน | **`tmth-th.com`** | ระบบเดิม `api.tmth-th.com` เปิดคู่ได้จนถึง M10 |
| D5 แบรนด์ | **TMPP** ยังไม่มีโลโก้ ให้ออกแบบให้ | โลโก้ SVG สีพื้นเรียบ (M0) |
| ธีม | **ตามเว็บเซ้งร้านด่วน** (`~/Documents/เซ้งร้าน/proptech`) | header ขาว, สีหลักชมพู `#e11d74`, ปุ่มหลักสีเขียว `#00C274`, การ์ดมุมโค้ง, แถบเมนูล่างบนมือถือ, Console มี sidebar · **ไม่เอา** gradient, อิโมจิ, Tailwind CDN, animation กระดุกกระดิก |

## 4. โครงสร้างโฟลเดอร์

```
foodnes/
├── CLAUDE.md                    กฎการเขียนโค้ดของโปรเจกต์
├── PLAN.md                      ไฟล์นี้
├── docs/modules/                1 โมดูล = 1 ไฟล์ .md
├── manage.py
├── requirements/
│   ├── base.txt
│   ├── local.txt
│   └── production.txt
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── local.py
│   │   └── production.py
│   ├── urls.py
│   ├── celery.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── core/            โมเดลฐาน (UUID, timestamps), decorators สิทธิ์, เงิน/พิกัด utils
│   ├── accounts/        User, บทบาท, ล็อกอิน, ที่อยู่ลูกค้า
│   ├── catalog/         Branch, Category, MenuItem, MenuOption
│   ├── orders/          Order, OrderItem, OrderStatusLog, ตะกร้า, ค่าส่ง
│   ├── payments/        SlipTransaction, QR พร้อมเพย์, EasySlip
│   ├── delivery/        RiderProfile, DeliveryProof, พิกัดสด
│   ├── notifications/   DeviceToken, Notification, FCM
│   └── console/         หน้าเจ้าของร้าน + AuditLog (เรียก service ของ app อื่น)
│
│   แต่ละ app มีโครงเดียวกัน:
│   ├── models.py
│   ├── services/        งานเขียนข้อมูล / หลายขั้นตอน
│   ├── selectors/       งานอ่านข้อมูลที่ซับซ้อน
│   ├── views.py         รับ request → เรียก service/selector → render
│   ├── forms.py
│   ├── urls.py
│   ├── tasks.py         Celery (ถ้ามี)
│   └── tests/
├── templates/
│   ├── base.html
│   ├── layouts/         customer.html, kitchen.html, rider.html, console.html
│   ├── components/      ปุ่ม การ์ด badge สถานะ ที่ใช้ซ้ำ
│   └── <app>/           หน้าและ partial ของแต่ละ app (partial ขึ้นต้นด้วย _)
├── static/
│   ├── vendor/          bootstrap-5.3.8, bootstrap-icons, htmx, alpinejs (ไฟล์จริง ไม่ใช้ CDN)
│   ├── css/tmpp.css     ตัวแปรสี ฟอนต์ ปรับแต่ง Bootstrap
│   └── js/              rider-location.js, tracking-map.js, fcm.js, address-picker.js
├── deploy/
│   ├── Caddyfile
│   └── docker-compose.prod.yml
├── docker-compose.yml           สำหรับพัฒนาบนเครื่อง (PostGIS, Redis)
├── Dockerfile
└── .env.example
```

---

## 5. โมเดลข้อมูลหลัก

```
User (UUID, email, google_id, display_name, phone, role: CUSTOMER | KITCHEN | RIDER | OWNER)
 ├── CustomerAddress (label, address_text, location Point, is_default)
 ├── RiderProfile    (vehicle_plate, is_online, current_location Point)
 └── DeviceToken     (fcm_token, platform, is_active)

Branch (name, phone, address, location Point, is_open, is_active, promptpay_id)
 ├── Category (name, sort_order)
 └── MenuItem (name, price, image, is_available, category)
       └── MenuOption (name, extra_price)

Order (order_number, customer, branch, rider, status, subtotal, delivery_fee, total,
       address snapshot, delivery_location Point, distance_km, note, rider_fee*)
 ├── OrderItem       (snapshot ชื่อ ราคา ตัวเลือก ณ ตอนสั่ง)
 ├── OrderStatusLog  (from, to, actor, role, note)
 ├── SlipTransaction (attempt_no, image (private), status, provider_ref, amount, reason)
 └── DeliveryProof   (photo (private), created_at)

AuditLog (actor, action, target, before/after JSON, ip)
```
`rider_fee*` = ค่าส่งส่วนของไรเดอร์ตามสูตร (D3) ใช้สรุปยอดใน Console

**สถานะออเดอร์:** `PENDING_PAYMENT → PAYMENT_REVIEW → PAID → PREPARING → READY → DELIVERING → COMPLETED` และ `CANCELLED` จากสถานะก่อน DELIVERING
(เพิ่ม `PAYMENT_REVIEW` ให้เห็นชัดว่าสลิปรอตรวจ ระบบเดิมไม่มีสถานะนี้)

---

## 6. แผนงานเป็นโมดูล

แต่ละโมดูลจบด้วยไฟล์ `docs/modules/module_XX_*.md` และผ่าน QA §7

| โมดูล | งาน | ผลที่ได้ (AC) |
|---|---|---|
| **M0 ฐานราก** | สร้างโปรเจกต์, แยก settings, docker-compose สำหรับพัฒนา, `core` app, base template + ตัวแปรสี/ฟอนต์, ย้าย Bootstrap เข้า `static/vendor/` | `runserver` ขึ้น, `check` ผ่าน, หน้าเปล่าใช้ Bootstrap จากเครื่องตัวเอง |
| **M1 บัญชีผู้ใช้** | User + บทบาท, ล็อกอินอีเมล + Google, decorators `role_required`, เจ้าของสร้างบัญชีครัว/ไรเดอร์ใน Console | แต่ละบทบาทเข้าได้เฉพาะหน้าของตัวเอง, test สิทธิ์ครบ |
| **M2 เมนู** | Branch, Category, MenuItem, MenuOption, หน้าร้านฝั่งลูกค้า, จัดการเมนูใน Console | ลูกค้าเห็นเมนูจัดหมวด, เจ้าของเพิ่ม/แก้/ปิดขายเมนูได้ |
| **M3 สั่งอาหาร** | ตะกร้า (session), ปักหมุดที่อยู่ (Google Maps), คิดค่าส่งด้วย PostGIS, หน้าทวนออเดอร์, สร้างออเดอร์ | ราคาและค่าส่งคิดฝั่งเซิร์ฟเวอร์เท่านั้น, เกินระยะสั่งไม่ได้ |
| **M4 ชำระเงิน** | QR พร้อมเพย์ตามยอด, แนบสลิป, Celery task เรียก EasySlip, โหมด HYBRID (EasySlip ล่ม → คิวเจ้าของ), หน้าตรวจสลิปใน Console | สลิปถูก → PAID เอง, ซ้ำ/ยอดไม่ตรง/ผู้รับไม่ตรง → ปฏิเสธ, timeout → คิวตรวจเอง |
| **M5 จอครัว** | `/kitchen/` คิวออเดอร์ (HTMX poll), รับ → ทำ → พร้อมส่ง, เสียงแจ้งเตือน, เปิด/ปิดร้าน | ออเดอร์ที่จ่ายแล้วขึ้นภายใน 5 วิ พร้อมเสียง |
| **M6 ไรเดอร์** | `/rider/` แผนที่เต็มจอ + การ์ดงาน, รับงาน, ไปถึงร้าน, รับอาหาร, นำทาง (เปิด Google Maps), ถ่ายรูปส่ง, ส่งพิกัดทุก 5 วิ + Wake Lock | พิกัดใน Redis อัปเดตขณะมีงาน, ส่งสำเร็จต้องมีรูปหลักฐาน |
| **M7 ติดตามออเดอร์** | หน้า `/orders/<id>/` แสดงสถานะ + แผนที่ไรเดอร์เฉพาะตอน DELIVERING, หมุดเลื่อนนุ่ม, แจ้งเมื่อพิกัดเก่า | ลูกค้าคนอื่นดูไม่ได้, ส่งเสร็จแล้วไม่คืนพิกัด |
| **M8 แจ้งเตือน FCM** | service worker ที่โดเมนเดียว, ลงทะเบียน token, แจ้ง: ออเดอร์ใหม่ (ครัว), สลิปรอตรวจ (เจ้าของ), งานใหม่ (ไรเดอร์), สถานะ (ลูกค้า) | ส่งผ่าน Celery ทั้งหมด, token เสียถูกปิดอัตโนมัติ |
| **M9 Console เจ้าของ** | ภาพรวมยอดวันนี้/7 วัน, ค้นหาออเดอร์, ยกเลิก/คืนเงิน (บันทึกเหตุผล), ผู้ใช้, สาขา, ไรเดอร์, บันทึกการแก้ไข, สรุปยอดไรเดอร์ (ตาม D3) | ทุกการแก้ไขมี AuditLog |
| **M10 ขึ้นระบบจริง** | Caddyfile โดเมนเดียว `tmth-th.com`, `docker-compose.prod.yml`, `check --deploy`, สำรองฐานข้อมูลรายวัน, ทดสอบมือถือจริง 2 เครื่อง | สั่ง → จ่าย → สลิปผ่าน → ครัวรับ → ไรเดอร์ส่ง → ลูกค้าเห็นแผนที่ ครบทั้งเส้น |

**ลำดับ:** M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 · M8 และ M9 ทำแทรกได้หลัง M4 · M10 ทำสุดท้าย

---

## 7. QA ทุกโมดูล

- `python manage.py check`, `makemigrations --check --dry-run`, `pytest` ผ่านทั้งชุด
- ไม่มี N+1: test สำคัญใช้ `assertNumQueries` (หน้าเมนู, คิวครัว, รายการออเดอร์ใน Console)
- หน้าเว็บ: ไม่มีอิโมจิ, ไม่มี gradient, ใช้สีพื้นเรียบ, กว้าง 375px ไม่ล้น
- ความปลอดภัย: ทุก view มีตรวจสิทธิ์, ไฟล์สลิปและรูปส่งของไม่เปิดเป็น public, ไม่มี secret ในโค้ด
- ทดสอบจริงบนมือถือ (GPS และ FCM ต้องใช้ HTTPS) — user ทดสอบหลัง deploy

---

## 8. ความเสี่ยง

| ความเสี่ยง | ผล | ทางรับมือ |
|---|---|---|
| ไรเดอร์ล็อกจอ / สลับแอป | หมุดหยุด | Wake Lock, ส่งพิกัดทันทีเมื่อกลับเข้าหน้า, แถบบอกอายุพิกัด |
| EasySlip ล่ม หรือโควต้าหมด | ลูกค้าจ่ายแล้วค้าง | HYBRID → คิวเจ้าของ + FCM แจ้งเจ้าของ |
| ค่า Google Maps เกินโควต้าฟรี | มีค่าใช้จ่าย | จำกัด key ตามโดเมน, budget alert, โหลดแผนที่เฉพาะ 3 หน้า (ปักหมุด, ไรเดอร์, ติดตาม) |
| HTMX polling หลายแท็บ | โหลดเซิร์ฟเวอร์ | หยุดเมื่อแท็บถูกซ่อน, partial เล็ก, ใช้ cache |
| สลับจากระบบเดิม | ลูกค้าสับสน / ข้อมูลหาย | เปิดคู่กันระหว่างพัฒนา, สลับโดเมนเมื่อผ่าน M10, สำรองฐานข้อมูลเดิมก่อน |

---

## 9. สิ่งที่ต้องเตรียม (user)

- Google Maps JavaScript API key จำกัด HTTP referrer เป็นโดเมนใหม่
- Firebase: ใช้โปรเจกต์เดิมได้ ต้องเพิ่มโดเมนใหม่ใน Authorized domains
- EasySlip API key (มีแล้ว) + ชื่อบัญชี/เลขบัญชี/พร้อมเพย์ของร้านสำหรับเช็คผู้รับ
- Google OAuth: เพิ่ม redirect URI ของโดเมนใหม่

## 10. บันทึกการทำงาน

| วันที่ | โมดูล | สรุป | ผลตรวจ |
|---|---|---|---|
| 16/11/2569 | แผน | สำรวจระบบเดิม (ถึง commit `eba521d`) และร่างแผนนี้ | — |
| 16/11/2569 | M0 | ฐานราก + ธีม TMPP ตามเว็บเซ้งร้านด่วน + โลโก้ (`docs/modules/module_00_foundation.md`) | AI: compile, อิโมจิ 0, render 4 หน้า 375/1024px ไม่ล้น · รอ user: check, pytest |
| 16/11/2569 | M0 (เครื่อง user) | รันบน localhost ไม่ใช้ Docker: PostgreSQL 17 Homebrew + cache ในหน่วยความจำ | check ok, pytest 8 passed |
| 16/11/2569 | M1 | บัญชีผู้ใช้ 4 บทบาท, ล็อกอิน/สมัคร/Google, หน้าแรกลูกค้า, บัญชีลูกค้า, หน้าไรเดอร์ + เปิด/ปิดรับงาน, Console จัดการพนักงาน + AuditLog (`docs/modules/module_01_accounts.md`) | pytest 43 passed, migrate บนเครื่องแล้ว, ตรวจในเบราว์เซอร์ |
| 16/11/2569 | M2+M3 | ร้าน/เมนู/ตัวเลือก, ตะกร้า, ค่าส่ง PostGIS, checkout + GPS/แผนที่, สร้างออเดอร์ + สถานะ, หน้าออเดอร์ลูกค้า, Console ร้าน/เมนู/ออเดอร์ (`docs/modules/module_02_menu_and_orders.md`) | pytest 98 passed, ทดสอบในเบราว์เซอร์ครบเส้นทาง, แก้บั๊ก 3 จุด |
| 16/11/2569 | M4 | QR พร้อมเพย์, แนบสลิป, ตรวจ EasySlip ใน Celery, คิวเจ้าของตรวจเอง, ไฟล์สลิปส่วนตัว, ยกเลิกออเดอร์ไม่จ่ายอัตโนมัติ (`docs/modules/module_03_payments.md`) | pytest 134 passed, ทดสอบแนบสลิป + อนุมัติในเบราว์เซอร์, แก้บั๊ก test เขียนไฟล์ลงโฟลเดอร์จริง |
| 16/11/2569 | M5 | จอครัว 3 คอลัมน์/แท็บ, รับ-พร้อม-ยกเลิก, เสียงกระดิ่ง + ดังซ้ำ, กันจอดับ, ปิดร้าน/เมนูหมดจากครัว (`docs/modules/module_04_kitchen.md`) | pytest 145 passed, ทดสอบแท็บเล็ต/จอใหญ่ + ออเดอร์ใหม่ขึ้นเองใน 6 วิ |
| 16/11/2569 | M6 (+M7 บางส่วน) | หน้าไรเดอร์: รับงาน/รับอาหาร/ส่งพร้อมรูป, นำทาง, เสียงงานใหม่, ส่ง GPS ทุก 5 วิ + กันจอดับ · ลูกค้าเห็นระยะไรเดอร์ + อายุตำแหน่ง (`docs/modules/module_05_rider.md`) | pytest 164 passed, ทดสอบจอมือถือครบเส้นทาง + รูปไม่หายระหว่างรีเฟรช |
| 17/11/2569 | M9 | ค่าส่งไรเดอร์ + บันทึกจ่าย, ลูกค้า + ปิดบัญชี, หน้าบันทึกการแก้ไข, ยอดขาย 7 วัน + เมนูขายดี, ดาวน์โหลด CSV (`docs/modules/module_06_console.md`) | pytest 180 passed, ทดสอบในเบราว์เซอร์ + มือถือ, ไม่มีลิงก์ว่างในเมนู |
| 17/11/2569 | M8 | แจ้งเตือนในเว็บ (กระดิ่ง + หน้าแจ้งเตือน) + push FCM ผ่าน Celery, ทุกเหตุการณ์ออเดอร์/สลิป/ไรเดอร์ใกล้ถึง, service worker, manifest (`docs/modules/module_07_notifications.md`) | pytest 198 passed, ทดสอบกระดิ่ง/หน้าแจ้งเตือนในเบราว์เซอร์ · รอค่า Firebase ทดสอบ push จริง |
| 17/11/2569 | M10 ขั้นที่ 1 | ขึ้น VPS ด้วย docker compose `tmpp-prod` + Caddy พอร์ต 8080 (80/443 เป็นของระบบเดิม), แก้ worker พังเพราะขาด `packaging` (`docs/modules/module_08_deploy.md`) | migrate ผ่าน, ทุก service ขึ้นค้าง, /healthz/ ok จากภายนอก, หน้าเว็บโหลดครบ |
