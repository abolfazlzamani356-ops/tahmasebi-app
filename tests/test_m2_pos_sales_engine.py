import json
import pytest
from app import app, db
from models import User, Shop, ProductCatalog, InventoryItem, Invoice, InvoiceItem, Customer, Cheque, StockLog

@pytest.fixture
def client():
    app.config['TESTING'] = True
    ctx = app.app_context()
    ctx.push()
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['user_id'] = 1
            sess['role'] = 'admin'
            sess['full_name'] = 'مدیر سیستم طهماسبی'
            sess['shop_id'] = 1
        yield c
    ctx.pop()

def test_invoice_add_json_api_success(client):
    """تست ثبت فاکتور از طریق API به صورت JSON و دریافت پاسخ استاندارد"""
    payload = {
        'shop_id': 1,
        'invoice_type': 'final',
        'customer_name': 'مشتری تست API لمسی',
        'customer_phone': '09129990011',
        'total_amount': 5000000,
        'paid_pos': 3000000,
        'paid_cash': 2000000,
        'paid_card': 0,
        'paid_cheque': 0,
        'remaining_balance': 0,
        'items': [
            {
                'name': 'شیر دوش تست M2',
                'category': 'شیرآلات',
                'quantity': 1,
                'unit_price': 5000000,
                'original_price': 5000000,
                'buy_price': 3500000,
                'discount': 0
            }
        ]
    }
    
    resp = client.post('/invoice/add', data=json.dumps(payload), content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data is not None
    assert data.get('success') is True
    assert 'invoice_id' in data
    assert data['total_amount'] == 5000000
    assert data['remaining_balance'] == 0

    # بررسی ثبت واقعی در دیتابیس
    inv = Invoice.query.get(data['invoice_id'])
    assert inv is not None
    assert inv.customer_name == 'مشتری تست API لمسی'
    assert inv.paid_pos == 3000000
    assert inv.paid_cash == 2000000
    assert inv.remaining_balance == 0
    assert inv.is_settled is True

    # پاکسازی
    InvoiceItem.query.filter_by(invoice_id=inv.id).delete()
    db.session.delete(inv)
    db.session.commit()

def test_5way_split_payment_persistence(client):
    """تست تفکیک ۵ گانه پرداخت: کارتخوان، کارت/شبا، نقد، چک صیادی و مانده نسیه"""
    payload = {
        'shop_id': 1,
        'invoice_type': 'final',
        'customer_name': 'آقای پرداخت ترکیبی ۵ کاناله',
        'customer_phone': '09127778899',
        'total_amount': 25000000,
        'paid_pos': 5000000,
        'paid_card': 4000000,
        'paid_cash': 3000000,
        'paid_cheque': 8000000,
        'remaining_balance': 5000000,
        'items': [
            {
                'name': 'کابین روشویی لوکس تست',
                'category': 'روشویی کابینتی',
                'quantity': 1,
                'unit_price': 25000000,
                'original_price': 25000000,
                'buy_price': 18000000
            }
        ],
        'cheques': [
            {
                'sayad': '1122334455667788',
                'bank': 'ملی',
                'amount': 8000000,
                'due_date': '1405/09/20'
            }
        ]
    }

    resp = client.post('/invoice/add', data=json.dumps(payload), content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    inv_id = data['invoice_id']

    inv = Invoice.query.get(inv_id)
    assert inv is not None
    assert inv.paid_pos == 5000000
    assert inv.paid_card == 4000000
    assert inv.paid_cash == 3000000
    assert inv.paid_cheque == 8000000
    assert inv.remaining_balance == 5000000
    assert inv.total_amount == 25000000
    # مجموع دریافتی با چک ۲۰ میلیون است و ۵ میلیون مانده، پس تسویه نشده
    assert inv.is_settled is False

    # بررسی ثبت چک
    chk = Cheque.query.filter_by(invoice_id=inv.id).first()
    assert chk is not None
    assert chk.sayad_number == '1122334455667788'
    assert chk.bank_name == 'ملی'
    assert chk.amount == 8000000
    assert chk.status == 'pending'

    # پاکسازی
    Cheque.query.filter_by(invoice_id=inv.id).delete()
    InvoiceItem.query.filter_by(invoice_id=inv.id).delete()
    db.session.delete(inv)
    db.session.commit()

def test_non_coercive_nesyeh_zero_payments(client):
    """تست نسیه غیرتحمیلی: در صورت عدم ورود پرداخت، مانده برابر کل مبلغ است و هرگز به کارتخوان تحمیل نمی‌شود"""
    payload = {
        'shop_id': 1,
        'invoice_type': 'final',
        'customer_name': 'مشتری حساب دفتری (نسیه کامل)',
        'customer_phone': '09121110022',
        'total_amount': 18500000,
        'paid_pos': 0,
        'paid_card': 0,
        'paid_cash': 0,
        'paid_cheque': 0,
        'remaining_balance': 18500000,
        'items': [
            {
                'name': 'ست شیرآلات کامل تست نسیه',
                'category': 'شیرآلات',
                'quantity': 1,
                'unit_price': 18500000,
                'original_price': 18500000
            }
        ]
    }

    resp = client.post('/invoice/add', data=json.dumps(payload), content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    inv_id = data['invoice_id']

    inv = Invoice.query.get(inv_id)
    assert inv is not None
    # اینواریانت حیاتی: عدم تحمیل کارتخوان به فاکتور نسیه
    assert inv.paid_pos == 0
    assert inv.paid_card == 0
    assert inv.paid_cash == 0
    assert inv.paid_cheque == 0
    assert inv.remaining_balance == 18500000
    assert inv.is_settled is False
    assert 'نسیه' in inv.payment_method

    # پاکسازی
    InvoiceItem.query.filter_by(invoice_id=inv.id).delete()
    db.session.delete(inv)
    db.session.commit()

def test_sayad_cheque_capture_and_persistence(client):
    """تست ثبت مشخصات چک صیادی ۱۶ رقمی و ایجاد رکورد Cheque در پایگاه داده"""
    payload = {
        'shop_id': 1,
        'invoice_type': 'final',
        'customer_name': 'مشتری چک صیادی بنفش',
        'customer_phone': '09351234567',
        'total_amount': 14000000,
        'paid_pos': 2000000,
        'paid_card': 0,
        'paid_cash': 0,
        'paid_cheque': 12000000,
        'remaining_balance': 0,
        'cheques': [
            {
                'sayad': '9876543210987654',
                'bank': 'بانک ملت شعبه طالقانی',
                'amount': 12000000,
                'due_date': '1405/11/15'
            }
        ],
        'items': [
            {
                'name': 'سینک گرانیتی دو لگنه تست',
                'category': 'سینک گرانیتی',
                'quantity': 1,
                'unit_price': 14000000
            }
        ]
    }

    resp = client.post('/invoice/add', data=json.dumps(payload), content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    inv_id = data['invoice_id']

    cheques = Cheque.query.filter_by(invoice_id=inv_id).all()
    assert len(cheques) == 1
    chk = cheques[0]
    assert chk.sayad_number == '9876543210987654'
    assert chk.bank_name == 'بانک ملت شعبه طالقانی'
    assert chk.amount == 12000000
    assert chk.due_shamsi_date == '1405/11/15'
    assert chk.status == 'pending'

    # پاکسازی
    Cheque.query.filter_by(invoice_id=inv_id).delete()
    InvoiceItem.query.filter_by(invoice_id=inv_id).delete()
    inv = Invoice.query.get(inv_id)
    if inv: db.session.delete(inv)
    db.session.commit()

def test_atomic_stock_deduction_and_stock_log(client):
    """تست کسر اتمیک موجودی انبار شعبه انتخابی و ثبت لاگ StockLog"""
    # ایجاد یا دریافت یک کالای انبار در شعبه ۱
    test_item = InventoryItem.query.filter_by(name='توالت فرنگی تست کسر اتمیک M2', shop_id=1).first()
    if not test_item:
        test_item = InventoryItem(
            name='توالت فرنگی تست کسر اتمیک M2',
            category='توالت فرنگی',
            brand='مروارید',
            code='MOR-TEST-M2',
            sell_price=6000000,
            buy_price=4500000,
            stock_quantity=25,
            shop_id=1
        )
        db.session.add(test_item)
        db.session.commit()
    else:
        test_item.stock_quantity = 25
        db.session.commit()

    initial_stock = test_item.stock_quantity
    deduct_qty = 3

    payload = {
        'shop_id': 1,
        'invoice_type': 'final',
        'customer_name': 'خریدار تستی انبار',
        'customer_phone': '09190001122',
        'total_amount': 18000000,
        'paid_pos': 18000000,
        'items': [
            {
                'inventory_id': test_item.id,
                'name': test_item.name,
                'category': test_item.category,
                'quantity': deduct_qty,
                'unit_price': 6000000,
                'original_price': 6000000,
                'buy_price': 4500000
            }
        ]
    }

    resp = client.post('/invoice/add', data=json.dumps(payload), content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    inv_id = data['invoice_id']

    # بررسی کسر موجودی
    refreshed_item = InventoryItem.query.get(test_item.id)
    assert refreshed_item.stock_quantity == initial_stock - deduct_qty

    # بررسی لاگ انبار StockLog
    inv = Invoice.query.get(inv_id)
    stock_log = StockLog.query.filter_by(reference_id=inv.invoice_number, inventory_item_id=test_item.id).first()
    assert stock_log is not None
    assert stock_log.change_type == 'sale'
    assert stock_log.quantity_changed == -deduct_qty
    assert stock_log.stock_after == initial_stock - deduct_qty

    # پاکسازی
    StockLog.query.filter_by(reference_id=inv.invoice_number).delete()
    InvoiceItem.query.filter_by(invoice_id=inv.id).delete()
    db.session.delete(inv)
    db.session.delete(test_item)
    db.session.commit()

def test_proportional_combo_package_exact_penny_rounding():
    """تست فرمول ریاضی تسهیم متناسب پکیج ترکیبی با گردکردن دقیق عدد صحیح بدون حتی ۱ تومان اختلاف"""
    items = [
        {'id': 1, 'name': 'روشویی کابینتی رویال', 'catalog_price': 4500000, 'qty': 1},
        {'id': 2, 'name': 'آینه بک لایت رویال', 'catalog_price': 3200000, 'qty': 1},
        {'id': 3, 'name': 'باکس جانبی رویال', 'catalog_price': 1800000, 'qty': 1}
    ]
    catalog_sum = sum(it['catalog_price'] * it['qty'] for it in items)
    assert catalog_sum == 9500000

    agreed_bundle_price = 8000000 # توافق روی ۸ میلیون تومان (۱۵۰۰۰۰۰ تخفیف کلی)

    # الگوریتم تسهیم دقیق
    allocated_rows = []
    allocated_sum = 0
    for idx, it in enumerate(items):
        if idx == len(items) - 1:
            row_alloc = agreed_bundle_price - allocated_sum
        else:
            ratio = (it['catalog_price'] * it['qty']) / catalog_sum
            row_alloc = round(agreed_bundle_price * ratio)
            allocated_sum += row_alloc
        unit_price = row_alloc // it['qty']
        allocated_rows.append({
            'name': it['name'],
            'qty': it['qty'],
            'unit_price': unit_price,
            'total': unit_price * it['qty']
        })

    # تأیید مجموع دقیقاً برابر با مبلغ توافقی
    total_calculated = sum(r['total'] for r in allocated_rows)
    assert total_calculated == agreed_bundle_price, f"اختلاف در مجموع پکیج: {total_calculated} != {agreed_bundle_price}"
    
    # تست حالت تقسیم فرد (Odd Divisions) با ۳ کالا به مبلغ کل ۲,۵۰۰,۰۰۰ تومان
    odd_items = [
        {'id': 10, 'name': 'قلم الف', 'catalog_price': 1000000, 'qty': 1},
        {'id': 11, 'name': 'قلم ب', 'catalog_price': 1000000, 'qty': 1},
        {'id': 12, 'name': 'قلم ج', 'catalog_price': 1000000, 'qty': 1}
    ]
    odd_cat_sum = 3000000
    odd_agreed = 2500000
    odd_alloc_sum = 0
    odd_results = []
    for idx, it in enumerate(odd_items):
        if idx == len(odd_items) - 1:
            row_alloc = odd_agreed - odd_alloc_sum
        else:
            ratio = (it['catalog_price'] * it['qty']) / odd_cat_sum
            row_alloc = round(odd_agreed * ratio)
            odd_alloc_sum += row_alloc
        odd_results.append(row_alloc)

    assert sum(odd_results) == odd_agreed
    assert odd_results == [833333, 833333, 833334] # تضمین عدم پرتاب خطای اعشار و مطابقت ۱۰۰٪ با ریال/تومان

def test_clean_product_naming_invariant(client):
    """تست اینواریانت نام تمیز اقلام: عدم الحاق برچسب '(پکیج ترکیبی)' به نام کالا در دیتابیس و فاکتور"""
    payload = {
        'shop_id': 1,
        'invoice_type': 'final',
        'customer_name': 'مشتری پکیج ترکیبی تمیز',
        'customer_phone': '09123337788',
        'total_amount': 7000000,
        'paid_pos': 7000000,
        'items': [
            {
                'name': 'روشویی کابینتی مدل رویال', # نام تمیز بدون هیچ پسوند
                'category': 'روشویی کابینتی',
                'quantity': 1,
                'unit_price': 4000000,
                'original_price': 4500000
            },
            {
                'name': 'آینه هوشمند مدل رویال', # نام تمیز
                'category': 'روشویی کابینتی',
                'quantity': 1,
                'unit_price': 3000000,
                'original_price': 3500000
            }
        ]
    }

    resp = client.post('/invoice/add', data=json.dumps(payload), content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    inv_id = data['invoice_id']

    items = InvoiceItem.query.filter_by(invoice_id=inv_id).all()
    for item in items:
        assert '(پکیج ترکیبی)' not in item.item_name
        assert 'پکیج ترکیبی' not in item.item_name
        assert item.item_name in ['روشویی کابینتی مدل رویال', 'آینه هوشمند مدل رویال']

    # پاکسازی
    InvoiceItem.query.filter_by(invoice_id=inv_id).delete()
    inv = Invoice.query.get(inv_id)
    if inv: db.session.delete(inv)
    db.session.commit()

def test_customer_lookup_endpoint(client):
    """تست استعلام آنی سوابق مشتری با پارامتر q و دریافت مانده بدهی و رتبه اعتباری"""
    # ایجاد مشتری نمونه با بدهی
    cust = Customer.query.filter_by(phone='09128887766').first()
    if not cust:
        cust = Customer(
            name='مهندس کمالی اعتباری',
            phone='09128887766',
            outstanding_balance=12500000,
            total_purchases=45000000,
            ai_credit_score=85,
            ai_risk_tier='A'
        )
        db.session.add(cust)
        db.session.commit()
    else:
        cust.outstanding_balance = 12500000
        cust.ai_credit_score = 85
        cust.ai_risk_tier = 'A'
        db.session.commit()

    # استعلام با q حاوی شماره تلفن
    resp = client.get('/api/customer/lookup?q=09128887766')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['found'] is True
    assert data['name'] == 'مهندس کمالی اعتباری'
    assert data['outstanding_balance'] == 12500000
    assert data['ai_credit_score'] >= 80
    assert data['ai_risk_tier'] in ['A+', 'A', 'B']

    # استعلام با شماره ناموجود
    resp2 = client.get('/api/customer/lookup?q=09999999999')
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2['found'] is False

    # پاکسازی
    db.session.delete(cust)
    db.session.commit()

def test_print_routes_thermal_and_a4(client):
    """تست صحت و سلامت رندرهای چاپی: فیش حرارتی ۸۰ میلی‌متری و فاکتور رسمی A4"""
    # ایجاد یک فاکتور تستی
    test_inv = Invoice(
        invoice_number='INV-TEST-PRINT-M2',
        customer_name='خریدار چاپ فاکتور M2',
        customer_phone='09124445566',
        status='final',
        invoice_type='sale',
        payment_method='کارتخوان: 7,500,000',
        total_amount=7500000,
        paid_pos=7500000,
        paid_amount=7500000,
        remaining_balance=0,
        is_settled=True,
        seller_id=1,
        shamsi_year=1403,
        shamsi_month=8,
        shamsi_day=15,
        shamsi_date_time='1403/08/15 - 14:30:00',
        shop_id=1
    )
    db.session.add(test_inv)
    db.session.commit()

    # ردیف فاکتور
    row = InvoiceItem(
        invoice_id=test_inv.id,
        item_name='علم دوش دوکاره لوکس استیل',
        category='علم دوش',
        quantity=1,
        unit_buy_price=5000000,
        unit_sell_price=7500000,
        discount=0,
        total_price=7500000,
        row_profit=2500000
    )
    db.session.add(row)
    db.session.commit()

    # ۱. تست فیش پرینتر ۸۰ میلی‌متری
    resp_pos = client.get(f'/print_pos/{test_inv.id}')
    assert resp_pos.status_code == 200
    pos_html = resp_pos.get_data(as_text=True)
    assert 'INV-TEST-PRINT-M2' in pos_html
    assert 'علم دوش دوکاره لوکس استیل' in pos_html
    assert '7,500,000' in pos_html

    # ۲. تست فاکتور رسمی A4 با هر دو آدرس
    resp_a4_1 = client.get(f'/invoice/print/a4/{test_inv.id}')
    assert resp_a4_1.status_code == 200
    a4_html1 = resp_a4_1.get_data(as_text=True)
    assert 'INV-TEST-PRINT-M2' in a4_html1
    assert 'خریدار چاپ فاکتور M2' in a4_html1

    resp_a4_2 = client.get(f'/invoice/print_a4/{test_inv.id}')
    assert resp_a4_2.status_code == 200
    a4_html2 = resp_a4_2.get_data(as_text=True)
    assert 'INV-TEST-PRINT-M2' in a4_html2

    # پاکسازی
    InvoiceItem.query.filter_by(invoice_id=test_inv.id).delete()
    db.session.delete(test_inv)
    db.session.commit()

def test_pos_demo_html_components_present():
    """تست انطباق تمپلیت pos_demo.html با الزامات R1 و Milestone 2"""
    with open('templates/pos_demo.html', encoding='utf-8') as f:
        content = f.read()

    # دکمه بازنشانی به جمع مصوب اقلام
    assert '🔄 بازنشانی به جمع مصوب اقلام' in content

    # دکمه پرداخت کل با این روش
    assert '⚡ پرداخت کل با این روش' in content

    # مودال پیش‌نمایش چاپ فاکتور با گزینه‌های حرارتی و A4
    assert 'showPrintModal' in content
    assert '/print_pos/' in content
    assert '/invoice/print_a4/' in content
    assert 'فاکتور جدید' in content

    # چک صیادی
    assert 'شناسه ۱۶ رقمی صیادی' in content
    assert 'chequeForm' in content

    # استعلام آنی مشتری و بدهی قبلی
    assert 'onCustomerPhoneInput' in content
    assert 'customerInfo.outstanding_balance' in content
    assert 'customerInfo.ai_credit_score' in content

    # بازخورد صوتی و لرزشی
    assert 'tahmasebi_pos_sound' in content
    assert 'AudioContext' in content
    assert 'vibrate' in content
