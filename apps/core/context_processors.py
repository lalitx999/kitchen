from django.conf import settings


def site(request):
    """ค่าแบรนด์ที่ทุก template ใช้ (ชื่อร้าน, คำโปรย, URL หลัก)"""
    return {
        'SITE_NAME': settings.SITE_NAME,
        'SITE_TAGLINE': settings.SITE_TAGLINE,
        'SITE_URL': settings.SITE_URL,
    }
