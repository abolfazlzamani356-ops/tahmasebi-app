import unittest
from app import app, db
from models import User, Shop, ProductCatalog, InventoryItem, Invoice, InvoiceItem, StockLog

class CatalogInventorySyncTest(unittest.TestCase):
    def setUp(self):
        self.ctx = app.app_context()
        self.ctx.push()
        self.client = app.test_client()

    def tearDown(self):
        self.ctx.pop()

    def test_quick_stock_api_and_auto_invoice_deduction(self):
        admin = User.query.filter_by(role='admin').first()
        self.assertIsNotNone(admin)

        shop1 = db.session.get(Shop, 1)
        if not shop1:
            shop1 = Shop(id=1, name='شعبه ۱ مرکزی')
            db.session.add(shop1)
            db.session.commit()

        test_cat_name = 'سینک تستی انبارگردانی مدل ویژه X'
        
        # پاکسازی موارد قبلی
        InventoryItem.query.filter_by(name=test_cat_name).delete()
        ProductCatalog.query.filter_by(name=test_cat_name).delete()
        Invoice.query.filter(Invoice.invoice_number.like('TEST-INV-SYNC-%')).delete()
        db.session.commit()

        cat_item = ProductCatalog(
            name=test_cat_name,
            category='سینک',
            brand='ایلیا استیل (Ilia Steel)',
            buy_price=3000000,
            sell_price=4500000
        )
        db.session.add(cat_item)
        db.session.commit()

        # لاگین با ادمین
        with self.client.session_transaction() as sess:
            sess['user_id'] = admin.id
            sess['role'] = 'admin'
            sess['full_name'] = 'محمد طهماسبی'
            sess['shop_id'] = 1

        # ۱. ثبت موجودی ۵ عدد در شعبه ۱
        res = self.client.post('/api/inventory/quick_stock', json={
            'catalog_id': cat_item.id,
            'name': test_cat_name,
            'shop_id': 1,
            'stock_quantity': 5,
            'min_alert_stock': 2
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['stock_quantity'], 5)
        self.assertEqual(data['status_badge'], 'available')

        # ۲. بررسی موجودی دیتابیس در شعبه ۱
        inv1 = InventoryItem.query.filter_by(name=test_cat_name, shop_id=1).first()
        self.assertIsNotNone(inv1)
        self.assertEqual(inv1.stock_quantity, 5)

        # ۳. صدور فاکتور در شعبه ۱ و کسر خودکار ۲ عدد
        import time
        inv_num = f'TEST-INV-SYNC-{int(time.time())}'
        res_inv = self.client.post('/invoice/add', data={
            'invoice_number': inv_num,
            'customer_name': 'خریدار سینک',
            'doc_status': 'final',
            'target_shop_id': '1',
            'item_inventory_id[]': [''],
            'item_custom_name[]': [test_cat_name],
            'item_category[]': ['سینک'],
            'item_quantity[]': ['2'],
            'item_price[]': ['4,500,000'],
            'total_amount': '9,000,000',
            'paid_pos': '9,000,000'
        }, follow_redirects=True)
        self.assertEqual(res_inv.status_code, 200)

        # ۴. موجودی باید ۳ شده باشد (۵ - ۲ = ۳)
        db.session.expire_all()
        inv1_after = InventoryItem.query.filter_by(name=test_cat_name, shop_id=1).first()
        self.assertEqual(inv1_after.stock_quantity, 3)

        # ۵. تست ذخیره دسته‌جمعی (Batch)
        res_batch = self.client.post('/api/inventory/batch_quick_stock', json={
            'shop_id': 1,
            'items': [
                {
                    'catalog_id': cat_item.id,
                    'name': test_cat_name,
                    'stock_quantity': 8,
                    'min_alert_stock': 2
                }
            ]
        })
        self.assertEqual(res_batch.status_code, 200)
        b_data = res_batch.get_json()
        self.assertTrue(b_data['success'])
        self.assertEqual(b_data['updated_count'], 1)

        db.session.expire_all()
        inv1_batch = InventoryItem.query.filter_by(name=test_cat_name, shop_id=1).first()
        self.assertEqual(inv1_batch.stock_quantity, 8)

    def test_catalog_add_and_edit_with_stock(self):
        admin = User.query.filter_by(role='admin').first()
        with self.client.session_transaction() as sess:
            sess['user_id'] = admin.id
            sess['role'] = 'admin'
            sess['full_name'] = 'محمد طهماسبی'
            sess['shop_id'] = 1

        test_prod_name = 'هود تستی ورودی بار کارخانه طهماسبی'
        InventoryItem.query.filter_by(name=test_prod_name).delete()
        ProductCatalog.query.filter_by(name=test_prod_name).delete()
        db.session.commit()

        # ۱. افزودن کالا همراه با موجودی اولیه شعب ۱ و ۲
        res_add = self.client.post('/admin/catalog/add', data={
            'name': test_prod_name,
            'category': 'هود',
            'brand': 'داتیس (Datees)',
            'buy_price': '2,000,000',
            'sell_price': '3,500,000',
            'code': 'DT-TEST-HOOD',
            'stock_quantity_1': '4',
            'stock_quantity_2': '6'
        }, follow_redirects=True)
        self.assertEqual(res_add.status_code, 200)

        cat_prod = ProductCatalog.query.filter_by(name=test_prod_name).first()
        self.assertIsNotNone(cat_prod)

        db.session.expire_all()
        inv_s1 = InventoryItem.query.filter_by(name=test_prod_name, shop_id=1).first()
        inv_s2 = InventoryItem.query.filter_by(name=test_prod_name, shop_id=2).first()
        self.assertIsNotNone(inv_s1)
        self.assertEqual(inv_s1.stock_quantity, 4)
        self.assertIsNotNone(inv_s2)
        self.assertEqual(inv_s2.stock_quantity, 6)

        # ۲. ویرایش و اصلاح موجودی کالا از طریق مودال ویرایش کاتالوگ
        res_edit = self.client.post(f'/admin/catalog/edit/{cat_prod.id}', data={
            'name': test_prod_name,
            'category': 'هود',
            'brand': 'داتیس (Datees)',
            'buy_price': '2,100,000',
            'sell_price': '3,600,000',
            'code': 'DT-TEST-HOOD',
            'stock_quantity_1': '10',  # افزایش از ۴ به ۱۰
            'stock_quantity_2': '2'    # کاهش از ۶ به ۲ (اصلاح اشتباه)
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)

        db.session.expire_all()
        inv_s1_after = InventoryItem.query.filter_by(name=test_prod_name, shop_id=1).first()
        inv_s2_after = InventoryItem.query.filter_by(name=test_prod_name, shop_id=2).first()
        self.assertEqual(inv_s1_after.stock_quantity, 10)
        self.assertEqual(inv_s2_after.stock_quantity, 2)

        # بررسی لاگ انبار
        logs = StockLog.query.filter_by(inventory_item_id=inv_s1.id).all()
        self.assertTrue(len(logs) >= 2)

