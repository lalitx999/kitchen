from django import forms
from django.contrib.auth import password_validation

from apps.core.validators import normalize_thai_phone, validate_thai_phone

from .models import normalize_email_address
from .selectors import user_selector


class ThaiPhoneField(forms.CharField):
    def __init__(self, **kwargs):
        kwargs.setdefault('max_length', 20)
        kwargs.setdefault('label', 'เบอร์โทร')
        super().__init__(**kwargs)
        self.widget.attrs.update({'inputmode': 'tel', 'autocomplete': 'tel', 'placeholder': '0812345678'})

    def clean(self, value):
        value = normalize_thai_phone(super().clean(value))
        if value or self.required:
            validate_thai_phone(value)
        return value


class LoginForm(forms.Form):
    email = forms.EmailField(label='อีเมล', widget=forms.EmailInput(attrs={'autocomplete': 'email', 'autofocus': True}))
    password = forms.CharField(label='รหัสผ่าน', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))


class RegisterForm(forms.Form):
    full_name = forms.CharField(label='ชื่อ-นามสกุล', max_length=150, widget=forms.TextInput(attrs={'autocomplete': 'name'}))
    email = forms.EmailField(label='อีเมล', widget=forms.EmailInput(attrs={'autocomplete': 'email'}))
    phone = ThaiPhoneField(help_text='ไรเดอร์ใช้โทรหาตอนไปส่ง')
    password1 = forms.CharField(label='รหัสผ่าน', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    password2 = forms.CharField(label='ยืนยันรหัสผ่าน', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))

    def clean_email(self):
        email = normalize_email_address(self.cleaned_data['email'])
        if user_selector.email_exists(email):
            raise forms.ValidationError('อีเมลนี้มีบัญชีแล้ว ลองเข้าสู่ระบบ')
        return email

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get('password1'), cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'รหัสผ่านทั้งสองช่องไม่ตรงกัน')
        if p1:
            try:
                password_validation.validate_password(p1)
            except forms.ValidationError as exc:
                self.add_error('password1', exc)
        return cleaned


class ProfileForm(forms.Form):
    full_name = forms.CharField(label='ชื่อ-นามสกุล', max_length=150)
    phone = ThaiPhoneField()
