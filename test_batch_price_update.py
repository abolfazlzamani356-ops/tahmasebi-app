import pytest
from app import app, db
from models import User, ProductCatalog, InventoryItem

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        yield client

def test_batch_price_update_brand(client):
    with app.app_context():
        # دریافت ادمین
        admin = User.query.filter_by(role='admin').first()
        
        # ثبت کالای تستی برای برند آس
        test_item = ProductCatalog.query.filter_by(name="شیر روشویی تست آس").first()
        if not test_item:
            test_item = ProductCatalog(
                name="شیر روشویی تست آس",
                category="شیرآلات",
                brand="آس",
                sell_price=1000000,
                buy_price=800000
            )
            db.session.add(test_item)
            db.session.commit()
        else:
            test_item.sell_price = 1000000
            test_item.buy_price = 800000
            db.session.commit()

        # ثبت موجودی انبار متناظر
        inv_item = InventoryItem.query.filter_by(name=test_item.name).first()
        if not inv_item:
            inv_item = InventoryItem(
                name=test_item.name,
                category="شیرآلات",
                brand="آس",
                shop_id=1,
                stock_quantity=5,
                sell_price=1000000,
                buy_price=800000
            )
            db.session.add(inv_item)
            db.session.commit()

        # شبیه‌سازی لاگین ادمین
        with client.session_transaction() as sess:
            sess['user_id'] = admin.id
            sess['role'] = 'admin'
            sess['full_name'] = admin.full_name
            sess['tenant_id'] = 1

        # اعمال آپدیت تخفیف ۲۸٪ روی برند آس
        res = client.post('/admin/catalog/batch_price_update', data={
            'target_brand': 'آس',
            'target_category': 'all',
            'update_type': 'buy_discount',
            'discount_percent': '28',
            'sync_inventory': '1'
        }, follow_redirects=True)
        assert res.status_code == 200

        # بررسی نتایج: قیمت خرید باید ۱،۰۰۰،۰۰۰ * (۱ - ۰.۲۸) = ۷۲۰،۰۰۰ تومان شده باشد
        db.session.refresh(test_item)
        assert test_item.buy_price == 720000
        assert test_item.sell_price == 1000000

        # بررسی همگام‌سازی با انبار
        db.session.refresh(inv_item)
        assert inv_item.buy_price == 720000

        # پاکسازی رکورد تست
        db.session.delete(inv_item)
        db.session.delete(test_item)
        db.session.commit()
