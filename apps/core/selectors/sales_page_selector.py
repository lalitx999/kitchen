"""
ข้อมูลเซลเพจ /about/ (หน้าแนะนำร้าน): ทุกอย่างมาจากข้อมูลจริงของร้าน ไม่มีตัวเลข/รีวิว/รูปปลอม
ส่วนไหนไม่มีข้อมูล template ซ่อนส่วนนั้นเอง
"""
from apps.catalog.models import Branch, MenuItem
from apps.catalog.selectors import menu_selector
from apps.orders.selectors import order_selector

FEATURED_LIMIT = 8      # เมนูแนะนำ
FLOAT_LIMIT = 6         # รูปเมนูที่ลอยรอบหัวข้อ


def sales_page(branch: Branch | None) -> dict:
    """
    เมนูแนะนำ = ขายดี 30 วันก่อน แล้วเติมด้วยเมนูอื่นที่มีขาย (เฉพาะสาขานี้) · 2 query
    รูปลอย = เมนูแนะนำที่มีรูป (ไม่มีรูปก็ไม่แสดงส่วนนั้น)
    """
    if branch is None:
        return {'branch': None, 'shop': menu_selector.shop_status(None), 'featured': [], 'float_items': []}
    popular_ids = order_selector.popular_item_ids(branch, limit=FEATURED_LIMIT)
    rank = {str(pk): n for n, pk in enumerate(popular_ids)}
    items = list(
        MenuItem.objects.filter(branch=branch, is_available=True)
        .only('id', 'name', 'description', 'price', 'image', 'sort_order')
    )
    items.sort(key=lambda i: (rank.get(str(i.pk), len(rank)), i.sort_order, i.name))
    featured = items[:FEATURED_LIMIT]
    for item in featured:
        item.is_popular = str(item.pk) in rank
    return {
        'branch': branch,
        'shop': menu_selector.shop_status(branch),
        'featured': featured,
        'float_items': [i for i in featured if i.image][:FLOAT_LIMIT],
    }


def share_image(branch: Branch | None, featured) -> str:
    """รูปตอนแชร์ลิงก์ (og:image): ภาพปกร้าน > ภาพหน้าร้าน > รูปเมนูแรก · ไม่มีเลย = '' (ใช้ไอคอนแอป)"""
    if branch is not None:
        for field in (branch.cover_image, branch.storefront_image):
            if field:
                return field.url
    return next((i.image.url for i in featured if i.image), '')
