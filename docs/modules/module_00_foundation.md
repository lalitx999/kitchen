# Module 00 — ฐานรากโปรเจกต์ + ธีม TMPP

> วันที่: 16/11/2569 · สถานะ: โค้ดเสร็จ รอ user ติดตั้งและรันตรวจ (ขั้นตอน §4)

## 1. ทำอะไรไปแล้ว

| ส่วน | ไฟล์ | ทำไม |
|---|---|---|
| Settings แยก 3 ไฟล์ | `config/settings/base.py`, `local.py`, `production.py` | ค่าร่วมอยู่ที่เดียว แต่ละ environment override เฉพาะที่ต่าง (กฎข้อ 5) |
| ข้อมูลลับจาก `.env` | `.env.example` | ไม่มี secret ในโค้ด ทุก key มี comment ภาษาไทย |
| Celery | `config/celery.py`, `config/__init__.py` | พร้อมสำหรับงานเบื้องหลัง (ตรวจสลิป, FCM) ตั้ง `acks_late` ให้งานไม่หายถ้า worker ตาย |
| Session แทน JWT | `base.py` | โดเมนเดียวใช้ cookie ของ Django ได้ ปลอดภัยกว่าเก็บ token ในเบราว์เซอร์ |
| `core` app | `apps/core/` | โมเดลฐาน UUID + timestamps, `role_required`, context แบรนด์, `/healthz/` |
| ตรวจสิทธิ์ | `apps/core/decorators.py` | ไม่ล็อกอิน → ไปหน้าล็อกอิน · ผิดบทบาท → 403 (ไม่ redirect วนลูป) |
| Health check | `/healthz/` ผ่าน `selectors/health_selector.py` | ให้ Caddy/Docker รู้ว่า DB + Redis พร้อม |
| ฐานข้อมูลใหม่ | `docker-compose.yml` | PostGIS 16 + Redis 7 ที่พอร์ต 5433/6380 ผูก 127.0.0.1 ใช้ volume ใหม่ `tmpp_pgdata` ไม่ชนระบบเดิม (D1) |
| Dockerfile | `Dockerfile` | image เดียวใช้ทั้ง web/worker/beat, มี GDAL สำหรับ PostGIS, ไม่รันด้วย root |
| ไลบรารีหน้าเว็บในเครื่อง | `static/vendor/`, `scripts/fetch_vendor.sh` | Bootstrap 5.3.8 ย้ายมาแล้ว · HTMX, Alpine, Bootstrap Icons, ฟอนต์ ดาวน์โหลดด้วยสคริปต์ (ล็อกเวอร์ชัน) |
| โลโก้ | `static/img/logo-mark.svg` | ชามข้าว + ไอน้ำ บนพื้นชมพูเรียบ ขอบชามสีส้ม ไม่มี gradient |
| ธีม | `static/css/tmpp.css` | ตามเว็บเซ้งร้านด่วน: header ขาว, ชมพู `#e11d74`, ปุ่มสั่งสีเขียว `#00c274`, ส้ม `#ff6b00`, การ์ดมุมโค้ง 1.5rem, ฟอนต์ Plus Jakarta Sans + Noto Sans Thai · เปลี่ยนสีทั้งเว็บที่ `:root` ที่เดียว |
| Layout ลูกค้า | `templates/layouts/customer.html` | header + ปุ่มตะกร้าสีเขียว + แถบเมนูล่างบนมือถือ + footer เข้ม |
| Layout Console | `templates/layouts/console.html` | แถบบนสีเข้ม + sidebar (จอใหญ่) / ปุ่ม 2 คอลัมน์ (มือถือ) เมนูที่เลือกพื้นดำ |
| หน้าตรวจธีม | `/dev/styleguide/`, `/dev/styleguide/console/` | รวมปุ่ม การ์ด สถานะออเดอร์ ฟอร์ม ตาราง เปิดเฉพาะ `DEBUG` |
| หน้า error | `templates/403.html`, `404.html`, `500.html` | 500 ไม่ extends layout เพราะ Django render โดยไม่มี context |
| Test | `apps/core/tests/test_core.py` | สิทธิ์ 5 กรณี, หน้าแรกมีชื่อแบรนด์, healthz, styleguide ปิดเมื่อไม่ DEBUG |

**ที่ไม่ยกมาจากธีมต้นแบบ:** gradient ของ banner/ปุ่ม VIP, อิโมจิ, animation กระดุกกระดิก, Tailwind CDN, Lucide/HTMX/Leaflet จาก unpkg

## 2. ผลตรวจที่ทำแล้ว (AI)
- `py_compile` ไฟล์ Python ทั้งหมด: ผ่าน
- ค้นหาอิโมจิทั้งโปรเจกต์: 0
- ค้นหา gradient: เจอเฉพาะใน comment ที่บอกว่าห้ามใช้
- render template จริงด้วย Django แล้วเปิดในเบราว์เซอร์: หน้าแรก, styleguide, console, 404
  - 375px: ไม่ล้นแนวนอน (scrollWidth = 375)
  - 1024px: console เคยล้นขวาเพราะ main กว้าง 100% + sidebar → แก้เป็น `flex: 1 1 0` แล้ว ไม่ล้น
  - pill หมวดหมู่ที่เป็นลิงก์มีขีดเส้นใต้ → แก้ `text-decoration: none` แล้ว

**ยังไม่ได้ตรวจ (ต้องรันบนเครื่อง user):** `manage.py check`, `migrate`, `pytest`, การต่อ PostGIS/Redis จริง, ฟอนต์และไอคอนจากสคริปต์

## 3. โครงสร้างหลัง M0
```
foodnes/
├── apps/core/{models,decorators,context_processors,views,urls}.py
│   ├── selectors/health_selector.py
│   └── tests/test_core.py
├── config/{settings/{base,local,production}.py, urls.py, celery.py, wsgi.py, asgi.py}
├── static/{css/tmpp.css, js/app.js, img/logo-mark.svg, vendor/bootstrap-5.3.8/}
├── templates/{base.html, 403/404/500.html, layouts/, components/, core/}
├── requirements/{base,local,production}.txt
├── scripts/fetch_vendor.sh
├── docker-compose.yml · Dockerfile · .env.example · pyproject.toml
```

## 4. ขั้นตอนที่ user รันเอง (R0 / กฎข้อ 18)

ต้องมีก่อน: Python 3.12+, Docker Desktop, GDAL (`brew install gdal`)

1. สร้าง `.env` จาก `.env.example` แล้วตั้ง `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD` และแก้รหัสใน `DATABASE_URL` ให้ตรงกัน
2. `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements/local.txt`
4. `bash scripts/fetch_vendor.sh`
5. `docker compose up -d`
6. `python manage.py check`
7. **ยังไม่ต้อง `migrate`** — รอ M1 สร้าง User model ก่อน (custom User ต้องอยู่ใน migration แรก)
8. `pytest` (pytest สร้างฐานข้อมูลทดสอบแยกเองแล้วลบทิ้ง ไม่กระทบฐานข้อมูลจริง)
9. `python manage.py runserver` (จะมีคำเตือนว่ายังไม่ migrate ไม่เป็นไร) แล้วเปิด http://127.0.0.1:8000/ , `/dev/styleguide/` , `/dev/styleguide/console/` , `/healthz/`

## 4.1 เครื่องนี้ (ไม่ใช้ Docker) — ตั้งค่าแล้ว 16/11/2569
user สั่งให้รันบน localhost โดยไม่ใช้ Docker จึงตั้งแบบนี้:
- **PostgreSQL 17 ของ Homebrew** (พอร์ต 5432 ที่รันอยู่แล้ว) สร้าง role `tmpp` (LOGIN, CREATEDB, ไม่ใช่ superuser) + ฐานข้อมูล `tmpp` + PostGIS 3.6
- ฐานข้อมูล `tmpp_template_postgis` (เป็น template มี PostGIS) ให้ pytest สร้างฐานข้อมูลทดสอบได้โดยไม่ต้องเป็น superuser → `.env` `DB_TEST_TEMPLATE`
- **ไม่มี Redis:** `.env` `REDIS_URL=` ว่าง → `local.py` ใช้ cache ในหน่วยความจำ และ Celery รันงานทันที (eager) · ใช้ได้แค่ตอนพัฒนา ต้องมี Redis ก่อนทำ M6 (พิกัดไรเดอร์ต้องแชร์ข้าม process)
- เปิดเว็บ: `.claude/launch.json` ชื่อ `tmpp-django` (= `.venv/bin/python manage.py runserver 127.0.0.1:8000`)

ผลตรวจบนเครื่องจริง: `check` ไม่มีปัญหา · `pytest` 8 passed · `/healthz/` ok (database + cache) · HTMX, Alpine, Bootstrap, ไอคอน, ฟอนต์ไทย/อังกฤษ โหลดครบ · หน้าแคบไม่ล้น

## 5. คำถามทบทวน (กฎข้อ 8)
1. ถ้าลูกค้าที่ล็อกอินแล้วเปิด `/console/` (ซึ่งใช้ `@role_required('OWNER')`) จะเกิดอะไรขึ้น และทำไมไม่ redirect ไปหน้าล็อกอิน
2. ทำไม `docker-compose.yml` ผูกพอร์ตกับ `127.0.0.1` และใช้ 5433 แทน 5432
3. ถ้าจะเปลี่ยนสีหลักของทั้งเว็บจากชมพูเป็นสีอื่น ต้องแก้ที่ไฟล์ไหน กี่จุด

## 6. ต่อไป: M1 บัญชีผู้ใช้
User + บทบาท (CUSTOMER / KITCHEN / RIDER / OWNER), ล็อกอินอีเมล + Google, เจ้าของสร้างบัญชีครัว/ไรเดอร์ · `migrate` ครั้งแรกทำหลัง M1
**ถ้าเผลอ `migrate` ไปแล้ว:** ล้างฐานข้อมูลใหม่ด้วย `docker compose down -v` ก่อนเริ่ม M1 (ฐานข้อมูลยังว่าง ไม่เสียอะไร)
