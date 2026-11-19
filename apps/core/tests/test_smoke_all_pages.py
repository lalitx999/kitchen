"""
QC: เปิดทุกหน้าที่ไม่ต้องใส่ id ด้วยทุกบทบาท ต้องไม่มี error 500
(หน้าที่ไม่มีสิทธิ์ได้ 302/403/404 ได้ แต่ห้ามพัง) · มีข้อมูลจริงครบ: 2 สาขา เมนู ออเดอร์ทุกสถานะ
"""
from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from apps.accounts.models import Role, User
from apps.catalog.models import Branch, MenuItem
from apps.delivery.services import rider_service
from apps.orders.models import Order, OrderStatus
from apps.orders.services import order_service
from apps.orders.tests.conftest import (  # noqa: F401 - fixtures
    SHOP_LAT, SHOP_LNG, branch, checkout_payload, customer, customer_client, menu,
)

SKIP_PREFIXES = ('admin', 'dev/', 'static', 'media')


def _plain_urls():
    """path ที่ไม่มีพารามิเตอร์ (GET ได้ทันที)"""
    out = []

    def walk(patterns, prefix='', ns=''):
        for p in patterns:
            if isinstance(p, URLResolver):
                new_ns = f'{ns}:{p.namespace}' if ns and p.namespace else (p.namespace or ns)
                walk(p.url_patterns, prefix + str(p.pattern), new_ns)
            elif isinstance(p, URLPattern) and p.name and not p.pattern.converters:
                route = prefix + str(p.pattern)
                if route.startswith(SKIP_PREFIXES) or '<' in route or '(' in route:
                    continue
                out.append(f'{ns}:{p.name}'.lstrip(':'))
    walk(get_resolver().url_patterns)
    return sorted(set(out))


def _login(email, role, **extra):
    user = User.objects.create_user(email=email, password='x' * 12, full_name=email, role=role, **extra)
    if role == Role.RIDER:
        rider_service.create_rider_profile(user)
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def world(customer_client, customer, menu, branch):
    Branch.objects.create(name='สาขาสอง', location=Point(SHOP_LNG + 0.01, SHOP_LAT, srid=4326), is_open=True)
    customer_client.post(reverse('core:select_branch', args=[branch.pk]))
    orders = []
    for target in (OrderStatus.PENDING_PAYMENT, OrderStatus.PAID, OrderStatus.PREPARING, OrderStatus.READY,
                   OrderStatus.CANCELLED):
        customer_client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})
        customer_client.post(reverse('orders:checkout'), checkout_payload())
        order = Order.objects.filter(customer=customer).order_by('-created_at').first()
        path = {OrderStatus.PENDING_PAYMENT: [], OrderStatus.CANCELLED: [OrderStatus.CANCELLED],
                OrderStatus.PAID: [OrderStatus.PAYMENT_REVIEW, OrderStatus.PAID],
                OrderStatus.PREPARING: [OrderStatus.PAYMENT_REVIEW, OrderStatus.PAID, OrderStatus.PREPARING],
                OrderStatus.READY: [OrderStatus.PAYMENT_REVIEW, OrderStatus.PAID, OrderStatus.PREPARING, OrderStatus.READY]}[target]
        for step in path:
            order = order_service.transition_order(order, step)
        orders.append(order)
    return orders


@pytest.mark.django_db
def test_every_plain_page_renders_for_every_role(world, customer_client):
    clients = {
        'anon': Client(),
        'customer': customer_client,
        'owner': _login('o@example.test', Role.OWNER),
        'kitchen': _login('k@example.test', Role.KITCHEN),
        'rider': _login('r@example.test', Role.RIDER),
    }
    # ไรเดอร์มีงานกำลังไปส่ง 1 งาน (หน้าไรเดอร์แสดงฟอร์มถ่ายรูป)
    rider_user = User.objects.get(email='r@example.test')
    ready = next(o for o in world if o.status == OrderStatus.READY)
    order_service.assign_rider(ready, rider_user)
    order_service.transition_order(Order.objects.get(pk=ready.pk), OrderStatus.DELIVERING, actor=rider_user)

    failures = []
    for name in _plain_urls():
        url = reverse(name)
        for role, client in clients.items():
            response = client.get(url)
            if response.status_code >= 500:
                failures.append(f'{role} GET {url} -> {response.status_code}')
            elif response.status_code == 200 and response.get('Content-Type', '').startswith('text/html'):
                body = response.content.decode()
                # comment {# #} ของ Django ใช้ได้บรรทัดเดียว ถ้าขึ้นบรรทัดใหม่จะโผล่บนหน้าเว็บ (บั๊กที่เจอจริง)
                if '{#' in body or '#}' in body or '{%' in body:
                    failures.append(f'{role} GET {url} -> template syntax shown as text')
    assert not failures, '\n'.join(failures)


@pytest.mark.django_db
def test_order_pages_render_in_every_status(world, customer_client):
    owner = _login('o2@example.test', Role.OWNER)
    for order in world:
        assert customer_client.get(reverse('orders:detail', args=[order.pk])).status_code == 200, order.status
        assert owner.get(reverse('console:order_detail', args=[order.pk])).status_code == 200, order.status


def test_no_htmx_inside_alpine_templates():
    """
    ปุ่ม hx-* ใน <template x-if/x-for> ถูก Alpine สร้างทีหลัง HTMX ไม่รู้จัก กดแล้วเงียบ
    (บั๊กจริง: ปุ่ม + / - ในหน้าตะกร้า) · ใช้ x-show หรือสลับ class แทน
    """
    import re
    from pathlib import Path

    from django.conf import settings

    bad = []
    for path in Path(settings.BASE_DIR, 'templates').rglob('*.html'):
        for block in re.findall(r'<template[^>]*x-(?:if|for)[^>]*>(.*?)</template>', path.read_text(), re.S):
            if re.search(r'\shx-(get|post|put|patch|delete)=', block):
                bad.append(str(path))
    assert not bad, bad
