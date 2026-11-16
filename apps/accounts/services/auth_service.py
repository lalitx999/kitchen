"""
ล็อกอิน สมัครสมาชิก และเลือกหน้าแรกตามบทบาท
view เรียกฟังก์ชันในไฟล์นี้เท่านั้น ไม่เขียน logic เองใน view
"""
import hashlib
import logging
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from ..models import Role, User, normalize_email_address

logger = logging.getLogger(__name__)


class LoginLocked(Exception):
    def __init__(self, retry_after_seconds: int):
        super().__init__('login locked')
        self.retry_after_seconds = retry_after_seconds


class EmailAlreadyUsed(Exception):
    pass


class GoogleLoginError(Exception):
    """ข้อความใน exception แสดงให้ผู้ใช้เห็นได้"""


# ---------------------------------------------------------------------------
# กันเดารหัสผ่าน: นับครั้งที่ผิดต่ออีเมล และต่อ IP แยกกัน
# ---------------------------------------------------------------------------
def _fail_keys(email: str, ip: str | None) -> list[str]:
    # hash อีเมลก่อนใช้เป็น cache key ไม่ให้อีเมลไปโผล่ใน Redis ตรงๆ
    email_hash = hashlib.sha256(email.encode()).hexdigest()[:24]
    keys = [f'login-fail:email:{email_hash}']
    if ip:
        keys.append(f'login-fail:ip:{ip}')
    return keys


def _is_locked(keys: list[str]) -> bool:
    limit = settings.LOGIN_MAX_FAILURES
    # IP ได้โควต้ามากกว่า เพราะหลายคนอาจใช้ Wi-Fi ร้านเดียวกัน
    return any(
        (cache.get(key) or 0) >= (limit * 4 if ':ip:' in key else limit) for key in keys
    )


def _record_failure(keys: list[str]) -> None:
    for key in keys:
        if cache.add(key, 1, timeout=settings.LOGIN_LOCKOUT_SECONDS):
            continue
        try:
            cache.incr(key)
        except ValueError:  # key หมดอายุพอดีระหว่างทาง
            cache.set(key, 1, timeout=settings.LOGIN_LOCKOUT_SECONDS)


def authenticate_user(request, *, email: str, password: str, ip: str | None) -> User | None:
    """
    คืน User ถ้าอีเมล/รหัสผ่านถูก และบัญชียังใช้งานได้
    คืน None ถ้าผิด · ยก LoginLocked ถ้าผิดเกินกำหนด
    """
    email = normalize_email_address(email)
    keys = _fail_keys(email, ip)
    if _is_locked(keys):
        raise LoginLocked(settings.LOGIN_LOCKOUT_SECONDS)

    # ModelBackend ตรวจ is_active ให้แล้ว (บัญชีที่ถูกปิดจะได้ None)
    user = authenticate(request, username=email, password=password)
    if user is None:
        _record_failure(keys)
        return None

    cache.delete_many(keys)
    return user


# ---------------------------------------------------------------------------
# สมัครสมาชิก (ลูกค้าเท่านั้น)
# ---------------------------------------------------------------------------
def register_customer(*, full_name: str, email: str, phone: str, password: str) -> User:
    email = normalize_email_address(email)
    try:
        with transaction.atomic():
            return User.objects.create_user(
                email=email, password=password, full_name=full_name.strip(), phone=phone, role=Role.CUSTOMER
            )
    except IntegrityError as exc:
        # กรณีสองคนกดสมัครอีเมลเดียวกันพร้อมกัน ฟอร์มตรวจแล้วแต่ DB จับได้อีกชั้น
        raise EmailAlreadyUsed from exc


# ---------------------------------------------------------------------------
# Google Sign-In
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    name: str


def verify_google_credential(credential: str) -> GoogleIdentity:
    """
    ตรวจ ID token กับ Google (ลายเซ็น, อายุ, audience = Client ID ของเรา)
    เรียกใน request ได้เพราะเป็นขั้นตอนล็อกอินที่ต้องรอผล และ google-auth cache public key ไว้
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise GoogleLoginError('ยังไม่ได้ตั้งค่าการล็อกอินด้วย Google')
    if not credential or len(credential) > 4096:
        raise GoogleLoginError('ข้อมูลจาก Google ไม่ถูกต้อง')

    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        info = id_token.verify_oauth2_token(
            credential, google_requests.Request(), settings.GOOGLE_CLIENT_ID, clock_skew_in_seconds=10
        )
    except ValueError as exc:
        logger.info('google token rejected: %s', exc)
        raise GoogleLoginError('ยืนยันตัวตนกับ Google ไม่สำเร็จ ลองใหม่อีกครั้ง') from exc

    if not info.get('email') or not info.get('email_verified'):
        raise GoogleLoginError('บัญชี Google นี้ยังไม่ได้ยืนยันอีเมล')
    return GoogleIdentity(
        sub=str(info['sub']),
        email=normalize_email_address(info['email']),
        name=(info.get('name') or info['email'].split('@')[0])[:150],
    )


def login_or_register_with_google(identity: GoogleIdentity) -> User:
    """
    1. เคยผูก Google แล้ว -> ใช้บัญชีนั้น
    2. มีบัญชีลูกค้าอีเมลเดียวกัน -> ผูก Google เข้าบัญชีเดิม
    3. ไม่มี -> สร้างบัญชีลูกค้าใหม่
    บัญชีพนักงาน (ครัว/ไรเดอร์/เจ้าของ) ต้องล็อกอินด้วยรหัสผ่านเท่านั้น
    """
    with transaction.atomic():
        user = User.objects.select_for_update().filter(google_sub=identity.sub).first()
        if user is None:
            user = User.objects.select_for_update().filter(email__iexact=identity.email).first()
            if user is not None:
                if user.role != Role.CUSTOMER:
                    raise GoogleLoginError('บัญชีพนักงานต้องเข้าสู่ระบบด้วยอีเมลและรหัสผ่าน')
                user.google_sub = identity.sub
                user.save(update_fields=['google_sub', 'updated_at'])
            else:
                user = User.objects.create_user(
                    email=identity.email, password=None, full_name=identity.name,
                    role=Role.CUSTOMER, google_sub=identity.sub,
                )

    if not user.is_active:
        raise GoogleLoginError('บัญชีนี้ถูกปิดการใช้งาน ติดต่อร้าน')
    return user


# ---------------------------------------------------------------------------
# หลังล็อกอินไปไหน
# ---------------------------------------------------------------------------
_HOME_BY_ROLE = {
    Role.CUSTOMER: 'core:home',
    Role.KITCHEN: 'orders:kitchen',
    Role.RIDER: 'delivery:rider_home',
    Role.OWNER: 'console:overview',
}


def home_url_for(user: User) -> str:
    return reverse(_HOME_BY_ROLE.get(user.role, 'core:home'))


def redirect_url_after_login(request, user: User, next_url: str | None) -> str:
    # รับ next เฉพาะ path ในโดเมนเรา กันถูกหลอกให้เด้งไปเว็บอื่นหลังล็อกอิน (open redirect)
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return next_url
    return home_url_for(user)
