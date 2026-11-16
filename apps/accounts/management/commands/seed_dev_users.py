"""
สร้างบัญชีทดสอบ 4 บทบาท สำหรับเครื่องพัฒนาเท่านั้น (ปฏิเสธถ้า DEBUG=False)
รหัสผ่านอ่านจาก DEV_SEED_PASSWORD ใน .env (ไม่ hardcode ในโค้ด)
    python manage.py seed_dev_users
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role, User
from apps.delivery.services import rider_service

DEV_USERS = [
    ('owner@tmpp.test', 'เจ้าของร้าน (ทดสอบ)', Role.OWNER, '0800000001'),
    ('kitchen@tmpp.test', 'ครัว (ทดสอบ)', Role.KITCHEN, '0800000002'),
    ('rider@tmpp.test', 'ไรเดอร์ (ทดสอบ)', Role.RIDER, '0800000003'),
    ('customer@tmpp.test', 'ลูกค้า (ทดสอบ)', Role.CUSTOMER, '0800000004'),
]


class Command(BaseCommand):
    help = 'สร้างบัญชีทดสอบทุกบทบาท (เฉพาะ DEBUG)'

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('ใช้ได้เฉพาะเครื่องพัฒนา (DEBUG=True)')
        from environ import Env

        password = Env().str('DEV_SEED_PASSWORD', default='')
        if len(password) < 12:
            raise CommandError('ตั้ง DEV_SEED_PASSWORD ใน .env (อย่างน้อย 12 ตัว)')

        for email, name, role, phone in DEV_USERS:
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create_user(email=email, password=password, full_name=name, role=role, phone=phone)
                state = 'สร้างแล้ว'
            else:
                user.set_password(password)
                user.save(update_fields=['password', 'updated_at'])
                state = 'มีอยู่แล้ว (รีเซ็ตรหัสผ่าน)'
            if role == Role.RIDER:
                profile = rider_service.ensure_rider_profile(user)
                if not profile.vehicle_plate:
                    rider_service.update_vehicle_plate(profile, '1กข 1234')
            self.stdout.write(f'{role:<9} {email:<22} {state}')
