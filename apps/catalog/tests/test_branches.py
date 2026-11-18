"""หลายสาขา: ลูกค้าเลือกสาขา, ตะกร้า 1 สาขา, ครัวเห็นเฉพาะสาขาตัวเอง, เจ้าของเพิ่ม/สลับ/ซ่อนสาขา"""
from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.catalog.models import Branch, MenuItem
from apps.notifications.models import Notification
from apps.orders.models import Order, OrderStatus
from apps.orders.services import order_service
from apps.orders.tests.conftest import (  # noqa: F401 - fixtures
    SHOP_LAT, SHOP_LNG, branch, checkout_payload, customer, customer_client, menu, owner_client,
)


@pytest.fixture
def branch2(db):
    return Branch.objects.create(name='สาขาสอง', location=Point(SHOP_LNG + 0.01, SHOP_LAT, srid=4326),
                                 is_open=True, sort_order=5)


@pytest.fixture
def noodle(branch2):
    return MenuItem.objects.create(branch=branch2, name='ก๋วยเตี๋ยว', price=Decimal('50'))


def _kitchen(email, branch=None):
    user = User.objects.create_user(email=email, password='x' * 12, full_name=email, role=Role.KITCHEN, branch=branch)
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_single_branch_goes_straight_to_menu(client, menu):
    body = client.get(reverse('core:home')).content.decode()
    assert 'กะเพราหมู' in body and 'เลือกสาขา' not in body


@pytest.mark.django_db
def test_many_branches_show_picker_then_menu_of_chosen(client, menu, noodle, branch2):
    body = client.get(reverse('core:home')).content.decode()
    assert 'เลือกสาขา' in body and 'สาขาสอง' in body and 'กะเพราหมู' not in body
    client.post(reverse('core:select_branch', args=[branch2.pk]))
    body = client.get(reverse('core:home')).content.decode()
    assert 'ก๋วยเตี๋ยว' in body and 'กะเพราหมู' not in body and 'เปลี่ยนสาขา' in body


@pytest.mark.django_db
def test_switching_branch_clears_cart_from_other_branch(customer_client, menu, branch, branch2, noodle):
    customer_client.post(reverse('core:select_branch', args=[branch.pk]))
    customer_client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})
    # เมนูของอีกสาขาเพิ่มไม่ได้ ขณะที่เลือกสาขาแรกอยู่
    customer_client.post(reverse('orders:cart_add'), {'item_id': noodle.pk})
    assert customer_client.session['cart_v1']['lines'][0]['item_id'] == str(menu['water'].pk)
    assert len(customer_client.session['cart_v1']['lines']) == 1
    customer_client.post(reverse('core:select_branch', args=[branch2.pk]))
    assert not customer_client.session.get('cart_v1', {}).get('lines')


@pytest.mark.django_db
def test_order_is_placed_at_chosen_branch_with_its_rates(customer_client, customer, branch, branch2, noodle, menu):
    Branch.objects.filter(pk=branch2.pk).update(delivery_base_fare=Decimal('40'), rider_base_fare=Decimal('30'))
    customer_client.post(reverse('core:select_branch', args=[branch2.pk]))
    customer_client.post(reverse('orders:cart_add'), {'item_id': noodle.pk})
    customer_client.post(reverse('orders:checkout'), checkout_payload(lng=SHOP_LNG + 0.01))
    order = Order.objects.get(customer=customer)
    assert order.branch_id == branch2.pk and order.delivery_fee == Decimal('40') and order.rider_fee == Decimal('30')


def _paid(customer_client, customer, branch_obj, item):
    customer_client.post(reverse('core:select_branch', args=[branch_obj.pk]))
    customer_client.post(reverse('orders:cart_add'), {'item_id': item.pk})
    customer_client.post(reverse('orders:checkout'), checkout_payload(lng=branch_obj.location.x))
    order = Order.objects.filter(customer=customer).order_by('-created_at').first()
    order_service.transition_order(order, OrderStatus.PAYMENT_REVIEW)
    return order_service.transition_order(order, OrderStatus.PAID)


@pytest.mark.django_db(transaction=True)
def test_kitchen_sees_and_acts_only_on_own_branch(customer_client, customer, branch, branch2, menu, noodle):
    k1, k2 = _kitchen('k1@example.test'), _kitchen('k2@example.test', branch2)  # k1 ไม่ผูก = สาขาหลัก
    o1 = _paid(customer_client, customer, branch, menu['water'])
    o2 = _paid(customer_client, customer, branch2, noodle)
    board1 = k1.get(reverse('orders:kitchen_board')).content.decode()
    board2 = k2.get(reverse('orders:kitchen_board')).content.decode()
    assert o1.order_number in board1 and o2.order_number not in board1
    assert o2.order_number in board2 and o1.order_number not in board2
    # ครัวสาขาสองกดรับออเดอร์ของสาขาหลักไม่ได้ แม้รู้ id
    k2.post(reverse('orders:kitchen_action', args=[o1.pk]), {'action': 'accept'})
    o1.refresh_from_db()
    assert o1.status == OrderStatus.PAID
    # แจ้งเตือนออเดอร์ใหม่ไปเฉพาะครัวของสาขานั้น
    k2_user = User.objects.get(email='k2@example.test')
    assert list(Notification.objects.filter(user=k2_user, kind='kitchen.new').values_list('body', flat=True)) == [
        f'{o2.recipient_name} · ฿{o2.total:,.0f} · สาขาสอง']


@pytest.mark.django_db
def test_owner_adds_branch_hidden_then_shows_it(owner_client, branch):
    owner_client.post(reverse('console:branches'), {'name': 'สาขานาเกลือ'})
    new = Branch.objects.get(name='สาขานาเกลือ')
    assert not new.is_active and not new.is_open and new.delivery_base_fare == branch.delivery_base_fare
    # สลับไปสาขาใหม่อัตโนมัติ: หน้าข้อมูลร้านแก้สาขาใหม่
    assert 'สาขานาเกลือ' in owner_client.get(reverse('console:shop')).content.decode()
    assert 'เลือกสาขา' not in Client().get(reverse('core:home')).content.decode()  # ยังซ่อน ลูกค้าเห็นสาขาเดียว
    owner_client.post(reverse('console:branch_toggle_active', args=[new.pk]), {'active': '1'})
    assert 'เลือกสาขา' in Client().get(reverse('core:home')).content.decode()


@pytest.mark.django_db
def test_cannot_hide_last_active_branch(owner_client, branch):
    owner_client.post(reverse('console:branch_toggle_active', args=[branch.pk]), {'active': '0'})
    assert Branch.objects.get(pk=branch.pk).is_active


@pytest.mark.django_db
def test_console_menu_follows_switched_branch(owner_client, menu, branch2, noodle):
    owner_client.post(reverse('console:branch_switch', args=[branch2.pk]), {'next': reverse('console:menu')})
    body = owner_client.get(reverse('console:menu')).content.decode()
    assert 'ก๋วยเตี๋ยว' in body and 'กะเพราหมู' not in body


@pytest.mark.django_db
def test_branch_switch_ignores_external_next(owner_client, branch2):
    response = owner_client.post(reverse('console:branch_switch', args=[branch2.pk]), {'next': 'https://evil.example.com/'})
    assert response['Location'] == reverse('console:overview')


@pytest.mark.django_db
def test_staff_kitchen_created_with_branch_and_moved(owner_client, branch, branch2):
    owner_client.post(reverse('console:staff'), {
        'role': 'KITCHEN', 'full_name': 'ครัวสอง', 'email': 'kk@example.test', 'phone': '0811112222',
        'password': 'StrongPass!2026', 'branch': str(branch2.pk),
    })
    user = User.objects.get(email='kk@example.test')
    assert user.branch_id == branch2.pk
    owner_client.post(reverse('console:staff_move_branch', args=[user.pk]), {'branch': str(branch.pk)})
    user.refresh_from_db()
    assert user.branch_id == branch.pk


@pytest.mark.django_db
def test_customer_cannot_use_branch_console(customer_client, branch2):
    assert customer_client.post(reverse('console:branches'), {'name': 'x'}).status_code in (302, 403)
    assert not Branch.objects.filter(name='x').exists()
