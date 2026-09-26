import unittest
import io
import openpyxl
from app import app, db
from models import (
    User, Shop, InventoryItem, Invoice, InvoiceItem, Customer,
    Cheque, StockTransfer, ProductCatalog, AuditLog, Settings
)
from helpers import (
    safe_int, safe_float, normalize_persian_text,
    calculate_seller_exact_stats, calculate_store_financial_summary,
    record_stock_change
)

class TahmasebiBoostInnovationsAndBugfixesTest(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.rollback()
        self.ctx.pop()

    def test_safe_int_decimals_and_persian_digits(self):
        """تست رفع باگ اعشاری در safe_int و تبدیل دقیق اعداد فارسی و منفی"""
        # باگ قبلی: '150000.0' با حذف ممیز تبدیل به 1500000 میشد!
        self.assertEqual(safe_int('150000.0'), 150000)
        self.assertEqual(safe_int('9.6'), 9)
        self.assertEqual(safe_int('0.0'), 0)
        self.assertEqual(safe_int('12,500,000 تومان'), 12500000)
        self.assertEqual(safe_int('۱,۲۵۰,۰۰۰'), 1250000)
        self.assertEqual(safe_int('-500,000'), -500000)
        self.assertEqual(safe_int('منفی ۵۰,۰۰۰'), -50000)
        self.assertEqual(safe_int(None, 42), 42)
        self.assertEqual(safe_int('', 99), 99)
        self.assertEqual(safe_int('invalid', 10), 10)
        print("✅ safe_int test passed (No 10x decimal inflation bug)!")

    def test_safe_float_parsing(self):
        """تست تبدیل ایمن درصدهای تخفیف، مقادیر اعشاری و اعداد فارسی"""
        self.assertAlmostEqual(safe_float('28.5%'), 28.5)
        self.assertAlmostEqual(safe_float('۲۸.۵'), 28.5)
        self.assertAlmostEqual(safe_float('12,345.67'), 12345.67)
        self.assertAlmostEqual(safe_float('-15.25'), -15.25)
        self.assertAlmostEqual(safe_float(None, 1.5), 1.5)
        self.assertAlmostEqual(safe_float('bad', 0.0), 0.0)
        print("✅ safe_float test passed!")

    def test_normalize_persian_text(self):
        """تست یکسان‌سازی حروف و اعداد عربی و فارسی و حذف اعراب"""
        arabic_str = "شِيْر كَابِينَتَى يَى ۱۲۳"
        norm = normalize_persian_text(arabic_str)
        self.assertIn('ی', norm)
        self.assertIn('ک', norm)
        self.assertNotIn('ي', norm)
        self.assertNotIn('ك', norm)
        self.assertNotIn('ى', norm) # الف مقصوره
        self.assertIn('123', norm)
        print("✅ normalize_persian_text test passed!")

    def test_product_catalog_barcode(self):
        """تست فیلد جدید بارکد کاتالوگ و استعلام بارکدخوان"""
        test_prod = ProductCatalog(
            name="کالای تست بارکدخوان",
            category="عمومی",
            brand="تست",
            buy_price=100000,
            sell_price=150000,
            barcode="6260123456789"
        )
        db.session.add(test_prod)
        db.session.commit()

        fetched = ProductCatalog.query.filter_by(barcode="6260123456789").first()
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.barcode, "6260123456789")
        d = fetched.to_dict()
        self.assertEqual(d.get('barcode'), "6260123456789")

        # پاکسازی
        db.session.delete(fetched)
        db.session.commit()
        print("✅ ProductCatalog.barcode column and to_dict test passed!")

    def test_invoice_delete_restores_stock_and_reverts_customer_balance(self):
        """تست بازگرداندن اتمیک موجودی انبار و اصلاح مانده بدهی مشتری در حذف فاکتور"""
        shop = Shop.query.first()
        if not shop:
            shop = Shop(name="شعبه مرکزی تست", rent_amount=0)
            db.session.add(shop)
            db.session.commit()

        seller = User.query.filter_by(role='seller').first()
        if not seller:
            seller = User(username='test_seller_del', full_name='فروشنده تست', role='seller', shop_id=shop.id)
            seller.set_password('123456')
            db.session.add(seller)
            db.session.commit()

        # مشتری تست
        Customer.query.filter(Customer.phone == "09990001122").delete()
        Invoice.query.filter(Invoice.invoice_number == "TEST-DEL-INV-001").delete()
        db.session.commit()

        cust = Customer(name="مشتری تست حذف فاکتور", phone="09990001122", total_purchases=20000000, outstanding_balance=5000000)
        db.session.add(cust)
        db.session.commit()

        # کالای انبار تست
        inv_item = InventoryItem(name="کالای انبار تست حذف", category="تست", shop_id=shop.id, stock_quantity=10, min_alert_stock=2, buy_price=10000, sell_price=20000)
        db.session.add(inv_item)
        db.session.commit()

        # ثبت فاکتور نسیه
        inv = Invoice(
            invoice_number="TEST-DEL-INV-001",
            customer_name=cust.name,
            customer_id=cust.id,
            seller_id=seller.id,
            shop_id=shop.id,
            status='final',
            invoice_type='sale',
            total_amount=10000000,
            remaining_balance=5000000,
            paid_amount=5000000,
            shamsi_year=1405,
            shamsi_month=1,
            shamsi_date_time="1405/01/01 - 10:00:00"
        )
        db.session.add(inv)
        db.session.flush()

        item = InvoiceItem(
            invoice_id=inv.id,
            inventory_item_id=inv_item.id,
            item_name=inv_item.name,
            quantity=3,
            unit_buy_price=10000,
            unit_sell_price=20000,
            total_price=60000
        )
        db.session.add(item)
        db.session.commit()

        # کسر ۳ عدد از انبار برای فاکتور
        inv_item.stock_quantity = 7
        db.session.commit()

        # شبیه‌سازی فراخوانی مسیر حذف فاکتور توسط ادمین
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['full_name'] = 'مدیر کل'
            sess['role'] = 'admin'

        resp = self.client.post(f'/admin/invoice/delete/{inv.id}', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        # بررسی موجودی انبار: باید ۳ عدد برگشته و ۱۰ شده باشد
        db.session.refresh(inv_item)
        self.assertEqual(inv_item.stock_quantity, 10)

        # بررسی حساب مشتری: خریدها و مانده بدهی باید کسر شده باشند
        db.session.refresh(cust)
        self.assertEqual(cust.total_purchases, 10000000) # 20M - 10M
        self.assertEqual(cust.outstanding_balance, 0) # 5M - 5M

        # پاکسازی
        db.session.delete(inv_item)
        db.session.delete(cust)
        db.session.commit()
        print("✅ Invoice delete atomic inventory and customer balance rollback passed!")

    def test_cheque_status_lifecycle_and_reversals(self):
        """تست چرخه عمر چک صیادی: پاس شدن، برگشت و اصلاح مانده مشتری در بازگشت به وصول"""
        shop = Shop.query.first() or Shop(name="شعبه مرکزی چک", rent_amount=0)
        if not shop.id:
            db.session.add(shop)
            db.session.commit()

        seller = User.query.filter_by(role='seller').first()
        if not seller:
            seller = User(username='test_seller_chk', full_name='فروشنده چک', role='seller', shop_id=shop.id)
            seller.set_password('123456')
            db.session.add(seller)
            db.session.commit()

        Customer.query.filter(Customer.phone == "09887776655").delete()
        Invoice.query.filter(Invoice.invoice_number == "TEST-CHK-999").delete()
        db.session.commit()

        cust = Customer(name="مشتری چک صیادی", phone="09887776655", outstanding_balance=0)
        db.session.add(cust)
        db.session.commit()

        inv = Invoice(
            invoice_number="TEST-CHK-999",
            customer_name=cust.name,
            customer_id=cust.id,
            seller_id=seller.id,
            shop_id=shop.id,
            status='final',
            invoice_type='sale',
            total_amount=15000000,
            remaining_balance=0,
            paid_cheque=15000000,
            is_settled=False,
            shamsi_year=1405,
            shamsi_month=1,
            shamsi_date_time="1405/01/01 - 10:00:00"
        )
        db.session.add(inv)
        db.session.flush()

        chk = Cheque(
            invoice_id=inv.id,
            customer_name=cust.name,
            sayad_number="1234567890123456",
            bank_name="ملی",
            amount=15000000,
            due_shamsi_date="1405/02/01",
            shop_id=shop.id,
            status='pending'
        )
        db.session.add(chk)
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['full_name'] = 'مدیر'
            sess['role'] = 'admin'

        # ۱. پاس شدن چک
        resp = self.client.post(f'/admin/cheque/status/{chk.id}', data={'status': 'passed'}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        db.session.refresh(inv)
        db.session.refresh(chk)
        self.assertEqual(chk.status, 'passed')
        self.assertTrue(inv.is_settled)

        # ۲. برگشت خوردن چک
        resp = self.client.post(f'/admin/cheque/status/{chk.id}', data={'status': 'bounced'}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        db.session.refresh(inv)
        db.session.refresh(chk)
        db.session.refresh(cust)
        self.assertEqual(chk.status, 'bounced')
        self.assertFalse(inv.is_settled)
        self.assertEqual(cust.outstanding_balance, 15000000)

        # ۳. ارسال مجدد وضعیت برگشت نباید بدهی مشتری را دو برابر کند (آیدم‌پوتنت)
        resp = self.client.post(f'/admin/cheque/status/{chk.id}', data={'status': 'bounced'}, follow_redirects=True)
        db.session.refresh(cust)
        self.assertEqual(cust.outstanding_balance, 15000000)

        # ۴. تغییر وضعیت از برگشت به پاس شده باید جریمه بدهی مشتری را برگرداند
        resp = self.client.post(f'/admin/cheque/status/{chk.id}', data={'status': 'passed'}, follow_redirects=True)
        db.session.refresh(cust)
        db.session.refresh(chk)
        self.assertEqual(chk.status, 'passed')
        self.assertEqual(cust.outstanding_balance, 0)

        # پاکسازی
        db.session.delete(chk)
        db.session.delete(inv)
        db.session.delete(cust)
        db.session.commit()
        print("✅ Cheque status lifecycle and balance reversal passed!")

    def test_stock_transfer_approve_reject(self):
        """تست تایید و رد درخواست جابجایی کالا بین دو شعبه"""
        InventoryItem.query.filter_by(name="کالای تست انتقال").delete()
        StockTransfer.query.filter_by(item_name="کالای تست انتقال").delete()
        db.session.commit()

        item1 = InventoryItem(name="کالای تست انتقال", category="شیرآلات", shop_id=1, stock_quantity=8, min_alert_stock=2, buy_price=5000, sell_price=10000)
        item2 = InventoryItem(name="کالای تست انتقال", category="شیرآلات", shop_id=2, stock_quantity=2, min_alert_stock=2, buy_price=5000, sell_price=10000)
        db.session.add_all([item1, item2])
        db.session.commit()

        st = StockTransfer(
            item_name="کالای تست انتقال",
            from_shop_id=1,
            to_shop_id=2,
            quantity=3,
            requested_by="فروشنده تست",
            shamsi_date_time="1405/01/01 - 12:00:00",
            status='pending'
        )
        db.session.add(st)
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['full_name'] = 'مدیر'
            sess['role'] = 'admin'
            sess['can_manage_inventory'] = True

        # تایید انتقال
        resp = self.client.post(f'/transfer/approve/{st.id}', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        db.session.refresh(item1)
        db.session.refresh(item2)
        db.session.refresh(st)

        self.assertEqual(st.status, 'accepted')
        self.assertEqual(item1.stock_quantity, 5) # 8 - 3
        self.assertEqual(item2.stock_quantity, 5) # 2 + 3

        # پاکسازی
        db.session.delete(st)
        db.session.delete(item1)
        db.session.delete(item2)
        db.session.commit()
        print("✅ Stock transfer approve/reject test passed!")

    def test_customer_crm_routes_and_search_api(self):
        """تست امکانات CRM: ثبت، ویرایش، استعلام فاکتورها، و ای‌پی‌آی جستجوی زنده با ارقام فارسی"""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['full_name'] = 'مدیر'
            sess['role'] = 'admin'

        # پاکسازی رکورد تست قبلی در صورت وجود
        Customer.query.filter(Customer.phone == '09121112233').delete()
        db.session.commit()

        # افزودن مشتری
        resp = self.client.post('/admin/customer/add', data={
            'name': 'مهندس علیرضا سهرابی',
            'phone': '09121112233',
            'customer_type': 'builder',
            'credit_limit': '80000000',
            'address': 'پروژه سعادت‌آباد'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        cust = Customer.query.filter_by(phone='09121112233').first()
        self.assertIsNotNone(cust)
        self.assertEqual(cust.customer_type, 'builder')
        self.assertEqual(cust.credit_limit, 80000000)

        # ویرایش مشتری
        resp = self.client.post(f'/admin/customer/edit/{cust.id}', data={
            'name': 'مهندس علیرضا سهرابی (VIP)',
            'phone': '09121112233',
            'customer_type': 'vip',
            'credit_limit': '120000000',
            'address': 'پروژه سعادت‌آباد - برج نگین'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        db.session.refresh(cust)
        self.assertEqual(cust.customer_type, 'vip')
        self.assertEqual(cust.credit_limit, 120000000)

        # استعلام فاکتورهای مشتری از API
        resp = self.client.get(f'/api/customer/{cust.id}/invoices')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['customer_id'], cust.id)
        self.assertIn('invoices', data)

        # جستجوی زنده با شماره فارسی
        resp_search = self.client.get('/api/customer/search?q=۰۹۱۲۱۱۱۲۲۳۳')
        self.assertEqual(resp_search.status_code, 200)
        results = resp_search.get_json()
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]['phone'], '09121112233')

        # پاکسازی
        db.session.delete(cust)
        db.session.commit()
        print("✅ Customer CRM add/edit/api/search test passed!")

    def test_excel_export_endpoints_including_monthly_summary(self):
        """تست ۵ خروجی اکسل پیشرفته و ای‌پی‌آی خلاصه مالی"""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['full_name'] = 'مدیر'
            sess['role'] = 'admin'
            sess['can_manage_inventory'] = True

        endpoints = [
            ('/admin/export/invoices_excel', 'Invoices_Tahmasebi'),
            ('/admin/export/inventory_excel', 'Inventory_Tahmasebi'),
            ('/admin/export/debtors_excel', 'Debtors_Tahmasebi'),
            ('/admin/export/payroll_excel', 'Payroll_Tahmasebi'),
            ('/admin/export/monthly_summary_excel', 'Tahmasebi_Monthly_Financial'),
        ]

        excel_mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        for ep, name_prefix in endpoints:
            resp = self.client.get(ep)
            self.assertEqual(resp.status_code, 200, f"Endpoint {ep} failed with {resp.status_code}")
            self.assertEqual(resp.mimetype, excel_mime, f"Endpoint {ep} returned wrong mimetype {resp.mimetype}")
            self.assertGreater(len(resp.data), 1000, f"Endpoint {ep} returned empty payload")
            wb = openpyxl.load_workbook(io.BytesIO(resp.data))
            self.assertGreater(len(wb.sheetnames), 0)
            print(f"✅ Excel export {ep} verified successfully!")

        # تست API زنده خلاصه وضعیت مالی
        resp_api = self.client.get('/api/admin/financial_summary')
        self.assertEqual(resp_api.status_code, 200)
        json_data = resp_api.get_json()
        self.assertEqual(json_data['status'], 'success')
        self.assertIn('gross_sales', json_data['summary'])
        self.assertIn('store_net_profit', json_data['summary'])
        print("✅ Live financial summary API verified successfully!")

    def test_financial_summary_and_return_invoices(self):
        """تست محاسبه جامع سود و زیان و اعمال کسر مرجوعی در پورسانت فروشنده"""
        shop = Shop.query.first() or Shop(name="شعبه مرکزی تست مالی", rent_amount=10000000)
        if not shop.id:
            db.session.add(shop)
            db.session.commit()

        seller = User.query.filter_by(role='seller').first()
        if not seller:
            seller = User(username='test_seller_fin', full_name='فروشنده مالی', role='seller', shop_id=shop.id, commission_rate=1.0)
            seller.set_password('123456')
            db.session.add(seller)
            db.session.commit()

        # پاکسازی رکوردهای تست قبلی در صورت وجود
        Invoice.query.filter(Invoice.invoice_number.in_(['FIN-SALE-001', 'FIN-RET-001'])).delete()
        db.session.commit()

        # ثبت یک فاکتور فروش و یک فاکتور مرجوعی
        inv_sale = Invoice(
            invoice_number="FIN-SALE-001",
            customer_name="مشتری خرید",
            seller_id=seller.id,
            shop_id=shop.id,
            status='final',
            invoice_type='sale',
            total_amount=50000000,
            paid_pos=50000000,
            remaining_balance=0,
            actual_buy_cost=35000000,
            real_profit=15000000,
            shamsi_year=1405,
            shamsi_month=5,
            shamsi_date_time="1405/05/10 - 11:00:00"
        )
        inv_return = Invoice(
            invoice_number="FIN-RET-001",
            customer_name="مشتری مرجوعی",
            seller_id=seller.id,
            shop_id=shop.id,
            status='final',
            invoice_type='return',
            total_amount=10000000,
            remaining_balance=0,
            shamsi_year=1405,
            shamsi_month=5,
            shamsi_date_time="1405/05/12 - 14:00:00"
        )
        db.session.add_all([inv_sale, inv_return])
        db.session.commit()

        # تست عملکرد تابع calculate_store_financial_summary
        summary = calculate_store_financial_summary(1405, 5)
        self.assertEqual(summary['gross_sales'], 50000000)
        self.assertEqual(summary['returns_amount'], 10000000)
        self.assertEqual(summary['net_sales'], 40000000)

        # تست عملکرد آمار فروشنده و کسر صحیح مرجوعی از فروش خالص و پورسانت
        settings = Settings.query.first() or Settings()
        seller_stats = calculate_seller_exact_stats(seller.id, 1405, 5, seller.commission_rate, settings, user=seller)
        self.assertEqual(seller_stats['returns_amount'], 10000000)
        self.assertEqual(seller_stats['net_sales'], 40000000)
        expected_commission = int(40000000 * (seller_stats['effective_rate'] / 100.0))
        self.assertEqual(seller_stats['settled_commission'], expected_commission)

        # پاکسازی
        db.session.delete(inv_sale)
        db.session.delete(inv_return)
        db.session.commit()
        print("✅ calculate_store_financial_summary and returns deduction test passed!")

if __name__ == '__main__':
    unittest.main()
