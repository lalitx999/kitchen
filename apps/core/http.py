def client_ip(request) -> str | None:
    """
    IP ของผู้ใช้จริง: หลัง Caddy อยู่ใน X-Forwarded-For ตัวแรก
    (Caddy ไม่เชื่อค่า X-Forwarded-For ที่ client ส่งมาเองถ้าไม่ได้ตั้ง trusted_proxies)
    """
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    ip = forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR')
    return ip or None
