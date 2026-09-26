import pytest
from app import app, db
from models import User, Shop, Customer, ProductCatalog, InventoryItem, Invoice, InvoiceItem
from helpers import get_persian_word_variants, normalize_persian_text, build_catalog_search_filter

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        yield client

def test_persian_search_variants_and_normalization():
    """تست اعتبارسنجی تغییرات نرمال‌سازی فارسی، کلمات هم‌ریشه و انواع الف/ی/ک"""
    # تست ریشه‌یابی و پسوندهای صفت‌ساز
    variants_italy = get_persian_word_variants("ایتالیایی")
    assert "ایتالیایی" in variants_italy
    assert "ایتالیا" in variants_italy
    assert "ایتالی" in variants_italy

    # تست یکسان‌سازی کلاهک الف
    variants_as = get_persian_word_variants("آس")
    assert "آس" in variants_as
    assert "اس" in variants_as

    # تست کاراکترهای عربی و ارقام فارسی
    raw_text = "شيرآلات ۱۲۳ كابينت"
    norm = normalize_persian_text(raw_text)
    assert "ی" in norm
    assert "ک" in norm
    assert "123" in norm

def test_catalog_search_filter_and_route(client):
    """بررسی فیلتر جستجوی کاتالوگ با واژه‌های فارسی و فالبک در صورت عدم تطابق با برند انتخاب شده"""
    with app.app_context():
        # ورود ادمین یا ایجاد آن
        admin = User.query.filter_by(username='admin_test_search').first()
        if not admin:
            admin = User(
                username='admin_test_search',
                full_name='مدیر تست سرچ',
                role='admin',
                shop_id=1,
                is_active=True
            )
            admin.set_password('123456')
            db.session.add(admin)
            db.session.commit()
        admin_id = admin.id

    with client.session_transaction() as sess:
        sess['user_id'] = admin_id
        sess['role'] = 'admin'
        sess['full_name'] = 'مدیر تست سرچ'

    # جستجوی کالای ایتالیایی حتی اگر برند دیگری فیلتر شده باشد
    resp = client.get('/admin/catalog?search=ایتالیایی&brand=آس+(ABS)')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert "کاتالوگ مرجع" in html

def test_inventory_view_and_search(client):
    """بررسی رندر صفحه انبارداری و جستجوی تب کاتالوگ در انبار بدون خطای نیم‌ارور ai_insights"""
    with app.app_context():
        admin = User.query.filter_by(role='admin').first()
        admin_id = admin.id

    with client.session_transaction() as sess:
        sess['user_id'] = admin_id
        sess['role'] = 'admin'
        sess['full_name'] = 'مدیر طهماسبی'
        sess['shop_id'] = 1
        sess['can_manage_inventory'] = True

    # فراخوانی صفحه انبار معمولی
    resp1 = client.get('/inventory')
    assert resp1.status_code == 200
    html1 = resp1.data.decode('utf-8')
    assert "لیست قیمت پایه محصولات مجموعه طهماسبی" in html1
    assert "catalogTabSearchInput" in html1

    # فراخوانی با پارامتر جستجو
    resp2 = client.get('/inventory?search=داتیس')
    assert resp2.status_code == 200
    html2 = resp2.data.decode('utf-8')
    assert "داتیس" in html2

def test_manual_total_amount_invoice_submission(client):
    """بررسی ثبت فاکتور زمانی که فروشنده مبلغ کل را دستی وارد کرده و ردیف کالا بدون قیمت پیش‌فرض است"""
    with app.app_context():
        seller = User.query.filter_by(username='seller_test_price').first()
        if not seller:
            seller = User(
                username='seller_test_price',
                full_name='فروشنده تست مبالغ',
                role='seller',
                shop_id=1,
                commission_rate=1.0,
                is_active=True
            )
            seller.set_password('123456')
            db.session.add(seller)
            db.session.commit()
        seller_id = seller.id

    with client.session_transaction() as sess:
        sess['user_id'] = seller_id
        sess['role'] = 'seller'
        sess['shop_id'] = 1
        sess['full_name'] = 'فروشنده تست مبالغ'

    # ارسال فاکتور با قیمت کل دستی (بدون قیمت در ردیف کالا)
    payload = {
        'customer_name': 'مشتری قیمت دستی',
        'customer_phone': '09120000099',
        'status': 'final',
        'invoice_type': 'sale',
        'total_amount': '3,500,000',
        'paid_pos': '1,500,000',
        'paid_card': '0',
        'paid_cash': '0',
        'remaining_balance': '2,000,000',
        'item_inventory_id[]': [''],
        'item_custom_name[]': ['کالای دستی سفارشی'],
        'item_category[]': ['شیرآلات'],
        'item_quantity[]': ['1'],
        'item_original_price[]': [''],
        'item_discount_percent[]': ['0'],
        'item_price[]': [''],
        'item_buy_price[]': ['']
    }

    resp = client.post('/invoice/add', data=payload, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        inv = Invoice.query.filter_by(customer_name='مشتری قیمت دستی').order_by(Invoice.id.desc()).first()
        assert inv is not None
        assert inv.total_amount == 3500000
        assert inv.subtotal_amount == 3500000
        assert inv.remaining_balance == 2000000
        assert len(inv.items) >= 1
        # اقلام نباید قیمت ۰ داشته باشند و مبلغ فاکتور باید روی ردیف اعمال شده باشد
        assert inv.items[0].total_price == 3500000
        assert inv.items[0].unit_sell_price == 3500000
        assert inv.items[0].unit_buy_price > 0

def test_edit_invoice_with_manual_price_override(client):
    """بررسی ویرایش فاکتور با تغییر مبلغ کل و اعمال تخفیف فاکتوری"""
    with app.app_context():
        seller = User.query.filter_by(username='seller_test_price').first()
        seller_id = seller.id

    with client.session_transaction() as sess:
        sess['user_id'] = seller_id
        sess['role'] = 'seller'
        sess['shop_id'] = 1
        sess['full_name'] = 'فروشنده تست مبالغ'

    # ایجاد فاکتور اولیه
    initial_payload = {
        'customer_name': 'مشتری ویرایش فاکتور',
        'customer_phone': '09121111199',
        'status': 'final',
        'invoice_type': 'sale',
        'total_amount': '2,000,000',
        'paid_pos': '2,000,000',
        'paid_card': '0',
        'paid_cash': '0',
        'remaining_balance': '0',
        'item_inventory_id[]': [''],
        'item_custom_name[]': ['کالای اولیه'],
        'item_category[]': ['لوازم'],
        'item_quantity[]': ['1'],
        'item_original_price[]': ['2000000'],
        'item_discount_percent[]': ['0'],
        'item_price[]': ['2000000'],
        'item_buy_price[]': ['1500000']
    }
    client.post('/invoice/add', data=initial_payload, follow_redirects=True)

    with app.app_context():
        inv = Invoice.query.filter_by(customer_name='مشتری ویرایش فاکتور').order_by(Invoice.id.desc()).first()
        assert inv is not None
        inv_id = inv.id

    # حال ویرایش به مبلغ جدید و اضافه کردن ردیف با قیمت دستی
    edit_payload = {
        'customer_name': 'مشتری ویرایش فاکتور',
        'customer_phone': '09121111199',
        'status': 'final',
        'invoice_type': 'sale',
        'total_amount': '4,800,000',
        'paid_pos': '4,800,000',
        'paid_card': '0',
        'paid_cash': '0',
        'item_inventory_id[]': [''],
        'item_custom_name[]': ['کالای ویرایش شده'],
        'item_category[]': ['لوازم'],
        'item_quantity[]': ['2'],
        'item_original_price[]': ['2400000'],
        'item_discount_percent[]': ['0'],
        'item_price[]': ['2400000'],
        'item_buy_price[]': ['1800000']
    }
    edit_resp = client.post(f'/invoice/edit/{inv_id}', data=edit_payload, follow_redirects=True)
    assert edit_resp.status_code == 200

    with app.app_context():
        updated_inv = db.session.get(Invoice, inv_id)
        assert updated_inv.total_amount == 4800000
        assert updated_inv.subtotal_amount == 4800000
        assert updated_inv.is_settled == True
        assert len(updated_inv.items) == 1
        assert updated_inv.items[0].total_price == 4800000
