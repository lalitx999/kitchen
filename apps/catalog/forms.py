from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from apps.core.validators import normalize_thai_phone, validate_thai_phone

MAX_IMAGE_BYTES = 3 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}


def validate_upload_image(image):
    """รูปที่อัปโหลด: ไม่เกิน 3 MB และเป็น JPG/PNG/WEBP จริง (ImageField ตรวจด้วย Pillow แล้วว่าเป็นรูป)"""
    if not image:
        return image
    if image.size > MAX_IMAGE_BYTES:
        raise ValidationError('รูปใหญ่เกิน 3 MB')
    fmt = getattr(getattr(image, 'image', None), 'format', None)
    if fmt not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError('รองรับเฉพาะ JPG, PNG, WEBP')
    return image


def _money(label, help_text=''):
    return forms.DecimalField(label=label, min_value=Decimal('0'), max_value=Decimal('9999'), max_digits=7,
                              decimal_places=2, help_text=help_text)


class BranchForm(forms.Form):
    name = forms.CharField(label='ชื่อร้าน', max_length=120)
    phone = forms.CharField(label='เบอร์ร้าน', max_length=20, required=False)
    address = forms.CharField(label='ที่อยู่ร้าน', widget=forms.Textarea(attrs={'rows': 2}), required=False)
    maps_link = forms.CharField(
        label='ลิงก์ Google Maps ของร้าน', required=False, max_length=600,
        help_text='เปิด Google Maps กดค้างที่ร้านจนมีหมุดแดง กด "แชร์" แล้วคัดลอกลิงก์มาวาง (วางตัวเลขพิกัดก็ได้)',
    )
    opens_at = forms.TimeField(label='เวลาเปิด', required=False, widget=forms.TimeInput(attrs={'type': 'time'}))
    closes_at = forms.TimeField(label='เวลาปิด', required=False, widget=forms.TimeInput(attrs={'type': 'time'}))
    storefront_image = forms.ImageField(label='ภาพหน้าร้าน', required=False, help_text='JPG / PNG / WEBP ไม่เกิน 3 MB')
    remove_storefront_image = forms.BooleanField(label='ลบภาพหน้าร้าน', required=False)
    cover_image = forms.ImageField(label='ภาพปกร้าน', required=False, help_text='แนวนอน เช่น 1600 x 600 · ไม่เกิน 3 MB')
    remove_cover_image = forms.BooleanField(label='ลบภาพปก', required=False)

    delivery_base_km = forms.DecimalField(label='ระยะเหมา (กม.)', min_value=Decimal('0'), max_value=Decimal('50'),
                                          max_digits=5, decimal_places=2)
    delivery_base_fare = _money('ลูกค้าจ่าย (ช่วงเหมา)')
    rider_base_fare = _money('ไรเดอร์ได้ (ช่วงเหมา)')
    delivery_per_km_fare = _money('ลูกค้าจ่าย / กม. ถัดไป')
    rider_per_km_fare = _money('ไรเดอร์ได้ / กม. ถัดไป')
    max_delivery_km = forms.DecimalField(label='ส่งไกลสุด (กม.)', min_value=Decimal('1'), max_value=Decimal('100'),
                                         max_digits=5, decimal_places=2)

    def clean_phone(self):
        phone = normalize_thai_phone(self.cleaned_data['phone'])
        if phone:
            validate_thai_phone(phone)
        return phone

    def clean_maps_link(self):
        from .services.maps_link_service import InvalidMapsLink, parse_maps_input
        try:
            self.cleaned_maps = parse_maps_input(self.cleaned_data.get('maps_link', ''))
        except InvalidMapsLink as exc:
            raise ValidationError(str(exc)) from exc
        return self.cleaned_data.get('maps_link', '')

    def clean_storefront_image(self):
        return validate_upload_image(self.cleaned_data.get('storefront_image'))

    def clean_cover_image(self):
        return validate_upload_image(self.cleaned_data.get('cover_image'))

    def clean(self):
        cleaned = super().clean()
        maps = getattr(self, 'cleaned_maps', None)
        cleaned['maps_url'], cleaned['latitude'], cleaned['longitude'] = maps if maps else ('', None, None)
        if bool(cleaned.get('opens_at')) != bool(cleaned.get('closes_at')):
            self.add_error('closes_at', 'ใส่ทั้งเวลาเปิดและเวลาปิด หรือเว้นว่างทั้งคู่')
        # ไรเดอร์ได้มากกว่าที่ลูกค้าจ่ายไม่ได้ (ร้านจะขาดทุนค่าส่ง)
        for rider_key, fare_key in (('rider_base_fare', 'delivery_base_fare'), ('rider_per_km_fare', 'delivery_per_km_fare')):
            rider, fare = cleaned.get(rider_key), cleaned.get(fare_key)
            if rider is not None and fare is not None and rider > fare:
                self.add_error(rider_key, 'ไรเดอร์ได้มากกว่าที่ลูกค้าจ่ายไม่ได้')
        base_km, max_km = cleaned.get('delivery_base_km'), cleaned.get('max_delivery_km')
        if base_km is not None and max_km is not None and max_km < base_km:
            self.add_error('max_delivery_km', 'ต้องไม่น้อยกว่าระยะเหมา')
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
        return validate_upload_image(self.cleaned_data.get('image'))


class CategoryForm(forms.Form):
    name = forms.CharField(label='ชื่อหมวด', max_length=80)
    sort_order = forms.IntegerField(label='ลำดับ', min_value=0, max_value=999, initial=0, required=False)

    def clean_sort_order(self):
        return self.cleaned_data.get('sort_order') or 0


class MenuOptionForm(forms.Form):
    name = forms.CharField(label='ตัวเลือก', max_length=80)
    extra_price = forms.DecimalField(label='ราคาเพิ่ม', min_value=Decimal('0'), max_digits=8, decimal_places=2, initial=0)
