"""
สร้างบัญชีเจ้าของร้าน (ทำครั้งเดียวตอนติดตั้ง)
    python manage.py create_owner --email owner@example.com --name "ชื่อเจ้าของ"
รหัสผ่านถามผ่าน prompt (ไม่พิมพ์ใน command line เพราะจะค้างใน shell history)
"""
import getpass

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role, User, normalize_email_address


class Command(BaseCommand):
    help = 'สร้างบัญชีเจ้าของร้าน (role OWNER)'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)
        parser.add_argument('--name', required=True)
        parser.add_argument('--phone', default='')

    def handle(self, *args, email, name, phone, **options):
        email = normalize_email_address(email)
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError(f'มีบัญชี {email} แล้ว')

        password = getpass.getpass('รหัสผ่าน: ')
        if password != getpass.getpass('ยืนยันรหัสผ่าน: '):
            raise CommandError('รหัสผ่านไม่ตรงกัน')
        try:
            password_validation.validate_password(password)
        except ValidationError as exc:
            raise CommandError(' '.join(exc.messages)) from exc

        User.objects.create_user(email=email, password=password, full_name=name, phone=phone, role=Role.OWNER)
        self.stdout.write(self.style.SUCCESS(f'สร้างบัญชีเจ้าของร้าน {email} แล้ว'))
