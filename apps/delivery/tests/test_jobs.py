import json
from datetime import timedelta
from io import BytesIO

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accounts.models import Role, User
from apps.delivery.models import DeliveryProof, RiderProfile
from apps.delivery.selectors import job_selector
from apps.delivery.services import live_location_service, rider_service
from apps.orders.models import Order, OrderStatus
from apps.orders.services import order_service
from apps.orders.tests.conftest import (  # noqa: F401 - fixtures
    SHOP_LAT, SHOP_LNG, branch, checkout_payload, customer, customer_client, menu, owner_client,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def make_rider(email='rider@example.test', online=True):
    user = User.objects.create_user(email=email, password='x' * 12, full_name='น้องไรเดอร์', phone='0899999999', role=Role.RIDER)
    profile = rider_service.create_rider_profile(user, vehicle_plate='1กข1234')
    if online:
        rider_service.set_online(profile, online=True)
    client = Client()
    client.force_login(user)
    client.user = user
    return client


@pytest.fixture
def rider_client(db):
    return make_rider()


def paid_order(customer_client, customer, menu, status=OrderStatus.PAID):
    customer_client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})
    customer_client.post(reverse('orders:checkout'), checkout_payload())
    order = Order.objects.filter(customer=customer).order_by('-created_at').first()
    for s in (OrderStatus.PAYMENT_REVIEW, OrderStatus.PAID, OrderStatus.PREPARING, OrderStatus.READY):
        order = order_service.transition_order(order, s)
        if s == status:
            break
    return order


def act(client, order, action):
    return client.post(reverse('delivery:rider_job_action', args=[order.pk]), {'action': action})


def photo():
    buf = BytesIO()
    Image.new('RGB', (30, 30), 'blue').save(buf, format='JPEG')
    return SimpleUploadedFile('p.jpg', buf.getvalue(), content_type='image/jpeg')


# --------------------------------------------------------------------------- jobs
@pytest.mark.django_db
def test_paid_order_appears_as_new_job_only_when_online(rider_client, customer_client, customer, menu):
    order = paid_order(customer_client, customer, menu)
    body = rider_client.get(reverse('delivery:rider_jobs')).content.decode()
    assert order.order_number in body and 'รับงานนี้' in body
    offline = make_rider('off@example.test', online=False)
    assert order.order_number not in offline.get(reverse('delivery:rider_jobs')).content.decode()


@pytest.mark.django_db
def test_full_delivery_flow(rider_client, customer_client, customer, menu, settings, tmp_path):
    order = paid_order(customer_client, customer, menu, status=OrderStatus.PREPARING)
    act(rider_client, order, 'accept')
    order.refresh_from_db()
    assert order.rider == rider_client.user and order.rider_assigned_at

    # ครัวยังไม่เสร็จ รับอาหารไม่ได้
    response = act(rider_client, order, 'pickup')
    assert 'ครัวยังทำอาหารไม่เสร็จ' in json.loads(response['HX-Trigger'])['tmpp:toast']['message']
    order_service.transition_order(order, OrderStatus.READY)
    act(rider_client, order, 'pickup')
    order.refresh_from_db()
    assert order.status == OrderStatus.DELIVERING and order.picked_up_at

    response = rider_client.post(reverse('delivery:rider_complete', args=[order.pk]), {
        'photo': photo(), 'latitude': order.delivery_location.y + 0.0001, 'longitude': order.delivery_location.x,
    })
    assert response.status_code == 302
    order.refresh_from_db()
    proof = DeliveryProof.objects.get(order=order)
    assert order.status == OrderStatus.COMPLETED and order.completed_at
    assert proof.rider == rider_client.user and 5 <= proof.distance_to_customer_m <= 20
    assert proof.photo.storage.exists(proof.photo.name)


@pytest.mark.django_db
def test_complete_requires_photo(rider_client, customer_client, customer, menu):
    order = paid_order(customer_client, customer, menu, status=OrderStatus.READY)
    act(rider_client, order, 'accept')
    act(rider_client, order, 'pickup')
    rider_client.post(reverse('delivery:rider_complete', args=[order.pk]), {})
    rider_client.post(reverse('delivery:rider_complete', args=[order.pk]),
                      {'photo': SimpleUploadedFile('x.jpg', b'nope', content_type='image/jpeg')})
    order.refresh_from_db()
    assert order.status == OrderStatus.DELIVERING and not DeliveryProof.objects.exists()


@pytest.mark.django_db
def test_two_riders_cannot_take_same_job(rider_client, customer_client, customer, menu):
    order = paid_order(customer_client, customer, menu)
    other = make_rider('other@example.test')
    act(rider_client, order, 'accept')
    response = act(other, order, 'accept')
    assert 'มีไรเดอร์รับงานนี้ไปแล้ว' in json.loads(response['HX-Trigger'])['tmpp:toast']['message']
    order.refresh_from_db()
    assert order.rider == rider_client.user
    # คนอื่นทำขั้นต่อไปกับงานที่ไม่ใช่ของตัวเองไม่ได้
    order_service.transition_order(order, OrderStatus.PREPARING)
    order_service.transition_order(order, OrderStatus.READY)
    act(other, order, 'pickup')
    order.refresh_from_db()
    assert order.status == OrderStatus.READY


@pytest.mark.django_db
def test_release_job_returns_it_to_pool(rider_client, customer_client, customer, menu):
    order = paid_order(customer_client, customer, menu)
    act(rider_client, order, 'accept')
    act(rider_client, order, 'release')
    order.refresh_from_db()
    assert order.rider is None
    assert order.order_number in rider_client.get(reverse('delivery:rider_jobs')).content.decode()


@pytest.mark.django_db
def test_cannot_go_offline_with_active_job(rider_client, customer_client, customer, menu):
    order = paid_order(customer_client, customer, menu)
    act(rider_client, order, 'accept')
    response = rider_client.post(reverse('delivery:rider_set_status'), {'online': '0'})
    assert 'งานค้าง' in json.loads(response['HX-Trigger'])['tmpp:toast']['message']
    assert RiderProfile.objects.get(user=rider_client.user).is_online


@pytest.mark.django_db
def test_customer_and_kitchen_cannot_use_rider_actions(customer_client, customer, menu, owner_client):
    order = paid_order(customer_client, customer, menu)
    assert act(customer_client, order, 'accept').status_code == 403
    assert act(owner_client, order, 'accept').status_code == 403


@pytest.mark.django_db
def test_rider_today_summary(rider_client, customer_client, customer, menu):
    order = paid_order(customer_client, customer, menu, status=OrderStatus.READY)
    act(rider_client, order, 'accept')
    act(rider_client, order, 'pickup')
    rider_client.post(reverse('delivery:rider_complete', args=[order.pk]), {'photo': photo()})
    summary = job_selector.today_summary(rider_client.user)
    assert summary['jobs'] == 1 and summary['earned'] == order.rider_fee


@pytest.mark.django_db
def test_jobs_query_count_constant(rider_client, customer_client, customer, menu, django_assert_max_num_queries):
    for _ in range(4):
        paid_order(customer_client, customer, menu)
    with django_assert_max_num_queries(8):
        response = rider_client.get(reverse('delivery:rider_jobs'))
    assert response.content.decode().count('รับงานนี้') == 4


# --------------------------------------------------------------------------- live location
def _send(client, **data):
    return client.post(reverse('delivery:rider_location'), json.dumps(data), content_type='application/json')


@pytest.mark.django_db
def test_location_is_stored_and_db_written_at_most_once_a_minute(rider_client):
    assert _send(rider_client, lat=13.75, lng=100.5, accuracy=10).json()['ok']
    loc = live_location_service.get(rider_client.user.pk)
    assert (loc.lat, loc.lng) == (13.75, 100.5)
    profile = RiderProfile.objects.get(user=rider_client.user)
    assert profile.current_location is not None
    first_db_time = profile.location_updated_at
    cache.delete(f'rider:loc:{rider_client.user.pk}')  # ข้ามการกันส่งถี่ 2 วิ
    _send(rider_client, lat=13.76, lng=100.5, accuracy=10)
    profile.refresh_from_db()
    assert profile.location_updated_at == first_db_time  # ยังไม่ครบนาที ไม่เขียน DB ซ้ำ
    assert live_location_service.get(rider_client.user.pk).lat == 13.76


@pytest.mark.django_db
@pytest.mark.parametrize('payload', [{'lat': 0, 'lng': 0}, {'lat': 95, 'lng': 1}, {'lat': 'x', 'lng': 1}, {'lng': 1},
                                     {'lat': 13.7, 'lng': 100.5, 'accuracy': 5000}])
def test_bad_locations_rejected(rider_client, payload):
    response = _send(rider_client, **payload)
    assert response.status_code == 400 and not response.json()['ok']
    assert live_location_service.get(rider_client.user.pk) is None


@pytest.mark.django_db
def test_offline_rider_location_not_stored(db):
    client = make_rider('off2@example.test', online=False)
    assert _send(client, lat=13.75, lng=100.5).status_code == 409


@pytest.mark.django_db
def test_customer_tracking_only_while_delivering(rider_client, customer_client, customer, menu):
    order = paid_order(customer_client, customer, menu, status=OrderStatus.READY)
    act(rider_client, order, 'accept')
    url = reverse('orders:tracking', args=[order.pk])
    assert 'ห่างจากบ้าน' not in customer_client.get(url).content.decode()

    act(rider_client, order, 'pickup')
    assert 'กำลังรอตำแหน่ง' in customer_client.get(url).content.decode()
    _send(rider_client, lat=SHOP_LAT, lng=SHOP_LNG, accuracy=8)  # อยู่ที่ร้าน ~1.1 กม. จากบ้าน
    body = customer_client.get(url).content.decode()
    assert 'ห่างจากบ้านประมาณ 1.1 กม.' in body and 'น้องไรเดอร์' in body

    # คนอื่นดูไม่ได้
    other = User.objects.create_user(email='o2@example.test', password='x' * 12, full_name='O', role=Role.CUSTOMER)
    c = Client()
    c.force_login(other)
    assert c.get(url).status_code == 404

    # ส่งเสร็จแล้ว ลบตำแหน่งไรเดอร์ (ความเป็นส่วนตัว)
    rider_client.post(reverse('delivery:rider_complete', args=[order.pk]), {'photo': photo()})
    assert live_location_service.get(rider_client.user.pk) is None
    assert 'ส่งถึงแล้ว' in customer_client.get(url).content.decode()


@pytest.mark.django_db
def test_stale_location_is_reported_honestly(rider_client, customer_client, customer, menu):
    order = paid_order(customer_client, customer, menu, status=OrderStatus.READY)
    act(rider_client, order, 'accept')
    act(rider_client, order, 'pickup')
    old = (timezone.now() - timedelta(minutes=5)).isoformat()
    cache.set(f'rider:loc:{rider_client.user.pk}', {'lat': SHOP_LAT, 'lng': SHOP_LNG, 'accuracy': 5,
                                                    'heading': None, 'speed': None, 'updated_at': old}, 600)
    body = customer_client.get(reverse('orders:tracking', args=[order.pk])).content.decode()
    assert 'สัญญาณไม่ดี' in body


@pytest.mark.django_db
def test_proof_photo_access(rider_client, customer_client, customer, menu, owner_client):
    order = paid_order(customer_client, customer, menu, status=OrderStatus.READY)
    act(rider_client, order, 'accept')
    act(rider_client, order, 'pickup')
    rider_client.post(reverse('delivery:rider_complete', args=[order.pk]), {'photo': photo()})
    url = reverse('delivery:proof_photo', args=[order.pk])
    assert customer_client.get(url).status_code == 200
    assert owner_client.get(url).status_code == 200
    assert rider_client.get(url).status_code == 200
    assert make_rider('x@example.test').get(url).status_code == 404
    assert Client().get(url).status_code == 302
