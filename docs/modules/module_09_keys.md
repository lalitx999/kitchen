# Module 09 — คีย์บริการภายนอก: ไปเอามาจากไหน และใส่อย่างไร

> วันที่: 18/11/2569 · ข้อ 2 ของลำดับงาน (1 โดเมน ✔ → 2 คีย์ → 3 ทดสอบจริง + ปิดระบบเดิม)

## หลักการ
- **ห้ามวางค่าลับในแชท / LINE / อีเมล** — ใส่บน server ด้วย `python3 deploy/set_env.py ชื่อคีย์` (พิมพ์แล้วไม่ขึ้นจอ ไม่ค้างใน history)
- ตรวจหลังใส่: `dc exec web python manage.py check_integrations --online` (ไม่แสดงค่าจริง)
- ใส่แล้วต้องสร้างคอนเทนเนอร์ใหม่: `dc up -d --force-recreate web worker beat`

| บริการ | ใช้ทำอะไร | ไม่ใส่ = |
|---|---|---|
| Firebase (FCM) | แจ้งเตือนเด้งบนมือถือ | ยังเห็นแจ้งเตือนในเว็บ แต่ไม่เด้ง |
| พร้อมเพย์ + บัญชีร้าน | QR จ่ายเงิน + เทียบบัญชีผู้รับในสลิป | **ลูกค้าจ่ายเงินไม่ได้** |
| EasySlip V2 | ตรวจสลิปอัตโนมัติ | สลิปทุกใบไปคิวเจ้าของตรวจเอง (ยังใช้งานได้) |
| Google Maps | แผนที่ปักหมุดบ้านตอนสั่ง | ลูกค้าใช้ปุ่ม "ใช้ตำแหน่งปัจจุบัน" (GPS) อย่างเดียว |
| Google Sign-In | ปุ่ม "ดำเนินการต่อด้วย Google" | สมัครด้วยอีเมล/รหัสผ่านอย่างเดียว |

---

## 1. Firebase — โปรเจกต์ `rider-a9729`
18/11: ย้ายจากโปรเจกต์ระบบเดิม (`lucidsoci`) มาใช้ `rider-a9729` ที่เปิด Blaze และมีคีย์ Maps อยู่แล้ว → แผนที่ + แจ้งเตือน + บิลอยู่โปรเจกต์เดียว
(ทำได้โดยไม่เสียอะไรเพราะฐานข้อมูลใหม่ ยังไม่มี DeviceToken · ค่าฝั่งเว็บ/VAPID ต้องมาจากโปรเจกต์เดียวกับ service account ไม่งั้น FCM ปฏิเสธ)
เตรียมไว้บน Mac แล้ว 2 ไฟล์ใน `~/.config/tmpp/` (สิทธิ์ 600): `firebase-service-account.json` และ `server-firebase.env` · ชุดเก่าเก็บใน `old-lucidsoci/`
1. ส่งขึ้น server (รันบน Mac):
   `scp ~/.config/tmpp/firebase-service-account.json root@177.202.247.183:/root/kitchen/secrets/`
   `scp ~/.config/tmpp/server-firebase.env root@177.202.247.183:/root/firebase.env`
2. บน server: `python3 deploy/set_env.py --from-file /root/firebase.env` (รวมค่าแล้วลบไฟล์ให้)
   และให้ผู้ใช้ `app` (uid 1000) ในคอนเทนเนอร์อ่านไฟล์ได้: `chown 1000:1000 secrets/firebase-service-account.json && chmod 400 secrets/firebase-service-account.json`
   (เจอแล้ว 18/11: scp ด้วย root ได้ไฟล์ของ root สิทธิ์ 600 → แอปอ่านไม่ได้ `PermissionError`)
3. ตรวจใน Google Cloud Console (โปรเจกต์เดียวกับ Firebase) > APIs & Services > Credentials > **Browser key (auto created by Firebase)**: ถ้าตั้ง "Website restrictions" ไว้ ต้องเพิ่ม `https://tmth-th.com/*`
4. Firebase Console > Project settings > Cloud Messaging: **Firebase Cloud Messaging API (V1)** ต้องเป็น Enabled

## 2. พร้อมเพย์ + บัญชีร้าน (ข้อมูลของร้าน ไม่ต้องสมัครอะไร)
| คีย์ | ใส่อะไร |
|---|---|
| `PROMPTPAY_ID` | เบอร์มือถือ 10 หลัก หรือเลขบัตรประชาชน 13 หลัก ที่ผูกพร้อมเพย์ไว้ |
| `SHOP_BANK_ACCOUNT` | เลขบัญชีธนาคารที่ผูกกับพร้อมเพย์นั้น (ตัวเลขล้วน) |
| `SHOP_BANK_CODE` | รหัสธนาคาร: 002 กรุงเทพ · 004 กสิกรไทย · 006 กรุงไทย · 011 ทีทีบี · 014 ไทยพาณิชย์ · 025 กรุงศรี · 030 ออมสิน |
| `SHOP_ACCOUNT_NAMES` | ชื่อบัญชี **ตามที่ขึ้นในสลิป** ไทยและอังกฤษ คั่นด้วย comma เช่น `นาย สมชาย ใจดี,MR. SOMCHAI JAIDEE` |

วิธีดูชื่อที่ขึ้นในสลิป: ให้คนอื่นโอนเข้าบัญชีร้าน 1 บาท แล้วดูชื่อผู้รับในสลิป · ไม่ใส่ชื่อ = ระบบจะไม่อนุมัติสลิปเอง (ปลอดภัยไว้ก่อน)

ร้านนี้ (18/11): QR ร้านเป็น **K SHOP กสิกร** ถอดได้ว่าเป็นพร้อมเพย์ **15 หลัก** (tag 29/03) → ใช้เลข 15 หลักนั้นเป็น `PROMPTPAY_ID`, `SHOP_BANK_CODE=004`
ค่าจริงเก็บใน `.env` บน server เท่านั้น ไม่ใส่ใน repo · QR ที่ระบบสร้างมีส่วนผู้รับตรงกับ QR ของธนาคาร ต่างแค่ระบุยอด (มี test)

## 3. EasySlip V2 (ตรวจสลิปอัตโนมัติ)
เอกสาร: https://document.easyslip.com/th/
1. สมัคร/ล็อกอินที่ **developer.easyslip.com** → สร้างแอปพลิเคชัน → เลือกแพ็กเกจ
2. Dashboard ของแอป → หัวข้อ **Credentials** → คัดลอก **API Key** (รูปแบบ UUID) → `EASYSLIP_API_KEY`
3. **ตั้งค่าแอปพลิเคชัน** → IP whitelist ใส่ `177.202.247.183` (อย่าใช้ `*`)
4. ระบบเรียก `POST https://api.easyslip.com/v2/verify/bank` ส่งแค่ `image` + `remark` (เลขออเดอร์)
   - **ไม่ส่ง** `matchAccount` (ต้องลงทะเบียนบัญชีผ่าน Bank Accounts API ไม่งั้นตีกลับทุกใบ), `matchAmount`, `checkDuplicate` (นับทุกครั้งที่เรียก ถ้า task retry สลิปจริงจะโดนว่าซ้ำ)
   - ตรวจเองใน `slip_checks`: เลขบัญชี/พร้อมเพย์ + รหัสธนาคาร, ชื่อผู้รับ, ยอดทุกสตางค์, `transRef` ไม่ซ้ำกับที่อนุมัติแล้ว, รูปไม่ซ้ำ (sha256)
5. EasySlip ล่ม/โควต้าหมด/IP ไม่อนุญาต → สลิปไปคิว `/console/slips/` อัตโนมัติ (ลูกค้าไม่โดนปฏิเสธ)
6. ทดสอบจริง: สั่ง 1 ออเดอร์ โอนจริง แล้วดูว่าอนุมัติเอง ถ้าไปคิวเจ้าของ ให้ดูเหตุผลใน `/console/slips/` (มักเป็นชื่อผู้รับในสลิปสะกดต่าง → เพิ่มชื่อนั้นใน `SHOP_ACCOUNT_NAMES`)

## 4. Google Maps (แผนที่ปักหมุด)
ทำใน **console.cloud.google.com** เลือกโปรเจกต์เดียวกับ Firebase จะจัดการง่าย
1. **Billing**: ผูกบัตร (Maps บังคับ) · มีโควต้าใช้ฟรีรายเดือน ตรวจราคาล่าสุดที่หน้า Google Maps Platform Pricing · **ตั้ง Budget alert** (Billing > Budgets & alerts) เช่น 300 บาท
2. APIs & Services > Library > เปิด **Maps JavaScript API**
3. APIs & Services > Credentials > **Create credentials > API key** → กด Edit:
   - Application restrictions: **Websites** → `https://tmth-th.com/*`, `https://www.tmth-th.com/*`, `http://localhost:8000/*`
   - API restrictions: **Restrict key** → เลือกเฉพาะ Maps JavaScript API
   - คัดลอกคีย์ (ขึ้นต้น `AIza`) → `GOOGLE_MAPS_API_KEY`
4. Google Maps Platform > **Map Management > Create Map ID** (ประเภท JavaScript) → `GOOGLE_MAPS_MAP_ID` (ไม่ใส่ก็ได้ ใช้ DEMO_MAP_ID)
5. แผนที่โหลดเฉพาะหน้า checkout เท่านั้น (ลดค่าใช้จ่าย) · คีย์นี้อยู่ในหน้าเว็บ (เป็นเรื่องปกติ) จึงต้องจำกัดตามโดเมนในข้อ 3

## 5. Google Sign-In (ไม่บังคับ)
1. Google Cloud Console > **Google Auth Platform** (เดิมชื่อ OAuth consent screen):
   - Branding: ชื่อแอป `TMPP`, อีเมลติดต่อ, Authorized domain `tmth-th.com`
   - Audience: **External** → **Publish app** (ใช้แค่ชื่อ/อีเมล ไม่ต้องรอ Google ตรวจ)
2. Clients > **Create client > Web application**
   - Authorized JavaScript origins: `https://tmth-th.com`, `https://www.tmth-th.com`, `http://localhost:8000`
   - Authorized redirect URIs: **ไม่ต้องใส่** (ใช้แบบ popup)
3. คัดลอก **Client ID** (ลงท้าย `.apps.googleusercontent.com`) → `GOOGLE_CLIENT_ID` · **ไม่ต้องใช้ Client secret**
- แก้ไปแล้ว: Django ตั้ง `Cross-Origin-Opener-Policy: same-origin` เป็นค่าเริ่มต้น ซึ่งบล็อก popup ของ Google → ตั้งเป็น `same-origin-allow-popups`

---

## 6. ใส่บน server (ทีละกลุ่มได้)
```
cd ~/kitchen && git pull
alias dc='docker compose -f deploy/docker-compose.prod.yml --env-file .env'
python3 deploy/set_env.py PROMPTPAY_ID SHOP_BANK_ACCOUNT SHOP_BANK_CODE SHOP_ACCOUNT_NAMES EASYSLIP_API_KEY
python3 deploy/set_env.py GOOGLE_MAPS_API_KEY GOOGLE_MAPS_MAP_ID GOOGLE_CLIENT_ID
python3 deploy/set_env.py --status
dc up -d --build && dc up -d --force-recreate web worker beat
dc exec web python manage.py check_integrations --online
```

## 7. ทำไมทำแบบนี้
- `set_env.py` ใช้ `getpass` → ค่าไม่ขึ้นจอ ไม่ค้างใน `~/.bash_history` · `.env` ถูกตั้งสิทธิ์ 600 ทุกครั้ง · `--status` แสดงแค่ "ตั้งแล้ว (ยาว n)"
- `check_integrations` ตรวจรูปแบบคีย์ + สร้าง QR ได้จริง + Firebase ยืนยันตัวตนจริง (dry run ไม่ส่งถึงใคร) โดยไม่พิมพ์ค่าลับ (มี test)
- ไฟล์ค่าลับที่ส่งด้วย scp ถูกลบทันทีหลังรวมเข้า `.env`

## 8. คำถามทบทวน (กฎข้อ 8)
1. ทำไมคีย์ Google Maps อยู่ในหน้าเว็บได้ แต่ต้องจำกัดตามโดเมน
2. ถ้าไม่ใส่ `SHOP_ACCOUNT_NAMES` แต่ใส่ EasySlip key ระบบจะอนุมัติสลิปเองไหม เพราะอะไร
3. ทำไมไม่ใช้ `nano .env` แล้ววางคีย์เอง
