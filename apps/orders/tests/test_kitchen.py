import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.catalog.models import Branch
from apps.console.models import AuditLog
from apps.orders.models import Order, OrderStatus
from apps.orders.selectors import kitchen_selector
from apps.orders.services import order_service

from .conftest import checkout_payload


@pytest.fixture
def kitchen_client(db):
    user = User.objects.create_user(email='k@example.test', password='x' * 12, full_name='ครัว', role=Role.KITCHEN)
    client = Client()
    client.force_login(user)
    client.user = user
    return client


def _paid_order(customer_client, customer, menu, *, qty=1):
    customer_client.post(reverse('orders:cart_add'), {
        'item_id': menu['kaprao'].pk, 'option_ids': [menu['egg'].pk], 'qty': qty, 'note': 'ไม่เผ็ด',
    })
    customer_client.post(reverse('orders:checkout'), checkout_payload())
    order = Order.objects.filter(customer=customer).order_by('-created_at').first()
    order_service.transition_order(order, OrderStatus.PAYMENT_REVIEW)
    return order_service.transition_order(order, OrderStatus.PAID)


def _action(client, order, action, **extra):
    return client.post(reverse('orders:kitchen_action', args=[order.pk]), {'action': action}, **extra)


@pytest.mark.django_db
def test_kitchen_and_owner_can_open_but_not_customer_or_rider(kitchen_client, owner_client, customer_client, branch):
    url = reverse('orders:kitchen')
    assert kitchen_client.get(url).status_code == 200
    assert owner_client.get(url).status_code == 200
    assert customer_client.get(url).status_code == 403
    rider = User.objects.create_user(email='r@example.test', password='x' * 12, full_name='R', role=Role.RIDER)
    client = Client()
    client.force_login(rider)
    assert client.get(url).status_code == 403
    assert client.post(reverse('orders:kitchen_toggle_shop'), {'is_open': '0'}).status_code == 403


@pytest.mark.django_db
def test_paid_order_shows_on_board_with_items_options_and_notes(kitchen_client, customer_client, customer, menu):
    order = _paid_order(customer_client, customer, menu, qty=2)
    body = kitchen_client.get(reverse('orders:kitchen_board')).content.decode()
    assert order.order_number in body and 'กะเพราหมู' in body and 'ไข่ดาว' in body and 'ไม่เผ็ด' in body
    assert 'รับออเดอร์' in body
    # id ของออเดอร์ใหม่ส่งให้ JS ใช้เล่นเสียง
    assert str(order.pk) in body and 'kds-new-ids' in body


@pytest.mark.django_db
def test_unpaid_orders_do_not_reach_kitchen(kitchen_client, customer_client, customer, menu):
    customer_client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})
    customer_client.post(reverse('orders:checkout'), checkout_payload())
    order = Order.objects.get(customer=customer)
    assert order.order_number not in kitchen_client.get(reverse('orders:kitchen_board')).content.decode()


@pytest.mark.django_db
def test_accept_then_ready_flow(kitchen_client, customer_client, customer, menu):
    order = _paid_order(customer_client, customer, menu)
    body = _action(kitchen_client, order, 'accept').content.decode()
    order.refresh_from_db()
    assert order.status == OrderStatus.PREPARING and 'อาหารพร้อม' in body
    _action(kitchen_client, order, 'ready')
    order.refresh_from_db()
    assert order.status == OrderStatus.READY
    log = order.status_logs.get(to_status=OrderStatus.READY)
    assert log.actor == kitchen_client.user and log.note == 'อาหารพร้อมส่ง'


@pytest.mark.django_db
def test_double_tap_shows_toast_and_does_not_break(kitchen_client, customer_client, customer, menu):
    order = _paid_order(customer_client, customer, menu)
    _action(kitchen_client, order, 'accept')
    response = _action(kitchen_client, order, 'accept')
    assert response.status_code == 200
    toast = json.loads(response['HX-Trigger'])['tmpp:toast']
    assert order.order_number in toast['message']
    assert order.status_logs.filter(to_status=OrderStatus.PREPARING).count() == 1


@pytest.mark.django_db
def test_cannot_skip_to_ready_or_use_unknown_action(kitchen_client, customer_client, customer, menu):
    order = _paid_order(customer_client, customer, menu)
    _action(kitchen_client, order, 'ready')
    _action(kitchen_client, order, 'complete')
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID


@pytest.mark.django_db
def test_cancel_uses_prompt_reason_and_audits(kitchen_client, customer_client, customer, menu):
    order = _paid_order(customer_client, customer, menu)
    response = _action(kitchen_client, order, 'cancel')  # ไม่มีเหตุผล
    assert 'เหตุผล' in json.loads(response['HX-Trigger'])['tmpp:toast']['message']
    _action(kitchen_client, order, 'cancel', HTTP_HX_PROMPT='ของหมด')
    order.refresh_from_db()
    assert order.status == OrderStatus.CANCELLED and order.cancelled_reason == 'ของหมด'
    assert AuditLog.objects.filter(action='order.cancel', actor=kitchen_client.user).exists()


@pytest.mark.django_db
def test_kitchen_toggles_shop_and_menu_item(kitchen_client, client, branch, menu):
    kitchen_client.post(reverse('orders:kitchen_toggle_shop'), {'is_open': '0'})
    assert not Branch.objects.get(pk=branch.pk).is_open
    kitchen_client.post(reverse('orders:kitchen_toggle_item', args=[menu['kaprao'].pk]), {'available': '0'})
    menu['kaprao'].refresh_from_db()
    assert not menu['kaprao'].is_available
    assert 'กะเพราหมู' not in client.get(reverse('core:home')).content.decode()
    assert AuditLog.objects.filter(action__in=['branch.close', 'menu_item.sold_out']).count() == 2


@pytest.mark.django_db
def test_waiting_minutes_and_late_flag(customer_client, customer, menu):
    order = _paid_order(customer_client, customer, menu)
    Order.objects.filter(pk=order.pk).update(paid_at=timezone.now() - timedelta(minutes=20))
    data = kitchen_selector.board()
    ticket = data['new_orders'][0]
    assert ticket.waiting_minutes >= 20 and ticket.is_late


@pytest.mark.django_db
def test_board_query_count_is_constant(kitchen_client, customer_client, customer, menu, django_assert_max_num_queries):
    for _ in range(5):
        _paid_order(customer_client, customer, menu)
    # session + user + orders + items + delivering (ไม่โตตามจำนวนออเดอร์)
    with django_assert_max_num_queries(6):
        response = kitchen_client.get(reverse('orders:kitchen_board'))
    assert response.content.decode().count('รับออเดอร์') == 5


@pytest.mark.django_db
def test_customer_sees_kitchen_progress(kitchen_client, customer_client, customer, menu):
    order = _paid_order(customer_client, customer, menu)
    _action(kitchen_client, order, 'accept')
    body = customer_client.get(reverse('orders:detail', args=[order.pk])).content.decode()
    assert 'ครัวกำลังทำ' in body
    assert Decimal(order.total) > 0
