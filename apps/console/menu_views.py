"""Console: จัดการเมนู หมวด และตัวเลือก (ทุกการแก้ไขบันทึก AuditLog)"""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_safe, require_http_methods, require_POST

from apps.accounts.models import Role
from apps.catalog.forms import CategoryForm, MenuItemForm, MenuOptionForm
from apps.catalog.selectors import menu_selector
from apps.catalog.services import branch_service, menu_service
from apps.core.decorators import role_required

from .services import audit_service

owner_required = role_required(Role.OWNER)


def _audit(request, action, obj, changes=None):
    audit_service.record(request, action=action, target_type=obj._meta.model_name, target_id=obj.pk,
                         target_label=str(obj), changes=changes)


@owner_required
@require_safe
def menu_list(request):
    branch = branch_service.get_console_branch(request.session)
    categories, uncategorized = menu_selector.console_menu(branch)
    return render(request, 'console/menu/list.html', {
        'console_active': 'menu', 'branch': branch, 'categories': categories,
        'uncategorized': uncategorized, 'category_form': CategoryForm(),
    })


@owner_required
@require_http_methods(['GET', 'POST'])
def item_create(request):
    branch = branch_service.get_console_branch(request.session)
    categories = menu_selector.category_choices(branch)
    initial = {'category': request.GET.get('category')} if request.GET.get('category') else {}
    form = MenuItemForm(request.POST or None, request.FILES or None, categories=categories, initial=initial)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        item = menu_service.create_item(
            branch, image=data.pop('image'), **{k: v for k, v in data.items() if k != 'remove_image'},
        )
        _audit(request, 'menu_item.create', item, {'price': [None, str(item.price)]})
        messages.success(request, f'เพิ่ม "{item.name}" แล้ว เพิ่มตัวเลือกเสริมได้ด้านล่าง')
        return redirect('console:menu_item_edit', item_id=item.pk)
    return render(request, 'console/menu/item_form.html', {'console_active': 'menu', 'form': form, 'item': None})


@owner_required
@require_http_methods(['GET', 'POST'])
def item_edit(request, item_id):
    branch = branch_service.get_console_branch(request.session)
    item = menu_selector.get_branch_item(branch, item_id)
    categories = menu_selector.category_choices(branch)
    if request.method == 'POST':
        form = MenuItemForm(request.POST, request.FILES, categories=categories)
        if form.is_valid():
            data = form.cleaned_data
            changes = menu_service.update_item(item, image=data.pop('image'), remove_image=data.pop('remove_image'), **data)
            if changes:
                _audit(request, 'menu_item.update', item, changes)
                messages.success(request, f'บันทึก "{item.name}" แล้ว')
            return redirect('console:menu_item_edit', item_id=item.pk)
    else:
        form = MenuItemForm(categories=categories, initial={
            'name': item.name, 'description': item.description, 'price': item.price, 'category': item.category_id,
            'sort_order': item.sort_order, 'is_available': item.is_available,
        })
    return render(request, 'console/menu/item_form.html', {
        'console_active': 'menu', 'form': form, 'item': item, 'option_form': MenuOptionForm(),
    })


@owner_required
@require_POST
def item_toggle(request, item_id):
    """HTMX: ปิด/เปิดขาย แล้วคืนแถวเมนูที่อัปเดต"""
    branch = branch_service.get_console_branch(request.session)
    item = menu_selector.get_branch_item(branch, item_id)
    available = request.POST.get('available') == '1'
    if menu_service.set_available(item, available=available):
        _audit(request, 'menu_item.available' if available else 'menu_item.sold_out', item,
               {'is_available': [not available, available]})
    return render(request, 'console/menu/_item_row.html', {'item': item})


@owner_required
@require_POST
def item_delete(request, item_id):
    branch = branch_service.get_console_branch(request.session)
    item = menu_selector.get_branch_item(branch, item_id)
    name = item.name
    _audit(request, 'menu_item.delete', item, {'name': [name, None]})
    menu_service.delete_item(item)
    messages.info(request, f'ลบ "{name}" แล้ว (ออเดอร์เก่ายังเห็นชื่อเมนูนี้ตามเดิม)')
    return redirect('console:menu')


@owner_required
@require_POST
def option_add(request, item_id):
    branch = branch_service.get_console_branch(request.session)
    item = menu_selector.get_branch_item(branch, item_id)
    form = MenuOptionForm(request.POST)
    if form.is_valid():
        option = menu_service.add_option(item, **form.cleaned_data)
        _audit(request, 'menu_option.create', item, {'option': [None, str(option)]})
    else:
        messages.error(request, 'ตัวเลือกไม่ถูกต้อง: ' + ' '.join(e for errs in form.errors.values() for e in errs))
    return redirect('console:menu_item_edit', item_id=item.pk)


@owner_required
@require_POST
def option_delete(request, item_id, option_id):
    branch = branch_service.get_console_branch(request.session)
    item = menu_selector.get_branch_item(branch, item_id)
    option = menu_service.delete_option(item, option_id)
    if option:
        _audit(request, 'menu_option.delete', item, {'option': [str(option), None]})
    return redirect('console:menu_item_edit', item_id=item.pk)


@owner_required
@require_POST
def category_create(request):
    branch = branch_service.get_console_branch(request.session)
    form = CategoryForm(request.POST)
    if form.is_valid():
        try:
            category = menu_service.create_category(branch, **form.cleaned_data)
        except menu_service.DuplicateCategory:
            messages.error(request, 'มีหมวดชื่อนี้แล้ว')
        else:
            _audit(request, 'category.create', category)
            messages.success(request, f'เพิ่มหมวด "{category.name}" แล้ว')
    return redirect('console:menu')


@owner_required
@require_POST
def category_update(request, category_id):
    branch = branch_service.get_console_branch(request.session)
    category = menu_selector.get_branch_category(branch, category_id)
    form = CategoryForm(request.POST)
    if form.is_valid():
        try:
            changes = menu_service.update_category(category, **form.cleaned_data)
        except menu_service.DuplicateCategory:
            messages.error(request, 'มีหมวดชื่อนี้แล้ว')
        else:
            if changes:
                _audit(request, 'category.update', category, changes)
    return redirect('console:menu')


@owner_required
@require_POST
def category_delete(request, category_id):
    branch = branch_service.get_console_branch(request.session)
    category = menu_selector.get_branch_category(branch, category_id)
    _audit(request, 'category.delete', category)
    moved = menu_service.delete_category(category)
    messages.info(request, f'ลบหมวดแล้ว เมนู {moved} รายการย้ายไป "ไม่มีหมวด"')
    return redirect('console:menu')
