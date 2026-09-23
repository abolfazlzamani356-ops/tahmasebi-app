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

def test_warehouse_admin_buy_price_permissions():
    with app.app_context():
        # Cleanup any previous test item
        for old_p in ProductCatalog.query.filter_by(code='WH-TEST-01').all():
            db.session.delete(old_p)
        for old_i in InventoryItem.query.filter_by(name='تست کالای فیزیکی انبار دار').all():
            db.session.delete(old_i)
        db.session.commit()

        # Setup delegated warehouse user
        user = User.query.filter_by(username='wh_admin_tester').first()
        if not user:
            user = User(username='wh_admin_tester', full_name='ادمین انبار تستی', role='seller', shop_id=1)
            user.set_password('123456')
            db.session.add(user)
            db.session.commit()
        user.can_manage_inventory = True
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['full_name'] = user.full_name
            sess['role'] = 'seller'
            sess['shop_id'] = 1
            sess['can_manage_inventory'] = True

        # 1. Delegated user views /admin/catalog:
        # Table column for buy_price is hidden, but modals have the input
        res_cat = client.get('/admin/catalog')
        assert res_cat.status_code == 200
        cat_html = res_cat.data.decode('utf-8')
        assert '<th class="p-4 text-blue-700">قیمت خرید مرجع (پایه)</th>' not in cat_html
        assert 'name="buy_price"' in cat_html
        assert 'category-pill' in cat_html

        # 2. Delegated user adds a catalog product with buy_price
        res_add = client.post('/admin/catalog/add', data={
            'name': 'تست شیرآلات انبار دار',
            'category': 'شیرآلات',
            'brand': 'آس',
            'code': 'WH-TEST-01',
            'buy_price': '3,500,000',
            'sell_price': '5,000,000',
            'description': 'تست قیمت خرید برای ادمین انبار'
        }, follow_redirects=True)
        assert res_add.status_code == 200

        added_prod = ProductCatalog.query.filter_by(code='WH-TEST-01').first()
        assert added_prod is not None
        assert added_prod.buy_price == 3500000
        assert added_prod.sell_price == 5000000

        # 3. Delegated user edits catalog product buy_price
        res_edit = client.post(f'/admin/catalog/edit/{added_prod.id}', data={
            'name': 'تست شیرآلات انبار دار ویرایش شده',
            'category': 'شیرآلات',
            'brand': 'آس',
            'code': 'WH-TEST-01',
            'buy_price': '3,800,000',
            'sell_price': '5,200,000',
            'description': 'ویرایش تست'
        }, follow_redirects=True)
        assert res_edit.status_code == 200

        db.session.refresh(added_prod)
        assert added_prod.buy_price == 3800000
        assert added_prod.sell_price == 5200000

        # 4. Delegated user adds inventory item with buy_price
        res_inv_add = client.post('/admin/inventory/add', data={
            'name': 'تست کالای فیزیکی انبار دار',
            'category': 'شیرآلات',
            'shop_id': '1',
            'stock_quantity': '10',
            'min_alert_stock': '2',
            'buy_price': '2,400,000',
            'sell_price': '3,900,000'
        }, follow_redirects=True)
        assert res_inv_add.status_code == 200

        inv_item = InventoryItem.query.filter_by(name='تست کالای فیزیکی انبار دار').first()
        assert inv_item is not None
        assert inv_item.buy_price == 2400000
        assert inv_item.sell_price == 3900000
