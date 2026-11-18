import json
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.catalog.models import Branch

from apps.orders.services import cart_service, pricing_service

from .conftest import SHOP_LAT, SHOP_LNG


@pytest.mark.parametrize('km,fee,rider', [
    ('0.50', '30.00', '25.00'),   # ระยะแรก
    ('3.00', '30.00', '25.00'),   # ขอบพอดี
    ('3.20', '36.00', '30.00'),   # เกิน 0.2 กม. ปัดเป็น 1 กม.
    ('5.00', '42.00', '35.00'),
    ('7.40', '60.00', '50.00'),   # เกิน 4.4 -> 5 กม.
])
def test_delivery_fee_formula(km, fee, rider):
    quote = pricing_service.quote_for_distance(Decimal(km), Branch())
    assert quote.fee == Decimal(fee)
    assert quote.rider_fee == Decimal(rider)
    assert quote.within_range


def test_over_max_distance_is_out_of_range():
    assert not pricing_service.quote_for_distance(Decimal('15.01'), Branch(max_delivery_km=Decimal('15'))).within_range


def test_rates_come_from_branch_and_shop_keeps_the_difference():
    # 3 กม.แรก 30 (ไรเดอร์ 25 ร้าน 5) · กม.ถัดไป 6 (ไรเดอร์ 5 ร้าน 1)
    rows = {r.km: r for r in pricing_service.fee_table(Branch())}
    assert (rows[3].fee, rows[3].rider_fee, rows[3].shop_fee) == (Decimal('30.00'), Decimal('25.00'), Decimal('5.00'))
    assert (rows[5].fee, rows[5].rider_fee, rows[5].shop_fee) == (Decimal('42.00'), Decimal('35.00'), Decimal('7.00'))
    custom = Branch(delivery_base_fare=Decimal('40'), rider_base_fare=Decimal('30'))
    assert pricing_service.quote_for_distance(Decimal('2'), custom).fee == Decimal('40.00')


@pytest.mark.django_db
def test_distance_uses_real_geodesic_distance(branch):
    # 0.01 องศาละติจูด ~ 1.11 กม.
    km = pricing_service.distance_km(branch, pricing_service.make_point(SHOP_LAT + 0.01, SHOP_LNG))
    assert Decimal('1.09') <= km <= Decimal('1.12')


@pytest.mark.parametrize('lat,lng', [(None, None), ('abc', '1'), (0, 0), (91, 100), (13, 181)])
def test_invalid_points_rejected(lat, lng):
    with pytest.raises(pricing_service.InvalidLocation):
        pricing_service.make_point(lat, lng)


# --------------------------------------------------------------------------- cart
@pytest.mark.django_db
def _toast(response) -> dict:
    # header ต้องเป็น ASCII ล้วน (ไม่ถูกเข้ารหัส MIME) และ HTMX อ่านเป็น JSON ได้
    raw = response['HX-Trigger']
    raw.encode('ascii')
    return json.loads(raw)['tmpp:toast']


@pytest.mark.django_db
def test_cart_add_success_toast_is_ascii_json(client, menu):
    response = client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})
    toast = _toast(response)
    assert toast['level'] == 'success' and 'น้ำเปล่า' in toast['message']
    assert 'cart-count-header' in response.content.decode()


@pytest.mark.django_db
def test_cart_prices_from_database_not_from_browser(client, menu):
    client.post(reverse('orders:cart_add'), {
        'item_id': menu['kaprao'].pk, 'option_ids': [menu['egg'].pk], 'qty': 2, 'price': '1',  # ราคาปลอมถูกเมิน
    })
    cart = cart_service.priced_cart(client.session, menu['kaprao'].branch)
    assert cart.subtotal == Decimal('140')  # (60 + 10) x 2
    assert client.session[cart_service.SESSION_KEY]['lines'][0]['qty'] == 2


@pytest.mark.django_db
def test_same_item_same_options_merges_lines(client, menu):
    for _ in range(2):
        client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})
    lines = client.session[cart_service.SESSION_KEY]['lines']
    assert len(lines) == 1 and lines[0]['qty'] == 2


@pytest.mark.django_db
def test_option_from_another_item_is_rejected(client, menu):
    response = client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk, 'option_ids': [menu['egg'].pk]})
    assert 'ตัวเลือกไม่ถูกต้อง' in _toast(response)['message']
    assert cart_service.SESSION_KEY not in client.session or not client.session[cart_service.SESSION_KEY]['lines']


@pytest.mark.django_db
def test_sold_out_item_cannot_be_added(client, menu):
    menu['water'].is_available = False
    menu['water'].save()
    response = client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})
    assert 'หมดแล้ว' in _toast(response)['message']


@pytest.mark.django_db
def test_price_change_after_adding_is_reflected(client, menu):
    client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk, 'qty': 3})
    menu['water'].price = Decimal('12')
    menu['water'].save()
    assert cart_service.priced_cart(client.session, menu['water'].branch).subtotal == Decimal('36')


@pytest.mark.django_db
def test_cart_update_and_remove(client, menu):
    client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk, 'qty': 2})
    key = client.session[cart_service.SESSION_KEY]['lines'][0]['key']
    response = client.post(reverse('orders:cart_update'), {'key': key, 'qty': 5})
    assert 'cart-count-header' in response.content.decode()  # OOB badge
    assert client.session[cart_service.SESSION_KEY]['lines'][0]['qty'] == 5
    client.post(reverse('orders:cart_update'), {'key': key, 'qty': 0})
    assert client.session[cart_service.SESSION_KEY]['lines'] == []


@pytest.mark.django_db
def test_deleted_menu_item_drops_out_of_cart(client, menu):
    client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})
    branch = menu['water'].branch
    menu['water'].delete()
    assert cart_service.priced_cart(client.session, branch).is_empty
