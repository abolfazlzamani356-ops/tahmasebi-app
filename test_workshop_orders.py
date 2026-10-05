import pytest
import json
import uuid
import jdatetime
from app import app, db
from models import User, Shop, Customer, CustomWorkshopOrder, AuditLog

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        yield client

@pytest.fixture
def test_setup():
    with app.app_context():
        # اطمینان از وجود شعبه
        shop = Shop.query.first()
        if not shop:
            shop = Shop(name="شعبه ۱ مرکزی", rent_amount=15000000)
            db.session.add(shop)
            db.session.commit()

        # کاربر فروشنده
        seller = User.query.filter_by(username='seller_workshop_test').first()
        if not seller:
            seller = User(
                username='seller_workshop_test',
                full_name='فروشنده تست کارگاه',
                role='seller',
                shop_id=shop.id,
                is_active=True
            )
            seller.set_password('123456')
            db.session.add(seller)
            db.session.commit()

        # کاربر مدیر
        admin = User.query.filter_by(username='admin_workshop_test').first()
        if not admin:
            admin = User(
                username='admin_workshop_test',
                full_name='مدیر تست کارگاه',
                role='admin',
                shop_id=shop.id,
                is_active=True
            )
            admin.set_password('123456')
            db.session.add(admin)
            db.session.commit()

        return {
            'shop_id': shop.id,
            'seller_id': seller.id,
            'admin_id': admin.id
        }

def test_workshop_order_model_and_dict(test_setup):
    """تست ساختار داده و متدهای مدل سفارش ساخت کارگاه"""
    with app.app_context():
        now_j = jdatetime.datetime.now()
        uid = uuid.uuid4().hex[:6]
        order = CustomWorkshopOrder(
            order_number=f"ORD-{now_j.year}-{uid}",
            seller_id=test_setup['seller_id'],
            shop_id=test_setup['shop_id'],
            customer_name="آقای رضوی (تست)",
            customer_phone="09121234567",
            product_type="کابین روشویی",
            model_name="آرشام",
            quantity=3,
            width=60,
            depth=40,
            height=60,
            dimensions_text="۶۰×۴۰ ارتفاع ۶۰",
            body_color="سفید",
            door_color="طوسی بتن",
            sheet_thickness="ورق ۱۶ میل PVC ضدآب",
            hinge_type="لولای تمام استیل آرام‌بند",
            door_drawer_config="۲ درب",
            sink_type="کاسه روکار",
            priority="urgent",
            status="pending",
            shamsi_date=now_j.strftime('%Y/%m/%d %H:%M'),
            shamsi_year=now_j.year,
            shamsi_month=now_j.month,
            promised_delivery_date=f"{now_j.year}/07/15",
            customer_price=4500000,
            prepaid_amount=1500000,
            special_notes="کف کار کاملاً ضدآب شود و شیارها تراز باشند."
        )
        db.session.add(order)
        db.session.commit()

        try:
            d = order.to_dict()
            assert d['order_number'] == f"ORD-{now_j.year}-{uid}"
            assert d['customer_name'] == "آقای رضوی (تست)"
            assert d['model_name'] == "آرشام"
            assert d['quantity'] == 3
            assert d['remaining_balance'] == 3000000
            assert "۶۰×۴۰" in d['dimensions_text']
        finally:
            db.session.delete(order)
            db.session.commit()

def test_api_create_workshop_order(client, test_setup):
    """تست اندپوینت ایجاد سفارش کارگاهی با محاسبه خودکار شماره سفارش و ایجاد مشتری"""
    with client.session_transaction() as sess:
        sess['user_id'] = test_setup['seller_id']
        sess['role'] = 'seller'
        sess['full_name'] = 'فروشنده تست کارگاه'

    payload = {
        'customer_name': 'مهندس کاظمی',
        'customer_phone': '09351112233',
        'product_type': 'کابین روشویی',
        'model_name': 'یوکا',
        'quantity': '3',
        'width': '75',
        'depth': '43',
        'height': '60',
        'body_color': 'طوسی بتن',
        'door_color': 'سفید استپ',
        'sheet_thickness': 'ورق ۱۶ میل PVC ضدآب',
        'hinge_type': 'لولای تمام استیل آرام‌بند',
        'door_drawer_config': '۲ کشو',
        'sink_type': 'سنگ لبه‌دار توکار',
        'priority': 'urgent',
        'promised_delivery_date': '1405/08/01',
        'customer_price': '5,800,000',
        'prepaid_amount': '2,000,000',
        'estimated_cost': '3,200,000',
        'special_notes': 'تراز خطوط کشوها دقیق بررسی شود'
    }

    resp = client.post('/api/workshop_orders/create', data=payload)
    assert resp.status_code == 201
    data = json.loads(resp.data.decode('utf-8'))
    assert data['success'] is True
    assert 'ORD-' in data['order_number']
    assert data['order']['quantity'] == 3
    order_id = data['order_id']

    # بررسی ثبت در دیتابیس
    with app.app_context():
        ord_db = db.session.get(CustomWorkshopOrder, order_id)
        try:
            assert ord_db is not None
            assert ord_db.customer_name == 'مهندس کاظمی'
            assert ord_db.model_name == 'یوکا'
            assert ord_db.quantity == 3
            assert ord_db.customer_price == 5800000
            assert ord_db.prepaid_amount == 2000000
            assert ord_db.status == 'pending'

            # بررسی ایجاد اتوماتیک مشتری
            cust = Customer.query.filter_by(phone='09351112233').first()
            assert cust is not None
            assert cust.name == 'مهندس کاظمی'
        finally:
            if ord_db:
                db.session.delete(ord_db)
                db.session.commit()

def test_workshop_orders_hub_and_filters(client, test_setup):
    """تست میز کار سفارشات و بارگذاری نماهای کانبان و جدول با آمار"""
    with client.session_transaction() as sess:
        sess['user_id'] = test_setup['admin_id']
        sess['role'] = 'admin'
        sess['full_name'] = 'مدیر تست کارگاه'

    with app.app_context():
        now_j = jdatetime.datetime.now()
        uid = uuid.uuid4().hex[:6]
        order = CustomWorkshopOrder(
            order_number=f"ORD-{now_j.year}-{uid}",
            seller_id=test_setup['seller_id'],
            shop_id=test_setup['shop_id'],
            customer_name="مشتری تست کانبان",
            product_type="باکس دیواری تک",
            model_name="هلیا",
            status="in_production",
            priority="normal",
            shamsi_date=now_j.strftime('%Y/%m/%d %H:%M'),
            shamsi_year=now_j.year,
            shamsi_month=now_j.month
        )
        db.session.add(order)
        db.session.commit()
        oid = order.id

    try:
        # نمای کانبان
        resp = client.get('/workshop_orders?view=kanban')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert "میز کار سفارشات ساخت کارگاهی" in html
        assert "مشتری تست کانبان" in html
        assert "بورد کانبان" in html or "نمای کانبان" in html

        # نمای جدول
        resp_tbl = client.get('/workshop_orders?view=table')
        assert resp_tbl.status_code == 200
        html_tbl = resp_tbl.data.decode('utf-8')
        assert "نمای جدول" in html_tbl
        assert "مشتری تست کانبان" in html_tbl
    finally:
        with app.app_context():
            ord_db = db.session.get(CustomWorkshopOrder, oid)
            if ord_db:
                db.session.delete(ord_db)
                db.session.commit()

def test_api_update_status_and_lifecycle(client, test_setup):
    """تست تغییر وضعیت سفارش در کارگاه و ثبت لاگ ممیزی"""
    with client.session_transaction() as sess:
        sess['user_id'] = test_setup['admin_id']
        sess['role'] = 'admin'
        sess['full_name'] = 'مدیر تست کارگاه'

    with app.app_context():
        now_j = jdatetime.datetime.now()
        uid = uuid.uuid4().hex[:6]
        order = CustomWorkshopOrder(
            order_number=f"ORD-{now_j.year}-{uid}",
            seller_id=test_setup['seller_id'],
            shop_id=test_setup['shop_id'],
            customer_name="مشتری تست وضعیت",
            product_type="کابین روشویی",
            status="pending",
            shamsi_date=now_j.strftime('%Y/%m/%d %H:%M'),
            shamsi_year=now_j.year,
            shamsi_month=now_j.month
        )
        db.session.add(order)
        db.session.commit()
        oid = order.id

    try:
        # تغییر وضعیت به در حال ساخت
        resp = client.post(f'/api/workshop_orders/{oid}/update_status', json={
            'status': 'in_production',
            'assigned_worker': 'آقای حسینی (استادکار)',
            'admin_notes': 'ورق‌ها برش داده شد'
        })
        assert resp.status_code == 200
        data = json.loads(resp.data.decode('utf-8'))
        assert data['success'] is True
        assert data['status'] == 'in_production'

        # تغییر وضعیت به تحویل شده
        resp2 = client.post(f'/api/workshop_orders/{oid}/update_status', json={
            'status': 'delivered'
        })
        assert resp2.status_code == 200

        with app.app_context():
            ord_db = db.session.get(CustomWorkshopOrder, oid)
            assert ord_db.status == 'delivered'
            assert ord_db.delivered_at is not None
            assert ord_db.assigned_worker == 'آقای حسینی (استادکار)'

            # بررسی لاگ
            last_log = AuditLog.query.filter_by(category="کارگاه").order_by(AuditLog.id.desc()).first()
            assert last_log is not None
            assert ord_db.order_number in last_log.action
    finally:
        with app.app_context():
            ord_db = db.session.get(CustomWorkshopOrder, oid)
            if ord_db:
                db.session.delete(ord_db)
                db.session.commit()

def test_print_workshop_order_job_sheet(client, test_setup):
    """تست چاپ برگه حواله ساخت کارگاه A4/A5 با تمامی مشخصات و چک‌لیست کنترل کیفیت"""
    with client.session_transaction() as sess:
        sess['user_id'] = test_setup['seller_id']
        sess['role'] = 'seller'
        sess['full_name'] = 'فروشنده تست کارگاه'

    with app.app_context():
        now_j = jdatetime.datetime.now()
        uid = uuid.uuid4().hex[:6]
        order = CustomWorkshopOrder(
            order_number=f"ORD-{now_j.year}-{uid}",
            seller_id=test_setup['seller_id'],
            shop_id=test_setup['shop_id'],
            customer_name="خریدار حواله چاپ",
            product_type="ست کامل کابین و آینه",
            model_name="ماربل",
            dimensions_text="۸۰×۴۵ ارتفاع ۶۵",
            body_color="مشکی ماربل",
            door_color="طلایی مات",
            sheet_thickness="ورق ۱۶ میل PVC ضدآب",
            hinge_type="لولای تمام استیل ضدزنگ آرام‌بند",
            sink_type="سنگ سرامیکی پرسلان",
            status="approved",
            shamsi_date=now_j.strftime('%Y/%m/%d %H:%M'),
            shamsi_year=now_j.year,
            shamsi_month=now_j.month
        )
        db.session.add(order)
        db.session.commit()
        oid = order.id

    try:
        resp = client.get(f'/workshop_orders/{oid}/print')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert "حواله فنی ساخت کارگاه" in html
        assert f"ORD-{now_j.year}-{uid}" in html
        assert "کنترل کیفیت نهایی کارگاه (QC)" in html
        assert "استادکار سازنده کارگاه" in html
    finally:
        with app.app_context():
            ord_db = db.session.get(CustomWorkshopOrder, oid)
            if ord_db:
                db.session.delete(ord_db)
                db.session.commit()

def test_api_share_workshop_order_text(client, test_setup):
    """تست ساخت متن فنی جهت ارسال سریع در روبیکا، ایتا و واتساپ"""
    with client.session_transaction() as sess:
        sess['user_id'] = test_setup['seller_id']
        sess['role'] = 'seller'
        sess['full_name'] = 'فروشنده تست کارگاه'

    with app.app_context():
        now_j = jdatetime.datetime.now()
        uid = uuid.uuid4().hex[:6]
        order = CustomWorkshopOrder(
            order_number=f"ORD-{now_j.year}-{uid}",
            seller_id=test_setup['seller_id'],
            shop_id=test_setup['shop_id'],
            customer_name="مشتری روبیکا",
            customer_phone="09120000000",
            product_type="کابین روشویی",
            model_name="آرشام",
            dimensions_text="۶۰×۴۰",
            body_color="سفید",
            door_color="طوسی بتن",
            priority="urgent",
            status="pending",
            shamsi_date=now_j.strftime('%Y/%m/%d %H:%M'),
            shamsi_year=now_j.year,
            shamsi_month=now_j.month
        )
        db.session.add(order)
        db.session.commit()
        oid = order.id

    try:
        resp = client.get(f'/api/workshop_orders/{oid}/share_text')
        assert resp.status_code == 200
        data = json.loads(resp.data.decode('utf-8'))
        assert data['success'] is True
        assert 'حواله دستور ساخت کارگاه طهماسبی' in data['text']
        assert 'ORD-' in data['text']
        assert 'مشتری روبیکا' in data['text']
        assert 'طوسی بتن' in data['text']
    finally:
        with app.app_context():
            ord_db = db.session.get(CustomWorkshopOrder, oid)
            if ord_db:
                db.session.delete(ord_db)
                db.session.commit()
