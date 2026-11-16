# ย้ายไปไว้ที่ apps/core/storage.py แล้ว (ใช้ร่วมกับรูปหลักฐานการส่ง) — คงไฟล์นี้ไว้เพราะ migration อ้างถึง
from apps.core.storage import PrivateStorage, get_private_storage, private_storage  # noqa: F401
