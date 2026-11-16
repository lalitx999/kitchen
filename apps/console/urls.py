from django.urls import path

from . import menu_views, order_views, people_views, shop_views, slip_views, views

app_name = 'console'

urlpatterns = [
    path('', views.overview, name='overview'),
    # พนักงาน
    path('staff/', views.staff_list, name='staff'),
    path('staff/<uuid:user_id>/active/', views.staff_toggle_active, name='staff_toggle_active'),
    path('staff/<uuid:user_id>/password/', views.staff_password, name='staff_password'),
    # ร้าน
    path('shop/', shop_views.shop_settings, name='shop'),
    path('shop/open/', shop_views.shop_toggle_open, name='shop_toggle_open'),
    # เมนู
    path('menu/', menu_views.menu_list, name='menu'),
    path('menu/items/new/', menu_views.item_create, name='menu_item_create'),
    path('menu/items/<uuid:item_id>/', menu_views.item_edit, name='menu_item_edit'),
    path('menu/items/<uuid:item_id>/toggle/', menu_views.item_toggle, name='menu_item_toggle'),
    path('menu/items/<uuid:item_id>/delete/', menu_views.item_delete, name='menu_item_delete'),
    path('menu/items/<uuid:item_id>/options/', menu_views.option_add, name='menu_option_add'),
    path('menu/items/<uuid:item_id>/options/<uuid:option_id>/delete/', menu_views.option_delete, name='menu_option_delete'),
    path('menu/categories/', menu_views.category_create, name='category_create'),
    path('menu/categories/<uuid:category_id>/', menu_views.category_update, name='category_update'),
    path('menu/categories/<uuid:category_id>/delete/', menu_views.category_delete, name='category_delete'),
    # สลิป
    path('slips/', slip_views.slip_queue, name='slips'),
    path('slips/<uuid:slip_id>/approve/', slip_views.slip_approve, name='slip_approve'),
    path('slips/<uuid:slip_id>/reject/', slip_views.slip_reject, name='slip_reject'),
    # ออเดอร์
    path('orders/', order_views.order_list, name='orders'),
    path('orders/export.csv', order_views.order_export, name='order_export'),
    path('orders/<uuid:order_id>/', order_views.order_detail, name='order_detail'),
    path('orders/<uuid:order_id>/cancel/', order_views.order_cancel, name='order_cancel'),
    # ค่าส่งไรเดอร์
    path('riders/pay/', people_views.rider_pay_list, name='rider_pay'),
    path('riders/<uuid:rider_id>/pay/', people_views.rider_pay_detail, name='rider_pay_detail'),
    path('riders/<uuid:rider_id>/pay/record/', people_views.rider_pay_record, name='rider_pay_record'),
    # ลูกค้า
    path('customers/', people_views.customer_list, name='customers'),
    path('customers/<uuid:user_id>/', people_views.customer_detail, name='customer_detail'),
    path('customers/<uuid:user_id>/active/', people_views.customer_toggle_active, name='customer_toggle_active'),
    # บันทึกการแก้ไข
    path('audit/', people_views.audit_list, name='audit'),
]
