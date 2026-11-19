"""M15 เซลเพจ /about/: ข้อมูลจริงเท่านั้น, เมนูขายดีมาก่อน, ซ่อนส่วนที่ไม่มีข้อมูล, รูปตอนแชร์ลิงก์"""
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.catalog.models import Branch, MenuItem
from apps.orders.tests.conftest import branch, customer, customer_client, menu  # noqa: F401 - fixtures
from apps.orders.tests.test_kitchen import _paid_order


def _image(name='m.jpg'):
    buf = BytesIO()
    Image.new('RGB', (40, 40), 'white').save(buf, format='JPEG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


@pytest.mark.django_db
def test_page_is_public_and_links_to_menu(client, menu):
    response = client.get(reverse('core:about'))
    assert response.status_code == 200
    body = response.content.decode()
    assert 'ร้านทดสอบ' in body and f'href="{reverse("core:home")}"' in body
    assert 'กะเพราหมู' in body and 'น้ำเปล่า' in body                  # เมนูจริงของสาขา
    assert 'og:title' in body and 'og:image' in body
    assert 'salespage.js' in body and 'sp-nav' in body
    assert 'เกี่ยวกับร้าน' in client.get(reverse('core:home')).content.decode()   # ลิงก์จากหน้าร้าน


@pytest.mark.django_db
def test_best_seller_first_and_sold_out_hidden(client, menu, customer_client, customer):
    _paid_order(customer_client, customer, menu, qty=3)                 # กะเพราขายแล้ว
    MenuItem.objects.filter(pk=menu['water'].pk).update(is_available=False)
    body = client.get(reverse('core:about')).content.decode()
    assert 'ขายดี' in body and 'กะเพราหมู' in body
    assert 'น้ำเปล่า' not in body                                     # หมดแล้วไม่โชว์


@pytest.mark.django_db
def test_floating_images_only_from_real_menu_photos(client, menu):
    body = client.get(reverse('core:about')).content.decode()
    assert 'sp-float-1' not in body                                     # ไม่มีรูปเมนู = ไม่มีรูปลอย
    item = menu['kaprao']
    item.image.save('k.jpg', _image(), save=True)
    body = client.get(reverse('core:about')).content.decode()
    assert 'sp-float-1' in body and item.image.url in body
    assert f'content="http://testserver{item.image.url}"' in body       # og:image ใช้รูปเมนูเมื่อไม่มีภาพร้าน


@pytest.mark.django_db
def test_shop_facts_shown_only_when_set(client, branch):
    body = client.get(reverse('core:about')).content.decode()
    assert 'bi-clock' not in body                                        # ยังไม่ได้ตั้งเวลาเปิด
    Branch.objects.filter(pk=branch.pk).update(opens_at='10:00', closes_at='20:00', address='99 ถนนทดสอบ')
    body = client.get(reverse('core:about')).content.decode()
    assert '10:00 - 20:00' in body and '99 ถนนทดสอบ' in body and 'ส่งไกลสุด' in body


@pytest.mark.django_db
def test_page_works_without_any_branch(client):
    response = client.get(reverse('core:about'))
    assert response.status_code == 200
    body = response.content.decode()
    assert 'id="popular"' not in body and 'id="shop"' not in body       # ไม่มีข้อมูลก็ไม่แสดงส่วนนั้น


@pytest.mark.django_db
def test_query_count_is_small(client, menu, django_assert_max_num_queries):
    with django_assert_max_num_queries(8):
        client.get(reverse('core:about'))
