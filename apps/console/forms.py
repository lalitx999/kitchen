from decimal import Decimal

from django import forms
from django.contrib.auth import password_validation

from apps.accounts.forms import ThaiPhoneField
from apps.accounts.models import Role, normalize_email_address
from apps.accounts.selectors import user_selector


def _validate_new_password(form, field):
    value = form.cleaned_data.get(field)
    if value:
        try:
            password_validation.validate_password(value)
        except forms.ValidationError as exc:
            form.add_error(field, exc)


class StaffCreateForm(forms.Form):
    role = forms.ChoiceField(
        label='ตำแหน่ง', choices=[(Role.RIDER, 'ไรเดอร์'), (Role.KITCHEN, 'ครัว')], initial=Role.RIDER,
    )
    full_name = forms.CharField(label='ชื่อ', max_length=150)
    email = forms.EmailField(label='อีเมล (ใช้ล็อกอิน)')
    phone = ThaiPhoneField()
    vehicle_plate = forms.CharField(label='ทะเบียนรถ (ไรเดอร์)', max_length=20, required=False)
    branch = forms.ChoiceField(label='สาขา (ครัว)', required=False, choices=())
    password = forms.CharField(
        label='รหัสผ่านเริ่มต้น', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text='อย่างน้อย 8 ตัว ส่งให้พนักงานแล้วให้เปลี่ยนภายหลัง',
    )

    def __init__(self, *args, branches=(), **kwargs):
        super().__init__(*args, **kwargs)
        # สาขามาจาก selector ของ catalog (console ไม่แตะ model ของ app อื่นตรงๆ)
        self.fields['branch'].choices = [(str(b.pk), b.name) for b in branches]
        if branches:
            self.fields['branch'].initial = str(branches[0].pk)

    def clean_email(self):
        email = normalize_email_address(self.cleaned_data['email'])
        if user_selector.email_exists(email):
            raise forms.ValidationError('อีเมลนี้มีบัญชีแล้ว')
        return email

    def clean(self):
        cleaned = super().clean()
        _validate_new_password(self, 'password')
        if cleaned.get('role') != Role.RIDER:
            cleaned['vehicle_plate'] = ''
        if cleaned.get('role') != Role.KITCHEN:
            cleaned['branch'] = ''  # ไรเดอร์ใช้ร่วมกันทุกสาขา
        return cleaned


class StaffPasswordForm(forms.Form):
    new_password = forms.CharField(
        label='รหัสผ่านใหม่', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    def clean(self):
        cleaned = super().clean()
        _validate_new_password(self, 'new_password')
        return cleaned


class BranchCreateForm(forms.Form):
    name = forms.CharField(label='ชื่อสาขา', max_length=120, widget=forms.TextInput(attrs={'placeholder': 'เช่น TMPP สาขา 2 นาเกลือ'}))


class CouponForm(forms.Form):
    """คูปอง: ฟอร์มธรรมดา (console ไม่ใช้ ModelForm ของ app อื่น) · กติกาตรวจซ้ำใน orders.coupon_service"""
    KIND_CHOICES = [('AMOUNT', 'ลดเป็นบาท'), ('PERCENT', 'ลดเป็น %'), ('FREE_DELIVERY', 'ส่งฟรี')]

    code = forms.CharField(label='รหัสคูปอง', max_length=30, help_text='ลูกค้าพิมพ์รหัสนี้ เช่น LUNCH30 (A-Z, 0-9)')
    name = forms.CharField(label='ชื่อที่ลูกค้าเห็น', max_length=120, widget=forms.TextInput(attrs={'placeholder': 'เช่น ซื้อครบ 200 ลด 30'}))
    kind = forms.ChoiceField(label='ประเภท', choices=KIND_CHOICES, initial='AMOUNT')
    value = forms.DecimalField(label='มูลค่า', min_value=Decimal('0'), max_digits=8, decimal_places=2, required=False,
                               help_text='บาท หรือ % ตามประเภท (ส่งฟรีไม่ต้องใส่)')
    max_discount = forms.DecimalField(label='ลดสูงสุด (บาท)', min_value=Decimal('0'), max_digits=8, decimal_places=2,
                                      required=False, help_text='เฉพาะแบบ % (ว่าง = ไม่จำกัด)')
    min_subtotal = forms.DecimalField(label='ยอดอาหารขั้นต่ำ (บาท)', min_value=Decimal('0'), max_digits=10,
                                      decimal_places=2, required=False, initial=0)
    starts_at = forms.DateTimeField(label='เริ่มใช้', required=False,
                                    widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'))
    ends_at = forms.DateTimeField(label='หมดอายุ', required=False,
                                  widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'))
    usage_limit = forms.IntegerField(label='ใช้ได้ทั้งหมด (ครั้ง)', min_value=1, required=False, help_text='ว่าง = ไม่จำกัด')
    per_customer_limit = forms.IntegerField(label='ต่อลูกค้า 1 คน (ครั้ง)', min_value=0, max_value=1000, initial=1,
                                            help_text='0 = ไม่จำกัด')
    branch = forms.ChoiceField(label='ใช้ได้ที่สาขา', required=False, choices=())
    show_in_checkout = forms.BooleanField(label='แสดงให้ลูกค้าแตะเลือกในหน้าชำระเงิน', required=False, initial=True)
    is_active = forms.BooleanField(label='เปิดใช้งาน', required=False, initial=True)

    def __init__(self, *args, branches=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['branch'].choices = [('', 'ทุกสาขา')] + [(str(b.pk), b.name) for b in branches]

    def clean(self):
        cleaned = super().clean()
        cleaned['value'] = cleaned.get('value') or Decimal('0')
        cleaned['min_subtotal'] = cleaned.get('min_subtotal') or Decimal('0')
        if cleaned.get('per_customer_limit') is None:
            cleaned['per_customer_limit'] = 1
        return cleaned
