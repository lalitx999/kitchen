"""
ที่เก็บไฟล์ส่วนตัว (สลิป, รูปหลักฐานส่ง): อยู่นอก MEDIA_ROOT และไม่มี URL สาธารณะ
เปิดดูได้ผ่าน view ที่ตรวจสิทธิ์เท่านั้น (CLAUDE.md กฎข้อ 4)
"""
import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateStorage(FileSystemStorage):
    """
    อ่าน PRIVATE_MEDIA_ROOT จาก settings ทุกครั้ง (ไม่จำค่าไว้)
    ถ้าจำไว้ test ที่เปลี่ยน settings จะเขียนไฟล์ลงโฟลเดอร์จริงแทนโฟลเดอร์ชั่วคราว
    """

    def __init__(self):
        # base_url=None: storage.url() ใช้ไม่ได้ กันเผลอเอาไฟล์ไปแสดงตรงๆ
        super().__init__(base_url=None)

    @property
    def base_location(self):
        return str(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        raise ValueError('ไฟล์ส่วนตัวไม่มี URL สาธารณะ ใช้ view ที่ตรวจสิทธิ์แทน')


private_storage = PrivateStorage()


def get_private_storage():
    return private_storage
