from django.urls import path

from . import kitchen_views, views

app_name = 'orders'

urlpatterns = [
    path('menu/<uuid:item_id>/', views.item_sheet, name='item_sheet'),
    path('cart/', views.cart_page, name='cart'),
    path('cart/add/', views.cart_add, name='cart_add'),
    path('cart/update/', views.cart_update, name='cart_update'),
    path('checkout/', views.checkout, name='checkout'),
    path('checkout/quote/', views.checkout_quote, name='checkout_quote'),
    path('orders/', views.order_list, name='list'),
    path('orders/<uuid:order_id>/', views.order_detail, name='detail'),
    path('orders/<uuid:order_id>/status/', views.order_status, name='status'),
    path('orders/<uuid:order_id>/cancel/', views.order_cancel, name='cancel'),
    path('orders/<uuid:order_id>/tracking/', views.order_tracking, name='tracking'),
    # จอครัว
    path('kitchen/', kitchen_views.kitchen_home, name='kitchen'),
    path('kitchen/board/', kitchen_views.kitchen_board, name='kitchen_board'),
    path('kitchen/menu/', kitchen_views.kitchen_menu, name='kitchen_menu'),
    path('kitchen/history/', kitchen_views.kitchen_history, name='kitchen_history'),
    path('kitchen/orders/<uuid:order_id>/', kitchen_views.kitchen_action, name='kitchen_action'),
    path('kitchen/shop/', kitchen_views.kitchen_toggle_shop, name='kitchen_toggle_shop'),
    path('kitchen/menu/<uuid:item_id>/', kitchen_views.kitchen_toggle_item, name='kitchen_toggle_item'),
]
