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
