# Module 08 — ขึ้น server (M10 ในแผน) · ขั้นที่ 1: เปิดด้วย IP

> วันที่: 17/11/2569 · สถานะ: **ออนไลน์ที่ https://tmth-th.com** (ใช้คู่กับระบบเดิม) · เหลือขั้นที่ 3 ปิดระบบเดิม

## 1. สิ่งที่อยู่บน server
- Hostinger VPS (`srv2156478`) · โค้ดที่ `/root/kitchen` (clone จาก GitHub `lalitx999/kitchen`) · รันด้วย root
- Docker compose project **`tmpp-prod`** แยกจากระบบเดิม `foodrider-*` ทั้งหมด (คอนเทนเนอร์ / volume / network / ฐานข้อมูล)
- พอร์ต **8080 / 8443** เพราะ 80/443 เป็นของ Caddy ระบบเดิม (`api.tmth-th.com` ยังทำงานปกติ)

| service | หน้าที่ |
|---|---|
| `caddy` | หน้าสุด: เสิร์ฟ `/static/` `/media/` ส่งที่เหลือให้ web · ขั้นที่ 2 ออก HTTPS เอง |
| `web` | gunicorn 3 workers · `collectstatic` ทุกครั้งที่เริ่ม · healthcheck `/healthz/` |
| `worker` | Celery: ตรวจสลิป EasySlip, ส่ง push |
| `beat` | Celery beat: ยกเลิกออเดอร์ไม่จ่ายทุก 1 นาที |
| `db` | PostgreSQL 16 + PostGIS (ไม่เปิดออกภายนอก) |
| `redis` | cache, พิกัดไรเดอร์สด, broker (ไม่เปิดออกภายนอก) |

## 2. ไฟล์ที่เพิ่ม
- `deploy/docker-compose.prod.yml`, `deploy/Caddyfile`, `deploy/env.production.example`, `deploy/backup.sh`
- `config/settings/production.py`: สวิตช์ `HTTPS_ENABLED` (ปิด = ล็อกอินผ่าน HTTP ได้ เพราะ cookie ไม่บังคับ Secure) · `localhost` อยู่ใน ALLOWED_HOSTS ให้ healthcheck
- `Dockerfile`: สร้างโฟลเดอร์ static/media ให้ user `app` เขียนได้
- `.gitignore`: `secrets/` (ไฟล์ service account บน server)

## 3. ผลตรวจ
- เครื่องพัฒนา (ค่า production): `collectstatic` แบบ Manifest 244 ไฟล์, `check --deploy` (เหลือคำเตือนที่ตั้งใจ: HTTP ในขั้นที่ 1 / HSTS subdomain เพราะ `api.` ยังอยู่), หน้าเว็บ render ได้ + 404 + host แปลกได้ 400 + ไม่มี Secure cookie ตอน HTTP
- **บน server:** `migrate` ผ่านทุกตาราง · ทุก service `Up` ค้าง · web `healthy`
- **จากภายนอก:** `/healthz/` → `{"ok": true, "database": true, "cache": true}` · หน้าแรก/ล็อกอิน 0.15–0.23 วิ · static มี hash เสิร์ฟจาก Caddy · HTMX/Alpine/ไอคอน/ฟอนต์ไทยโหลดครบ · มือถือไม่ล้น
- ระบบเดิม `api.tmth-th.com` ยังตอบปกติ

### ปัญหาที่เจอ และแก้แล้ว
1. **พอร์ต 80/443 ชนระบบเดิม** → ใช้ 8080/8443 (`HTTP_PORT`, `HTTPS_PORT` ใน `.env`)
2. **worker/beat รีสตาร์ตวน `ModuleNotFoundError: packaging`** — kombu (Celery↔Redis) ต้องใช้แต่ไม่ได้ประกาศ · บนเครื่องพัฒนามีเพราะ pytest ติดตั้งมาให้ → เพิ่ม `packaging` ใน `requirements/base.txt` · ตรวจด้วย venv ใหม่ที่มีแค่แพ็กเกจ production
3. **รหัสลับที่สร้างถูกวางในแชท** → สร้างใหม่ด้วยสคริปต์ที่เขียนลง `.env` ตรงๆ ไม่แสดงบนจอ + `chmod 600 .env`

### คำเตือนที่ยังอยู่ (ยอมรับได้)
- `gis.W001` GDAL 3.6 (Debian bookworm) — เตือนเรื่องอ่าน spatial reference จากข้อมูลไม่น่าเชื่อถือ · ระบบสร้างพิกัดจากตัวเลข lat/lng เท่านั้น · แก้ได้โดยเปลี่ยน image เป็น Debian trixie (GDAL 3.10) ภายหลัง

## 4. คำสั่งที่ใช้บ่อยบน server (`cd ~/kitchen` ก่อน)
```
alias dc='docker compose -f deploy/docker-compose.prod.yml --env-file .env'
dc ps                                   # สถานะ
dc logs web --tail 50                   # log
git pull && dc up -d --build            # อัปเดตโค้ด
dc exec web python manage.py migrate    # หลังอัปเดตที่มี migration (R0)
bash deploy/backup.sh                   # สำรองทันที
```

## 5. ยังต้องทำ (user)
- `create_owner` สร้างบัญชีเจ้าของร้าน → ตั้งข้อมูลร้าน/พิกัด/เมนูที่ `/console/`
- ตั้ง cron สำรองข้อมูลทุกคืน (`deploy/backup.sh`)
- ส่งไฟล์ service account ไป `~/kitchen/secrets/` + ใส่ค่า `FIREBASE_*` ใน `.env` (ถ้าต้องการ push)
- ใส่ค่าพร้อมเพย์ / บัญชี / EasySlip ใน `.env` แล้ว `dc up -d`

## 6. ขั้นที่ 2: โดเมน `tmth-th.com` + HTTPS — แผนที่เลือก (17/11/2569)
user เรียงงาน: (1) โดเมน (2) คีย์ที่เหลือ (3) ทดสอบจริง + ปิดระบบเดิม → ช่วงนี้ **ใช้คู่กับระบบเดิม**

```
ลูกค้า ──HTTPS──> Caddy ระบบเดิม (ถือ 443, ขอใบรับรอง tmth-th.com)
                   ├─ api.tmth-th.com ──> ระบบเดิม (เหมือนเดิม)
                   └─ tmth-th.com ──────> 177.202.247.183:8080 ──> Caddy ระบบใหม่ ──> Django
```
- DNS (17/11): `tmth-th.com` → `2.57.91.91` (Hostinger hcdn) · NS `dns-parking.com` · ไม่มี MX / AAAA / CAA → แก้แค่ A record ปลอดภัย
- Caddy ระบบใหม่ `trusted_proxies` (ค่า `TRUSTED_PROXIES`) ให้เชื่อ `X-Forwarded-Proto: https` จาก Caddy ระบบเดิม ไม่อย่างนั้น Django คิดว่าเป็น HTTP แล้ว redirect วน
- ระบบใหม่ `.env`: `HTTPS_ENABLED=True`, โดเมนใน `DJANGO_ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` / `SITE_URL`, `SITE_ADDRESS=:80` (HTTP ภายใน), พอร์ต 8080 เหมือนเดิม
- ขั้นที่ 3 ปิดระบบเดิม: ระบบใหม่ใช้ `HTTP_PORT=80`, `HTTPS_PORT=443`, `SITE_ADDRESS=tmth-th.com, www.tmth-th.com` แล้ว Caddy ระบบใหม่ขอใบรับรองเอง

### ทางเลือกเดิม (อ้างอิง)
ต้องตัดสินใจก่อน เพราะ Caddy ระบบเดิมถือพอร์ต 80/443 อยู่:
- **A. ปิดระบบเดิม** แล้วให้ระบบใหม่ใช้ 80/443 (`HTTP_PORT=80`, `HTTPS_PORT=443`) — ง่ายสุด ถ้าเลิกใช้ระบบเดิมแล้ว
- **B. ให้ Caddy ระบบเดิมส่งต่อ** `tmth-th.com` มาที่ `:8080` — ใช้คู่กันได้ระหว่างเปลี่ยนผ่าน
จากนั้นใน `.env`: `SITE_ADDRESS`, `HTTPS_ENABLED=True`, `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL` เป็นโดเมน · เพิ่มโดเมนใน Google OAuth / Maps key / Firebase authorized domains

## 7. คำถามทบทวน (กฎข้อ 8)
1. ทำไมช่วงที่ยังเป็น HTTP ต้องตั้ง `HTTPS_ENABLED=False` ไม่อย่างนั้นจะเกิดอะไรกับการล็อกอิน
2. ทำไม worker พังบน server แต่บนเครื่องพัฒนาไม่พัง และกันปัญหาแบบนี้ในอนาคตได้อย่างไร
3. ถ้า server ดับแล้วเปิดใหม่ ระบบจะกลับมาทำงานเองไหม เพราะอะไร

## 8. บันทึก: ขั้นที่ 2 โดเมนเสร็จ (17/11/2569)
- DNS `tmth-th.com` → `177.202.247.183` (แก้ใน Hostinger) · ทั้ง 1.1.1.1 / 8.8.8.8 / NS ของ Hostinger ตอบตรง
- Caddy ระบบเดิม (`/home/deploy/foodrider/deploy/Caddyfile`, สำรองไว้ที่ `.bak-20261117`) เพิ่ม `tmth-th.com` → `177.202.247.183:8080` และ `www` → redirect 301
- ระบบใหม่ `.env`: `HTTPS_ENABLED=True`, โดเมนใน ALLOWED_HOSTS / CSRF / SITE_URL, `TRUSTED_PROXIES=private_ranges 177.202.247.183`
- **ผลตรวจจากภายนอก:** ใบรับรอง Let's Encrypt (หมด 14 ก.พ. 2570 ต่ออายุเอง) · `/healthz/` ok · `www` 301 · `http` 308 · HSTS · cookie `Secure; HttpOnly` · เข้าด้วย IP ตรงได้ 400 · ปลอม `X-Forwarded-Proto` จากภายนอกไม่ได้ · `api.tmth-th.com` ยังทำงาน
- เจอระหว่างทาง: (1) placeholder path ไม่ได้แทนค่า → `cp` ล้ม ไม่มีอะไรเปลี่ยน (2) ข้อความ `www.` ที่คัดลอกจากแชทกลายเป็นลิงก์ markdown → ใช้สคริปต์ Python ประกอบชื่อโดเมนแทน (3) หน้าเว็บตอบ HEAD เป็น 405 (บอทตรวจสถานะ/พรีวิวลิงก์ใช้ HEAD) → เปลี่ยน `require_GET` เป็น `require_safe` ทุก view + test
