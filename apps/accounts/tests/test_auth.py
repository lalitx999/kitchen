from unittest import mock

import pytest
from django.core.cache import cache
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.accounts.services import auth_service

PASSWORD = 'Kp9!long-test-pass'


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def make_user(role=Role.CUSTOMER, email=None, **extra):
    email = email or f'{role.lower()}@example.test'
    return User.objects.create_user(email=email, password=PASSWORD, full_name=f'{role} Test', role=role, **extra)


# --------------------------------------------------------------------------- model
@pytest.mark.django_db
def test_email_is_normalized_and_case_insensitive_unique():
    user = make_user(email='  Somchai@Example.TEST ')
    assert user.email == 'somchai@example.test'
    assert User.objects.get_by_natural_key('SOMCHAI@example.test') == user


@pytest.mark.django_db
def test_google_only_account_has_unusable_password():
    user = User.objects.create_user(email='g@example.test', password=None, full_name='G')
    assert not user.has_usable_password()


# --------------------------------------------------------------------------- register
@pytest.mark.django_db
def test_register_creates_customer_and_logs_in(client):
    response = client.post(reverse('accounts:register'), {
        'full_name': 'สมชาย ใจดี', 'email': 'new@example.test', 'phone': '081-234-5678',
        'password1': PASSWORD, 'password2': PASSWORD,
    })
    assert response.status_code == 302
    assert response['Location'] == reverse('core:home')
    user = User.objects.get(email='new@example.test')
    assert user.role == Role.CUSTOMER
    assert user.phone == '0812345678'
    assert client.get(reverse('accounts:account')).status_code == 200


@pytest.mark.django_db
def test_register_rejects_duplicate_email_any_case(client):
    make_user(email='dup@example.test')
    response = client.post(reverse('accounts:register'), {
        'full_name': 'X', 'email': 'DUP@example.test', 'phone': '0812345678',
        'password1': PASSWORD, 'password2': PASSWORD,
    })
    assert response.status_code == 200
    assert 'อีเมลนี้มีบัญชีแล้ว' in response.content.decode()
    assert User.objects.filter(email__iexact='dup@example.test').count() == 1


@pytest.mark.django_db
def test_register_rejects_bad_phone_and_mismatched_password(client):
    response = client.post(reverse('accounts:register'), {
        'full_name': 'X', 'email': 'x@example.test', 'phone': '12345',
        'password1': PASSWORD, 'password2': PASSWORD + 'x',
    })
    body = response.content.decode()
    assert 'เบอร์โทรต้องเป็นตัวเลข 10 หลัก' in body
    assert 'รหัสผ่านทั้งสองช่องไม่ตรงกัน' in body
    assert not User.objects.filter(email='x@example.test').exists()


# --------------------------------------------------------------------------- login + redirect by role
@pytest.mark.django_db
@pytest.mark.parametrize('role,expected', [
    (Role.CUSTOMER, 'core:home'),
    (Role.RIDER, 'delivery:rider_home'),
    (Role.KITCHEN, 'orders:kitchen'),
    (Role.OWNER, 'console:overview'),
])
def test_login_redirects_each_role_to_its_home(client, role, expected):
    make_user(role=role)
    response = client.post(reverse('accounts:login'), {'email': f'{role.lower()}@example.test', 'password': PASSWORD})
    assert response.status_code == 302
    assert response['Location'] == reverse(expected)


@pytest.mark.django_db
def test_login_honours_safe_next_but_not_external(client):
    make_user()
    ok = client.post(reverse('accounts:login'), {'email': 'customer@example.test', 'password': PASSWORD, 'next': '/account/'})
    assert ok['Location'] == '/account/'
    client.logout()
    evil = client.post(reverse('accounts:login'), {'email': 'customer@example.test', 'password': PASSWORD, 'next': 'https://evil.example/'})
    assert evil['Location'] == reverse('core:home')


@pytest.mark.django_db
def test_wrong_password_shows_generic_error(client):
    make_user()
    response = client.post(reverse('accounts:login'), {'email': 'customer@example.test', 'password': 'wrong'})
    assert response.status_code == 200
    assert 'อีเมลหรือรหัสผ่านไม่ถูกต้อง' in response.content.decode()


@pytest.mark.django_db
def test_login_locks_after_repeated_failures(client, settings):
    settings.LOGIN_MAX_FAILURES = 3
    make_user()
    for _ in range(3):
        client.post(reverse('accounts:login'), {'email': 'customer@example.test', 'password': 'wrong'})
    # รหัสถูกก็ยังเข้าไม่ได้ระหว่างถูกล็อก
    response = client.post(reverse('accounts:login'), {'email': 'customer@example.test', 'password': PASSWORD})
    assert response.status_code == 200
    assert 'ลองใหม่ในอีก' in response.content.decode()


@pytest.mark.django_db
def test_inactive_user_cannot_login(client):
    make_user(is_active=False)
    response = client.post(reverse('accounts:login'), {'email': 'customer@example.test', 'password': PASSWORD})
    assert response.status_code == 200
    assert '_auth_user_id' not in client.session


@pytest.mark.django_db
def test_logout_requires_post(client):
    user = make_user()
    client.force_login(user)
    assert client.get(reverse('accounts:logout')).status_code == 405
    assert client.post(reverse('accounts:logout')).status_code == 302
    assert '_auth_user_id' not in client.session


# --------------------------------------------------------------------------- access matrix
@pytest.mark.django_db
@pytest.mark.parametrize('url_name,allowed', [
    ('accounts:account', {Role.CUSTOMER}),
    ('delivery:rider_home', {Role.RIDER}),
    ('orders:kitchen', {Role.KITCHEN, Role.OWNER}),
    ('console:overview', {Role.OWNER}),
    ('console:staff', {Role.OWNER}),
])
def test_each_page_only_opens_for_its_roles(client, url_name, allowed):
    url = reverse(url_name)
    assert client.get(url).status_code == 302  # ยังไม่ล็อกอิน -> หน้าล็อกอิน
    for role in Role.values:
        client.force_login(make_user(role=role, email=f'{role.lower()}-{url_name.replace(":", "-")}@example.test'))
        expected = 200 if role in allowed else 403
        assert client.get(url).status_code == expected, f'{role} -> {url_name}'
        client.logout()


# --------------------------------------------------------------------------- profile
@pytest.mark.django_db
def test_customer_updates_profile(client):
    user = make_user()
    client.force_login(user)
    response = client.post(reverse('accounts:account'), {'full_name': 'ชื่อใหม่', 'phone': '0899999999'})
    assert response.status_code == 302
    user.refresh_from_db()
    assert (user.full_name, user.phone) == ('ชื่อใหม่', '0899999999')


# --------------------------------------------------------------------------- google
IDENTITY = auth_service.GoogleIdentity(sub='google-123', email='g@example.test', name='Google User')


@pytest.mark.django_db
def test_google_login_creates_customer_then_reuses_it(client, settings):
    settings.GOOGLE_CLIENT_ID = 'test-client'
    with mock.patch.object(auth_service, 'verify_google_credential', return_value=IDENTITY):
        first = client.post(reverse('accounts:google'), {'credential': 'token'})
        client.logout()
        client.post(reverse('accounts:google'), {'credential': 'token'})
    assert first['Location'] == reverse('core:home')
    user = User.objects.get(google_sub='google-123')
    assert user.role == Role.CUSTOMER and not user.has_usable_password()
    assert User.objects.filter(email='g@example.test').count() == 1


@pytest.mark.django_db
def test_google_links_existing_customer_but_never_staff():
    customer = make_user(email='g@example.test')
    assert auth_service.login_or_register_with_google(IDENTITY) == customer
    customer.refresh_from_db()
    assert customer.google_sub == 'google-123'

    make_user(role=Role.RIDER, email='rider-g@example.test')
    rider_identity = auth_service.GoogleIdentity(sub='google-999', email='rider-g@example.test', name='R')
    with pytest.raises(auth_service.GoogleLoginError):
        auth_service.login_or_register_with_google(rider_identity)


def test_google_verify_refuses_without_client_id(settings):
    settings.GOOGLE_CLIENT_ID = ''
    with pytest.raises(auth_service.GoogleLoginError):
        auth_service.verify_google_credential('anything')
