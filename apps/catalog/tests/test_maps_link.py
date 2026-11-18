from decimal import Decimal
from unittest import mock

import pytest
import requests

from apps.catalog.services import maps_link_service as svc


@pytest.mark.parametrize('url,lat,lng', [
    ('https://www.google.com/maps/place/X/@13.70,100.40,17z/data=!3m1!4b1!3d13.756331!4d100.501765', '13.756331', '100.501765'),
    ('https://www.google.com/maps?q=13.756331,100.501765', '13.756331', '100.501765'),
    ('https://maps.google.com/?q=13.756331%2C100.501765', '13.756331', '100.501765'),
    ('https://www.google.com/maps/search/13.756331,+100.501765?entry=tts', '13.756331', '100.501765'),
    ('https://www.google.co.th/maps/@13.756331,100.501765,18z', '13.756331', '100.501765'),
])
def test_coordinates_from_full_links(url, lat, lng):
    _url, got_lat, got_lng = svc.parse_maps_input(url)
    assert (got_lat, got_lng) == (Decimal(lat), Decimal(lng))


def _redirect(location):
    return mock.Mock(status_code=302, headers={'Location': location}, close=lambda: None)


def test_short_link_follows_google_redirects_only():
    final = 'https://www.google.com/maps/place/TMPP/data=!3d13.1!4d100.2?g_st=ic'
    with mock.patch.object(svc.requests, 'get', return_value=_redirect(final)) as get:
        url, lat, lng = svc.parse_maps_input('https://maps.app.goo.gl/AbCdEf123')
    assert url == 'https://maps.app.goo.gl/AbCdEf123' and (lat, lng) == (Decimal('13.1'), Decimal('100.2'))
    assert get.call_args.kwargs['allow_redirects'] is False and get.call_args.kwargs['timeout'] == svc.TIMEOUT_SECONDS


def test_short_link_redirecting_outside_google_is_refused():
    with mock.patch.object(svc.requests, 'get', return_value=_redirect('http://169.254.169.254/latest')):
        with pytest.raises(svc.InvalidMapsLink, match='ไม่ได้พาไปที่ Google Maps'):
            svc.parse_maps_input('https://maps.app.goo.gl/AbCdEf123')


def test_short_link_network_error_gives_readable_message():
    with mock.patch.object(svc.requests, 'get', side_effect=requests.Timeout()):
        with pytest.raises(svc.InvalidMapsLink, match='ลิงก์สั้น'):
            svc.parse_maps_input('https://maps.app.goo.gl/AbCdEf123')


@pytest.mark.parametrize('value', ['https://example.com/maps/@13.7,100.5', 'http://localhost:8000/x', 'ftp://google.com/maps'])
def test_non_google_links_are_refused_without_network(value):
    with mock.patch.object(svc.requests, 'get') as get, pytest.raises(svc.InvalidMapsLink):
        svc.parse_maps_input(value)
    get.assert_not_called()


def test_empty_means_no_location():
    assert svc.parse_maps_input('  ') is None
