"""M13 แอปไรเดอร์: แถบล่าง 4 แท็บ, หน้างาน (นำทาง), ถึงร้านแล้ว, หน้าส่งสำเร็จ, ประวัติ, รายได้"""
import pytest
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.orders.models import Order, OrderStatus
from apps.orders.services import order_service
from apps.orders.tests.conftest import (  # noqa: F401 - fixtures
    branch, customer, customer_client, menu, owner_client,
)

from .test_jobs import _clear_cache, act, make_rider, paid_order, photo, rider_client  # noqa: F401 - fixtures

SHEET = {'HTTP_HX_REQUEST': 'true', 'HTTP_HX_TARGET': 'job-sheet'}


def sheet_act(client, order, action):
    return client.post(reverse('delivery:rider_job_action', args=[order.pk]), {'action': action}, **SHEET)


@pytest.mark.django_db
def test_home_has_four_stat_tiles_and_bottom_nav(rider_client):
    body = rider_client.get(reverse('delivery:rider_home')).content.decode()
    for label in ('งานรอรับ', 'ส่งวันนี้', 'ค่าส่งวันนี้', 'กม. วันนี้'):
        assert label in body
    for url in ('delivery:rider_history', 'delivery:rider_earnings', 'delivery:rider_profile'):
        assert reverse(url) in body
    assert 'rider.js' in body and 'id="rider-config"' in body


@pytest.mark.django_db
def test_every_tab_page_renders_for_rider(rider_client):
    for name in ('rider_home', 'rider_history', 'rider_earnings', 'rider_profile'):
        response = rider_client.get(reverse(f'delivery:{name}'))
        assert response.status_code == 200, name
        assert 'rider.js' in response.content.decode(), name   # GPS ส่งต่อได้ทุกแท็บ


@pytest.mark.django_db
def test_job_page_only_for_own_rider(rider_client, customer_client, customer, menu, settings):
    settings.GOOGLE_MAPS_API_KEY = ''
    order = paid_order(customer_client, customer, menu)
    url = reverse('delivery:rider_job', args=[order.pk])
    assert rider_client.get(url).status_code == 404            # ยังไม่ได้รับงาน

    act(rider_client, order, 'accept')
    body = rider_client.get(url).content.decode()
    assert 'ไปรับที่ร้าน' in body and 'ถึงร้านแล้ว' in body
    assert 'GOOGLE_MAPS_API_KEY' in body and 'maps.googleapis.com' not in body   # ไม่มีคีย์: บอกวิธีแก้ ไม่โหลดแผนที่
    assert 'rider-bottom-nav' not in body                         # หน้างานเต็มจอ ไม่มีแถบล่าง

    other = make_rider('other@example.test')
    assert other.get(url).status_code == 404
    assert other.get(reverse('delivery:rider_job_sheet', args=[order.pk])).status_code == 404
    assert other.get(reverse('delivery:rider_job_done', args=[order.pk])).status_code == 404


@pytest.mark.django_db
def test_job_page_loads_map_only_with_key(rider_client, customer_client, customer, menu, settings):
    settings.GOOGLE_MAPS_API_KEY = 'AIza' + 'x' * 35
    order = paid_order(customer_client, customer, menu)
    act(rider_client, order, 'accept')
    body = rider_client.get(reverse('delivery:rider_job', args=[order.pk])).content.decode()
    assert 'maps.googleapis.com' in body and 'tmppInitRiderMap' in body


@pytest.mark.django_db
def test_arrive_at_shop_shows_on_kitchen_and_is_idempotent(rider_client, customer_client, customer, menu, owner_client):
    order = paid_order(customer_client, customer, menu, status=OrderStatus.PREPARING)
    act(rider_client, order, 'accept')
    response = sheet_act(rider_client, order, 'arrive')
    assert 'แจ้งครัวแล้วว่าถึงร้าน' in response.content.decode()
    order.refresh_from_db()
    first = order.rider_arrived_at
    assert first is not None

    sheet_act(rider_client, order, 'arrive')                    # กดซ้ำ ไม่เปลี่ยนเวลา ไม่บันทึกซ้ำ
    order.refresh_from_db()
    assert order.rider_arrived_at == first
    assert order.status_logs.filter(note__contains='ถึงร้านแล้ว').count() == 1

    board = owner_client.get(reverse('orders:kitchen_board')).content.decode()
    assert 'ถึงร้านแล้ว' in board


@pytest.mark.django_db
def test_release_from_job_sheet_redirects_home_and_clears_arrival(rider_client, customer_client, customer, menu):
    order = paid_order(customer_client, customer, menu)
    act(rider_client, order, 'accept')
    sheet_act(rider_client, order, 'arrive')
    response = sheet_act(rider_client, order, 'release')
    assert response.status_code == 204 and response['HX-Redirect'] == reverse('delivery:rider_home')
    order.refresh_from_db()
    assert order.rider_id is None and order.rider_arrived_at is None


@pytest.mark.django_db
def test_full_flow_ends_on_done_page(rider_client, customer_client, customer, menu, settings, tmp_path):
    order = paid_order(customer_client, customer, menu, status=OrderStatus.READY)
    act(rider_client, order, 'accept')
    body = sheet_act(rider_client, order, 'pickup').content.decode()
    assert 'ไปส่งที่' in body and 'ถึงแล้ว ถ่ายรูป' in body and 'โทรลูกค้า' in body

    response = rider_client.post(reverse('delivery:rider_complete', args=[order.pk]), {'photos': [photo(), photo()]})
    done_url = reverse('delivery:rider_job_done', args=[order.pk])
    assert response.status_code == 302 and response['Location'] == done_url
    body = rider_client.get(done_url).content.decode()
    assert 'ส่งสำเร็จ' in body and '2 รูป' in body
    # หน้างาน/แผ่นล่างของงานที่ส่งแล้ว -> ไปหน้าสรุป
    assert rider_client.get(reverse('delivery:rider_job', args=[order.pk]))['Location'] == done_url
    assert rider_client.get(reverse('delivery:rider_job_sheet', args=[order.pk]))['HX-Redirect'] == done_url


@pytest.mark.django_db
def test_complete_without_photo_returns_to_job_page(rider_client, customer_client, customer, menu):
    order = paid_order(customer_client, customer, menu, status=OrderStatus.READY)
    act(rider_client, order, 'accept')
    act(rider_client, order, 'pickup')
    response = rider_client.post(reverse('delivery:rider_complete', args=[order.pk]), {})
    assert response['Location'] == reverse('delivery:rider_job', args=[order.pk])


@pytest.mark.django_db
def test_history_tabs_show_only_own_jobs(rider_client, customer_client, customer, menu):
    active = paid_order(customer_client, customer, menu)
    cancelled = paid_order(customer_client, customer, menu)
    act(rider_client, active, 'accept')
    act(rider_client, cancelled, 'accept')
    owner = User.objects.create_user(email='own@example.test', password='x' * 12, full_name='O', role=Role.OWNER)
    order_service.cancel_by_staff(Order.objects.get(pk=cancelled.pk), owner, 'วัตถุดิบหมด')

    url = reverse('delivery:rider_history')
    all_body = rider_client.get(url).content.decode()
    assert active.order_number[-4:] in all_body and cancelled.order_number[-4:] in all_body
    active_body = rider_client.get(url + '?tab=active').content.decode()
    assert reverse('delivery:rider_job', args=[active.pk]) in active_body
    assert reverse('delivery:rider_job', args=[cancelled.pk]) not in active_body
    assert reverse('delivery:rider_job', args=[cancelled.pk]) in rider_client.get(url + '?tab=cancelled').content.decode()
    assert rider_client.get(url + '?tab=hack').status_code == 200   # แท็บแปลก = ทั้งหมด

    other = make_rider('other2@example.test')
    assert active.order_number[-4:] not in other.get(url).content.decode()


@pytest.mark.django_db
def test_earnings_show_unpaid_fee(rider_client, customer_client, customer, menu):
    order = paid_order(customer_client, customer, menu, status=OrderStatus.READY)
    act(rider_client, order, 'accept')
    act(rider_client, order, 'pickup')
    rider_client.post(reverse('delivery:rider_complete', args=[order.pk]), {'photos': [photo()]})
    order.refresh_from_db()
    body = rider_client.get(reverse('delivery:rider_earnings')).content.decode()
    assert 'ร้านยังไม่ได้จ่าย' in body and order.order_number in body
    assert f'฿{order.rider_fee:.0f}' in body


@pytest.mark.django_db
def test_rider_pages_query_count_does_not_grow(rider_client, customer_client, customer, menu, django_assert_max_num_queries):
    for _ in range(3):
        act(rider_client, paid_order(customer_client, customer, menu), 'accept')
    with django_assert_max_num_queries(14):
        rider_client.get(reverse('delivery:rider_jobs'))
    with django_assert_max_num_queries(10):
        rider_client.get(reverse('delivery:rider_history'))
