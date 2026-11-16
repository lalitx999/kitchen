# TMPP — ระบบสั่งอาหารและส่งอาหาร

ร้านเดียว เจ้าของคนเดียว ไรเดอร์ 1 คน (น้องชายเจ้าของ) รองรับเพิ่มสาขาในอนาคต
แผนงานทั้งหมดอยู่ใน `PLAN.md` · ระบบเดิมสำหรับอ้างอิงอยู่ที่ `~/Documents/food`
กฎการทำงานร่วมกับ AI: `.agents/rules/collaboration_rules.md` (สำคัญ: R0 = migration/database/production user รันเอง, AI บอกคำสั่ง terminal แต่ user รันเอง, 1 โมดูล = 1 ไฟล์ .md, อธิบายเป็นภาษาไทยพร้อมเหตุผล, เสนออย่างน้อย 2 ทางเลือก)

## Stack
- Django 5 · PostgreSQL + PostGIS · Redis · Celery
- หน้าเว็บ: Django Templates + HTMX + Alpine.js + Bootstrap 5.3.8 (self-hosted ใน `static/vendor/`) — **ห้ามใช้ Next.js / React / Tailwind**
- Firebase Cloud Messaging · Google Maps JavaScript API · ตรวจสลิปด้วย EasySlip V2
- โดเมนเดียว หลัง Caddy · ล็อกอินด้วย Django session (ไม่ใช้ JWT ในหน้าเว็บ)

## กฎหน้าเว็บ
- ห้ามใช้อิโมจิ ทั้งในหน้าเว็บ ข้อความแจ้งเตือน และโค้ด — ใช้ Bootstrap Icons (ไฟล์ในเครื่อง) แทน
- ห้ามใช้ gradient — ใช้สีพื้นเรียบ (solid) จากตัวแปรใน `static/css/tmpp.css` เท่านั้น
- ห้ามโหลด CSS/JS จาก CDN ยกเว้น Google Maps, Firebase SDK และ Google Sign-In (`accounts.google.com/gsi/client`)
- ต้องใช้งานได้ที่ความกว้าง 375px โดยไม่ล้นแนวนอน
- ไม่มีข้อมูลปลอม/พิกัดสำรอง — ถ้าไม่มีข้อมูลให้แสดงสถานะและวิธีแก้

## กฎการเขียนโค้ด

### 1. Database & ORM
- ห้าม `objects.all()` ใน view หรือ template โดยไม่จำเป็น
- ความสัมพันธ์ FK/M2M ต้องใช้ `select_related()` / `prefetch_related()` เสมอ
- ข้อมูลจำนวนมากใน template ใช้ `.only()` หรือ `.values()`
- ห้าม query ใน loop — ใช้ `bulk_create`, `bulk_update`, `update()`
- หน้าสำคัญ (เมนู, คิวครัว, รายการออเดอร์) ต้องมี test `assertNumQueries`

### 2. Architecture
- ห้ามเขียน business logic ซับซ้อนใน `views.py` หรือ `models.py`
- งานเขียนข้อมูล/หลายขั้นตอน → `apps/<app>/services/<name>_service.py`
- งานอ่านข้อมูลซับซ้อน → `apps/<app>/selectors/<name>_selector.py`
- View ทำแค่: รับ request → เรียก service/selector → render template หรือ return response
- app `console` ห้ามเข้าถึง model ของ app อื่นตรงๆ ให้เรียกผ่าน service/selector ของ app นั้น
- เงินใช้ `Decimal` เสมอ · ราคาและค่าส่งคิดฝั่งเซิร์ฟเวอร์เท่านั้น
- การเปลี่ยนสถานะออเดอร์ทำผ่าน `orders.services.order_service.transition_order()` ที่เดียว

### 3. งานเบื้องหลัง
- ห้ามทำงานนานใน request: เรียก API ภายนอก (EasySlip, FCM), ประมวลผลรูป, สร้าง PDF → Celery task
- ใน Celery task ใช้ `requests` (sync) พร้อม timeout เสมอ · ใน `async def` view ใช้ `httpx`
- task ต้อง idempotent (รันซ้ำได้ไม่เกิดผลซ้ำ) และเรียกด้วย `transaction.on_commit()`

### 4. สิทธิ์และหลังบ้าน
- ห้ามใช้ Django Admin กับผู้ใช้ทั่วไป · เจ้าของร้านใช้ `/console/` (Template + Bootstrap)
- ทุก view ต้องตรวจสิทธิ์ด้วย decorator ใน `apps/core/decorators.py` (เช่น `@role_required(Role.OWNER)`)
- ข้อมูลที่ผูกกับเจ้าของ (ออเดอร์ลูกค้า, งานไรเดอร์) ต้องกรองด้วยผู้ใช้ปัจจุบันใน selector ไม่ใช่แค่ซ่อนในหน้าเว็บ
- ไฟล์สลิปและรูปหลักฐานส่งเก็บใน private storage และส่งผ่าน view ที่ตรวจสิทธิ์
- ทุกการแก้ไขใน console บันทึก `AuditLog`

### 5. Config & Security
- settings แยก `config/settings/base.py`, `local.py`, `production.py`
- ข้อมูลลับผ่าน `django-environ` จาก `.env` เท่านั้น ห้าม hardcode · key ใหม่ต้องเพิ่มใน `.env.example` พร้อม comment ภาษาไทย
- production: `DEBUG=False`, Caddy เสิร์ฟ static/media, cookie `Secure` + `HttpOnly`, HSTS

## การตอบกลับ
- โค้ดพร้อมใช้ production · comment เฉพาะจุดสำคัญ · แยกไฟล์ชัดเจน
- อธิบายสั้นๆ เป็นภาษาไทยว่าทำไมเขียนแบบนี้ ให้สอดคล้องกับกฎข้างบน
