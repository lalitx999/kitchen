#!/usr/bin/env python3
"""
ใส่ค่าลับลง .env บน server โดยไม่แสดงบนจอ และไม่ค้างใน shell history

  ถามทีละค่า (พิมพ์/วางแล้วกด Enter · ตัวอักษรไม่ขึ้นบนจอ · กด Enter เปล่า = ไม่เปลี่ยน):
    python3 deploy/set_env.py EASYSLIP_API_KEY PROMPTPAY_ID

  รวมค่าจากไฟล์ที่ส่งมาจากเครื่องอื่น (เช่นค่า Firebase จาก Mac) แล้วลบไฟล์นั้นทิ้ง:
    python3 deploy/set_env.py --from-file /root/firebase.env

  ดูว่าตั้งค่าอะไรไว้บ้าง (แสดงแค่ว่ามีค่า/ว่าง และความยาว ไม่แสดงค่าจริง):
    python3 deploy/set_env.py --status
"""
import getpass
import pathlib
import re
import sys

ENV_PATH = pathlib.Path(__file__).resolve().parent.parent / '.env'
KEY_RE = re.compile(r'^[A-Z][A-Z0-9_]*$')
# ค่าที่ไม่ลับ แสดงให้เห็นได้ตอน --status
PUBLIC_KEYS = {
    'DJANGO_ALLOWED_HOSTS', 'CSRF_TRUSTED_ORIGINS', 'SITE_URL', 'SITE_NAME', 'SITE_ADDRESS', 'HTTPS_ENABLED',
    'HTTP_PORT', 'HTTPS_PORT', 'TRUSTED_PROXIES', 'PAYMENT_VERIFICATION_MODE', 'POSTGRES_DB', 'POSTGRES_USER',
    'FIREBASE_PROJECT_ID', 'FIREBASE_AUTH_DOMAIN', 'FIREBASE_CREDENTIALS_PATH', 'SHOP_BANK_CODE',
    'SLIP_MAX_ATTEMPTS', 'PAYMENT_WINDOW_MINUTES', 'DJANGO_ADMIN_ENABLED',
}


def read_env() -> str:
    if not ENV_PATH.exists():
        sys.exit(f'ไม่พบ {ENV_PATH} (สร้างจาก deploy/env.production.example ก่อน)')
    return ENV_PATH.read_text(encoding='utf-8')


def write_values(values: dict[str, str]) -> None:
    text = read_env()
    for key, value in values.items():
        if '\n' in value:
            sys.exit(f'{key}: ค่ามีขึ้นบรรทัดใหม่ ไม่รับ')
        line = f'{key}={value}'
        text, n = re.subn(rf'^{re.escape(key)}=.*$', lambda _m: line, text, flags=re.M)
        if n == 0:
            text = text.rstrip('\n') + f'\n{line}\n'
    ENV_PATH.write_text(text, encoding='utf-8')
    ENV_PATH.chmod(0o600)


def parse_file(path: pathlib.Path) -> dict[str, str]:
    values = {}
    for raw in path.read_text(encoding='utf-8').splitlines():
        raw = raw.strip()
        if not raw or raw.startswith('#') or '=' not in raw:
            continue
        key, value = raw.split('=', 1)
        key = key.strip()
        if KEY_RE.match(key):
            values[key] = value.strip().strip('"').strip("'")
    return values


def status() -> None:
    for raw in read_env().splitlines():
        if '=' not in raw or raw.lstrip().startswith('#'):
            continue
        key, value = raw.split('=', 1)
        if not KEY_RE.match(key):
            continue
        if not value:
            shown = '(ว่าง)'
        elif key in PUBLIC_KEYS:
            shown = value
        else:
            shown = f'ตั้งแล้ว (ยาว {len(value)})'
        print(f'{key:32} {shown}')


def main(argv: list[str]) -> None:
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return
    if argv[0] == '--status':
        status()
        return
    if argv[0] == '--from-file':
        source = pathlib.Path(argv[1])
        values = parse_file(source)
        write_values(values)
        source.unlink()  # ไม่ทิ้งไฟล์ค่าลับไว้บน server
        print(f'รวม {len(values)} ค่าเข้า .env แล้ว: {", ".join(values)} · ลบ {source} แล้ว')
        return

    keys = [k for k in argv if KEY_RE.match(k)]
    changed = {}
    for key in keys:
        value = getpass.getpass(f'{key} (Enter เปล่า = ไม่เปลี่ยน): ').strip()
        if value:
            changed[key] = value
    if changed:
        write_values(changed)
    print(f'บันทึกแล้ว: {", ".join(changed) or "ไม่มี"}')


if __name__ == '__main__':
    main(sys.argv[1:])
