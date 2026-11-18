from datetime import time
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import CustomerAddress, Role, User
from apps.orders.models import Order, OrderStatus
from apps.orders.services import order_service

from .conftest import SHOP_LAT, SHOP_LNG, checkout_payload


def _fill_cart(client, menu):
    client.post(reverse('orders:cart_add'), {'item_id': menu['kaprao'].pk, 'option_ids': [menu['egg'].pk], 'qty': 2})
    client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})


# --------------------------------------------------------------------------- checkout
@pytest.mark.django_db
def test_checkout_requires_customer_login(client, menu):
    _fill_cart(client, menu)
    assert client.get(reverse('orders:checkout')).status_code == 302


@pytest.mark.django_db
def test_place_order_snapshots_items_and_prices(customer_client, customer, menu):
    _fill_cart(customer_client, menu)
    response = customer_client.post(reverse('orders:checkout'), checkout_payload())
    order = Order.objects.get(customer=customer)
    assert response['Location'] == reverse('orders:detail', args=[order.pk])
    assert order.status == OrderStatus.PENDING_PAYMENT
    assert order.subtotal == Decimal('150')          # (60+10)x2 + 10
    assert order.delivery_fee == Decimal('30')       # ~1.1 กม.
    assert order.total == Decimal('180')
    assert order.rider_fee == Decimal('25')
    kaprao = order.items.get(name='กะเพราหมู')
    assert kaprao.options == [{'name': 'ไข่ดาว', 'extra_price': '10.00'}]
    assert kaprao.unit_price == Decimal('70') and kaprao.quantity == 2
    assert order.status_logs.count() == 1
    # ตะกร้าถูกล้าง + จำที่อยู่ไว้ใช้ครั้งหน้า
    assert customer_client.get(reverse('orders:cart')).context['cart'].is_empty
    assert CustomerAddress.objects.filter(user=customer, address_text='99/1 ถนนทดสอบ').exists()

    # แก้ราคาเมนูทีหลัง ออเดอร์เก่าไม่เปลี่ยน
    menu['kaprao'].price = Decimal('999')
    menu['kaprao'].save()
    order.refresh_from_db()
    assert order.items.get(name='กะเพราหมู').unit_price == Decimal('70')


@pytest.mark.django_db
def test_checkout_without_location_is_rejected(customer_client, menu):
    _fill_cart(customer_client, menu)
    response = customer_client.post(reverse('orders:checkout'), checkout_payload(lat='', lng=''))
    assert response.status_code == 200
    assert 'ปักหมุด' in response.content.decode()
    assert not Order.objects.exists()


@pytest.mark.django_db
def test_checkout_too_far_is_rejected(customer_client, menu):
    _fill_cart(customer_client, menu)
    response = customer_client.post(reverse('orders:checkout'), checkout_payload(lat=SHOP_LAT + 0.5))  # ~55 กม.
    assert 'ไกลเกินระยะส่ง' in response.content.decode()
    assert not Order.objects.exists()


@pytest.mark.django_db
def test_checkout_when_shop_closed_is_rejected(customer_client, menu, branch):
    _fill_cart(customer_client, menu)
    branch.is_open = False
    branch.save()
    response = customer_client.post(reverse('orders:checkout'), checkout_payload())
    assert 'ปิดรับออเดอร์' in response.content.decode()
    assert not Order.objects.exists()


@pytest.mark.django_db
def test_checkout_outside_opening_hours_is_rejected(customer_client, menu, branch):
    _fill_cart(customer_client, menu)
    branch.opens_at, branch.closes_at = time(3, 0), time(3, 1)  # เปิดแค่นาทีเดียวตอนตีสาม
    branch.save()
    response = customer_client.post(reverse('orders:checkout'), checkout_payload())
    assert 'นอกเวลาเปิด' in response.content.decode()


@pytest.mark.django_db
def test_checkout_quote_partial(customer_client, menu):
    _fill_cart(customer_client, menu)
    response = customer_client.post(reverse('orders:checkout_quote'), {'latitude': SHOP_LAT + 0.03, 'longitude': SHOP_LNG})
    body = response.content.decode()
    assert 'ค่าส่ง' in body and '฿36' in body  # ~3.3 กม. -> 30 + 6


# --------------------------------------------------------------------------- pages + isolation
@pytest.fixture
def order(customer_client, customer, menu):
    _fill_cart(customer_client, menu)
    customer_client.post(reverse('orders:checkout'), checkout_payload())
    return Order.objects.get(customer=customer)


@pytest.mark.django_db
def test_customer_sees_own_orders(customer_client, order):
    assert order.order_number in customer_client.get(reverse('orders:list')).content.decode()
    body = customer_client.get(reverse('orders:detail', args=[order.pk])).content.decode()
    assert 'กะเพราหมู' in body and 'ยกเลิกออเดอร์' in body


@pytest.mark.django_db
def test_customer_cannot_see_other_customers_order(order):
    other = User.objects.create_user(email='x@example.test', password='x' * 12, full_name='X', role=Role.CUSTOMER)
    client = Client()
    client.force_login(other)
    assert client.get(reverse('orders:detail', args=[order.pk])).status_code == 404
    assert client.post(reverse('orders:cancel', args=[order.pk])).status_code == 404
    assert order.order_number not in client.get(reverse('orders:list')).content.decode()


@pytest.mark.django_db
def test_customer_cancels_pending_order(customer_client, order):
    customer_client.post(reverse('orders:cancel', args=[order.pk]))
    order.refresh_from_db()
    assert order.status == OrderStatus.CANCELLED and order.cancelled_at


@pytest.mark.django_db
def test_customer_cannot_cancel_after_paid(customer_client, order):
    order_service.transition_order(order, OrderStatus.PAID)
    customer_client.post(reverse('orders:cancel', args=[order.pk]))
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID


@pytest.mark.django_db
def test_status_poll_asks_refresh_only_when_changed(customer_client, order):
    url = reverse('orders:status', args=[order.pk])
    assert 'HX-Trigger' not in customer_client.get(url, {'current': 'PENDING_PAYMENT'})
    order_service.transition_order(order, OrderStatus.PAID)
    assert customer_client.get(url, {'current': 'PENDING_PAYMENT'})['HX-Trigger'] == 'tmpp-order-changed'


# --------------------------------------------------------------------------- state machine
@pytest.mark.django_db
def test_full_happy_path_transitions(order):
    for status in (OrderStatus.PAID, OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.DELIVERING, OrderStatus.COMPLETED):
        order = order_service.transition_order(order, status)
    assert order.paid_at and order.completed_at
    assert list(order.status_logs.values_list('to_status', flat=True)) == [
        'PENDING_PAYMENT', 'PAID', 'PREPARING', 'READY', 'DELIVERING', 'COMPLETED',
    ]


@pytest.mark.django_db
@pytest.mark.parametrize('to_status', [OrderStatus.PREPARING, OrderStatus.COMPLETED, OrderStatus.DELIVERING])
def test_cannot_skip_steps(order, to_status):
    with pytest.raises(order_service.InvalidTransition):
        order_service.transition_order(order, to_status)


@pytest.mark.django_db
def test_cannot_cancel_while_delivering(order):
    for status in (OrderStatus.PAID, OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.DELIVERING):
        order = order_service.transition_order(order, status)
    with pytest.raises(order_service.InvalidTransition):
        order_service.transition_order(order, OrderStatus.CANCELLED)


# --------------------------------------------------------------------------- performance
@pytest.mark.django_db
def test_storefront_query_count_is_constant(client, menu, branch, django_assert_max_num_queries):
    from apps.catalog.models import MenuItem, MenuOption
    for i in range(10):
        item = MenuItem.objects.create(branch=branch, category=menu['category'], name=f'เมนู {i}', price=Decimal('50'))
        MenuOption.objects.create(menu_item=item, name='เพิ่ม', extra_price=Decimal('5'))
    # branch + items + options + categories (+ session) ไม่โตตามจำนวนเมนู
    with django_assert_max_num_queries(6):
        response = client.get(reverse('core:home'))
    assert 'เมนู 9' in response.content.decode()


@pytest.mark.django_db
def test_order_list_query_count_is_constant(customer_client, customer, menu, django_assert_max_num_queries):
    for _ in range(4):
        _fill_cart(customer_client, menu)
        customer_client.post(reverse('orders:checkout'), checkout_payload())
    with django_assert_max_num_queries(5):
        response = customer_client.get(reverse('orders:list'))
    assert response.content.decode().count('กะเพราหมู') == 4
