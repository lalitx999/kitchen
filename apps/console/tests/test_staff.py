import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.console.models import AuditLog
from apps.delivery.models import RiderProfile
from apps.delivery.services import rider_service

PASSWORD = 'Kp9!long-test-pass'


@pytest.fixture
def owner(db):
    return User.objects.create_user(email='owner@example.test', password=PASSWORD, full_name='Owner', role=Role.OWNER)


@pytest.fixture
def owner_client(client, owner):
    client.force_login(owner)
    return client


def _create_payload(**overrides):
    data = {
        'role': Role.RIDER, 'full_name': 'น้องไรเดอร์', 'email': 'Brother@Example.test',
        'phone': '0811111111', 'vehicle_plate': '1กข 1234', 'password': PASSWORD,
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_owner_creates_rider_with_profile_and_audit(owner_client, owner):
    response = owner_client.post(reverse('console:staff'), _create_payload())
    assert response.status_code == 302
    rider = User.objects.get(email='brother@example.test')
    assert rider.role == Role.RIDER and rider.check_password(PASSWORD)
    assert RiderProfile.objects.get(user=rider).vehicle_plate == '1กข 1234'
    log = AuditLog.objects.get(action='staff.create')
    assert log.actor == owner and log.target_id == str(rider.pk)
    assert PASSWORD not in str(log.changes)


@pytest.mark.django_db
def test_new_rider_can_login_and_lands_on_rider_home(owner_client):
    client = Client()
    owner_client.post(reverse('console:staff'), _create_payload())
    response = client.post(reverse('accounts:login'), {'email': 'brother@example.test', 'password': PASSWORD})
    assert response['Location'] == reverse('delivery:rider_home')


@pytest.mark.django_db
def test_kitchen_account_ignores_vehicle_plate(owner_client):
    owner_client.post(reverse('console:staff'), _create_payload(role=Role.KITCHEN, email='k@example.test'))
    kitchen = User.objects.get(email='k@example.test')
    assert kitchen.role == Role.KITCHEN
    assert not RiderProfile.objects.filter(user=kitchen).exists()


@pytest.mark.django_db
def test_owner_cannot_create_owner_or_customer_via_form(owner_client):
    owner_client.post(reverse('console:staff'), _create_payload(role=Role.OWNER, email='o2@example.test'))
    assert not User.objects.filter(email='o2@example.test').exists()


@pytest.mark.django_db
def test_deactivating_rider_logs_them_out_and_sets_offline(owner_client):
    client = Client()
    rider = User.objects.create_user(email='r@example.test', password=PASSWORD, full_name='R', role=Role.RIDER)
    profile = rider_service.create_rider_profile(rider)
    rider_service.set_online(profile, online=True)
    client.force_login(rider)
    assert client.get(reverse('delivery:rider_home')).status_code == 200

    response = owner_client.post(reverse('console:staff_toggle_active', args=[rider.pk]), {'active': '0'})
    assert response.status_code == 200 and 'ปิดแล้ว' in response.content.decode()
    rider.refresh_from_db()
    profile.refresh_from_db()
    assert not rider.is_active and not profile.is_online
    # session เดิมของไรเดอร์ใช้ไม่ได้แล้ว
    assert client.get(reverse('delivery:rider_home')).status_code == 302
    assert AuditLog.objects.filter(action='staff.deactivate', target_id=str(rider.pk)).exists()


@pytest.mark.django_db
def test_owner_cannot_toggle_customer_through_staff_endpoint(owner_client):
    customer = User.objects.create_user(email='c@example.test', password=PASSWORD, full_name='C')
    response = owner_client.post(reverse('console:staff_toggle_active', args=[customer.pk]), {'active': '0'})
    assert response.status_code == 404
    customer.refresh_from_db()
    assert customer.is_active


@pytest.mark.django_db
def test_password_reset_invalidates_old_session(owner_client):
    client = Client()
    rider = User.objects.create_user(email='r@example.test', password=PASSWORD, full_name='R', role=Role.RIDER)
    client.force_login(rider)
    owner_client.post(reverse('console:staff_password', args=[rider.pk]), {'new_password': 'Another!pass-2026'})
    rider.refresh_from_db()
    assert rider.check_password('Another!pass-2026')
    assert client.get(reverse('delivery:rider_home')).status_code == 302
    assert AuditLog.objects.filter(action='staff.password_reset').exists()


@pytest.mark.django_db
def test_staff_list_query_count_does_not_grow_with_rows(owner_client, django_assert_max_num_queries):
    for i in range(6):
        user = User.objects.create_user(email=f'r{i}@example.test', password=PASSWORD, full_name=f'R{i}', role=Role.RIDER)
        rider_service.create_rider_profile(user, vehicle_plate=f'P{i}')
    # session + user + staff list (+ savepoints) — ต้องไม่เพิ่มตามจำนวนไรเดอร์
    with django_assert_max_num_queries(6):
        response = owner_client.get(reverse('console:staff'))
    assert response.status_code == 200
    assert 'P5' in response.content.decode()
