"""M14 จอครัว: แถบซ้าย, มุมมอง display/board, สีตามเวลารอ (ตั้งใน Console), ต้องทำรวม, ยกเลิกพร้อมเหตุผล, เมนูหมด, วันนี้"""
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Branch
from apps.console.tests.test_menu_and_orders import _shop_post
from apps.orders.models import Order, OrderStatus
from apps.orders.selectors import kitchen_selector

from .test_kitchen import _action, _paid_order, kitchen_client  # noqa: F401 - fixture


def _age(order, minutes):
    Order.objects.filter(pk=order.pk).update(paid_at=timezone.now() - timedelta(minutes=minutes, seconds=5))


def test_wait_level_thresholds():
    assert kitchen_selector.wait_level(0, 10, 15) == 'ok'
    assert kitchen_selector.wait_level(10, 10, 15) == 'warn'
    assert kitchen_selector.wait_level(15, 10, 15) == 'late'


@pytest.mark.django_db
def test_ticket_colour_follows_branch_thresholds(customer_client, customer, menu):
    branch = menu['kaprao'].branch
    Branch.objects.filter(pk=branch.pk).update(kitchen_warn_minutes=2, kitchen_late_minutes=5)
    fresh, middle, old = (_paid_order(customer_client, customer, menu) for _ in range(3))
    _age(middle, 3)
    _age(old, 6)
    data = kitchen_selector.board(Branch.objects.get(pk=branch.pk))
    levels = {o.pk: o.wait_level for o in data['active_orders']}
    assert levels == {fresh.pk: 'ok', middle.pk: 'warn', old.pk: 'late'}
    assert (data['warn_minutes'], data['late_minutes']) == (2, 5)


@pytest.mark.django_db
def test_ready_order_is_never_late(customer_client, customer, menu, kitchen_client):
    order = _paid_order(customer_client, customer, menu)
    _action(kitchen_client, order, 'accept')
    _action(kitchen_client, order, 'ready')
    _age(order, 60)
    ticket = kitchen_selector.board(order.branch)['ready_orders'][0]
    assert ticket.wait_level == 'ok' and not ticket.is_late


@pytest.mark.django_db
def test_display_is_default_and_view_choice_is_remembered(kitchen_client, customer_client, customer, menu):
    _paid_order(customer_client, customer, menu)
    body = kitchen_client.get(reverse('orders:kitchen')).content.decode()
    assert 'kds-grid' in body and 'kds-col-title' not in body
    assert 'kds-side' in body and reverse('orders:kitchen_menu') in body and reverse('orders:kitchen_history') in body

    body = kitchen_client.get(reverse('orders:kitchen') + '?view=board').content.decode()
    assert 'kds-col-title' in body
    # บอร์ดที่โหลดใหม่ทุก 5 วิ และการกดปุ่ม ใช้มุมมองที่จำไว้
    assert 'kds-col-title' in kitchen_client.get(reverse('orders:kitchen_board')).content.decode()
    kitchen_client.get(reverse('orders:kitchen') + '?view=weird')
    assert 'kds-col-title' in kitchen_client.get(reverse('orders:kitchen_board')).content.decode()


@pytest.mark.django_db
def test_to_cook_summary_adds_up_unfinished_orders(customer_client, customer, menu, kitchen_client):
    a = _paid_order(customer_client, customer, menu, qty=2)
    _paid_order(customer_client, customer, menu, qty=3)
    data = kitchen_selector.board(a.branch)
    assert data['to_cook'] == [('กะเพราหมู', 5)]
    _action(kitchen_client, a, 'accept')
    _action(kitchen_client, a, 'ready')                          # เสร็จแล้วไม่นับ
    assert kitchen_selector.board(a.branch)['to_cook'] == [('กะเพราหมู', 3)]
    assert 'ต้องทำรวม' in kitchen_client.get(reverse('orders:kitchen_board')).content.decode()


@pytest.mark.django_db
def test_cancel_modal_reason_reaches_order(customer_client, customer, menu, kitchen_client):
    order = _paid_order(customer_client, customer, menu)
    body = kitchen_client.get(reverse('orders:kitchen')).content.decode()
    assert 'วัตถุดิบหมด' in body and f'data-cancel-url="{reverse("orders:kitchen_action", args=[order.pk])}"' in body

    response = _action(kitchen_client, order, 'cancel', HTTP_HX_REQUEST='true')
    assert 'tmpp:toast' in response.get('HX-Trigger', '')          # ไม่มีเหตุผล = ไม่ยกเลิก
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID

    kitchen_client.post(reverse('orders:kitchen_action', args=[order.pk]), {'action': 'cancel', 'reason': 'วัตถุดิบหมด'})
    order.refresh_from_db()
    assert order.status == OrderStatus.CANCELLED and order.cancelled_reason == 'วัตถุดิบหมด'


@pytest.mark.django_db
def test_history_shows_today_left_and_cancelled_for_own_branch(customer_client, customer, menu, kitchen_client):
    done = _paid_order(customer_client, customer, menu)
    cancelled = _paid_order(customer_client, customer, menu)
    waiting = _paid_order(customer_client, customer, menu)
    Order.objects.filter(pk=done.pk).update(status=OrderStatus.DELIVERING)
    kitchen_client.post(reverse('orders:kitchen_action', args=[cancelled.pk]), {'action': 'cancel', 'reason': 'ลูกค้าขอยกเลิก'})

    body = kitchen_client.get(reverse('orders:kitchen_history')).content.decode()
    assert done.order_number[-4:] in body and cancelled.order_number[-4:] in body
    assert 'ลูกค้าขอยกเลิก' in body
    assert f'#{waiting.order_number[-4:]}' not in body                 # ยังอยู่ในครัว ไม่ใช่ประวัติ

    other = Branch.objects.create(name='สาขาอื่น', is_open=True)
    assert kitchen_selector.today_history(other) == []


@pytest.mark.django_db
def test_menu_page_lists_items_and_toggles(kitchen_client, menu):
    body = kitchen_client.get(reverse('orders:kitchen_menu')).content.decode()
    assert 'กะเพราหมู' in body and 'น้ำเปล่า' in body
    response = kitchen_client.post(reverse('orders:kitchen_toggle_item', args=[menu['water'].pk]), {'available': '0'})
    assert 'หมด' in response.content.decode()


@pytest.mark.django_db
def test_owner_sets_thresholds_and_late_must_exceed_warn(owner_client, branch):
    owner_client.get(reverse('console:shop'))
    response = _shop_post(owner_client, kitchen_warn_minutes='12', kitchen_late_minutes='12')
    assert response.status_code == 200 and 'ต้องมากกว่าเวลาเริ่มเตือน' in response.content.decode()
    _shop_post(owner_client, kitchen_warn_minutes='8', kitchen_late_minutes='20')
    branch.refresh_from_db()
    assert (branch.kitchen_warn_minutes, branch.kitchen_late_minutes) == (8, 20)


@pytest.mark.django_db
def test_display_view_query_count_is_constant(kitchen_client, customer_client, customer, menu, django_assert_max_num_queries):
    for _ in range(6):
        _paid_order(customer_client, customer, menu)
    kitchen_client.get(reverse('orders:kitchen') + '?view=display')
    with django_assert_max_num_queries(12):
        kitchen_client.get(reverse('orders:kitchen_board'))
    with django_assert_max_num_queries(12):
        kitchen_client.get(reverse('orders:kitchen_history'))
