import json
import pytest
from app import app, db
from models import User, Shop, Customer, Invoice, InvoiceItem, StockLog, InventoryItem

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        with app.app_context():
            yield client

def test_api_check_invoice_number_and_seller_identity(client):
    """تست استعلام آنی شماره فاکتور و تشخیص هویت فروشنده و شعبه ثبت‌کننده"""
    with app.app_context():
        # دریافت یا ایجاد کاربر تست
        seller1 = User.query.filter_by(username='seller1_test').first()
        if not seller1:
            seller1 = User(
                username='seller1_test',
                full_name='علی رضایی',
                role='seller',
                shop_id=1
            )
            seller1.set_password('123456')
            db.session.add(seller1)
            db.session.commit()

        seller_id = seller1.id
        seller_name = seller1.full_name

        # ایجاد فاکتور موجود با شماره مشخص
        test_inv_num = "TEST-INV-9988"
        old_inv = Invoice.query.filter_by(invoice_number=test_inv_num).first()
        if old_inv:
            InvoiceItem.query.filter_by(invoice_id=old_inv.id).delete()
            db.session.delete(old_inv)
            db.session.commit()

        inv = Invoice(
            invoice_number=test_inv_num,
            customer_name='آقای تست Collision',
            seller_id=seller_id,
            shop_id=1,
            total_amount=15000000,
            shamsi_year=1403,
            shamsi_month=7,
            shamsi_date_time='1403/07/28 10:30',
            status='final'
        )
        db.session.add(inv)
        db.session.commit()
        created_inv_id = inv.id

    with client.session_transaction() as sess:
        sess['user_id'] = seller_id
        sess['role'] = 'seller'
        sess['shop_id'] = 1
        sess['full_name'] = seller_name

    # ۱. استعلام فاکتور ناموجود
    res_not_found = client.get('/api/invoice/check_number?num=NON_EXISTENT_99999')
    assert res_not_found.status_code == 200
    data_nf = json.loads(res_not_found.data)
    assert data_nf['exists'] is False

    # ۲. استعلام فاکتور موجود -> باید هویت فروشنده و شعبه را برگرداند
    res_found = client.get(f'/api/invoice/check_number?num={test_inv_num}')
    assert res_found.status_code == 200
    data_f = json.loads(res_found.data)
    assert data_f['exists'] is True
    assert data_f['invoice_number'] == test_inv_num
    assert data_f['seller_name'] == 'علی رضایی'
    assert 'شعبه' in data_f['shop_name'] or data_f['shop_id'] == 1

    # ۳. استعلام با exclude_id برای صفحه ویرایش -> فاکتور خودش را نباید تکراری تشخیص دهد
    res_excluded = client.get(f'/api/invoice/check_number?num={test_inv_num}&exclude_id={created_inv_id}')
    assert res_excluded.status_code == 200
    data_ex = json.loads(res_excluded.data)
    assert data_ex['exists'] is False

def test_add_invoice_collision_detailed_message(client):
    """تست پیام خطای دقیق و هویت همکار هنگام ثبت فاکتور جدید با شماره تکراری"""
    with app.app_context():
        seller2 = User.query.filter_by(username='seller2_test').first()
        if not seller2:
            seller2 = User(
                username='seller2_test',
                full_name='حسین مرادی',
                role='seller',
                shop_id=2
            )
            seller2.set_password('123456')
            db.session.add(seller2)
            db.session.commit()

        seller_id = seller2.id
        seller_name = seller2.full_name

        dup_num = "TEST-DUP-7766"
        existing = Invoice.query.filter_by(invoice_number=dup_num).first()
        if existing:
            InvoiceItem.query.filter_by(invoice_id=existing.id).delete()
            db.session.delete(existing)
            db.session.commit()

        base_inv = Invoice(
            invoice_number=dup_num,
            customer_name='خریدار اول',
            seller_id=seller_id,
            shop_id=2,
            total_amount=20000000,
            shamsi_year=1403,
            shamsi_month=7,
            shamsi_date_time='1403/07/28 11:00',
            status='final'
        )
        db.session.add(base_inv)
        db.session.commit()

    with client.session_transaction() as sess:
        sess['user_id'] = seller_id
        sess['role'] = 'seller'
        sess['shop_id'] = 2
        sess['full_name'] = seller_name

    # درخواست JSON ثبت فاکتور با شماره تکراری
    payload = {
        'shop_id': 2,
        'invoice_type': 'final',
        'invoice_number': dup_num,
        'customer_name': 'خریدار دوم',
        'total_amount': 5000000,
        'paid_cash': 5000000,
        'items': [{
            'name': 'کالای تستی',
            'quantity': 1,
            'unit_price': 5000000,
            'original_price': 5000000,
            'buy_price': 3000000
        }]
    }

    res = client.post('/invoice/add', json=payload, headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
    assert res.status_code == 400
    res_data = json.loads(res.data)
    assert res_data['success'] is False
    assert 'حسین مرادی' in res_data['error']
    assert 'collision' in res_data
    assert res_data['collision']['seller_name'] == 'حسین مرادی'

def test_edit_invoice_number_change_and_stocklog_sync(client):
    """تست ویرایش شماره فاکتور و همگام‌سازی reference_id در لاگ‌های انبار"""
    with app.app_context():
        admin = User.query.filter_by(role='admin').first()
        admin_id = admin.id
        admin_name = admin.full_name

        inv_item = InventoryItem.query.filter_by(shop_id=1).first()
        if not inv_item:
            inv_item = InventoryItem(
                name='شیر ظرفشویی تست ویرایش',
                category='شیرآلات',
                shop_id=1,
                stock_quantity=10,
                buy_price=1000000,
                sell_price=2000000
            )
            db.session.add(inv_item)
            db.session.commit()

        item_id = inv_item.id
        item_name = inv_item.name
        item_buy = inv_item.buy_price
        item_sell = inv_item.sell_price

        initial_num = "TEST-EDIT-OLD-01"
        target_new_num = "TEST-EDIT-NEW-02"

        for num in [initial_num, target_new_num]:
            inv_found = Invoice.query.filter_by(invoice_number=num).first()
            if inv_found:
                InvoiceItem.query.filter_by(invoice_id=inv_found.id).delete()
                StockLog.query.filter_by(reference_id=num).delete()
                db.session.delete(inv_found)
                db.session.commit()

        test_inv = Invoice(
            invoice_number=initial_num,
            customer_name='خریدار ویرایش',
            seller_id=admin_id,
            shop_id=1,
            total_amount=2000000,
            paid_cash=2000000,
            shamsi_year=1403,
            shamsi_month=7,
            shamsi_date_time='1403/07/28 12:00',
            status='final'
        )
        db.session.add(test_inv)
        db.session.commit()

        item_row = InvoiceItem(
            invoice_id=test_inv.id,
            inventory_item_id=item_id,
            item_name=item_name,
            quantity=1,
            unit_buy_price=item_buy,
            unit_sell_price=item_sell,
            total_price=2000000,
            row_profit=1000000
        )
        db.session.add(item_row)

        old_log = StockLog(
            inventory_item_id=item_id,
            shop_id=1,
            change_type='sale',
            quantity_changed=-1,
            stock_after=9,
            reference_id=initial_num,
            user_name=admin_name,
            shamsi_date_time='1403/07/28 12:00'
        )
        db.session.add(old_log)
        db.session.commit()
        inv_id = test_inv.id

    with client.session_transaction() as sess:
        sess['user_id'] = admin_id
        sess['role'] = 'admin'
        sess['full_name'] = admin_name
        sess['shop_id'] = 1

    # ارسال درخواست ویرایش و تغییر شماره فاکتور به target_new_num
    form_data = {
        'invoice_number': target_new_num,
        'customer_name': 'خریدار ویرایش اصلاحی',
        'customer_phone': '09121112233',
        'status': 'final',
        'invoice_type': 'sale',
        'total_amount': '2,000,000',
        'paid_cash': '2,000,000',
        'item_inventory_id[]': [str(item_id)],
        'item_custom_name[]': [''],
        'item_category[]': ['شیرآلات'],
        'item_quantity[]': ['1'],
        'item_original_price[]': ['2,000,000'],
        'item_price[]': ['2,000,000'],
        'item_discount_percent[]': ['0'],
        'item_buy_price[]': ['1,000,000']
    }

    res_edit = client.post(f'/invoice/edit/{inv_id}', data=form_data, follow_redirects=True)
    assert res_edit.status_code == 200

    with app.app_context():
        refreshed_inv = db.session.get(Invoice, inv_id)
        assert refreshed_inv.invoice_number == target_new_num
        assert refreshed_inv.customer_name == 'خریدار ویرایش اصلاحی'

        # بررسی همگام‌سازی لاگ انبار با شماره جدید
        updated_logs = StockLog.query.filter_by(reference_id=target_new_num).all()
        assert len(updated_logs) >= 1
