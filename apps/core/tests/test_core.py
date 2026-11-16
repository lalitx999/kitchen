import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from apps.core.decorators import role_required


@role_required('OWNER')
def owner_only_view(request):
    return HttpResponse('ok')


class FakeUser:
    is_authenticated = True
    is_active = True

    def __init__(self, role):
        self.role = role


@pytest.fixture
def rf():
    return RequestFactory()


def test_role_required_redirects_anonymous_to_login(rf):
    request = rf.get('/console/')
    request.user = AnonymousUser()
    response = owner_only_view(request)
    assert response.status_code == 302
    assert '/auth/login/?next=/console/' in response['Location']


def test_role_required_forbids_wrong_role(rf):
    request = rf.get('/console/')
    request.user = FakeUser('CUSTOMER')
    with pytest.raises(PermissionDenied):
        owner_only_view(request)


def test_role_required_forbids_inactive_user(rf):
    request = rf.get('/console/')
    user = FakeUser('OWNER')
    user.is_active = False
    request.user = user
    with pytest.raises(PermissionDenied):
        owner_only_view(request)


def test_role_required_allows_matching_role(rf):
    request = rf.get('/console/')
    request.user = FakeUser('OWNER')
    assert owner_only_view(request).status_code == 200


def test_role_required_needs_at_least_one_role():
    with pytest.raises(ValueError):
        role_required()


@pytest.mark.django_db
def test_home_renders_with_brand(client):
    response = client.get(reverse('core:home'))
    assert response.status_code == 200
    assert b'TMPP' in response.content


@pytest.mark.django_db
def test_healthz_reports_database_and_cache(client):
    response = client.get(reverse('core:healthz'))
    body = response.json()
    assert body['database'] is True
    assert response.status_code in (200, 503)  # cache ขึ้นกับว่า Redis รันอยู่ไหม


@pytest.mark.django_db
def test_styleguide_hidden_when_not_debug(client, settings):
    settings.DEBUG = False
    assert client.get(reverse('core:styleguide')).status_code == 404
