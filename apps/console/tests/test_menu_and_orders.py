from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.catalog.models import Branch, Category, MenuItem
from apps.console.models import AuditLog
from apps.orders.models import Order, OrderStatus
from apps.orders.tests.conftest import (  # noqa: F401 - fixtures
    branch, checkout_payload, customer, customer_client, menu, owner_client,
)


def _png(size=(10, 10)):
    buf = BytesIO()
    Image.new('RGB', size, 'red').save(buf, format='PNG')
    return SimpleUploadedFile('dish.png', buf.getvalue(), content_type='image/png')


@pytest.mark.django_db
def test_console_creates_main_branch_on_first_visit(owner_client):
    assert owner_client.get(reverse('console:overview')).status_code == 200
    branch = Branch.objects.get()
    assert not branch.is_open and branch.location is None


RATES = {'delivery_base_km': '3', 'delivery_base_fare': '30', 'rider_base_fare': '25',
         'delivery_per_km_fare': '6', 'rider_per_km_fare': '5', 'max_delivery_km': '15'}


def _shop_post(client, **fields):
    data = {'name': 'TMPP สาขาหลัก', **RATES, **fields}
    return client.post(reverse('console:shop'), data)


@pytest.mark.django_db
def test_shop_settings_saves_maps_link_and_audits(owner_client):
    owner_client.get(reverse('console:shop'))
    link = 'https://www.google.com/maps/place/TMPP/@13.7500,100.5000,17z/data=!3m1!4b1!4m6!3m5!1s0x0:0x0!8m2!3d13.756331!4d100.501765'
    response = _shop_post(owner_client, phone='081-111-1111', address='ถนนทดสอบ', maps_link=link,
                          opens_at='10:00', closes_at='21:00')
    assert response.status_code == 302
    branch = Branch.objects.get()
    # ใช้หมุดสถานที่ (!3d!4d) ไม่ใช่จุดกึ่งกลางจอ (@)
    assert round(branch.location.y, 6) == 13.756331 and round(branch.location.x, 6) == 100.501765
    assert branch.maps_url == link and branch.phone == '0811111111'
    assert AuditLog.objects.filter(action='branch.update').exists()


@pytest.mark.django_db
def test_shop_settings_accepts_raw_coordinates_and_builds_link(owner_client):
    owner_client.get(reverse('console:shop'))
    _shop_post(owner_client, maps_link='13.756331, 100.501765')
    branch = Branch.objects.get()
    assert branch.maps_url == 'https://www.google.com/maps?q=13.756331,100.501765'


@pytest.mark.django_db
@pytest.mark.parametrize('link', ['abc', '0, 0', '95, 100', 'https://evil.example.com/maps/@13.7,100.5,17z',
                                  'https://www.google.com/maps/place/TMPP'])
def test_shop_settings_rejects_bad_maps_input(owner_client, link):
    owner_client.get(reverse('console:shop'))
    response = _shop_post(owner_client, maps_link=link)
    assert response.status_code == 200
    assert Branch.objects.get().location is None


@pytest.mark.django_db
def test_shop_settings_rider_cannot_earn_more_than_customer_pays(owner_client):
    owner_client.get(reverse('console:shop'))
    response = _shop_post(owner_client, rider_base_fare='35')
    assert response.status_code == 200 and 'ไรเดอร์ได้มากกว่า' in response.content.decode()
    _shop_post(owner_client, delivery_base_fare='40', rider_base_fare='32')
    branch = Branch.objects.get()
    assert (branch.delivery_base_fare, branch.rider_base_fare) == (Decimal('40'), Decimal('32'))


@pytest.mark.django_db
def test_shop_settings_uploads_and_removes_images(owner_client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    owner_client.get(reverse('console:shop'))
    _shop_post(owner_client, cover_image=_png((80, 30)), storefront_image=_png())
    branch = Branch.objects.get()
    assert branch.cover_image and branch.storefront_image
    old = tmp_path / branch.cover_image.name
    assert old.exists()
    _shop_post(owner_client, remove_cover_image='on')
    branch.refresh_from_db()
    assert not branch.cover_image and branch.storefront_image
    home = owner_client.get(reverse('core:home')).content.decode()
    assert branch.storefront_image.url in home


@pytest.mark.django_db
def test_cannot_open_shop_without_location(owner_client):
    owner_client.get(reverse('console:shop'))
    owner_client.post(reverse('console:shop_toggle_open'), {'is_open': '1'})
    assert not Branch.objects.get().is_open


@pytest.mark.django_db
def test_owner_creates_menu_item_with_image_and_option(owner_client, branch, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    cat = Category.objects.create(branch=branch, name='ข้าว')
    response = owner_client.post(reverse('console:menu_item_create'), {
        'name': 'ผัดไทย', 'description': 'กุ้งสด', 'price': '80', 'category': cat.pk,
        'sort_order': 0, 'is_available': 'on', 'image': _png(),
    })
    item = MenuItem.objects.get(name='ผัดไทย')
    assert response['Location'] == reverse('console:menu_item_edit', args=[item.pk])
    assert item.image.name.startswith(f'menu/{branch.pk}/') and item.category == cat
    owner_client.post(reverse('console:menu_option_add', args=[item.pk]), {'name': 'ไข่', 'extra_price': '10'})
    assert item.options.get().extra_price == Decimal('10')
    assert set(AuditLog.objects.values_list('action', flat=True)) >= {'menu_item.create', 'menu_option.create'}


@pytest.mark.django_db
def test_menu_image_rejects_non_image_and_gif(owner_client, branch):
    bad = SimpleUploadedFile('x.png', b'not an image', content_type='image/png')
    response = owner_client.post(reverse('console:menu_item_create'), {
        'name': 'X', 'price': '10', 'sort_order': 0, 'image': bad,
    })
    assert response.status_code == 200 and not MenuItem.objects.exists()

    buf = BytesIO()
    Image.new('RGB', (5, 5)).save(buf, format='GIF')
    gif = SimpleUploadedFile('x.gif', buf.getvalue(), content_type='image/gif')
    response = owner_client.post(reverse('console:menu_item_create'), {'name': 'X', 'price': '10', 'sort_order': 0, 'image': gif})
    assert 'รองรับเฉพาะ' in response.content.decode()


@pytest.mark.django_db
def test_toggle_sold_out_hides_from_storefront(owner_client, client, menu):
    kaprao = menu['kaprao']
    response = owner_client.post(reverse('console:menu_item_toggle', args=[kaprao.pk]), {'available': '0'})
    assert 'มีขาย' in response.content.decode()
    assert 'กะเพราหมู' not in client.get(reverse('core:home')).content.decode()
    assert AuditLog.objects.filter(action='menu_item.sold_out').exists()


@pytest.mark.django_db
def test_delete_category_keeps_items(owner_client, menu):
    owner_client.post(reverse('console:category_delete', args=[menu['category'].pk]))
    menu['kaprao'].refresh_from_db()
    assert menu['kaprao'].category is None


@pytest.mark.django_db
def test_duplicate_category_name_shows_error(owner_client, menu):
    owner_client.post(reverse('console:category_create'), {'name': 'ข้าว'})
    assert Category.objects.filter(name='ข้าว').count() == 1


@pytest.mark.django_db
def test_deleting_menu_item_keeps_order_history(owner_client, customer_client, customer, menu):
    customer_client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})
    customer_client.post(reverse('orders:checkout'), checkout_payload())
    owner_client.post(reverse('console:menu_item_delete', args=[menu['water'].pk]))
    order = Order.objects.get(customer=customer)
    assert order.items.get().name == 'น้ำเปล่า'


@pytest.mark.django_db
def test_console_orders_list_filter_and_cancel(owner_client, customer_client, customer, menu):
    customer_client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})
    customer_client.post(reverse('orders:checkout'), checkout_payload())
    order = Order.objects.get(customer=customer)

    body = owner_client.get(reverse('console:orders'), {'q': order.recipient_phone}).content.decode()
    assert order.order_number in body
    assert owner_client.get(reverse('console:order_detail', args=[order.pk])).status_code == 200

    owner_client.post(reverse('console:order_cancel', args=[order.pk]), {'reason': ''})
    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING_PAYMENT  # ไม่ใส่เหตุผล ยกเลิกไม่ได้

    owner_client.post(reverse('console:order_cancel', args=[order.pk]), {'reason': 'ของหมด'})
    order.refresh_from_db()
    assert order.status == OrderStatus.CANCELLED and order.cancelled_reason == 'ของหมด'
    assert AuditLog.objects.filter(action='order.cancel', target_id=str(order.pk)).exists()


@pytest.mark.django_db
def test_customer_cannot_open_console_menu_or_orders(customer_client):
    for name in ('console:menu', 'console:orders', 'console:shop'):
        assert customer_client.get(reverse(name)).status_code == 403


@pytest.mark.django_db
def test_create_item_without_sort_order_and_form_shows_zero(owner_client, branch):
    # บั๊กที่เจอตอนทดสอบในเบราว์เซอร์: ช่องลำดับค่าเริ่มต้น 0 ไม่ถูกแสดง ทำให้ฟอร์มฟ้องว่าจำเป็น
    page = owner_client.get(reverse('console:menu_item_create')).content.decode()
    assert 'name="sort_order"' in page and 'value="0"' in page
    owner_client.post(reverse('console:menu_item_create'), {'name': 'ข้าวไข่เจียว', 'price': '40'})
    assert MenuItem.objects.get(name='ข้าวไข่เจียว').sort_order == 0
