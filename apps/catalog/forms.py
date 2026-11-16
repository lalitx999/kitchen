import re
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from apps.core.validators import normalize_thai_phone, validate_thai_phone

MAX_IMAGE_BYTES = 3 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}
_COORDS = re.compile(r'^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$')


def parse_coordinates(value: str) -> tuple[Decimal, Decimal] | None:
    """รับ "13.7563, 100.5018" (คัดลอกจาก Google Maps คลิกขวาที่หมุด) คืน (lat, lng)"""
    if not value or not value.strip():
        return None
    match = _COORDS.match(value)
    if not match:
        raise ValidationError('รูปแบบพิกัดต้องเป็น "ละติจูด, ลองจิจูด" เช่น 13.7563, 100.5018')
    lat, lng = Decimal(match.group(1)), Decimal(match.group(2))
    if not (-90 <= lat <= 90 and -180 <= lng <= 180) or (lat == 0 and lng == 0):
        raise ValidationError('พิกัดไม่ถูกต้อง')
    return lat, lng


class BranchForm(forms.Form):
    name = forms.CharField(label='ชื่อร้าน', max_length=120)
    phone = forms.CharField(label='เบอร์ร้าน', max_length=20, required=False)
    address = forms.CharField(label='ที่อยู่ร้าน', widget=forms.Textarea(attrs={'rows': 2}), required=False)
    coordinates = forms.CharField(
        label='พิกัดร้าน', required=False,
        help_text='เปิด Google Maps คลิกขวาที่ร้าน แล้วกดตัวเลขพิกัดเพื่อคัดลอกมาวาง หรือกดปุ่มใช้ตำแหน่งเครื่องนี้ตอนอยู่ที่ร้าน',
    )
    opens_at = forms.TimeField(label='เวลาเปิด', required=False, widget=forms.TimeInput(attrs={'type': 'time'}))
    closes_at = forms.TimeField(label='เวลาปิด', required=False, widget=forms.TimeInput(attrs={'type': 'time'}))

    def clean_phone(self):
        phone = normalize_thai_phone(self.cleaned_data['phone'])
        if phone:
            validate_thai_phone(phone)
        return phone

    def clean(self):
        cleaned = super().clean()
        coords = parse_coordinates(cleaned.get('coordinates', ''))
        cleaned['latitude'], cleaned['longitude'] = coords if coords else (None, None)
        if bool(cleaned.get('opens_at')) != bool(cleaned.get('closes_at')):
            self.add_error('closes_at', 'ใส่ทั้งเวลาเปิดและเวลาปิด หรือเว้นว่างทั้งคู่')
        return cleaned


class MenuItemForm(forms.Form):
    name = forms.CharField(label='ชื่อเมนู', max_length=120)
    description = forms.CharField(label='รายละเอียด', max_length=255, required=False)
    price = forms.DecimalField(label='ราคา (บาท)', min_value=Decimal('0'), max_digits=8, decimal_places=2)
    category = forms.ModelChoiceField(label='หมวด', queryset=None, required=False, empty_label='ไม่มีหมวด')
    sort_order = forms.IntegerField(label='ลำดับ', min_value=0, max_value=999, initial=0, required=False,
                                    help_text='เลขน้อยแสดงก่อน')
    is_available = forms.BooleanField(label='มีขาย', required=False, initial=True)
    image = forms.ImageField(label='รูป', required=False, help_text='JPG / PNG / WEBP ไม่เกิน 3 MB')
    remove_image = forms.BooleanField(label='ลบรูปเดิม', required=False)

    def __init__(self, *args, categories, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = categories

    def clean_sort_order(self):
        return self.cleaned_data.get('sort_order') or 0

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if not image:
            return image
        if image.size > MAX_IMAGE_BYTES:
            raise ValidationError('รูปใหญ่เกิน 3 MB')
        # ImageField ตรวจด้วย Pillow แล้วว่าเป็นรูปจริง เช็คชนิดไฟล์เพิ่ม กันไฟล์แปลกๆ เช่น SVG/GIF
        fmt = getattr(getattr(image, 'image', None), 'format', None)
        if fmt not in ALLOWED_IMAGE_FORMATS:
            raise ValidationError('รองรับเฉพาะ JPG, PNG, WEBP')
        return image


class CategoryForm(forms.Form):
    name = forms.CharField(label='ชื่อหมวด', max_length=80)
    sort_order = forms.IntegerField(label='ลำดับ', min_value=0, max_value=999, initial=0, required=False)

    def clean_sort_order(self):
        return self.cleaned_data.get('sort_order') or 0


class MenuOptionForm(forms.Form):
    name = forms.CharField(label='ตัวเลือก', max_length=80)
    extra_price = forms.DecimalField(label='ราคาเพิ่ม', min_value=Decimal('0'), max_digits=8, decimal_places=2, initial=0)
