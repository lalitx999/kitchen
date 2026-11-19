"""
รุ่นของไฟล์ static ที่ deploy อยู่ตอนนี้ (ใช้ใน service worker ให้มือถือรู้ว่ามีเวอร์ชันใหม่)
"""
import hashlib
from functools import lru_cache

from django.contrib.staticfiles.storage import staticfiles_storage


@lru_cache(maxsize=1)
def asset_version() -> str:
    """
    production ใช้ ManifestStaticFilesStorage: ทุกไฟล์มีชื่อพร้อม hash ใน staticfiles.json
    -> เอารายชื่อทั้งหมดมา hash รวม: ไฟล์ไหนเปลี่ยน เลขนี้เปลี่ยน · ไม่เปลี่ยนก็ได้เลขเดิม (ไม่เด้งเตือนมั่ว)
    ตอนพัฒนาบนเครื่องไม่มี hash -> 'dev'
    คำนวณครั้งเดียวต่อ process (deploy ใหม่ = รีสตาร์ท process อยู่แล้ว)
    """
    manifest_hash = getattr(staticfiles_storage, 'manifest_hash', '')   # Django 4.2+ คำนวณให้แล้ว
    if manifest_hash:
        return manifest_hash[:12]
    hashed_files = getattr(staticfiles_storage, 'hashed_files', None)
    if not hashed_files:
        return 'dev'
    digest = hashlib.sha256()
    for name in sorted(hashed_files):
        digest.update(f'{name}={hashed_files[name]}\n'.encode())
    return digest.hexdigest()[:12]
