"""
ยกเลิกออเดอร์ที่ไม่จ่ายเกินเวลา (ปกติ Celery beat รันให้ทุกนาที คำสั่งนี้ใช้ตอนไม่มี beat หรือทดสอบ)
    python manage.py expire_unpaid_orders
"""
from django.core.management.base import BaseCommand

from apps.payments.services import slip_service


class Command(BaseCommand):
    help = 'ยกเลิกออเดอร์ที่ไม่ได้ชำระเงินภายในเวลาที่กำหนด'

    def handle(self, *args, **options):
        count = slip_service.expire_unpaid_orders()
        self.stdout.write(self.style.SUCCESS(f'ยกเลิก {count} ออเดอร์'))
