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
            sess['full_name'] = 'ممیز ضدخرابکاری سیستم طهماسبی'
            sess['shop_id'] = 1
        yield c
    ctx.pop()


# ==============================================================================
# Challenge 1: Proportional Combo Package Allocation & Mathematical Invariants
# ==============================================================================

def test_adversarial_combo_odd_prime_proportional_allocation(client):
    """
    استرس‌تست ۱: تسهیم متناسب پکیج با اعداد فرد و اول و بررسی عدم حتی ۱ تومان خطا
    مثال مأموریت: ۳ کالا با قیمت‌های مصوب کاتالوگ ۳۳,۳۳۳ و ۵۰,۰۰۰ و ۱۷,۷۷۷ (جمع کاتالوگ: ۱۰۱,۱۱۰)
    تخفیف توافقی کل به ۸۱,۱۱۱ تومان.
    تضمین ۱۰۰٪ تطابق ریاضی: sum(allocated_prices) == agreed_price بدون ۱ تومان خطا
    """
    items = [
        {'id': 101, 'name': 'شیر ظرفشویی شلنگدار استیل', 'catalog_price': 33333, 'qty': 1},
        {'id': 102, 'name': 'روشویی کابینتی مدل آیدین', 'catalog_price': 50000, 'qty': 1},
        {'id': 103, 'name': 'آینه لمسی ضد بخار رویال', 'catalog_price': 17777, 'qty': 1}
    ]
    catalog_sum = sum(it['catalog_price'] * it['qty'] for it in items)
    assert catalog_sum == 101110

    agreed_bundle_price = 81111

    # شبیه‌سازی الگوریتم دقیق پیاده‌سازی شده در pos_demo.html
    allocated_rows = []
    allocated_sum = 0
    for idx, it in enumerate(items):
        q = it['qty']
        if idx == len(items) - 1:
            row_alloc = max(0, agreed_bundle_price - allocated_sum)
        else:
            ratio = (it['catalog_price'] * q) / catalog_sum if catalog_sum > 0 else (1 / len(items))
            row_alloc = round(agreed_bundle_price * ratio)
            allocated_sum += row_alloc
        
        base_unit = row_alloc // q
        remainder = row_alloc - (base_unit * q)
        if remainder == 0 or q == 1:
            allocated_rows.append({
                'name': it['name'],
                'qty': q,
                'unit_price': round(row_alloc / q),
                'original_price': it['catalog_price'],
                'total': round(row_alloc / q) * q
            })
        else:
            allocated_rows.append({
                'name': it['name'],
                'qty': q - 1,
                'unit_price': base_unit,
                'original_price': it['catalog_price'],
                'total': base_unit * (q - 1)
            })
            allocated_rows.append({
                'name': it['name'],
                'qty': 1,
                'unit_price': base_unit + remainder,
                'original_price': it['catalog_price'],
                'total': base_unit + remainder
            })

    # تأیید انطباق دقیق ریاضی
    calculated_total = sum(r['total'] for r in allocated_rows)
    assert calculated_total == agreed_bundle_price, f"اختلاف تومانی رخ داده: {calculated_total} != {agreed_bundle_price}"
    
    # تست ثبت فاکتور این پکیج با اقلام در دیتابیس از طریق API
    payload = {
        'shop_id': 1,
        'invoice_type': 'final',
        'customer_name': 'خریدار پکیج آزمون اعداد اول',
        'customer_phone': '09121119988',
        'total_amount': agreed_bundle_price,
        'paid_pos': agreed_bundle_price,
        'items': [
            {
                'name': r['name'],
                'category': 'پکیج بهداشتی',
                'quantity': r['qty'],
                'unit_price': r['unit_price'],
                'original_price': r['original_price']
            }
            for r in allocated_rows
        ]
    }

    resp = client.post('/invoice/add', data=json.dumps(payload), content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    inv_id = data['invoice_id']

    inv = Invoice.query.get(inv_id)
    assert inv is not None
    assert inv.total_amount == agreed_bundle_price

    # بررسی اقلام ذخیره شده در پایگاه داده
    db_items = InvoiceItem.query.filter_by(invoice_id=inv_id).all()
    assert len(db_items) == len(allocated_rows)
    db_items_total = sum(it.total_price for it in db_items)
    assert db_items_total == agreed_bundle_price, f"مجموع اقلام دیتابیس برابر مبلغ توافقی نیست: {db_items_total} != {agreed_bundle_price}"

    # بررسی اینواریانت عدم دستکاری نام کالاها
    for it in db_items:
        assert '(پکیج ترکیبی)' not in it.item_name
        assert 'پکیج ترکیبی' not in it.item_name

    # پاکسازی
    InvoiceItem.query.filter_by(invoice_id=inv_id).delete()
    db.session.delete(inv)
    db.session.commit()


def test_adversarial_combo_multi_quantity_and_prime_variations():
    """
    استرس‌تست ۱ متمم: تست ۵ قلم کالا با تعداد‌های مختلف (۱، ۳، ۵، ۷، ۲) و مبالغ اول/پیچیده
    """
    items = [
        {'id': 1, 'name': 'کالای ۱', 'catalog_price': 13579, 'qty': 1},
        {'id': 2, 'name': 'کالای ۲', 'catalog_price': 24691, 'qty': 3},
        {'id': 3, 'name': 'کالای ۳', 'catalog_price': 35791, 'qty': 5},
        {'id': 4, 'name': 'کالای ۴', 'catalog_price': 48111, 'qty': 7},
        {'id': 5, 'name': 'کالای ۵', 'catalog_price': 53233, 'qty': 2}
    ]
    catalog_sum = sum(it['catalog_price'] * it['qty'] for it in items)
    agreed_bundle_price = 456789  # عدد اول و بسیار نامتعارف

    allocated_rows = []
    allocated_sum = 0
    for idx, it in enumerate(items):
        q = it['qty']
        if idx == len(items) - 1:
            row_alloc = max(0, agreed_bundle_price - allocated_sum)
        else:
            ratio = (it['catalog_price'] * q) / catalog_sum if catalog_sum > 0 else (1 / len(items))
            row_alloc = round(agreed_bundle_price * ratio)
            allocated_sum += row_alloc
        
        base_unit = row_alloc // q
        remainder = row_alloc - (base_unit * q)
        if remainder == 0 or q == 1:
            allocated_rows.append({
                'name': it['name'],
                'qty': q,
                'unit_price': round(row_alloc / q),
                'total': round(row_alloc / q) * q
            })
        else:
            allocated_rows.append({
                'name': it['name'],
                'qty': q - 1,
                'unit_price': base_unit,
                'total': base_unit * (q - 1)
            })
            allocated_rows.append({
                'name': it['name'],
                'qty': 1,
                'unit_price': base_unit + remainder,
                'total': base_unit + remainder
            })

    total_calculated = sum(r['total'] for r in allocated_rows)
    assert total_calculated == agreed_bundle_price
    # اطمینان از اینکه هیچ عددی اعشاری نیست
    for r in allocated_rows:
        assert isinstance(r['unit_price'], int)
        assert isinstance(r['total'], int)


# ==============================================================================
# Challenge 2: Non-coercive Nesyeh Stress Test
# ==============================================================================

def test_adversarial_non_coercive_nesyeh_full_debt(client):
    """
    استرس‌تست ۲: ثبت فاکتور نسیه ۱۰۰٪ بدون پرداخت و اطمینان از عدم تحمیل به کارتخوان و ثبت بدهی مشتری در CRM
    """
    phone = '09120003344'
    cust = Customer.query.filter_by(phone=phone).first()
    if not cust:
        cust = Customer(name='مشتری استرس نسیه', phone=phone, outstanding_balance=1000000, total_purchases=5000000)
        db.session.add(cust)
        db.session.commit()
    else:
        cust.outstanding_balance = 1000000
        db.session.commit()

    initial_cust_balance = cust.outstanding_balance
    invoice_total = 43250000

    payload = {
        'shop_id': 1,
        'invoice_type': 'final',
        'customer_name': cust.name,
        'customer_phone': cust.phone,
        'total_amount': invoice_total,
        # کلیه مقادیر پرداخت صراحتاً صفر یا خالی
        'paid_pos': 0,
        'paid_card': 0,
        'paid_cash': 0,
        'paid_cheque': 0,
        'remaining_balance': invoice_total,
        'items': [
            {
                'name': 'کاشی و سرامیک پرسلان کالیبره',
                'category': 'کاشی و سرامیک',
                'quantity': 25,
                'unit_price': 1730000,
                'original_price': 1730000
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

    # بررسی حیاتی: هیچ وجهی به کارتخوان یا سایر کانال‌ها تحمیل نشده باشد
    assert inv.paid_pos == 0
    assert inv.paid_card == 0
    assert inv.paid_cash == 0
    assert inv.paid_cheque == 0
    assert inv.paid_amount == 0
    assert inv.remaining_balance == invoice_total
    assert inv.total_amount == invoice_total
    assert inv.is_settled is False
    assert 'نسیه' in inv.payment_method

    # بررسی به‌روزرسانی بدهی مشتری در CRM
    db.session.refresh(cust)
    assert cust.outstanding_balance == initial_cust_balance + invoice_total

    # پاکسازی
    InvoiceItem.query.filter_by(invoice_id=inv_id).delete()
    db.session.delete(inv)
    db.session.delete(cust)
    db.session.commit()


def test_adversarial_non_coercive_nesyeh_partial_payment(client):
    """
    استرس‌تست ۲ متمم: پرداخت جزئی نقد و باقی نسیه
    """
    phone = '09121115566'
    cust = Customer.query.filter_by(phone=phone).first()
    if not cust:
        cust = Customer(name='مشتری بیعانه نقدی', phone=phone, outstanding_balance=0, total_purchases=0)
        db.session.add(cust)
        db.session.commit()
    else:
        cust.outstanding_balance = 0
        db.session.commit()

    total_amt = 30000000
    paid_cash = 8000000
    expected_remaining = 22000000

    payload = {
        'shop_id': 1,
        'invoice_type': 'final',
        'customer_name': cust.name,
        'customer_phone': cust.phone,
        'total_amount': total_amt,
        'paid_pos': 0,
        'paid_card': 0,
        'paid_cash': paid_cash,
        'paid_cheque': 0,
        'remaining_balance': expected_remaining,
        'items': [
            {
                'name': 'روشویی پایه دار کلاسیک',
                'category': 'روشویی',
                'quantity': 2,
                'unit_price': 15000000
            }
        ]
    }

    resp = client.post('/invoice/add', data=json.dumps(payload), content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    inv_id = data['invoice_id']

    inv = Invoice.query.get(inv_id)
    assert inv.paid_cash == paid_cash
    assert inv.paid_pos == 0
    assert inv.remaining_balance == expected_remaining
    assert inv.paid_amount == paid_cash
    assert inv.is_settled is False

    db.session.refresh(cust)
    assert cust.outstanding_balance == expected_remaining

    # پاکسازی
    InvoiceItem.query.filter_by(invoice_id=inv_id).delete()
    db.session.delete(inv)
    db.session.delete(cust)
    db.session.commit()


# ==============================================================================
# Challenge 3: 5-Way Split Payment Stress Test
# ==============================================================================

def test_adversarial_5way_split_payment_complex_distribution(client):
    """
    استرس‌تست ۳: پرداخت همزمان از هر ۵ کانال با ارقام نامتعارف و بررسی تراز کامل حسابداری
    جمع فاکتور: 100,000,000 تومان
    - کارتخوان (POS): 15,350,000
    - کارت‌به‌کارت / شبا (Card): 24,650,000
    - نقد (Cash): 10,000,000
    - چک صیادی (Cheque): 30,000,000
    - مانده نسیه (Remaining): 20,000,000
    جمع اجزا = 15,350,000 + 24,650,000 + 10,000,000 + 30,000,000 + 20,000,000 = 100,000,000
    """
    total = 100000000
    pos = 15350000
    card = 24650000
    cash = 10000000
    cheque = 30000000
    remaining = 20000000
    assert pos + card + cash + cheque + remaining == total

    phone = '09124449900'
    cust = Customer.query.filter_by(phone=phone).first()
    if not cust:
        cust = Customer(name='مشتری ۵ کاناله ادورسریال', phone=phone, outstanding_balance=0)
        db.session.add(cust)
        db.session.commit()
    else:
        cust.outstanding_balance = 0
        db.session.commit()

    payload = {
        'shop_id': 1,
        'invoice_type': 'final',
        'customer_name': cust.name,
        'customer_phone': cust.phone,
        'total_amount': total,
        'paid_pos': pos,
        'paid_card': card,
        'paid_cash': cash,
        'paid_cheque': cheque,
        'remaining_balance': remaining,
        'dest_card_number': '6037997511223344',
        'dest_sheba_number': 'IR500170000000112233445566',
        'payment_tracking_code': 'TRK-987654321',
        'cheques': [
            {
                'sayad': '7788990011223344',
                'bank': 'بانک ملت شعبه ونک',
                'amount': cheque,
                'due_date': '1405/08/10'
            }
        ],
        'items': [
            {
                'name': 'پکیج وان جکوزی لوکس هیدروماساژ',
                'category': 'جکوزی',
                'quantity': 1,
                'unit_price': total,
                'original_price': total
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
    assert inv.total_amount == total
    assert inv.paid_pos == pos
    assert inv.paid_card == card
    assert inv.paid_cash == cash
    assert inv.paid_cheque == cheque
    assert inv.remaining_balance == remaining
    assert inv.dest_card_number == '6037997511223344'
    assert inv.dest_sheba_number == 'IR500170000000112233445566'
    assert inv.payment_tracking_code == 'TRK-987654321'

    # پرداخت نقدی آنی = pos + card + cash
    assert inv.paid_amount == pos + card + cash
    # با توجه به وجود چک صیادی و مانده نسیه، فاکتور نباید تسویه‌شده باشد
    assert inv.is_settled is False

    # بررسی رشته payment_method که همه کانال‌ها را شامل شود
    assert f"کارتخوان: {pos:,}" in inv.payment_method
    assert f"کارت/شبا: {card:,}" in inv.payment_method
    assert f"نقد: {cash:,}" in inv.payment_method
    assert f"چک صیادی: {cheque:,}" in inv.payment_method
    assert f"مانده تسویه نشده (نسیه): {remaining:,}" in inv.payment_method

    # بدهی در CRM
    db.session.refresh(cust)
    assert cust.outstanding_balance == remaining

    # پاکسازی
    Cheque.query.filter_by(invoice_id=inv_id).delete()
    InvoiceItem.query.filter_by(invoice_id=inv_id).delete()
    db.session.delete(inv)
    db.session.delete(cust)
    db.session.commit()


# ==============================================================================
# Challenge 4: Sayad Cheque Stress Test (Multiple Cheques & Invariants)
# ==============================================================================

def test_adversarial_sayad_multiple_cheques_persistence(client):
    """
    استرس‌تست ۴: ثبت چندین فقره چک صیادی در یک فاکتور با مشخصات کامل (بانک، تاریخ سررسید، شناسه صیاد)
    و بررسی اینکه حتی در صورت صفر بودن مانده نسیه، فاکتور تا وصول چک‌ها تسویه‌نشده باقی بماند (is_settled == False).
    """
    cheques_input = [
        {
            'sayad': '1111222233334444',
            'bank': 'بانک سپه شعبه مرکزی',
            'amount': 12500000,
            'due_date': '1405/04/10'
        },
        {
            'sayad': '5555666677778888',
            'bank': 'بانک صادرات شعبه بازار',
            'amount': 17500000,
            'due_date': '1405/05/15'
        },
        {
            'sayad': '9999000011112222',
            'bank': 'بانک پاسارگاد شعبه تجریش',
            'amount': 8000000,
            'due_date': '1405/06/20'
        },
        {
            'sayad': '3333444455556666',
            'bank': 'بانک سامان شعبه سعادت آباد',
            'amount': 14000000,
            'due_date': '1405/07/25'
        }
    ]
    total_cheques = sum(c['amount'] for c in cheques_input)
    assert total_cheques == 52000000

    payload = {
        'shop_id': 1,
        'invoice_type': 'final',
        'customer_name': 'مشتری چند فقر چک صیادی',
        'customer_phone': '09351112233',
        'total_amount': total_cheques,
        'paid_pos': 0,
        'paid_card': 0,
        'paid_cash': 0,
        'paid_cheque': total_cheques,
        'remaining_balance': 0, # مانده نسیه صفر است اما چک وصول نشده است
        'cheques': cheques_input,
        'items': [
            {
                'name': 'کاشی بین کابینتی لوکس وارداتی',
                'category': 'کاشی',
                'quantity': 52,
                'unit_price': 1000000
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
    assert inv.paid_cheque == total_cheques
    assert inv.remaining_balance == 0
    # اینواریانت کلیدی حسابداری: فاکتور با چک وصول‌نشده هرگز نباید تسویه‌شده علامت بخورد
    assert inv.is_settled is False

    # بررسی ثبت تک تک چک‌ها در جدول Cheque
    db_cheques = Cheque.query.filter_by(invoice_id=inv_id).order_by(Cheque.id).all()
    assert len(db_cheques) == 4

    for original, saved in zip(cheques_input, db_cheques):
        assert saved.sayad_number == original['sayad']
        assert saved.bank_name == original['bank']
        assert saved.amount == original['amount']
        assert saved.due_shamsi_date == original['due_date']
        assert saved.status == 'pending'
        assert saved.shop_id == 1

    # پاکسازی
    Cheque.query.filter_by(invoice_id=inv_id).delete()
    InvoiceItem.query.filter_by(invoice_id=inv_id).delete()
    db.session.delete(inv)
    db.session.commit()


# ==============================================================================
# Challenge 5: Branch Stock Deduction & Multi-Branch Isolation & Negative Stock
# ==============================================================================

def test_adversarial_branch_stock_isolation(client):
    """
    استرس‌تست ۵ بخش اول: ایزولاسیون انبار شعب و اطمینان از کسر موجودی فقط از شعبه هدف (shop_id=2 vs shop_id=1)
    """
    # اطمینان از وجود شعبه ۲
    shop2 = Shop.query.get(2)
    if not shop2:
        shop2 = Shop(id=2, name='شعبه ۲ طهماسبی (خیابان کاشانی)')
        db.session.add(shop2)
        db.session.commit()

    # ایجاد کالای هم‌نام در هر دو شعبه
    item_shop1 = InventoryItem.query.filter_by(name='تست ایزولاسیون شعبه فرنگی', shop_id=1).first()
    if not item_shop1:
        item_shop1 = InventoryItem(
            name='تست ایزولاسیون شعبه فرنگی',
            category='چینی بهداشتی',
            brand='مروارید',
            sell_price=5000000,
            buy_price=3500000,
            stock_quantity=40,
            shop_id=1
        )
        db.session.add(item_shop1)
    else:
        item_shop1.stock_quantity = 40

    item_shop2 = InventoryItem.query.filter_by(name='تست ایزولاسیون شعبه فرنگی', shop_id=2).first()
    if not item_shop2:
        item_shop2 = InventoryItem(
            name='تست ایزولاسیون شعبه فرنگی',
            category='چینی بهداشتی',
            brand='مروارید',
            sell_price=5000000,
            buy_price=3500000,
            stock_quantity=40,
            shop_id=2
        )
        db.session.add(item_shop2)
    else:
        item_shop2.stock_quantity = 40

    db.session.commit()

    stock_s1_before = item_shop1.stock_quantity
    stock_s2_before = item_shop2.stock_quantity
    sale_qty = 15

    # ثبت فاکتور قطعی صراحتاً برای شعبه ۲ (shop_id: 2)
    payload = {
        'shop_id': 2,
        'invoice_type': 'final',
        'customer_name': 'مشتری حضوری شعبه ۲',
        'customer_phone': '09129997766',
        'total_amount': 75000000,
        'paid_pos': 75000000,
        'items': [
            {
                'inventory_id': item_shop2.id,
                'name': item_shop2.name,
                'quantity': sale_qty,
                'unit_price': 5000000,
                'original_price': 5000000
            }
        ]
    }

    resp = client.post('/invoice/add', data=json.dumps(payload), content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    inv_id = data['invoice_id']

    # بررسی تغییرات انبار
    db.session.refresh(item_shop1)
    db.session.refresh(item_shop2)

    # انبار شعبه ۱ نباید دست بخورد
    assert item_shop1.stock_quantity == stock_s1_before, f"خطای ایزولاسیون: موجودی شعبه ۱ تغییر کرد! {item_shop1.stock_quantity} != {stock_s1_before}"
    # انبار شعبه ۲ باید دقیقاً به میزان sale_qty کاهش یافته باشد
    assert item_shop2.stock_quantity == stock_s2_before - sale_qty

    # بررسی ثبت لاگ انبار در شعبه ۲
    inv = Invoice.query.get(inv_id)
    assert inv.shop_id == 2
    log = StockLog.query.filter_by(reference_id=inv.invoice_number, inventory_item_id=item_shop2.id).first()
    assert log is not None
    assert log.shop_id == 2
    assert log.quantity_changed == -sale_qty
    assert log.stock_after == stock_s2_before - sale_qty
    assert log.change_type == 'sale'

    # پاکسازی
    StockLog.query.filter_by(reference_id=inv.invoice_number).delete()
    InvoiceItem.query.filter_by(invoice_id=inv_id).delete()
    db.session.delete(inv)
    db.session.delete(item_shop1)
    db.session.delete(item_shop2)
    db.session.commit()


def test_adversarial_branch_negative_stock_handling(client):
    """
    استرس‌تست ۵ بخش دوم: مدیریت کسری موجودی منفی بدون کرش سیستم و ثبت دقیق در لاگ انبار StockLog
    اگر موجودی انبار ۲ عدد باشد و ۵ عدد فروخته شود، موجودی کلمپ شده به ۰ می‌شود و لاگ با -5 ثبت می‌گردد.
    """
    item = InventoryItem.query.filter_by(name='تست کسری موجودی منفی M2', shop_id=1).first()
    if not item:
        item = InventoryItem(
            name='تست کسری موجودی منفی M2',
            category='اکسسوری',
            brand='تست',
            sell_price=2000000,
            buy_price=1200000,
            stock_quantity=2,  # موجودی فیزیکی فقط ۲ عدد
            shop_id=1
        )
        db.session.add(item)
    else:
        item.stock_quantity = 2
    db.session.commit()

    sale_qty = 5  # درخواست فروش ۳ عدد بیش از موجودی

    payload = {
        'shop_id': 1,
        'invoice_type': 'final',
        'customer_name': 'خریدار کسری موجودی',
        'customer_phone': '09121234567',
        'total_amount': 10000000,
        'paid_pos': 10000000,
        'items': [
            {
                'inventory_id': item.id,
                'name': item.name,
                'quantity': sale_qty,
                'unit_price': 2000000,
                'original_price': 2000000
            }
        ]
    }

    resp = client.post('/invoice/add', data=json.dumps(payload), content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    inv_id = data['invoice_id']

    db.session.refresh(item)
    # طبق منطق record_stock_change در helpers.py، اگر موجودی زیر صفر برود روی صفر کلمپ می‌شود
    assert item.stock_quantity == 0

    inv = Invoice.query.get(inv_id)
    log = StockLog.query.filter_by(reference_id=inv.invoice_number, inventory_item_id=item.id).first()
    assert log is not None
    assert log.quantity_changed == -sale_qty
    assert log.stock_after == 0

    # پاکسازی
    StockLog.query.filter_by(reference_id=inv.invoice_number).delete()
    InvoiceItem.query.filter_by(invoice_id=inv_id).delete()
    db.session.delete(inv)
    db.session.delete(item)
    db.session.commit()


def test_adversarial_proforma_invoice_does_not_deduct_stock(client):
    """
    استرس‌تست ۵ بخش سوم: پیش‌فاکتور (proforma) نباید تحت هیچ شرایطی از انبار کسر کند
    """
    item = InventoryItem.query.filter_by(name='تست پیش فاکتور عدم کسر انبار', shop_id=1).first()
    if not item:
        item = InventoryItem(
            name='تست پیش فاکتور عدم کسر انبار',
            category='شیرآلات',
            brand='قهرمان',
            sell_price=4000000,
            buy_price=2800000,
            stock_quantity=20,
            shop_id=1
        )
        db.session.add(item)
    else:
        item.stock_quantity = 20
    db.session.commit()

    initial_stock = item.stock_quantity

    payload = {
        'shop_id': 1,
        'invoice_type': 'proforma', # پیش‌فاکتور
        'doc_status': 'proforma',
        'customer_name': 'متقاضی پیش‌فاکتور استعلامی',
        'customer_phone': '09128889900',
        'total_amount': 24000000,
        'items': [
            {
                'inventory_id': item.id,
                'name': item.name,
                'quantity': 6,
                'unit_price': 4000000
            }
        ]
    }

    resp = client.post('/invoice/add', data=json.dumps(payload), content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    inv_id = data['invoice_id']

    inv = Invoice.query.get(inv_id)
    assert inv.status == 'proforma'

    # اطمینان از دست نخوردن موجودی کالا
    db.session.refresh(item)
    assert item.stock_quantity == initial_stock

    # اطمینان از عدم وجود لاگ کسر انبار برای این پیش‌فاکتور
    logs = StockLog.query.filter_by(reference_id=inv.invoice_number).all()
    assert len(logs) == 0

    # پاکسازی
    InvoiceItem.query.filter_by(invoice_id=inv_id).delete()
    db.session.delete(inv)
    db.session.delete(item)
    db.session.commit()
