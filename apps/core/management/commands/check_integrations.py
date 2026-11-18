"""
ตรวจว่าบริการภายนอกตั้งค่าครบและใช้ได้ (ไม่แสดงค่าลับ)
    python manage.py check_integrations           # ดูสถานะ
    python manage.py check_integrations --online  # ลองเชื่อมต่อ Firebase จริงด้วย (ไม่ส่งแจ้งเตือนถึงใคร)
"""
import os
import re

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'ตรวจการตั้งค่า Firebase, Google, EasySlip, พร้อมเพย์'

    def add_arguments(self, parser):
        parser.add_argument('--online', action='store_true', help='ทดสอบเชื่อมต่อ Firebase จริง (dry run)')

    def line(self, ok, name, detail=''):
        mark = self.style.SUCCESS('OK  ') if ok is True else (self.style.WARNING('--  ') if ok is None else self.style.ERROR('ERR '))
        self.stdout.write(f'{mark} {name:28} {detail}')

    def handle(self, *args, online=False, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('การชำระเงิน'))
        self.check_promptpay()
        bank = re.sub(r'\D', '', settings.SHOP_BANK_ACCOUNT)
        self.line(bool(bank) or None, 'SHOP_BANK_ACCOUNT', f'{len(bank)} หลัก' if bank else 'ว่าง: เทียบเลขบัญชีในสลิปจากพร้อมเพย์อย่างเดียว')
        names = [n for n in settings.SHOP_ACCOUNT_NAMES if n.strip()]
        self.line(bool(names) or False, 'SHOP_ACCOUNT_NAMES', f'{len(names)} ชื่อ' if names else 'ว่าง: ระบบจะไม่อนุมัติสลิปเอง ส่งให้เจ้าของตรวจทุกใบ')
        self.line(bool(settings.EASYSLIP_API_KEY) or None, 'EASYSLIP_API_KEY',
                  'ตั้งแล้ว' if settings.EASYSLIP_API_KEY else 'ว่าง: สลิปทุกใบไปคิวเจ้าของตรวจเอง')
        self.line(True, 'PAYMENT_VERIFICATION_MODE', settings.PAYMENT_VERIFICATION_MODE)

        self.stdout.write(self.style.MIGRATE_HEADING('Google'))
        cid = settings.GOOGLE_CLIENT_ID
        if not cid:
            self.line(None, 'GOOGLE_CLIENT_ID', 'ว่าง: ซ่อนปุ่มล็อกอินด้วย Google')
        else:
            self.line(cid.endswith('.apps.googleusercontent.com'), 'GOOGLE_CLIENT_ID',
                      'รูปแบบถูก' if cid.endswith('.apps.googleusercontent.com') else 'ควรลงท้าย .apps.googleusercontent.com')
        key = settings.GOOGLE_MAPS_API_KEY
        self.line((key.startswith('AIza') and len(key) == 39) if key else None, 'GOOGLE_MAPS_API_KEY',
                  ('รูปแบบถูก' if key.startswith('AIza') and len(key) == 39 else 'รูปแบบไม่เหมือน API key ของ Google') if key else 'ว่าง: ไม่แสดงแผนที่ ใช้ GPS อย่างเดียว')
        self.line(True if settings.GOOGLE_MAPS_MAP_ID else None, 'GOOGLE_MAPS_MAP_ID',
                  'ตั้งแล้ว' if settings.GOOGLE_MAPS_MAP_ID else 'ว่าง: ใช้ DEMO_MAP_ID')

        self.stdout.write(self.style.MIGRATE_HEADING('Firebase (แจ้งเตือน)'))
        web = settings.FIREBASE_WEB_CONFIG
        missing = [k for k in ('apiKey', 'authDomain', 'projectId', 'messagingSenderId', 'appId') if not web.get(k)]
        self.line(not missing, 'ค่าฝั่งเว็บ', 'ครบ' if not missing else f'ขาด {", ".join(missing)}')
        self.line(bool(settings.FIREBASE_VAPID_KEY), 'FIREBASE_VAPID_KEY', 'ตั้งแล้ว' if settings.FIREBASE_VAPID_KEY else 'ว่าง')
        path = settings.FIREBASE_CREDENTIALS_PATH
        if not path:
            self.line(None, 'service account', 'ว่าง: ไม่ส่ง push (ยังเห็นแจ้งเตือนในเว็บ)')
        elif not os.path.isfile(path):
            self.line(False, 'service account', f'ไม่พบไฟล์ {path}')
        else:
            self.line(True, 'service account', 'พบไฟล์')
            if online:
                self.check_firebase_online(web.get('projectId'))

    def check_promptpay(self):
        from apps.payments.services import promptpay_service
        try:
            promptpay_service.build_payload(settings.PROMPTPAY_ID, 1)
            self.line(True, 'PROMPTPAY_ID', f'สร้าง QR ได้ ({promptpay_service.masked_promptpay_id()})')
        except promptpay_service.PromptPayNotConfigured as exc:
            self.line(False, 'PROMPTPAY_ID', str(exc) if settings.PROMPTPAY_ID else 'ว่าง: ลูกค้าจ่ายเงินไม่ได้')

    def check_firebase_online(self, web_project_id):
        from apps.notifications.services import notify_service
        try:
            messaging = notify_service._messaging()
            import firebase_admin
            app = firebase_admin.get_app()
            token_ok = bool(app.credential.get_access_token().access_token)
            self.line(token_ok, 'Google ยืนยันตัวตน', 'ขอ access token ได้')
            self.line(app.project_id == web_project_id, 'project ตรงกัน',
                      'service account กับค่าฝั่งเว็บเป็นโปรเจกต์เดียวกัน' if app.project_id == web_project_id else 'คนละโปรเจกต์')
            try:
                messaging.send(messaging.Message(token='integration-check-invalid-token', data={'t': 'x'}), dry_run=True)
            except Exception as exc:  # noqa: BLE001
                ok = type(exc).__name__ in ('InvalidArgumentError', 'UnregisteredError')
                self.line(ok, 'FCM (dry run)', 'ผ่านการยืนยันตัวตน' if ok else type(exc).__name__)
        except Exception as exc:  # noqa: BLE001
            self.line(False, 'Firebase', f'{type(exc).__name__}: {str(exc)[:120]}')
