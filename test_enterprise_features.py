import pytest
from app import app, db
from models import User, Settings, Shop, Customer, Invoice, Cheque
from werkzeug.security import generate_password_hash

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        with app.app_context():
            # ensure admin user exists
            admin = User.query.filter_by(username="test_admin_enterprise").first()
            if not admin:
                admin = User(
                    username="test_admin_enterprise",
                    password_hash=generate_password_hash("admin123"),
                    full_name="مدیر ارشد تست",
                    role="admin"
                )
                db.session.add(admin)
                db.session.commit()
        yield client

def login_as_admin(client):
    with client.session_transaction() as sess:
        admin = User.query.filter_by(username="test_admin_enterprise").first()
        sess['user_id'] = admin.id
        sess['role'] = 'admin'
        sess['full_name'] = admin.full_name
        sess['username'] = admin.username

def test_settings_and_branding_update(client):
    with app.app_context():
        login_as_admin(client)
        
        # Test GET settings
        res = client.get('/admin/settings')
        assert res.status_code == 200
        assert "تنظیمات جامع فروشگاه" in res.data.decode('utf-8')
        
        # Test POST update settings
        post_data = {
            'store_name': 'مجموعه تخصصی طهماسبی پرو',
            'store_slogan': 'پیشرو در صنعت شیرآلات و لوازم بهداشتی لوکس',
            'store_phone': '021-88889999',
            'store_address': 'تهران، خیابان بنی هاشم، برج طهماسبی',
            'store_instagram': 'tahmasebi_luxury',
            'store_website': 'https://tahmasebi.ir',
            'default_invoice_prefix': 'THM-PRO-',
            'invoice_footer_note': 'اجناس تحویل شده به مدت ۴۸ ساعت دارای مهلت تست است.',
            'store_warranty_text': 'ضمانت ۵ ساله اصالت کالا',
            'tier1_min': '50000000',
            'tier1_bonus': '0.3',
            'tier2_min': '100000000',
            'tier2_bonus': '0.6',
            'sms_api_key': 'test_mock_api_key',
            'sms_template_id': '355952',
            'sms_enabled': 'on'
        }
        res_post = client.post('/admin/settings', data=post_data, follow_redirects=True)
        assert res_post.status_code == 200
        
        # Verify in DB
        s = Settings.query.first()
        assert s.store_name == 'مجموعه تخصصی طهماسبی پرو'
        assert s.store_slogan == 'پیشرو در صنعت شیرآلات و لوازم بهداشتی لوکس'
        assert s.store_phone == '021-88889999'
        assert s.store_instagram == 'tahmasebi_luxury'
        assert s.default_invoice_prefix == 'THM-PRO-'
        assert s.sms_enabled is True

def test_cheques_hub_and_customer_statement(client):
    with app.app_context():
        login_as_admin(client)
        
        # Create or fetch test customer
        cust = Customer.query.filter((Customer.name == "حاج حسن طهماسبی") | (Customer.phone == "09121112233")).first()
        if not cust:
            cust = Customer(
                name="حاج حسن طهماسبی",
                phone="09121112233",
                address="خیابان شیراز جنوبی",
                outstanding_balance=15000000
            )
            db.session.add(cust)
            db.session.commit()
            
        # Clean up any existing test cheque
        old_chq = Cheque.query.filter_by(sayad_number='1234567890123456').first()
        if old_chq:
            db.session.delete(old_chq)
            db.session.commit()

        # Add a cheque via route
        cheque_data = {
            'sayad_number': '1234567890123456',
            'bank_name': 'بانک ملت شعبه مرکزی',
            'amount': '15,000,000',
            'due_shamsi_date': '1405/08/15',
            'customer_name': cust.name,
            'customer_phone': cust.phone,
            'payee_name': 'فروشگاه طهماسبی',
            'notes': 'چک بابت فاکتور خرید شیرآلات لوکس'
        }
        res_chq = client.post('/admin/cheque/add', data=cheque_data, follow_redirects=True)
        assert res_chq.status_code == 200
        
        chq = Cheque.query.filter_by(sayad_number='1234567890123456').first()
        assert chq is not None
        assert chq.amount == 15000000
        assert chq.status == 'pending'
        
        # Test cheques hub view
        res_hub = client.get('/admin/cheques')
        assert res_hub.status_code == 200
        html = res_hub.data.decode('utf-8')
        assert "1234567890123456" in html
        assert cust.name in html
        
        # Test customer statement route
        res_statement = client.get(f'/admin/customer/statement/{cust.id}')
        assert res_statement.status_code == 200
        st_html = res_statement.data.decode('utf-8')
        assert "صورتحساب مالی و کاردکس" in st_html
        assert cust.name in st_html
        assert "1234567890123456" in st_html

def test_higher_and_custom_unit_price_without_auto_discount(client):
    """تست ثبت فاکتور با قیمت بالاتر از کاتالوگ و عدم تولید درصد تخفیف ساختگی"""
    with app.app_context():
        login_as_admin(client)
        
        # ۱. فاکتور با قیمت بالاتر از کاتالوگ (مثلاً ۵,۰۰۰,۰۰۰ به جای ۴,۷۶۵,۰۰۰)
        payload_higher = {
            'customer_name': 'مشتری قیمت بالاتر',
            'customer_phone': '09129990011',
            'status': 'final',
            'invoice_type': 'sale',
            'total_amount': '5,000,000',
            'paid_pos': '5,000,000',
            'paid_card': '0',
            'paid_cash': '0',
            'remaining_balance': '0',
            'item_inventory_id[]': [''],
            'item_custom_name[]': ['آینه باکس لوکس طهماسبی'],
            'item_category[]': ['روشویی'],
            'item_quantity[]': ['1'],
            'item_original_price[]': ['5000000'],
            'item_discount_percent[]': [''],
            'item_price[]': ['5000000'],
            'item_buy_price[]': ['']
        }
        res1 = client.post('/invoice/add', data=payload_higher, follow_redirects=True)
        assert res1.status_code == 200
        
        inv1 = Invoice.query.filter_by(customer_name='مشتری قیمت بالاتر').order_by(Invoice.id.desc()).first()
        assert inv1 is not None
        assert inv1.total_amount == 5000000
        assert inv1.discount_amount == 0
        assert len(inv1.items) == 1
        assert inv1.items[0].unit_sell_price == 5000000
        assert inv1.items[0].total_price == 5000000
        assert inv1.items[0].discount == 0

        # ۲. فاکتور با قیمت دلخواه پایین‌تر توافقی بدون درصد تخفیف (مثلاً ۴,۲۰۰,۰۰۰)
        payload_custom = {
            'customer_name': 'مشتری قیمت توافقی دستی',
            'customer_phone': '09129990022',
            'status': 'final',
            'invoice_type': 'sale',
            'total_amount': '4,200,000',
            'paid_pos': '4,200,000',
            'paid_card': '0',
            'paid_cash': '0',
            'remaining_balance': '0',
            'item_inventory_id[]': [''],
            'item_custom_name[]': ['آینه باکس طرح دار'],
            'item_category[]': ['روشویی'],
            'item_quantity[]': ['1'],
            'item_original_price[]': ['4200000'],
            'item_discount_percent[]': [''],
            'item_price[]': ['4200000'],
            'item_buy_price[]': ['']
        }
        res2 = client.post('/invoice/add', data=payload_custom, follow_redirects=True)
        assert res2.status_code == 200
        
        inv2 = Invoice.query.filter_by(customer_name='مشتری قیمت توافقی دستی').order_by(Invoice.id.desc()).first()
        assert inv2 is not None
        assert inv2.total_amount == 4200000
        assert inv2.discount_amount == 0
        assert len(inv2.items) == 1
        assert inv2.items[0].unit_sell_price == 4200000
        assert inv2.items[0].total_price == 4200000
        assert inv2.items[0].discount == 0
