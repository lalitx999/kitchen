"""คูปองส่วนลด + กลุ่มตัวเลือก + แก้ไขรายการในตะกร้า"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import MenuOption, MenuOptionGroup
from apps.console.models import AuditLog
from apps.orders.models import Coupon, CouponKind, Order, OrderStatus
from apps.orders.services import coupon_service, order_service

from .conftest import branch, checkout_payload, customer, customer_client, menu, owner_client  # noqa: F401


def _coupon(**kw):
    data = dict(code='SAVE30', name='ซื้อครบ 100 ลด 30', kind=CouponKind.AMOUNT, value=Decimal('30'),
                min_subtotal=Decimal('100'))
    data.update(kw)
    return Coupon.objects.create(**data)


def _fill_cart(client, menu, qty=2):
    client.post(reverse('orders:cart_add'), {'item_id': menu['kaprao'].pk, 'qty': qty})  # 60 x qty


@pytest.mark.django_db
def test_coupon_discount_applied_server_side(customer_client, customer, menu):
    _coupon()
    _fill_cart(customer_client, menu)  # 120
    customer_client.post(reverse('orders:checkout'), checkout_payload(coupon_code=' save30 '))
    order = Order.objects.get(customer=customer)
    assert order.discount == Decimal('30') and order.coupon_code == 'SAVE30'
    assert order.total == order.subtotal + order.delivery_fee - Decimal('30')
    assert order.rider_fee == Decimal('25')  # ค่าไรเดอร์ไม่ลด


@pytest.mark.django_db
def test_coupon_min_subtotal_and_per_customer_limit(customer_client, customer, menu):
    _coupon()
    _fill_cart(customer_client, menu, qty=1)  # 60 < 100
    response = customer_client.post(reverse('orders:checkout'), checkout_payload(coupon_code='SAVE30'))
    assert 'สั่งอาหารอีก' in response.content.decode() and not Order.objects.exists()
    _fill_cart(customer_client, menu, qty=1)  # 120
    customer_client.post(reverse('orders:checkout'), checkout_payload(coupon_code='SAVE30'))
    assert Order.objects.count() == 1
    _fill_cart(customer_client, menu, qty=2)
    response = customer_client.post(reverse('orders:checkout'), checkout_payload(coupon_code='SAVE30'))
    assert 'ครบสิทธิ์' in response.content.decode() and Order.objects.count() == 1


@pytest.mark.django_db
def test_cancelled_order_gives_coupon_back(customer_client, customer, menu):
    _coupon()
    _fill_cart(customer_client, menu)
    customer_client.post(reverse('orders:checkout'), checkout_payload(coupon_code='SAVE30'))
    order = Order.objects.get()
    order_service.transition_order(order, OrderStatus.CANCELLED)
    _fill_cart(customer_client, menu)
    customer_client.post(reverse('orders:checkout'), checkout_payload(coupon_code='SAVE30'))
    assert Order.objects.filter(coupon_code='SAVE30').count() == 2


@pytest.mark.parametrize('kind,value,max_discount,fee,expected', [
    (CouponKind.PERCENT, '10', None, '30', '12.00'),
    (CouponKind.PERCENT, '50', '40', '30', '40.00'),
    (CouponKind.FREE_DELIVERY, '0', None, '36', '36.00'),
    (CouponKind.AMOUNT, '500', None, '30', '120.00'),   # ลดไม่เกินค่าอาหาร
])
def test_discount_formula(kind, value, max_discount, fee, expected):
    coupon = Coupon(kind=kind, value=Decimal(value), max_discount=Decimal(max_discount) if max_discount else None)
    assert coupon_service.discount_for(coupon, subtotal=Decimal('120'), delivery_fee=Decimal(fee)) == Decimal(expected)


@pytest.mark.django_db
def test_expired_and_inactive_coupon_rejected(customer):
    _coupon(code='OLD', ends_at=timezone.now() - timedelta(days=1))
    with pytest.raises(coupon_service.CouponError, match='หมดอายุ'):
        coupon_service.apply('OLD', customer=customer, branch=None, subtotal=Decimal('500'))
    _coupon(code='OFF', is_active=False)
    with pytest.raises(coupon_service.CouponError, match='ปิดใช้งาน'):
        coupon_service.apply('off', customer=customer, branch=None, subtotal=Decimal('500'))


@pytest.mark.django_db
def test_checkout_quote_shows_coupon_result(customer_client, menu):
    _coupon(kind=CouponKind.FREE_DELIVERY, value=0, code='FREESHIP', name='ส่งฟรี')
    _fill_cart(customer_client, menu)
    body = customer_client.post(reverse('orders:checkout_quote'), {
        'latitude': checkout_payload()['latitude'], 'longitude': checkout_payload()['longitude'], 'coupon_code': 'freeship',
    }).content.decode()
    assert 'ส่วนลด FREESHIP' in body and 'รวม' in body
    body = customer_client.post(reverse('orders:checkout_quote'), {'coupon_code': 'NOPE'}).content.decode()
    assert 'ไม่พบคูปอง' in body


@pytest.mark.django_db
def test_owner_coupon_crud_with_audit(owner_client, branch):
    url = reverse('console:coupon_create')
    owner_client.post(url, {'code': 'lunch-10', 'name': 'ลด 10%', 'kind': 'PERCENT', 'value': '10', 'max_discount': '50',
                            'min_subtotal': '200', 'per_customer_limit': '1', 'show_in_checkout': 'on', 'is_active': 'on'})
    coupon = Coupon.objects.get(code='LUNCH-10')
    assert coupon.max_discount == Decimal('50')
    bad = owner_client.post(url, {'code': 'X2', 'name': 'x', 'kind': 'PERCENT', 'value': '150', 'per_customer_limit': '1'})
    assert bad.status_code == 200 and not Coupon.objects.filter(code='X2').exists()
    owner_client.post(reverse('console:coupon_edit', args=[coupon.pk]), {
        'code': 'LUNCH-10', 'name': 'ลด 15%', 'kind': 'PERCENT', 'value': '15', 'per_customer_limit': '2', 'is_active': 'on'})
    coupon.refresh_from_db()
    assert coupon.value == Decimal('15') and coupon.per_customer_limit == 2 and not coupon.show_in_checkout
    owner_client.post(reverse('console:coupon_toggle', args=[coupon.pk]), {'active': '0'})
    coupon.refresh_from_db()
    assert not coupon.is_active
    assert owner_client.get(reverse('console:coupon_edit', args=[coupon.pk])).status_code == 200
    owner_client.post(reverse('console:coupon_delete', args=[coupon.pk]))
    assert not Coupon.objects.exists()
    assert set(AuditLog.objects.filter(target_type='coupon').values_list('action', flat=True)) == {
        'coupon.create', 'coupon.update', 'coupon.deactivate', 'coupon.delete'}


@pytest.mark.django_db
def test_deleted_coupon_keeps_order_history(customer_client, customer, menu):
    coupon = _coupon()
    _fill_cart(customer_client, menu)
    customer_client.post(reverse('orders:checkout'), checkout_payload(coupon_code='SAVE30'))
    coupon_service.delete_coupon(coupon)
    order = Order.objects.get()
    assert order.coupon is None and order.coupon_code == 'SAVE30' and order.discount == Decimal('30')


# --------------------------------------------------------------------------- กลุ่มตัวเลือก
@pytest.fixture
def meat_group(menu):
    group = MenuOptionGroup.objects.create(menu_item=menu['kaprao'], name='เลือกเนื้อ', min_select=1, max_select=1)
    pork = MenuOption.objects.create(menu_item=menu['kaprao'], group=group, name='หมู', extra_price=0)
    shrimp = MenuOption.objects.create(menu_item=menu['kaprao'], group=group, name='กุ้ง', extra_price=Decimal('20'))
    return group, pork, shrimp


@pytest.mark.django_db
def test_required_group_and_max_enforced_on_server(customer_client, menu, meat_group):
    _group, pork, shrimp = meat_group
    add = reverse('orders:cart_add')
    customer_client.post(add, {'item_id': menu['kaprao'].pk})
    assert not customer_client.session.get('cart_v1', {}).get('lines')  # ไม่เลือกเนื้อ = ไม่ได้
    customer_client.post(add, {'item_id': menu['kaprao'].pk, 'option_ids': [pork.pk, shrimp.pk]})
    assert not customer_client.session.get('cart_v1', {}).get('lines')  # เกินสูงสุด 1
    customer_client.post(add, {'item_id': menu['kaprao'].pk, 'option_ids': [shrimp.pk, menu['egg'].pk]})
    assert len(customer_client.session['cart_v1']['lines']) == 1


@pytest.mark.django_db
def test_item_sheet_shows_groups_and_edit_replaces_line(customer_client, menu, meat_group):
    _group, pork, shrimp = meat_group
    sheet = customer_client.get(reverse('orders:item_sheet', args=[menu['kaprao'].pk])).content.decode()
    assert 'เลือกเนื้อ' in sheet and 'ต้องเลือก 1' in sheet and 'ตัวเลือกเพิ่มเติม' in sheet
    customer_client.post(reverse('orders:cart_add'), {'item_id': menu['kaprao'].pk, 'option_ids': [pork.pk]})
    key = customer_client.session['cart_v1']['lines'][0]['key']
    edit = customer_client.get(reverse('orders:item_sheet', args=[menu['kaprao'].pk]), {'line': key}).content.decode()
    assert 'บันทึกการแก้ไข' in edit and key in edit
    customer_client.post(reverse('orders:cart_add'), {'item_id': menu['kaprao'].pk, 'option_ids': [shrimp.pk],
                                                      'qty': 3, 'replace_key': key})
    lines = customer_client.session['cart_v1']['lines']
    assert len(lines) == 1 and lines[0]['option_ids'] == [str(shrimp.pk)] and lines[0]['qty'] == 3


@pytest.mark.django_db
def test_cart_page_shows_suggestions_and_partial_refresh(customer_client, menu):
    customer_client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})
    page = customer_client.get(reverse('orders:cart')).content.decode()
    assert 'สรุปคำสั่งซื้อ' in page and 'รายการอื่นที่คนมักสั่งด้วย' in page and 'กะเพราหมู' in page
    partial = customer_client.get(reverse('orders:cart'), HTTP_HX_REQUEST='true').content.decode()
    assert partial.strip().startswith('<div id="cart-body"') or 'id="cart-body"' in partial[:300]


@pytest.mark.django_db
def test_owner_manages_option_groups(owner_client, menu, branch):
    item = menu['kaprao']
    owner_client.post(reverse('console:menu_option_group_add', args=[item.pk]), {'name': 'เลือกเนื้อ', 'required': 'on', 'max_select': '1'})
    group = MenuOptionGroup.objects.get(menu_item=item)
    assert group.min_select == 1 and group.max_select == 1
    owner_client.post(reverse('console:menu_option_add', args=[item.pk]), {'name': 'ทะเล', 'extra_price': '20', 'group': str(group.pk)})
    assert MenuOption.objects.get(name='ทะเล').group_id == group.pk
    assert 'ต้องเลือก 1' in owner_client.get(reverse('console:menu_item_edit', args=[item.pk])).content.decode()
    owner_client.post(reverse('console:menu_option_group_delete', args=[item.pk, group.pk]))
    assert not MenuOption.objects.filter(name='ทะเล').exists()
