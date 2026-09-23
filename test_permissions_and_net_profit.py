import pytest
from app import app, db
from models import User, Shop, ProductCatalog, InventoryItem, Settings, Invoice
import jdatetime

def test_inventory_delegation_and_net_profit():
    with app.app_context():
        # 1. Verify logistics staff exist
        khedmat1 = User.query.filter_by(username='khedmat1').first()
        khedmat2 = User.query.filter_by(username='khedmat2').first()
        assert khedmat1 is not None, "khedmat1 must exist"
        assert khedmat2 is not None, "khedmat2 must exist"
        assert khedmat1.role == 'logistics'
        assert khedmat1.commission_rate == 0.0

        # 2. Test warehouse delegation on seller
        seller = User.query.filter_by(role='seller').first()
        if not seller:
            seller = User(username='test_seller_inv', full_name='فروشنده تستی', role='seller', shop_id=1, commission_rate=1.0)
            seller.set_password('123456')
            db.session.add(seller)
            db.session.commit()

        seller.can_manage_inventory = True
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = seller.id
            sess['full_name'] = seller.full_name
            sess['role'] = 'seller'
            sess['shop_id'] = seller.shop_id
            sess['can_manage_inventory'] = True

        # Seller with delegation cannot access /admin dashboard (forbidden / redirects)
        res_admin = client.get('/admin')
        assert res_admin.status_code == 302, "Delegated seller must be redirected from admin panel"

        # Delegated seller CAN access /inventory
        res_inv = client.get('/inventory')
        assert res_inv.status_code == 200, "Delegated seller can access inventory"

        # Delegated seller CAN access /admin/catalog
        res_cat = client.get('/admin/catalog')
        assert res_cat.status_code == 200, "Delegated seller can access catalog"

        # Verify buy price is NOT exposed to non-admin
        html_content = res_inv.data.decode('utf-8')
        assert "قیمت خرید برای ما (پایه)" not in html_content, "Buy price header must NOT appear for seller"
        assert "سود پایه هر عدد" not in html_content, "Profit margin must NOT appear for seller"

        # 3. Test shop rent update by admin
        admin = User.query.filter_by(role='admin').first()
        with client.session_transaction() as sess:
            sess['user_id'] = admin.id
            sess['full_name'] = admin.full_name
            sess['role'] = 'admin'
            sess['shop_id'] = 1

        res_rent = client.post('/admin/shops/rent/update', data={
            'rent_shop_1': '15,000,000',
            'rent_shop_2': '10,000,000'
        }, follow_redirects=True)
        assert res_rent.status_code == 200

        db.session.expire_all()
        shop1 = Shop.query.get(1)
        shop2 = Shop.query.get(2)
        assert shop1.rent_amount == 15000000
        assert shop2.rent_amount == 10000000

        # 4. Test admin dashboard renders with rent and net profit
        now_j = jdatetime.datetime.now()
        res_dash = client.get(f'/admin?month={now_j.month}')
        assert res_dash.status_code == 200
        dash_html = res_dash.data.decode('utf-8')
        assert "سود خالص نهایی" in dash_html
        assert "اجاره شعب" in dash_html
        assert "رضا مرادی" in dash_html
