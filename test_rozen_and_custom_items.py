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

def test_custom_item_without_buy_cost_default_25_margin(client):
    """بررسی ثبت فاکتور بدون ورود بهای خرید با اعمال سود پیش‌فرض ۲۵ درصدی"""
    with app.app_context():
        seller = User.query.filter_by(role='seller', is_active=True).first()
        seller_id = seller.id
        seller_name = seller.full_name

    with client.session_transaction() as sess:
        sess['user_id'] = seller_id
        sess['role'] = 'seller'
        sess['shop_id'] = 1
        sess['full_name'] = seller_name

    data = {
        'customer_name': 'خریدار شیر پیسوار بدون بهای خرید',
        'customer_phone': '09129998877',
        'customer_address': 'کرج عظیمیه',
        'invoice_type': 'sale',
        'status': 'final',
        'payment_method': 'pos',
        'paid_pos': '8,000,000',
        'paid_card': '0',
        'paid_cash': '0',
        'total_amount': '8,000,000',
        'remaining_balance': '0',
        'customer_rating': '5',
        'item_inventory_id[]': [''],
        'item_custom_name[]': ['شیر پیسوار فیلتردار برنجی خاص صادراتی'],
        'item_category[]': ['اتصالات شیرآلات'],
        'item_quantity[]': ['2'],
        'item_original_price[]': ['4,000,000'],
        'item_discount_percent[]': ['0'],
        'item_price[]': ['4,000,000'],
        'item_buy_price[]': [''],
    }

    res = client.post('/invoice/add', data=data, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        inv = Invoice.query.filter_by(customer_name='خریدار شیر پیسوار بدون بهای خرید').order_by(Invoice.id.desc()).first()
        assert inv is not None
        assert inv.has_custom_items is True
        assert inv.total_amount == 8000000
        # سود پیش‌فرض ۲۵ درصد: بهای خرید = 75% فروش (8,000,000 * 0.75 = 6,000,000)
        assert inv.actual_buy_cost == 6000000, f"Expected 6,000,000, got {inv.actual_buy_cost}"
        assert inv.real_profit == 2000000, f"Expected 2,000,000, got {inv.real_profit}"
        
        item = inv.items[0]
        assert item.is_custom is True
        assert item.unit_buy_price == 3000000  # 4,000,000 * 0.75
        assert item.row_profit == 2000000

def test_auto_learning_catalog_registration(client):
    """بررسی خودآموزی کاتالوگ: ثبت خودکار کالای خارج از لیست در ProductCatalog و پاسخگویی در جستجو"""
    unique_item_name = "روشویی تمام چوب ضدآب سیسیلی لوکس"
    with app.app_context():
        # اطمینان از عدم وجود کالا در کاتالوگ قبل از ثبت فاکتور
        ProductCatalog.query.filter_by(name=unique_item_name).delete()
        db.session.commit()
        
        seller = User.query.filter_by(role='seller', is_active=True).first()
        seller_id = seller.id
        seller_name = seller.full_name

    with client.session_transaction() as sess:
        sess['user_id'] = seller_id
        sess['role'] = 'seller'
        sess['shop_id'] = 1
        sess['full_name'] = seller_name

    data = {
        'customer_name': 'خریدار روشویی چوبی سیسیلی',
        'customer_phone': '09123334455',
        'invoice_type': 'sale',
        'status': 'final',
        'payment_method': 'pos',
        'paid_pos': '10,800,000',
        'total_amount': '10,800,000',
        'remaining_balance': '0',
        'item_inventory_id[]': [''],
        'item_custom_name[]': [unique_item_name],
        'item_category[]': ['روشویی چوبی'],
        'item_quantity[]': ['1'],
        'item_original_price[]': ['12,000,000'],
        'item_discount_percent[]': ['10'],
        'item_price[]': ['10,800,000'],
        'item_buy_price[]': ['8,000,000'],
    }

    res = client.post('/invoice/add', data=data, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        # بررسی درج در جدول کاتالوگ
        cat_item = ProductCatalog.query.filter_by(name=unique_item_name).first()
        assert cat_item is not None, "Custom item was not auto-registered in ProductCatalog"
        assert cat_item.category == 'روشویی چوبی'
        assert cat_item.sell_price == 12000000  # قیمت مصوب
        assert cat_item.buy_price == 8000000

    # بررسی بازیابی از طریق API جستجوی کاتالوگ
    res_search = client.get('/api/catalog/search?q=' + 'سیسیلی')
    assert res_search.status_code == 200
    search_data = res_search.get_json()
    assert any(item['name'] == unique_item_name for item in search_data), "Auto-learned item was not returned by /api/catalog/search"

def test_bidirectional_price_discount_submission(client):
    """بررسی رفتار دوسویه و منعطف محاسبات قیمت مصوب، تخفیف و قیمت نهایی در ثبت فاکتور"""
    with app.app_context():
        seller = User.query.filter_by(role='seller', is_active=True).first()
        seller_id = seller.id
        seller_name = seller.full_name

    with client.session_transaction() as sess:
        sess['user_id'] = seller_id
        sess['role'] = 'seller'
        sess['shop_id'] = 1
        sess['full_name'] = seller_name

    # سناریو ۱: ورود قیمت مصوب و قیمت نهایی (محاسبه اختلاف به عنوان تخفیف)
    # مصوب: ۲,۰۰۰,۰۰۰ | نهایی: ۱,۸۰۰,۰۰۰ | تعداد: ۲ -> تخفیف کل: ۴۰۰,۰۰۰ | جمع نهایی: ۳,۶۰۰,۰۰۰
    data1 = {
        'customer_name': 'مشتری تست دوسویه ۱',
        'customer_phone': '09121001001',
        'invoice_type': 'sale',
        'status': 'final',
        'payment_method': 'pos',
        'paid_pos': '3,600,000',
        'total_amount': '3,600,000',
        'remaining_balance': '0',
        'item_inventory_id[]': [''],
        'item_custom_name[]': ['کالای تست تخفیف اختلافی'],
        'item_category[]': ['عمومی'],
        'item_quantity[]': ['2'],
        'item_original_price[]': ['2,000,000'],
        'item_discount_percent[]': [''],
        'item_price[]': ['1,800,000'],
        'item_buy_price[]': ['1,500,000'],
    }
    res1 = client.post('/invoice/add', data=data1, follow_redirects=True)
    assert res1.status_code == 200

    with app.app_context():
        inv1 = Invoice.query.filter_by(customer_name='مشتری تست دوسویه ۱').order_by(Invoice.id.desc()).first()
        assert inv1 is not None
        assert inv1.subtotal_amount == 4000000  # 2 * 2,000,000
        assert inv1.discount_amount == 400000   # 2 * 200,000
        assert inv1.total_amount == 3600000     # 2 * 1,800,000
        assert inv1.items[0].unit_sell_price == 2000000
        assert inv1.items[0].discount == 400000
        assert inv1.items[0].total_price == 3600000

    # سناریو ۲: ورود تک‌قیمت در قیمت نهایی (هم‌ترازی خودکار با قیمت مصوب و تخفیف صفر)
    data2 = {
        'customer_name': 'مشتری تست تک قیمت',
        'customer_phone': '09121001002',
        'invoice_type': 'sale',
        'status': 'final',
        'payment_method': 'pos',
        'paid_pos': '1,500,000',
        'total_amount': '1,500,000',
        'remaining_balance': '0',
        'item_inventory_id[]': [''],
        'item_custom_name[]': ['کالای تک قیمت بدون مصوب'],
        'item_category[]': ['عمومی'],
        'item_quantity[]': ['1'],
        'item_original_price[]': [''],
        'item_discount_percent[]': [''],
        'item_price[]': ['1,500,000'],
        'item_buy_price[]': [''],
    }
    res2 = client.post('/invoice/add', data=data2, follow_redirects=True)
    assert res2.status_code == 200

    with app.app_context():
        inv2 = Invoice.query.filter_by(customer_name='مشتری تست تک قیمت').order_by(Invoice.id.desc()).first()
        assert inv2 is not None
        assert inv2.total_amount == 1500000
        assert inv2.subtotal_amount == 1500000
        assert inv2.discount_amount == 0
        assert inv2.items[0].unit_sell_price == 1500000
        assert inv2.items[0].discount == 0
        assert inv2.actual_buy_cost == int(1500000 * 0.75)
        assert inv2.real_profit == 1500000 - int(1500000 * 0.75)

    # سناریو ۳: ورود قیمت مصوب و درصد تخفیف بدون قیمت نهایی (محاسبه خودکار نهایی توسط سرور)
    data3 = {
        'customer_name': 'مشتری تست درصد تخفیف سروری',
        'customer_phone': '09121001003',
        'invoice_type': 'sale',
        'status': 'final',
        'payment_method': 'pos',
        'paid_pos': '1,800,000',
        'total_amount': '1,800,000',
        'remaining_balance': '0',
        'item_inventory_id[]': [''],
        'item_custom_name[]': ['کالای تخفیف درصدی سرور'],
        'item_category[]': ['عمومی'],
        'item_quantity[]': ['1'],
        'item_original_price[]': ['2,000,000'],
        'item_discount_percent[]': ['10'],
        'item_price[]': [''],
        'item_buy_price[]': ['1,400,000'],
    }
    res3 = client.post('/invoice/add', data=data3, follow_redirects=True)
    assert res3.status_code == 200

    with app.app_context():
        inv3 = Invoice.query.filter_by(customer_name='مشتری تست درصد تخفیف سروری').order_by(Invoice.id.desc()).first()
        assert inv3 is not None
        assert inv3.total_amount == 1800000
        assert inv3.subtotal_amount == 2000000
        assert inv3.discount_amount == 200000
        assert inv3.items[0].total_price == 1800000
        assert inv3.items[0].discount == 200000

def test_edit_invoice_custom_item_auto_learning(client):
    """بررسی ثبت خودکار در کاتالوگ و محاسبه سود ۲۵٪ هنگام ویرایش فاکتور"""
    edit_item_name = "هود مخفی سفارشی مشکی طلایی توربو"
    with app.app_context():
        ProductCatalog.query.filter_by(name=edit_item_name).delete()
        db.session.commit()
        
        seller = User.query.filter_by(role='seller', is_active=True).first()
        seller_id = seller.id
        seller_name = seller.full_name

        # پیدا کردن یک فاکتور برای ویرایش
        inv = Invoice.query.filter_by(seller_id=seller_id).first()
        assert inv is not None
        inv_id = inv.id

    with client.session_transaction() as sess:
        sess['user_id'] = seller_id
        sess['role'] = 'seller'
        sess['shop_id'] = 1
        sess['full_name'] = seller_name

    edit_data = {
        'customer_name': 'مشتری ویرایش فاکتور سفارشی',
        'customer_phone': '09124445566',
        'invoice_type': 'sale',
        'status': 'final',
        'payment_method': 'pos',
        'paid_pos': '6,000,000',
        'total_amount': '6,000,000',
        'remaining_balance': '0',
        'item_inventory_id[]': [''],
        'item_custom_name[]': [edit_item_name],
        'item_category[]': ['هود آشپزخانه'],
        'item_quantity[]': ['1'],
        'item_original_price[]': ['6,000,000'],
        'item_discount_percent[]': ['0'],
        'item_price[]': ['6,000,000'],
        'item_buy_price[]': [''],  # بدون بهای خرید
    }

    res = client.post(f'/invoice/edit/{inv_id}', data=edit_data, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        # بررسی ثبت در کاتالوگ
        cat_p = ProductCatalog.query.filter_by(name=edit_item_name).first()
        assert cat_p is not None, "Custom item from edit_invoice was not registered in ProductCatalog"
        assert cat_p.sell_price == 6000000
        assert cat_p.buy_price == 4500000  # 6,000,000 * 0.75

        # بررسی فاکتور ویرایش شده
        updated_inv = Invoice.query.get(inv_id)
        assert updated_inv.has_custom_items is True
        assert updated_inv.actual_buy_cost == 4500000
        assert updated_inv.real_profit == 1500000


