"""M12 แบบแอป (PWA): แอปแยกตามบทบาท, service worker เก็บไฟล์ static, ปุ่มย้อนกลับ, ตัวเลขบนไอคอน"""
import json
from pathlib import Path

import pytest
from django.conf import settings as django_settings
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.core.selectors import asset_selector
from apps.delivery.services import rider_service

STATIC_DIR = Path(django_settings.BASE_DIR) / 'static'
MANIFESTS = {
    'manifest.webmanifest': '/start/',          # ลูกค้า: id เดิมห้ามเปลี่ยน (แอปที่ติดตั้งแล้วจะหลุด)
    'manifest-kitchen.webmanifest': '/kitchen/',
    'manifest-rider.webmanifest': '/rider/',
}


def _login(role, email, **extra):
    user = User.objects.create_user(email=email, password='x' * 12, full_name=email, role=role, **extra)
    client = Client()
    client.force_login(user)
    return client, user


def test_each_app_has_its_own_manifest_id():
    seen_ids, seen_names = set(), set()
    for filename, expected_id in MANIFESTS.items():
        manifest = json.loads((STATIC_DIR / filename).read_text(encoding='utf-8'))
        assert manifest['id'] == expected_id
        assert manifest['display'] == 'standalone' and manifest['scope'] == '/'
        assert any(icon['purpose'] == 'maskable' for icon in manifest['icons'])
        seen_ids.add(manifest['id'])
        seen_names.add(manifest['short_name'])
    assert len(seen_ids) == len(MANIFESTS) and len(seen_names) == len(MANIFESTS)


@pytest.mark.django_db
def test_layouts_link_the_manifest_of_their_role(client):
    body = client.get(reverse('core:home')).content.decode()
    assert 'manifest.webmanifest' in body and 'manifest-kitchen' not in body

    kitchen, _ = _login(Role.KITCHEN, 'k@example.test')
    body = kitchen.get(reverse('orders:kitchen')).content.decode()
    assert 'manifest-kitchen.webmanifest' in body
    assert 'content="TMPP ครัว"' in body
    assert 'data-app-badge="0"' in body           # ยังไม่มีออเดอร์ใหม่

    rider_client, rider = _login(Role.RIDER, 'r@example.test')
    rider_service.create_rider_profile(rider, vehicle_plate='1กข 1234')
    body = rider_client.get(reverse('delivery:rider_home')).content.decode()
    assert 'manifest-rider.webmanifest' in body
    assert 'content="TMPP ไรเดอร์"' in body
    assert 'data-app-badge="0"' in body           # ยังไม่เปิดรับงาน


@pytest.mark.django_db
def test_customer_header_has_back_button_and_skeleton(client):
    body = client.get(reverse('core:home')).content.decode()
    assert 'data-app-back' in body and f'data-fallback="{reverse("core:home")}"' in body
    assert 'id="item-sheet-skeleton"' in body
    assert 'id="tm-update"' in body and 'id="tm-ptr"' in body


@pytest.mark.django_db
def test_service_worker_caches_only_hashed_static_and_carries_version(client, monkeypatch):
    asset_selector.asset_version.cache_clear()
    monkeypatch.setattr(asset_selector, 'asset_version', lambda: 'abc123def456')
    body = client.get('/firebase-messaging-sw.js').content.decode()
    assert '// assets: abc123def456' in body
    assert 'HASHED_STATIC' in body and 'STATIC_CACHE' in body
    # หน้า HTML ไม่ถูกเก็บ: navigate ไปเซิร์ฟเวอร์เสมอ เก็บไว้แค่หน้า offline
    assert "request.mode === 'navigate'" in body


def test_asset_version_is_dev_without_manifest_storage():
    asset_selector.asset_version.cache_clear()
    try:
        assert asset_selector.asset_version() == 'dev'
    finally:
        asset_selector.asset_version.cache_clear()
