from django import forms

from apps.accounts.forms import ThaiPhoneField


class CheckoutForm(forms.Form):
    recipient_name = forms.CharField(label='ชื่อผู้รับ', max_length=150)
    recipient_phone = ThaiPhoneField(label='เบอร์โทรผู้รับ')
    address_text = forms.CharField(
        label='ที่อยู่จัดส่ง', max_length=500,
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'บ้านเลขที่ ซอย ถนน หมู่บ้าน'}),
    )
    address_note = forms.CharField(label='จุดสังเกต', max_length=255, required=False,
                                   widget=forms.TextInput(attrs={'placeholder': 'เช่น ประตูสีเขียว ตรงข้ามเซเว่น'}))
    note = forms.CharField(label='หมายเหตุถึงร้าน', max_length=255, required=False,
                           widget=forms.TextInput(attrs={'placeholder': 'เช่น ไม่ใส่ผัก'}))
    # ได้จาก GPS ของเครื่อง หรือหมุดบนแผนที่ (ไม่มีพิกัดสำรอง ถ้าว่าง = สั่งไม่ได้)
    latitude = forms.FloatField(widget=forms.HiddenInput, required=False)
    longitude = forms.FloatField(widget=forms.HiddenInput, required=False)
    coupon_code = forms.CharField(label='โค้ดส่วนลด', max_length=40, required=False)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('latitude') is None or cleaned.get('longitude') is None:
            raise forms.ValidationError('กรุณาปักหมุดตำแหน่งจัดส่ง (กด "ใช้ตำแหน่งปัจจุบัน")')
        return cleaned


class CancelOrderForm(forms.Form):
    reason = forms.CharField(label='เหตุผลที่ยกเลิก', max_length=255)
