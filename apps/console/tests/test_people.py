from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.accounts.models import Role, User
from apps.console.models import AuditLog
from apps.core.templatetags.tmpp_tags import audit_change
from apps.delivery.models import RiderPayout
from apps.delivery.selectors import payout_selector
from apps.delivery.services import payout_service
from apps.delivery.tests.test_jobs import act, make_rider, paid_order
from apps.orders.models import Order, OrderStatus
from apps.orders.selectors import order_selector
from apps.orders.tests.conftest import (  # noqa: F401 - fixtures
    branch, checkout_payload, customer, customer_client, menu, owner_client,
)


def _photo():
    buf = BytesIO()
    Image.new('RGB', (20, 20)).save(buf, format='JPEG')
    return SimpleUploadedFile('p.jpg', buf.getvalue(), content_type='image/jpeg')


def deliver(rider_client, customer_client, customer, menu):
    order = paid_order(customer_client, customer, menu, status=OrderStatus.READY)
    act(rider_client, order, 'accept')
    act(rider_client, order, 'pickup')
    rider_client.post(reverse('delivery:rider_complete', args=[order.pk]), {'photos': _photo()})
    order.refresh_from_db()
    assert order.status == OrderStatus.COMPLETED
    return order


# --------------------------------------------------------------------------- ค่าส่งไรเดอร์
@pytest.mark.django_db
def test_rider_pay_flow(owner_client, customer_client, customer, menu):
    rider = make_rider()
    orders = [deliver(rider, customer_client, customer, menu) for _ in range(2)]
    expected = sum(o.rider_fee for o in orders)

    body = owner_client.get(reverse('console:rider_pay')).content.decode()
    assert f'฿{expected:.0f}' in body and '2 เที่ยว' in body

    owner_client.post(reverse('console:rider_pay_record', args=[rider.user.pk]),
                      {'expected_amount': str(expected), 'note': 'โอนพร้อมเพย์'})
    payout = RiderPayout.objects.get()
    assert payout.amount == expected and payout.job_count == 2 and payout.paid_by == owner_client.user
    assert Order.objects.filter(rider_payout=payout).count() == 2
    assert payout_selector.unpaid_total(rider.user) == Decimal('0')
    assert AuditLog.objects.filter(action='rider_payout.create').exists()

    # งานใหม่หลังจ่าย นับเป็นรอบใหม่ ไม่รวมของเก่า
    new = deliver(rider, customer_client, customer, menu)
    assert payout_selector.unpaid_total(rider.user) == new.rider_fee


@pytest.mark.django_db
def test_payout_refuses_when_amount_changed(owner_client, customer_client, customer, menu):
    rider = make_rider()
    order = deliver(rider, customer_client, customer, menu)
    seen = order.rider_fee
    deliver(rider, customer_client, customer, menu)  # มีงานเพิ่มหลังเจ้าของเปิดหน้า
    owner_client.post(reverse('console:rider_pay_record', args=[rider.user.pk]), {'expected_amount': str(seen)})
    assert not RiderPayout.objects.exists()


@pytest.mark.django_db
def test_payout_with_nothing_unpaid_fails(owner_client):
    rider = make_rider()
    with pytest.raises(payout_service.PayoutError):
        payout_service.record_payout(rider.user, paid_by=owner_client.user, expected_amount=Decimal('0'))


@pytest.mark.django_db
def test_unfinished_and_cancelled_jobs_are_not_payable(owner_client, customer_client, customer, menu):
    rider = make_rider()
    order = paid_order(customer_client, customer, menu, status=OrderStatus.READY)
    act(rider, order, 'accept')
    assert payout_selector.unpaid_total(rider.user) == Decimal('0')


@pytest.mark.django_db
def test_rider_pay_list_query_count(owner_client, customer_client, customer, menu, django_assert_max_num_queries):
    for i in range(3):
        make_rider(f'r{i}@example.test')
    with django_assert_max_num_queries(7):  # +1 รายชื่อสาขาบน sidebar
        assert owner_client.get(reverse('console:rider_pay')).status_code == 200


# --------------------------------------------------------------------------- ลูกค้า
@pytest.mark.django_db
def test_customer_list_stats_and_search(owner_client, customer_client, customer, menu):
    rider = make_rider()
    order = deliver(rider, customer_client, customer, menu)
    body = owner_client.get(reverse('console:customers')).content.decode()
    assert customer.email in body and f'฿{order.total:.0f}' in body
    assert customer.email in owner_client.get(reverse('console:customers'), {'q': '0812345678'}).content.decode()
    assert customer.email not in owner_client.get(reverse('console:customers'), {'q': 'nobody'}).content.decode()
    detail = owner_client.get(reverse('console:customer_detail', args=[customer.pk])).content.decode()
    assert order.order_number in detail


@pytest.mark.django_db
def test_block_customer_logs_them_out(owner_client, customer_client, customer, menu):
    owner_client.post(reverse('console:customer_toggle_active', args=[customer.pk]), {'active': '0'})
    customer.refresh_from_db()
    assert not customer.is_active
    assert customer_client.get(reverse('orders:list')).status_code == 302  # session เดิมใช้ไม่ได้
    assert AuditLog.objects.filter(action='customer.deactivate').exists()


@pytest.mark.django_db
def test_customer_endpoints_reject_staff_ids(owner_client):
    rider = make_rider()
    assert owner_client.get(reverse('console:customer_detail', args=[rider.user.pk])).status_code == 404
    assert owner_client.post(reverse('console:customer_toggle_active', args=[rider.user.pk]), {'active': '0'}).status_code == 404


@pytest.mark.django_db
def test_customer_list_query_count(owner_client, django_assert_max_num_queries):
    for i in range(5):
        User.objects.create_user(email=f'c{i}@example.test', password='x' * 12, full_name=f'C{i}', role=Role.CUSTOMER)
    with django_assert_max_num_queries(7):  # +1 รายชื่อสาขาบน sidebar
        assert owner_client.get(reverse('console:customers')).status_code == 200


# --------------------------------------------------------------------------- audit / export / overview
@pytest.mark.django_db
def test_audit_page_filters(owner_client, menu):
    owner_client.post(reverse('console:menu_item_toggle', args=[menu['kaprao'].pk]), {'available': '0'})
    owner_client.post(reverse('console:shop_toggle_open'), {'is_open': '0'})
    body = owner_client.get(reverse('console:audit'), {'action': 'menu'}).content.decode()
    assert 'menu_item.sold_out' in body and 'branch.close' not in body
    assert 'is_available' in body and 'True → False' in body


def test_audit_change_filter():
    assert audit_change([1, 2]) == '1 → 2'
    assert audit_change([None, 'ใหม่']) == '- → ใหม่'
    assert audit_change('ของหมด') == 'ของหมด'


@pytest.mark.django_db
def test_order_csv_export(owner_client, customer_client, customer, menu):
    order = paid_order(customer_client, customer, menu)
    from django.utils import timezone
    today = timezone.localtime(order.created_at).date().isoformat()  # วันที่ตามเวลาไทย ไม่ใช่ UTC
    response = owner_client.get(reverse('console:order_export'), {'start': today, 'end': today})
    content = b''.join(response.streaming_content).decode('utf-8')
    assert content.startswith('﻿') and 'เลขออเดอร์' in content and order.order_number in content
    assert response['Content-Disposition'].startswith('attachment;')
    assert AuditLog.objects.filter(action='order.export').exists()


@pytest.mark.django_db
def test_customer_cannot_export_or_see_people_pages(customer_client):
    for name in ('console:order_export', 'console:rider_pay', 'console:customers', 'console:audit'):
        assert customer_client.get(reverse(name)).status_code == 403


@pytest.mark.django_db
def test_daily_sales_and_top_items(customer_client, customer, menu):
    paid_order(customer_client, customer, menu)
    days = order_selector.daily_sales(days=7)
    assert len(days) == 7 and days[-1]['count'] == 1 and days[-1]['percent'] == 100
    assert order_selector.top_items()[0]['name'] == 'น้ำเปล่า'


@pytest.mark.django_db
def test_overview_renders_with_stats(owner_client, customer_client, customer, menu):
    paid_order(customer_client, customer, menu)
    body = owner_client.get(reverse('console:overview')).content.decode()
    assert 'ยอดขาย 7 วัน' in body and 'เมนูขายดี' in body and 'น้ำเปล่า' in body


@pytest.mark.django_db
def test_console_sidebar_has_no_dead_links(owner_client):
    body = owner_client.get(reverse('console:overview')).content.decode()
    assert 'href="#"' not in body
