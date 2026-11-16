from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point
from django.test import Client

from apps.accounts.models import Role, User
from apps.catalog.models import Branch, Category, MenuItem, MenuOption

# ร้านทดสอบ: แถวสนามหลวง กรุงเทพ (พิกัดจริง)
SHOP_LAT, SHOP_LNG = 13.7563, 100.5018


@pytest.fixture
def branch(db):
    return Branch.objects.create(
        name='ร้านทดสอบ', phone='0811111111', location=Point(SHOP_LNG, SHOP_LAT, srid=4326), is_open=True,
    )


@pytest.fixture
def menu(branch):
    rice = Category.objects.create(branch=branch, name='ข้าว', sort_order=1)
    kaprao = MenuItem.objects.create(branch=branch, category=rice, name='กะเพราหมู', price=Decimal('60'))
    egg = MenuOption.objects.create(menu_item=kaprao, name='ไข่ดาว', extra_price=Decimal('10'))
    special = MenuOption.objects.create(menu_item=kaprao, name='พิเศษ', extra_price=Decimal('15'))
    water = MenuItem.objects.create(branch=branch, name='น้ำเปล่า', price=Decimal('10'))
    return {'category': rice, 'kaprao': kaprao, 'egg': egg, 'special': special, 'water': water}


@pytest.fixture
def customer(db):
    return User.objects.create_user(email='c@example.test', password='x' * 12, full_name='ลูกค้า ทดสอบ',
                                    phone='0812345678', role=Role.CUSTOMER)


@pytest.fixture
def customer_client(customer):
    client = Client()
    client.force_login(customer)
    return client


@pytest.fixture
def owner_client(db):
    owner = User.objects.create_user(email='o@example.test', password='x' * 12, full_name='Owner', role=Role.OWNER)
    client = Client()
    client.force_login(owner)
    client.user = owner
    return client


def checkout_payload(lat=SHOP_LAT + 0.01, lng=SHOP_LNG, **overrides):
    """ห่างร้านไปทางเหนือ ~1.1 กม. (อยู่ในระยะ 3 กม.แรก)"""
    data = {
        'recipient_name': 'ลูกค้า ทดสอบ', 'recipient_phone': '0812345678',
        'address_text': '99/1 ถนนทดสอบ', 'address_note': 'ประตูเขียว', 'note': 'ไม่เผ็ด',
        'latitude': lat, 'longitude': lng,
    }
    data.update(overrides)
    return data

