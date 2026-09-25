import pytest
import jdatetime
from app import app, db
from models import User, Shop, Customer, ProductCatalog, InventoryItem, Invoice, InvoiceItem

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        yield client

def test_rozen_catalog_count_and_discount():
    """بررسی درج صحیح کاتالوگ ۱۳۵ قلم شیرآلات رزن با تخفیف ۱۵ درصدی کارخانه"""
    with app.app_context():
        rozen_items = ProductCatalog.query.filter(ProductCatalog.brand.in_(['رزن', 'Rozen'])).all()
        assert len(rozen_items) >= 135, f"Expected at least 135 Rozen items, found {len(rozen_items)}"

        # بررسی اعمال دقیق تخفیف ۱۵ درصدی برای قیمت خرید
        sample_item = ProductCatalog.query.filter(ProductCatalog.name.contains('مدل لاله')).first()
        assert sample_item is not None
        assert sample_item.sell_price > 0
        expected_buy = int(sample_item.sell_price * 0.85)
        assert sample_item.buy_price == expected_buy, f"Buy price {sample_item.buy_price} does not match 15% discount {expected_buy}"

        # بررسی وجود مدل‌های مختلف
        for model_name in ['لاله', 'موج', 'اردکی', 'قاصدک', 'اسپانیایی']:
            model_items = ProductCatalog.query.filter(
                ProductCatalog.brand.in_(['رزن', 'Rozen']),
                ProductCatalog.name.contains(model_name)
            ).all()
            assert len(model_items) > 0, f"No Rozen items found for model {model_name}"

def test_custom_item_invoice_submission_and_profit(client):
    """بررسی ثبت فاکتور با کالای خارج از کاتالوگ، ثبت بهای خرید دستی و محاسبه دقیق سود واقعی"""
    with app.app_context():
        # دریافت یا ساخت کاربر فروشنده
        seller = User.query.filter_by(username='seller_test_rozen').first()
        if not seller:
            seller = User(
                username='seller_test_rozen',
                full_name='فروشنده تست سفارشی',
                role='seller',
                shop_id=1,
                commission_rate=1.0,
                is_active=True
            )
            seller.set_password('123456')
            db.session.add(seller)
            db.session.commit()

        seller_id = seller.id

    # ورود فروشنده
    with client.session_transaction() as sess:
        sess['user_id'] = seller_id
        sess['role'] = 'seller'
        sess['shop_id'] = 1
        sess['full_name'] = 'فروشنده تست سفارشی'

    now_j = jdatetime.datetime.now()
    inv_num = f"INV-CUSTOM-TEST-{now_j.year}{now_j.month:02d}{now_j.day:02d}-9999"

    # ارسال فرم فاکتور با جنس متفرقه و خارج از کاتالوگ و بهای خرید اعلامی فروشنده
    # فروش: ۲ عدد هر کدام ۵,۰۰۰,۰۰۰ تومان (جمع: ۱۰,۰۰۰,۰۰۰ تومان)
    # خرید دستی: ۲ عدد هر کدام ۳,۲۰۰,۰۰۰ تومان (جمع: ۶,۴۰۰,۰۰۰ تومان)
    # سود واقعی باید دقیقا ۳,۶۰۰,۰۰۰ تومان باشد
    data = {
        'customer_name': 'خریدار کالای سفارشی مرمر',
        'customer_phone': '09121112233',
        'customer_address': 'تهران بازار',
        'invoice_type': 'sale',
        'status': 'final',
        'payment_method': 'pos',
        'paid_pos': '10,000,000',
        'paid_card': '0',
        'paid_cash': '0',
        'total_amount': '10,000,000',
        'remaining_balance': '0',
        'customer_rating': '5',
        'item_inventory_id[]': [''],
        'item_custom_name[]': ['روشویی سنگی لوکس دست‌ساز مرمر اعلا'],
        'item_category[]': ['سنگ روشویی'],
        'item_quantity[]': ['2'],
        'item_original_price[]': ['5,000,000'],
        'item_discount_percent[]': ['0'],
        'item_price[]': ['5,000,000'],
        'item_buy_price[]': ['3,200,000'],
    }

    res = client.post('/invoice/add', data=data, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        inv = Invoice.query.filter_by(customer_name='خریدار کالای سفارشی مرمر').order_by(Invoice.id.desc()).first()
        assert inv is not None, "Invoice was not saved in database"
        assert inv.has_custom_items is True, "Invoice should have has_custom_items=True"
        assert inv.total_amount == 10000000
        assert inv.actual_buy_cost == 6400000, f"Expected actual_buy_cost=6400000, got {inv.actual_buy_cost}"
        assert inv.real_profit == 3600000, f"Expected real_profit=3600000, got {inv.real_profit}"

        # بررسی ردیف کالا
        assert len(inv.items) == 1
        item = inv.items[0]
        assert item.is_custom is True, "Item should have is_custom=True"
        assert item.unit_buy_price == 3200000
        assert item.row_profit == 3600000

def test_custom_invoices_filters_in_admin_and_seller(client):
    """بررسی تفکیک و فیلتر فاکتورهای دارای اقلام سفارشی در داشبورد ادمین و فروشنده"""
    with app.app_context():
        admin = User.query.filter_by(role='admin').first()
        admin_id = admin.id

    # بررسی پنل ادمین با فیلتر custom
    with client.session_transaction() as sess:
        sess['user_id'] = admin_id
        sess['role'] = 'admin'
        sess['shop_id'] = 1
        sess['full_name'] = 'مدیر سیستم'

    res_admin = client.get('/admin_dashboard?status_filter=custom')
    assert res_admin.status_code == 200
    assert "اقلام خارج از لیست (سفارشی)".encode('utf-8') in res_admin.data or "سفارشی".encode('utf-8') in res_admin.data

    # بررسی پنل فروشنده
    seller = None
    with app.app_context():
        seller = User.query.filter_by(role='seller', is_active=True).first()
        seller_id = seller.id

    with client.session_transaction() as sess:
        sess['user_id'] = seller_id
        sess['role'] = 'seller'
        sess['shop_id'] = 1
        sess['full_name'] = seller.full_name

    res_seller = client.get('/seller_dashboard')
    assert res_seller.status_code == 200
    assert "اقلام سفارشی".encode('utf-8') in res_seller.data
