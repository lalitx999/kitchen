import json
from types import SimpleNamespace
from unittest import mock

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.delivery.tests.test_jobs import act, make_rider, paid_order
from apps.notifications.models import DeviceToken, Notification
from apps.notifications.services import notify_service, order_events
from apps.orders.models import OrderStatus
from apps.orders.services import order_service
from apps.orders.tests.conftest import (  # noqa: F401 - fixtures
    branch, checkout_payload, customer, customer_client, menu, owner_client,
)

FULL_WEB_CONFIG = {'apiKey': 'k', 'authDomain': 'x.firebaseapp.com', 'projectId': 'p', 'messagingSenderId': '1', 'appId': 'a'}


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def kinds_for(user):
    return set(Notification.objects.filter(user=user).values_list('kind', flat=True))


# --------------------------------------------------------------------------- เหตุการณ์ออเดอร์ -> ใครได้แจ้งเตือน
@pytest.mark.django_db
def test_paid_notifies_customer_kitchen_owner_and_online_riders(customer_client, customer, menu, owner_client,
                                                               django_capture_on_commit_callbacks):
    kitchen = User.objects.create_user(email='k@example.test', password='x' * 12, full_name='K', role=Role.KITCHEN)
    online, offline = make_rider('on@example.test'), make_rider('off@example.test', online=False)
    with django_capture_on_commit_callbacks(execute=True):
        paid_order(customer_client, customer, menu, status=OrderStatus.PAID)
    assert 'order.paid' in kinds_for(customer)
    assert 'kitchen.new' in kinds_for(kitchen) and 'kitchen.new' in kinds_for(owner_client.user)
    assert 'job.new' in kinds_for(online.user)
    assert not kinds_for(offline.user)


@pytest.mark.django_db
def test_rejected_slip_and_progress_notify_customer(customer_client, customer, menu, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        order = paid_order(customer_client, customer, menu, status=OrderStatus.PAYMENT_REVIEW)
        order_service.transition_order(order, OrderStatus.PENDING_PAYMENT, note='สลิปไม่ผ่าน: ยอดไม่ตรง')
    n = Notification.objects.get(user=customer, kind='slip.rejected')
    assert n.body == 'ยอดไม่ตรง' and n.url == reverse('orders:detail', args=[order.pk])


@pytest.mark.django_db
def test_ready_goes_to_assigned_rider_only(customer_client, customer, menu, django_capture_on_commit_callbacks):
    assigned, other = make_rider('a@example.test'), make_rider('b@example.test')
    order = paid_order(customer_client, customer, menu, status=OrderStatus.PREPARING)
    act(assigned, order, 'accept')
    with django_capture_on_commit_callbacks(execute=True):
        order_service.transition_order(order, OrderStatus.READY)
    assert 'job.ready' in kinds_for(assigned.user)
    assert 'job.ready' not in kinds_for(other.user)


@pytest.mark.django_db
def test_cancel_notifies_customer_and_rider_with_reason(customer_client, customer, menu, django_capture_on_commit_callbacks):
    rider = make_rider()
    order = paid_order(customer_client, customer, menu)
    act(rider, order, 'accept')
    with django_capture_on_commit_callbacks(execute=True):
        order_service.cancel_by_staff(order, None, 'ของหมด')
    assert Notification.objects.get(user=customer, kind='order.cancelled').body == 'ของหมด'
    assert 'job.cancelled' in kinds_for(rider.user)


@pytest.mark.django_db
def test_rollback_sends_nothing(customer_client, customer, menu):
    # ไม่ capture on_commit = เหมือน transaction ถูก rollback -> ไม่มีแจ้งเตือน
    paid_order(customer_client, customer, menu)
    assert not Notification.objects.exists()


@pytest.mark.django_db
def test_slip_review_notifies_owner(customer_client, customer, menu, owner_client, settings, tmp_path,
                                    django_capture_on_commit_callbacks):
    from apps.payments.tests.test_payments import png
    settings.PAYMENT_VERIFICATION_MODE = 'MANUAL'
    settings.PROMPTPAY_ID = '0812345678'
    customer_client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})
    customer_client.post(reverse('orders:checkout'), checkout_payload())
    order = customer.orders.get()
    with django_capture_on_commit_callbacks(execute=True):
        customer_client.post(reverse('payments:upload_slip', args=[order.pk]), {'slip': png()})
    n = Notification.objects.get(user=owner_client.user, kind='slip.review')
    assert n.url == reverse('console:slips')


@pytest.mark.django_db
def test_rider_near_notifies_customer_once(customer_client, customer, menu, django_capture_on_commit_callbacks):
    rider = make_rider()
    order = paid_order(customer_client, customer, menu, status=OrderStatus.READY)
    act(rider, order, 'accept')
    act(rider, order, 'pickup')
    near = {'lat': order.delivery_location.y + 0.001, 'lng': order.delivery_location.x, 'accuracy': 5}  # ~110 ม.
    with django_capture_on_commit_callbacks(execute=True):
        for _ in range(3):
            cache.delete(f'rider:loc:{rider.user.pk}')  # ข้ามการกันส่งถี่
            rider.post(reverse('delivery:rider_location'), json.dumps(near), content_type='application/json')
    assert Notification.objects.filter(user=customer, kind='order.near').count() == 1


@pytest.mark.django_db
def test_inactive_users_are_skipped(customer):
    customer.is_active = False
    customer.save()
    assert notify_service.notify([customer], kind='x', title='t', body='b') == []


@pytest.mark.django_db
def test_event_failure_never_breaks_flow(customer_client, customer, menu):
    order = paid_order(customer_client, customer, menu)
    with mock.patch.object(order_events, 'notify', side_effect=RuntimeError('boom')):
        order_events.status_changed(order.pk, OrderStatus.PAYMENT_REVIEW, OrderStatus.PAID)  # ไม่ raise


# --------------------------------------------------------------------------- ส่ง push (FCM จำลอง)
class FakeMessaging:
    class UnregisteredError(Exception):
        pass

    class SenderIdMismatchError(Exception):
        pass

    def __init__(self):
        self.sent = []

    def MulticastMessage(self, **kw):
        return kw

    def WebpushConfig(self, **kw):
        return kw

    def WebpushNotification(self, **kw):
        return kw

    def WebpushFCMOptions(self, **kw):
        return kw

    def send_each_for_multicast(self, message):
        self.sent.append(message)
        responses = [
            SimpleNamespace(success=False, exception=self.UnregisteredError()) if t == 'dead' else SimpleNamespace(success=True, exception=None)
            for t in message['tokens']
        ]
        return SimpleNamespace(responses=responses, success_count=sum(r.success for r in responses))


@pytest.mark.django_db
def test_send_push_delivers_marks_sent_and_disables_dead_tokens(customer):
    DeviceToken.objects.create(user=customer, token='good')
    DeviceToken.objects.create(user=customer, token='dead')
    n = Notification.objects.create(user=customer, kind='order.paid', title='ชำระแล้ว', body='b', url='/orders/')
    fake = FakeMessaging()
    with mock.patch.object(notify_service, '_messaging', return_value=fake):
        assert notify_service.send_push([n.pk]) == 1
        assert notify_service.send_push([n.pk]) == 0  # ส่งแล้ว ไม่ส่งซ้ำ
    n.refresh_from_db()
    assert n.sent_at is not None and len(fake.sent) == 1
    assert fake.sent[0]['webpush']['fcm_options']['link'].endswith('/orders/')
    assert not DeviceToken.objects.get(token='dead').is_active


@pytest.mark.django_db
def test_send_push_without_credentials_keeps_notification(customer, settings):
    settings.FIREBASE_CREDENTIALS_PATH = ''
    DeviceToken.objects.create(user=customer, token='t')
    n = Notification.objects.create(user=customer, kind='x', title='t', body='b')
    assert notify_service.send_push([n.pk]) == 0
    n.refresh_from_db()
    assert n.sent_at is None


# --------------------------------------------------------------------------- หน้าเว็บ / อุปกรณ์
@pytest.mark.django_db
def test_device_register_and_token_moves_between_accounts(customer_client, customer):
    url = reverse('notifications:device_register')
    assert customer_client.post(url, json.dumps({'token': 'abc'}), content_type='application/json').json()['ok']
    other = User.objects.create_user(email='o@x.test', password='x' * 12, full_name='O')
    c = Client()
    c.force_login(other)
    c.post(url, json.dumps({'token': 'abc'}), content_type='application/json')
    assert DeviceToken.objects.get(token='abc').user == other  # เครื่องเดียวเปลี่ยนบัญชี push ไม่ไปผิดคน
    assert customer_client.post(url, json.dumps({'token': ''}), content_type='application/json').status_code == 400
    assert Client().post(url, json.dumps({'token': 'x'}), content_type='application/json').status_code == 302


@pytest.mark.django_db
def test_list_open_and_read_all(customer_client, customer):
    n = Notification.objects.create(user=customer, kind='order.paid', title='ชำระแล้ว', body='ออเดอร์ A1', url='/orders/')
    evil = Notification.objects.create(user=customer, kind='x', title='t', body='b', url='https://evil.example/')
    body = customer_client.get(reverse('notifications:list')).content.decode()
    assert 'ชำระแล้ว' in body and 'แจ้งเตือน 2 รายการที่ยังไม่อ่าน' in body
    assert customer_client.get(reverse('notifications:open', args=[n.pk]))['Location'] == '/orders/'
    assert customer_client.get(reverse('notifications:open', args=[evil.pk]))['Location'] == '/'
    customer_client.post(reverse('notifications:read_all'))
    assert not Notification.objects.filter(user=customer, read_at__isnull=True).exists()


@pytest.mark.django_db
def test_cannot_open_someone_elses_notification(customer_client, customer):
    other = User.objects.create_user(email='o2@x.test', password='x' * 12, full_name='O')
    n = Notification.objects.create(user=other, kind='x', title='secret', body='b', url='/x/')
    customer_client.get(reverse('notifications:open', args=[n.pk]))
    n.refresh_from_db()
    assert n.read_at is None
    assert 'secret' not in customer_client.get(reverse('notifications:list')).content.decode()


@pytest.mark.django_db
def test_list_uses_role_layout(owner_client):
    rider = make_rider()
    assert 'tm-brand-tag">ไรเดอร์' in rider.get(reverse('notifications:list')).content.decode()
    assert 'Console' in owner_client.get(reverse('notifications:list')).content.decode()


@pytest.mark.django_db
def test_push_button_and_script_only_when_configured(customer_client, settings):
    settings.FIREBASE_WEB_CONFIG, settings.FIREBASE_VAPID_KEY = {k: '' for k in FULL_WEB_CONFIG}, ''
    body = customer_client.get(reverse('accounts:account')).content.decode()
    assert 'data-push-enable' not in body and 'push.js' not in body
    settings.FIREBASE_WEB_CONFIG, settings.FIREBASE_VAPID_KEY = FULL_WEB_CONFIG, 'vapid'
    body = customer_client.get(reverse('accounts:account')).content.decode()
    assert 'data-push-enable' in body and 'push.js' in body and 'id="push-config"' in body


@pytest.mark.django_db
def test_service_worker_served_from_root(client, settings):
    settings.FIREBASE_WEB_CONFIG, settings.FIREBASE_VAPID_KEY = FULL_WEB_CONFIG, 'vapid'
    response = client.get('/firebase-messaging-sw.js')
    assert response['Content-Type'].startswith('application/javascript')
    assert response['Service-Worker-Allowed'] == '/'
    body = response.content.decode()
    assert "projectId: 'p'" in body and 'notificationclick' in body


def test_ago_th_filter():
    from datetime import timedelta

    from django.utils import timezone

    from apps.core.templatetags.tmpp_tags import ago_th
    now = timezone.now()
    assert ago_th(now) == 'เมื่อสักครู่'
    assert ago_th(now - timedelta(minutes=5)) == '5 นาทีที่แล้ว'
    assert ago_th(now - timedelta(hours=2)) == '2 ชม.ที่แล้ว'
    assert ago_th(now - timedelta(days=3)) == '3 วันที่แล้ว'
