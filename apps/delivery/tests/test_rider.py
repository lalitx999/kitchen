import pytest
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.delivery.models import RiderProfile
from apps.delivery.services import rider_service


@pytest.fixture
def rider(db):
    user = User.objects.create_user(email='rider@example.test', password='x' * 12, full_name='Rider', role=Role.RIDER)
    rider_service.create_rider_profile(user, vehicle_plate='1กข 1234')
    return user


@pytest.mark.django_db
def test_rider_home_shows_status_and_plate(client, rider):
    client.force_login(rider)
    body = client.get(reverse('delivery:rider_home')).content.decode()
    assert 'ปิดรับงาน' in body
    # M13: ทะเบียนรถย้ายไปแท็บ "โปรไฟล์"
    assert '1กข 1234' in client.get(reverse('delivery:rider_profile')).content.decode()


@pytest.mark.django_db
def test_rider_toggles_online_via_htmx(client, rider):
    client.force_login(rider)
    response = client.post(reverse('delivery:rider_set_status'), {'online': '1'}, HTTP_HX_REQUEST='true')
    assert response.status_code == 200
    assert 'กำลังรับงาน' in response.content.decode()
    profile = RiderProfile.objects.get(user=rider)
    assert profile.is_online and profile.online_since is not None

    client.post(reverse('delivery:rider_set_status'), {'online': '0'})
    profile.refresh_from_db()
    assert not profile.is_online and profile.online_since is None


@pytest.mark.django_db
def test_rider_without_profile_gets_one_created(client):
    user = User.objects.create_user(email='r2@example.test', password='x' * 12, full_name='R2', role=Role.RIDER)
    client.force_login(user)
    assert client.get(reverse('delivery:rider_home')).status_code == 200
    assert RiderProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_customer_cannot_toggle_rider_status(client, rider):
    customer = User.objects.create_user(email='c@example.test', password='x' * 12, full_name='C')
    client.force_login(customer)
    assert client.post(reverse('delivery:rider_set_status'), {'online': '1'}).status_code == 403
    assert not RiderProfile.objects.get(user=rider).is_online
