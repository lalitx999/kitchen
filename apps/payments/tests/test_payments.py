import binascii
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accounts.models import Role, User
from apps.console.models import AuditLog
from apps.orders.models import Order, OrderStatus
from apps.orders.services import order_service
from apps.orders.tests.conftest import (  # noqa: F401 - fixtures
    branch, checkout_payload, customer, customer_client, menu, owner_client,
)
from apps.payments.models import SlipStatus, SlipTransaction
from apps.payments.services import easyslip_client, promptpay_service, slip_checks, slip_service

SHOP_SETTINGS = {
    'PROMPTPAY_ID': '0812345678',
    'SHOP_BANK_ACCOUNT': '2108583463',
    'SHOP_BANK_CODE': '004',
    'SHOP_ACCOUNT_NAMES': ['นาย ทดสอบ ร้านดี', 'MR. TOSOB RANDEE'],
    'EASYSLIP_API_KEY': 'test-key',
    'PAYMENT_VERIFICATION_MODE': 'AUTO',
}


@pytest.fixture(autouse=True)
def shop_settings(settings, tmp_path):
    for key, value in SHOP_SETTINGS.items():
        setattr(settings, key, value)
    settings.PRIVATE_MEDIA_ROOT = tmp_path / 'private'
    settings.CELERY_TASK_ALWAYS_EAGER = True
    return settings


def png(color='white', size=(40, 60)):
    buf = BytesIO()
    Image.new('RGB', size, color).save(buf, format='PNG')
    return SimpleUploadedFile('slip.png', buf.getvalue(), content_type='image/png')


def good_slip(total, trans_ref='TX-001', **overrides):
    data = dict(
        trans_ref=trans_ref, amount=str(total), sender_name='ลูกค้า',
        receiver_names=['นาย ทดสอบ ร้านดี'], receiver_accounts=['xxx-x-x8346-x'], receiver_bank_code='004',
        is_duplicate=False, raw={'success': True},
    )
    data.update(overrides)
    return easyslip_client.SlipData(**data)


@pytest.fixture
def order(customer_client, customer, menu):
    customer_client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})
    customer_client.post(reverse('orders:checkout'), checkout_payload())
    return Order.objects.get(customer=customer)


def upload(client, order, file=None, capture=None):
    url = reverse('payments:upload_slip', args=[order.pk])
    if capture is None:
        return client.post(url, {'slip': file or png()})
    with capture(execute=True):
        return client.post(url, {'slip': file or png()})


# --------------------------------------------------------------------------- PromptPay
def test_promptpay_payload_structure_and_crc():
    payload = promptpay_service.build_payload('081-234-5678', Decimal('176'))
    assert payload.startswith('000201010212')
    assert '0113006681234567' in payload          # เบอร์ 081... -> 006681...
    assert '5406176.00' in payload and '5802TH' in payload and '5303764' in payload
    body, crc = payload[:-4], payload[-4:]
    # เทียบกับ CRC-CCITT ของไลบรารีมาตรฐาน (คนละ implementation)
    assert crc == f'{binascii.crc_hqx(body.encode(), 0xFFFF):04X}'


@pytest.mark.parametrize('pp_id,tag', [('1234567890123', '0213'), ('123456789012345', '0315')])
def test_promptpay_national_id_and_ewallet(pp_id, tag):
    assert tag in promptpay_service.build_payload(pp_id, 10)


@pytest.mark.parametrize('pp_id', ['12345', '', 'abc'])
def test_promptpay_rejects_bad_id(pp_id):
    with pytest.raises(promptpay_service.PromptPayNotConfigured):
        promptpay_service.build_payload(pp_id, 10)


def test_promptpay_rejects_zero_amount():
    with pytest.raises(ValueError):
        promptpay_service.build_payload('0812345678', 0)


# --------------------------------------------------------------------------- slip checks
@pytest.mark.parametrize('masked,ok', [
    ('xxx-x-x8346-x', True), ('XXX-X-X8346-X', True), ('2108583463', True),
    ('xxx-x-x9346-x', False), ('xxx-x-xxx46-x', False),  # เห็นแค่ 2 หลัก ไม่พอ
])
def test_masked_account_matching(masked, ok):
    assert slip_checks.masked_account_matches(masked, '2108583463') is ok


@pytest.mark.parametrize('slip_name,ok', [
    ('นาย ทดสอบ ร้านดี', True), ('ทดสอบ ร้านดี', True), ('MR. TOSOB R', True),   # ตัดคำนำหน้า / ชื่อถูกตัดสั้น
    ('นาย ทดสอบ รานดี', False),  # สระต่าง ต้องไม่ผ่าน
    ('นาย สมชาย', False),
])
def test_receiver_name_matching(slip_name, ok):
    assert slip_checks.receiver_name_matches([slip_name], SHOP_SETTINGS['SHOP_ACCOUNT_NAMES']) is ok


def test_check_rejects_wrong_amount_wrong_account_and_duplicate():
    never_used = lambda ref: False  # noqa: E731
    with pytest.raises(easyslip_client.SlipProblem, match='ยอดในสลิป'):
        slip_checks.check_against_order(good_slip('99.00'), expected_total=Decimal('100.00'), trans_ref_used=never_used)
    with pytest.raises(easyslip_client.SlipProblem, match='ไม่ได้โอนเข้าบัญชี'):
        slip_checks.check_against_order(good_slip('100', receiver_accounts=['xxx-x-x1111-x']),
                                        expected_total=Decimal('100.00'), trans_ref_used=never_used)
    with pytest.raises(easyslip_client.SlipProblem, match='ถูกใช้ไปแล้ว'):
        slip_checks.check_against_order(good_slip('100'), expected_total=Decimal('100.00'), trans_ref_used=lambda r: True)
    assert slip_checks.check_against_order(good_slip('100'), expected_total=Decimal('100.00'), trans_ref_used=never_used) == Decimal('100.00')


def test_kshop_promptpay_id_matches_bank_qr_and_slip(settings):
    """รูปแบบเดียวกับร้าน: QR K SHOP (พร้อมเพย์ 15 หลัก) + บัญชีกสิกร + ชื่อร้านไม่มีคำนำหน้า"""
    settings.PROMPTPAY_ID = '004999000012345'
    settings.SHOP_ACCOUNT_NAMES = ['ทีเอ็มทดสอบร้าน']
    payload = promptpay_service.build_payload(settings.PROMPTPAY_ID, Decimal('1'))
    # ส่วนผู้รับต้องตรงกับ QR ที่แอปธนาคารออกให้ร้านทุกตัวอักษร
    assert '29390016A0000006770101110315004999000012345' in payload
    slip = good_slip('1', receiver_names=['ทีเอ็มทดสอบร้าน'])
    assert slip_checks.check_against_order(slip, expected_total=Decimal('1.00'), trans_ref_used=lambda r: False) == Decimal('1.00')
    # ผ่านได้ด้วยรหัสพร้อมเพย์อย่างเดียวก็ได้ ถ้าธนาคารไม่แสดงเลขบัญชี
    by_proxy = good_slip('1', receiver_names=['ทีเอ็มทดสอบร้าน'], receiver_accounts=['004999000012345'], receiver_bank_code='')
    assert slip_checks.check_against_order(by_proxy, expected_total=Decimal('1.00'), trans_ref_used=lambda r: False)


def test_easyslip_request_sends_no_match_flags():
    """ตรวจบัญชี/ยอด/สลิปซ้ำเองทั้งหมด -> ไม่ให้ EasySlip ปฏิเสธแทน (กัน retry แล้วโดนว่าสลิปซ้ำ)"""
    ok = mock.Mock(status_code=200, json=lambda: {'success': True, 'data': {'rawSlip': {'transRef': 'T1'}}})
    with mock.patch.object(easyslip_client.requests, 'post', return_value=ok) as post:
        easyslip_client.verify(b'img', filename='s.png', content_type='image/png', expected_amount=Decimal('1'), remark='TM-1')
    sent = post.call_args.kwargs['data']
    assert sent == {'remark': 'TM-1'}
    assert post.call_args.kwargs['headers'] == {'Authorization': 'Bearer test-key'}


@pytest.mark.parametrize('body,problem', [
    ({'success': False, 'error': {'code': 'SLIP_NOT_FOUND'}}, True),
    ({'status': 404, 'message': 'slip_not_found', 'data': {}}, True),   # รูปแบบในหน้า error codes
    ({'success': False, 'error': {'code': 'QUOTA_EXCEEDED'}}, False),  # โควต้าหมด = ส่งเจ้าของตรวจ
])
def test_easyslip_error_envelopes(body, problem):
    resp = mock.Mock(status_code=404 if problem else 403, json=lambda: body)
    expected = easyslip_client.SlipProblem if problem else easyslip_client.ProviderUnavailable
    with mock.patch.object(easyslip_client.requests, 'post', return_value=resp), pytest.raises(expected):
        easyslip_client.verify(b'img', filename='s.png', content_type='image/png', expected_amount=Decimal('1'))


def test_check_refuses_auto_approve_when_shop_not_configured(settings):
    settings.SHOP_BANK_ACCOUNT, settings.PROMPTPAY_ID = '', ''
    with pytest.raises(slip_checks.ShopNotConfigured):
        slip_checks.check_against_order(good_slip('100'), expected_total=Decimal('100.00'), trans_ref_used=lambda r: False)


# --------------------------------------------------------------------------- flow
@pytest.mark.django_db
def test_order_page_shows_qr_when_configured(customer_client, order, settings):
    body = customer_client.get(reverse('orders:detail', args=[order.pk])).content.decode()
    assert 'data:image/png;base64,' in body and 'xxxxxx5678' in body
    settings.PROMPTPAY_ID = ''
    body = customer_client.get(reverse('orders:detail', args=[order.pk])).content.decode()
    assert 'ยังไม่ได้ตั้งค่าพร้อมเพย์' in body


@pytest.mark.django_db
def test_good_slip_auto_approves_and_marks_paid(customer_client, order, django_capture_on_commit_callbacks):
    with mock.patch.object(easyslip_client, 'verify', return_value=good_slip(order.total)) as verify:
        upload(customer_client, order, capture=django_capture_on_commit_callbacks)
    assert verify.call_args.kwargs['expected_amount'] == order.total
    order.refresh_from_db()
    slip = order.slips.get()
    assert order.status == OrderStatus.PAID and order.paid_at
    assert slip.status == SlipStatus.APPROVED and slip.trans_ref == 'TX-001' and slip.review_source == 'AUTO'
    assert slip.image.storage.exists(slip.image.name)  # เก็บใน private storage


@pytest.mark.django_db
def test_bad_slip_rejects_and_customer_can_retry(customer_client, order, django_capture_on_commit_callbacks):
    with mock.patch.object(easyslip_client, 'verify', side_effect=easyslip_client.SlipProblem('อ่าน QR บนสลิปไม่ได้')):
        upload(customer_client, order, capture=django_capture_on_commit_callbacks)
    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING_PAYMENT
    body = customer_client.get(reverse('orders:detail', args=[order.pk])).content.decode()
    assert 'อ่าน QR บนสลิปไม่ได้' in body and 'แนบได้อีก 2 ครั้ง' in body


@pytest.mark.django_db
def test_provider_down_goes_to_owner_queue(customer_client, order, owner_client, django_capture_on_commit_callbacks):
    with mock.patch.object(easyslip_client, 'verify', side_effect=easyslip_client.ProviderUnavailable('timeout')):
        upload(customer_client, order, capture=django_capture_on_commit_callbacks)
    order.refresh_from_db()
    assert order.status == OrderStatus.PAYMENT_REVIEW
    assert order.slips.get().status == SlipStatus.NEEDS_REVIEW
    assert order.order_number in owner_client.get(reverse('console:slips')).content.decode()


@pytest.mark.django_db
def test_no_api_key_goes_to_owner_queue(customer_client, order, settings, django_capture_on_commit_callbacks):
    settings.EASYSLIP_API_KEY = ''
    upload(customer_client, order, capture=django_capture_on_commit_callbacks)
    assert order.slips.get().status == SlipStatus.NEEDS_REVIEW


@pytest.mark.django_db
def test_manual_mode_skips_easyslip(customer_client, order, settings, django_capture_on_commit_callbacks):
    settings.PAYMENT_VERIFICATION_MODE = 'MANUAL'
    with mock.patch.object(easyslip_client, 'verify') as verify:
        upload(customer_client, order, capture=django_capture_on_commit_callbacks)
    verify.assert_not_called()
    assert order.slips.get().status == SlipStatus.NEEDS_REVIEW


@pytest.mark.django_db
def test_same_trans_ref_cannot_pay_two_orders(customer_client, customer, menu, django_capture_on_commit_callbacks):
    orders = []
    for _ in range(2):
        customer_client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})
        customer_client.post(reverse('orders:checkout'), checkout_payload())
        orders.append(Order.objects.filter(customer=customer).order_by('-created_at').first())
    for i, o in enumerate(orders):
        with mock.patch.object(easyslip_client, 'verify', return_value=good_slip(o.total, trans_ref='SAME')):
            upload(customer_client, o, file=png(color='red' if i else 'blue'), capture=django_capture_on_commit_callbacks)
    for o in orders:
        o.refresh_from_db()
    assert [o.status for o in orders] == [OrderStatus.PAID, OrderStatus.PENDING_PAYMENT]
    assert 'ถูกใช้ไปแล้ว' in orders[1].slips.get().reason


@pytest.mark.django_db
def test_reusing_identical_image_file_is_blocked_before_easyslip(customer_client, customer, menu, django_capture_on_commit_callbacks):
    customer_client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})
    customer_client.post(reverse('orders:checkout'), checkout_payload())
    first = Order.objects.get(customer=customer)
    with mock.patch.object(easyslip_client, 'verify', return_value=good_slip(first.total, trans_ref='A')):
        upload(customer_client, first, capture=django_capture_on_commit_callbacks)
    customer_client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})
    customer_client.post(reverse('orders:checkout'), checkout_payload())
    second = Order.objects.filter(customer=customer).exclude(pk=first.pk).get()
    with mock.patch.object(easyslip_client, 'verify') as verify:
        response = upload(customer_client, second, capture=django_capture_on_commit_callbacks)  # รูปเดิมเป๊ะ
    verify.assert_not_called()
    assert not second.slips.exists()
    assert response.status_code == 302


@pytest.mark.django_db
def test_upload_rejects_non_image_and_respects_attempt_limit(customer_client, order, settings, django_capture_on_commit_callbacks):
    upload(customer_client, order, file=SimpleUploadedFile('x.png', b'not image', content_type='image/png'))
    assert not order.slips.exists()
    settings.SLIP_MAX_ATTEMPTS = 1
    with mock.patch.object(easyslip_client, 'verify', side_effect=easyslip_client.SlipProblem('ไม่ผ่าน')):
        upload(customer_client, order, capture=django_capture_on_commit_callbacks)
        upload(customer_client, order, file=png('green'), capture=django_capture_on_commit_callbacks)
    assert order.slips.count() == 1


@pytest.mark.django_db
def test_other_customer_cannot_upload_or_view_slip(customer_client, order):
    upload(customer_client, order)
    slip = order.slips.get()
    other = User.objects.create_user(email='z@example.test', password='x' * 12, full_name='Z', role=Role.CUSTOMER)
    client = Client()
    client.force_login(other)
    assert client.post(reverse('payments:upload_slip', args=[order.pk]), {'slip': png()}).status_code == 404
    assert client.get(reverse('payments:slip_image', args=[slip.pk])).status_code == 404
    assert Client().get(reverse('payments:slip_image', args=[slip.pk])).status_code == 302
    own = customer_client.get(reverse('payments:slip_image', args=[slip.pk]))
    assert own.status_code == 200
    assert 'private' in own['Cache-Control'] and 'no-store' in own['Cache-Control']


# --------------------------------------------------------------------------- owner review
@pytest.fixture
def queued_slip(customer_client, order, settings, django_capture_on_commit_callbacks):
    settings.EASYSLIP_API_KEY = ''
    upload(customer_client, order, capture=django_capture_on_commit_callbacks)
    return order.slips.get()


@pytest.mark.django_db
def test_owner_can_view_and_approve_slip(owner_client, queued_slip):
    assert owner_client.get(reverse('payments:slip_image', args=[queued_slip.pk])).status_code == 200
    owner_client.post(reverse('console:slip_approve', args=[queued_slip.pk]), {'trans_ref': 'REF-9'})
    queued_slip.refresh_from_db()
    assert queued_slip.status == SlipStatus.APPROVED and queued_slip.review_source == 'MANUAL'
    assert queued_slip.order.status == OrderStatus.PAID
    assert AuditLog.objects.filter(action='slip.approve').exists()
    # อนุมัติซ้ำไม่ได้
    owner_client.post(reverse('console:slip_approve', args=[queued_slip.pk]))
    assert queued_slip.order.status_logs.filter(to_status=OrderStatus.PAID).count() == 1


@pytest.mark.django_db
def test_owner_reject_requires_reason(owner_client, queued_slip):
    owner_client.post(reverse('console:slip_reject', args=[queued_slip.pk]), {'reason': ''})
    queued_slip.refresh_from_db()
    assert queued_slip.status == SlipStatus.NEEDS_REVIEW
    owner_client.post(reverse('console:slip_reject', args=[queued_slip.pk]), {'reason': 'ยอดไม่เข้า'})
    queued_slip.refresh_from_db()
    assert queued_slip.status == SlipStatus.REJECTED and queued_slip.reason == 'ยอดไม่เข้า'
    assert queued_slip.order.status == OrderStatus.PENDING_PAYMENT


@pytest.mark.django_db
def test_customer_cannot_use_console_slip_actions(customer_client, queued_slip):
    assert customer_client.post(reverse('console:slip_approve', args=[queued_slip.pk])).status_code == 403


@pytest.mark.django_db
def test_order_cancelled_during_review_flags_for_refund(order):
    slip = SlipTransaction.objects.create(order=order, attempt_no=1, image_sha256='x' * 64, image='slips/x.png')
    order_service.transition_order(order, OrderStatus.PAYMENT_REVIEW)
    order_service.transition_order(order, OrderStatus.CANCELLED, note='ของหมด')
    with mock.patch.object(easyslip_client, 'verify', return_value=good_slip(order.total)), \
         mock.patch('django.db.models.fields.files.FieldFile.open', mock.mock_open(read_data=b'img')):
        result = slip_service.verify_slip(slip.pk)
    assert result == SlipStatus.NEEDS_REVIEW
    slip.refresh_from_db()
    assert 'โอนคืน' in slip.reason


# --------------------------------------------------------------------------- expiry
@pytest.mark.django_db
def test_expire_cancels_old_unpaid_but_not_under_review(order, customer_client, customer, menu, settings):
    settings.PAYMENT_WINDOW_MINUTES = 20
    customer_client.post(reverse('orders:cart_add'), {'item_id': menu['water'].pk})
    customer_client.post(reverse('orders:checkout'), checkout_payload())
    reviewing = Order.objects.filter(customer=customer).exclude(pk=order.pk).get()
    order_service.transition_order(reviewing, OrderStatus.PAYMENT_REVIEW)
    old = timezone.now() - timedelta(minutes=30)
    Order.objects.filter(pk__in=[order.pk, reviewing.pk]).update(updated_at=old)

    assert slip_service.expire_unpaid_orders() == 1
    order.refresh_from_db()
    reviewing.refresh_from_db()
    assert order.status == OrderStatus.CANCELLED and 'ไม่ได้ชำระเงิน' in order.cancelled_reason
    assert reviewing.status == OrderStatus.PAYMENT_REVIEW


@pytest.mark.django_db
def test_recent_unpaid_order_is_not_expired(order):
    assert slip_service.expire_unpaid_orders() == 0


def test_private_storage_follows_settings_and_has_no_url(settings, tmp_path):
    from apps.payments.storage import private_storage
    settings.PRIVATE_MEDIA_ROOT = tmp_path / 'elsewhere'
    assert private_storage.location == str(tmp_path / 'elsewhere')
    with pytest.raises(ValueError):
        private_storage.url('slips/x.png')
