"""
เรียก EasySlip V2 (POST /v2/verify/bank, multipart field `image`)
https://document.easyslip.com/th/v2/verify/bank/image
เรียกจาก Celery task เท่านั้น (เป็น API ภายนอก ห้ามเรียกใน request — CLAUDE.md กฎข้อ 3)
"""
import logging
from dataclasses import dataclass, field

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class SlipProblem(Exception):
    """สลิปมีปัญหา ข้อความบอกลูกค้าได้"""


class ProviderUnavailable(Exception):
    """EasySlip ใช้ไม่ได้ (ไม่มีคีย์/โควต้าหมด/ล่ม) ไม่ใช่ความผิดของลูกค้า -> ส่งให้เจ้าของตรวจ"""


# error code ที่เป็นปัญหาของ "สลิป" (บอกลูกค้าได้) โค้ดอื่นถือว่าปัญหาฝั่งเรา
SLIP_PROBLEM_MESSAGES = {
    'SLIP_NOT_FOUND': 'อ่าน QR บนสลิปไม่ได้ หรือไม่พบรายการโอนนี้ ถ่ายให้เห็น QR ชัดๆ แล้วลองใหม่',
    'QRCODE_NOT_FOUND': 'ไม่พบ QR บนสลิป ใช้รูปสลิปจากแอปธนาคารโดยตรง',
    'SLIP_PENDING': 'ธนาคารยังไม่ยืนยันรายการนี้ รอประมาณ 5 นาทีแล้วส่งใหม่',
    'SLIP_EXPIRED': 'สลิปนี้เก่าเกินกว่าจะตรวจสอบได้',
    'INVALID_IMAGE_FORMAT': 'ไฟล์นี้ไม่ใช่รูปที่ระบบอ่านได้ (ใช้ JPG หรือ PNG)',
    'INVALID_IMAGE': 'ไฟล์นี้ไม่ใช่รูปที่ระบบอ่านได้ (ใช้ JPG หรือ PNG)',
    'IMAGE_SIZE_TOO_LARGE': 'รูปสลิปใหญ่เกิน 4 MB',
    'DUPLICATE_SLIP': 'สลิปนี้ถูกใช้ไปแล้ว',
}
# เอกสาร V2 ใช้ 2 รูปแบบ: {"error": {"code": "SLIP_NOT_FOUND"}} และ {"message": "slip_not_found"} -> แปลงเป็นตัวใหญ่ก่อนเทียบ


@dataclass
class SlipData:
    trans_ref: str | None
    amount: str | None
    sender_name: str
    receiver_names: list[str] = field(default_factory=list)
    receiver_accounts: list[str] = field(default_factory=list)
    receiver_bank_code: str = ''
    is_duplicate: bool = False
    raw: dict = field(default_factory=dict)


def normalize_v2(body: dict) -> SlipData:
    data = body.get('data') or {}
    raw = data.get('rawSlip') or {}
    sender = raw.get('sender') or {}
    receiver = raw.get('receiver') or {}
    receiver_account = receiver.get('account') or {}
    sender_name = (sender.get('account') or {}).get('name') or {}
    receiver_name = receiver_account.get('name') or {}
    accounts = [
        str(value) for value in (
            (receiver_account.get('bank') or {}).get('account'),
            (receiver_account.get('proxy') or {}).get('account'),
        ) if value
    ]
    amount = (raw.get('amount') or {}).get('amount')
    if amount is None:
        amount = data.get('amountInSlip')
    return SlipData(
        trans_ref=raw.get('transRef'),
        amount=str(amount) if amount is not None else None,
        sender_name=(sender_name.get('th') or sender_name.get('en') or '')[:150],
        receiver_names=[n for n in (receiver_name.get('th'), receiver_name.get('en')) if n],
        receiver_accounts=accounts,
        receiver_bank_code=str((receiver.get('bank') or {}).get('id') or ''),
        is_duplicate=bool(data.get('isDuplicate')),
        raw=body,
    )


def verify(image_bytes: bytes, *, filename: str, content_type: str, expected_amount, remark: str = '') -> SlipData:
    api_key = (settings.EASYSLIP_API_KEY or '').strip()
    if not api_key:
        raise ProviderUnavailable('ยังไม่ได้ตั้งค่า EASYSLIP_API_KEY')
    try:
        response = requests.post(
            settings.EASYSLIP_API_URL,
            headers={'Authorization': f'Bearer {api_key}'},
            files={'image': (filename, image_bytes, content_type)},
            # ไม่ส่ง checkDuplicate / matchAccount / matchAmount: ตรวจเองทั้งหมดใน slip_checks
            # - matchAccount ต้องลงทะเบียนบัญชีผ่าน Bank Accounts API ก่อน ไม่งั้นได้ account_not_match ทุกใบ
            # - checkDuplicate นับทุกครั้งที่เรียก ถ้า task รันซ้ำ (retry) สลิปจริงจะโดนตีว่าใช้ซ้ำ
            #   กันสลิปซ้ำด้วย trans_ref ที่อนุมัติแล้ว + sha256 ของรูปแทน (idempotent)
            data={'remark': remark[:255]} if remark else {},
            timeout=settings.EASYSLIP_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise ProviderUnavailable(f'เชื่อมต่อ EasySlip ไม่ได้: {exc.__class__.__name__}') from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise ProviderUnavailable(f'EasySlip ตอบกลับไม่ใช่ JSON (HTTP {response.status_code})') from exc

    if response.status_code != 200 or not body.get('success'):
        error = body.get('error') if isinstance(body.get('error'), dict) else {}
        code = str(error.get('code') or body.get('message') or '').upper()
        if code in SLIP_PROBLEM_MESSAGES:
            raise SlipProblem(SLIP_PROBLEM_MESSAGES[code])
        logger.warning('easyslip unavailable: HTTP %s %s', response.status_code, code)
        raise ProviderUnavailable(f'EasySlip ตอบ HTTP {response.status_code} {code or "-"}')
    return normalize_v2(body)
