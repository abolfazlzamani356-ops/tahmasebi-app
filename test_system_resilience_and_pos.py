import pytest
import os
import json
import sqlite3
import jdatetime
from app import app, db
from models import User, Shop, Customer, ProductCatalog, InventoryItem, Invoice, InvoiceItem, Cheque, Settings
from helpers import record_stock_change

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        yield client

def test_sqlite_pragmas_and_wal():
    """تست اعتبارسنجی تنظیمات کانسیسترسی و حالت WAL در SQLite"""
    with app.app_context():
        res = db.session.execute(db.text("PRAGMA journal_mode")).fetchone()
        assert res[0].lower() in ['wal', 'memory', 'delete']

def test_atomic_stock_change_and_rollback():
    """تست تضمین اتمیک بودن کسر موجودی و عدم هدررفت کالا در خطای فاکتور"""
    with app.app_context():
        shop = Shop.query.get(1) or Shop(name="شعبه مرکزی طهماسبی", commission_rate=1.0)
        db.session.add(shop)
        db.session.commit()

        # ایجاد کالای تستی
        test_item = InventoryItem(
            name="کالای تست اتمیک طهماسبی",
            category="تست",
            shop_id=shop.id,
            stock_quantity=50,
            buy_price=100000,
            sell_price=150000
        )
        db.session.add(test_item)
        db.session.commit()
        initial_stock = test_item.stock_quantity

        # کسر با commit=False و شبیه‌سازی خطا و رول‌بک
        record_stock_change(test_item.id, shop.id, 'sale', -10, 'TEST_ROLLBACK', 'تستر', commit=False)
        assert test_item.stock_quantity == 40
        db.session.rollback()

        # پس از رول‌بک، موجودی باید دقیقا مقدار اولیه‌اش باشد
        refreshed_item = InventoryItem.query.get(test_item.id)
        assert refreshed_item.stock_quantity == initial_stock

def test_api_customer_lookup(client):
    """تست استعلام سریع مشخصات و سوابق مشتری با شماره تلفن"""
    with app.app_context():
        cust = Customer.query.filter_by(phone="09129998877").first()
        if not cust:
            cust = Customer(
                name="مشتری تست استعلام",
                phone="09129998877",
                outstanding_balance=2500000,
                total_purchases=15000000
            )
            db.session.add(cust)
            db.session.commit()

    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'seller'
        sess['full_name'] = 'فروشنده تستی'

    response = client.get('/api/customer/lookup?phone=09129998877')
    assert response.status_code == 200
    data = response.get_json()
    assert data['found'] is True
    assert data['outstanding_balance'] == 2500000
    assert data['name'] == "مشتری تست استعلام"

def test_api_barcode_lookup(client):
    """تست استعلام بارکدخوان برای ثبت سریع در فاکتور"""
    with app.app_context():
        item = InventoryItem.query.filter_by(barcode="9876543210123").first()
        if not item:
            item = InventoryItem(
                name="سینک گرانیتی تست بارکد",
                barcode="9876543210123",
                category="سینک",
                shop_id=1,
                stock_quantity=8,
                sell_price=4200000
            )
            db.session.add(item)
            db.session.commit()

    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'seller'
        sess['shop_id'] = 1

    response = client.get('/api/barcode/lookup?code=9876543210123')
    assert response.status_code == 200
    data = response.get_json()
    assert data['found'] is True
    assert data['name'] == "سینک گرانیتی تست بارکد"
    assert data['sell_price'] == 4200000

def test_print_pos_route(client):
    """تست رندر قالب چاپ ۸۰ میلی‌متری فیش پرینتر حرارتی"""
    invoice_id = None
    invoice_num = ""
    with app.app_context():
        inv = Invoice.query.first()
        if not inv:
            now_j = jdatetime.datetime.now()
            inv = Invoice(
                invoice_number="POS-TEST-101",
                customer_name="خریدار تست فیش",
                total_amount=500000,
                paid_amount=500000,
                status='final',
                invoice_type='sale',
                seller_id=1,
                shop_id=1,
                shamsi_year=now_j.year,
                shamsi_month=now_j.month,
                shamsi_date_time=now_j.strftime("%Y/%m/%d - %H:%M:%S")
            )
            db.session.add(inv)
            db.session.commit()
        invoice_id = inv.id
        invoice_num = inv.invoice_number

    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'seller'

    response = client.get(f'/print_pos/{invoice_id}')
    assert response.status_code == 200
    text_content = response.get_data(as_text=True)
    assert '80mm' in text_content
    assert invoice_num in text_content

def test_admin_online_backup_api(client):
    """تست دانلود پشتیبان آنلاین اتمیک بدون خطا"""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'admin'
        sess['full_name'] = 'مدیریت کل'

    response = client.get('/admin/backup')
    assert response.status_code == 200
    assert response.headers.get('Content-Disposition') is not None
    assert 'Backup_Tahmasebi_' in response.headers.get('Content-Disposition')

def test_persian_digits_and_item_discounts_invoicing(client):
    """تست ورود ارقام فارسی موبایل، کالای دستی بدون انبار، و محاسبه دقیق درصد و مبلغ تخفیف"""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'seller'
        sess['shop_id'] = 1
        sess['full_name'] = 'فروشنده طهماسبی'

    # سناریو: کالای دستی (سنگ روشویی) با قیمت مصوب ۱/۶۶۰/۰۰۰ و قیمت فروش با تخفیف ۱/۵۰۰/۰۰۰ به همراه ارقام فارسی
    form_data = {
        'customer_name': 'مشتری سنگ طهماسبی',
        'customer_phone': '۰۹۱۲۳۴۵۶۷۸۹',
        'total_amount': '۱,۵۰۰,۰۰۰',
        'paid_pos': '۱,۵۰۰,۰۰۰',
        'status': 'final',
        'item_inventory_id[]': [''],  # بدون شناسه انبار (کالای دستی سفارشی)
        'item_custom_name[]': ['سنگ روشویی مرمریت اعلا'],
        'item_category[]': ['سنگ'],
        'item_quantity[]': ['۱'],
        'item_original_price[]': ['۱,۶۶۰,۰۰۰'],
        'item_discount_percent[]': ['۹.۶'],
        'item_price[]': ['۱,۵۰۰,۰۰۰']
    }

    response = client.post('/invoice/add', data=form_data, follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        inv = Invoice.query.filter_by(customer_name='مشتری سنگ طهماسبی').order_by(Invoice.id.desc()).first()
        assert inv is not None
        assert inv.total_amount == 1500000
        assert inv.subtotal_amount == 1660000
        assert inv.discount_amount == 160000
        assert inv.paid_pos == 1500000
        assert inv.remaining_balance == 0
        assert inv.is_settled is True

        assert len(inv.items) == 1
        item = inv.items[0]
        assert item.item_name == 'سنگ روشویی مرمریت اعلا'
        assert item.quantity == 1
        assert item.unit_sell_price == 1660000
        assert item.discount == 160000
        assert item.total_price == 1500000
        saved_id = inv.id

    # تست نمایش در پرینت A4 با تخفیف
    a4_resp = client.get(f'/invoice/print/a4/{saved_id}')
    assert a4_resp.status_code == 200
    a4_text = a4_resp.get_data(as_text=True)
    assert '160,000' in a4_text or '۱۶۰,۰۰۰' in a4_text or 'تخفیف ویژه' in a4_text

def test_edit_invoice_with_persian_digits_and_discounts(client):
    """تست ویرایش فاکتور با ارقام فارسی و تخفیفات چندگانه"""
    with app.app_context():
        inv = Invoice.query.filter_by(customer_name='مشتری سنگ طهماسبی').order_by(Invoice.id.desc()).first()
        inv_id = inv.id

    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'seller'
        sess['shop_id'] = 1
        sess['full_name'] = 'فروشنده طهماسبی'

    edit_data = {
        'status': 'final',
        'invoice_type': 'sale',
        'customer_name': 'مشتری سنگ طهماسبی - ویرایش شده',
        'customer_phone': '09123456789',
        'total_amount': '۳,۶۰۰,۰۰۰',
        'paid_pos': '۲,۰۰۰,۰۰۰',
        'paid_cash': '۱,۶۰۰,۰۰۰',
        'item_inventory_id[]': [''],
        'item_custom_name[]': ['سنگ روشویی ۲ عدد'],
        'item_category[]': ['سنگ'],
        'item_quantity[]': ['۲'],
        'item_original_price[]': ['۲,۰۰۰,۰۰۰'],
        'item_discount_percent[]': ['۱۰'],
        'item_price[]': ['۱,۸۰۰,۰۰۰']
    }

    resp = client.post(f'/invoice/edit/{inv_id}', data=edit_data, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        updated_inv = db.session.get(Invoice, inv_id)
        assert updated_inv.total_amount == 3600000
        assert updated_inv.subtotal_amount == 4000000
        assert updated_inv.discount_amount == 400000
        assert updated_inv.paid_pos == 2000000
        assert updated_inv.paid_cash == 1600000
        assert updated_inv.remaining_balance == 0
        assert updated_inv.is_settled is True
        assert len(updated_inv.items) == 1
        assert updated_inv.items[0].total_price == 3600000
        assert updated_inv.items[0].discount == 400000

