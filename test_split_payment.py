import unittest
from app import app, db
from models import User, Shop, InventoryItem, Invoice, InvoiceItem, Customer, Cheque
from helpers import calculate_seller_exact_stats, parse_smart_invoice_text, get_inventory_ai_insights

class TahmasebiComprehensiveTest(unittest.TestCase):
    def setUp(self):
        self.ctx = app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_multi_payment_invoice(self):
        seller = User.query.filter_by(role='seller').first()
        shop = Shop.query.first()
        
        # ثبت فاکتور نمونه با پرداخت ترکیبی
        test_inv = Invoice(
            invoice_number='TEST-SPLIT-999',
            customer_name='آقای تست ترکیبی',
            customer_phone='09129998877',
            status='final',
            invoice_type='sale',
            total_amount=40000000,
            paid_pos=2000000,
            paid_card=4000000,
            paid_cash=5000000,
            paid_cheque=20000000,
            remaining_balance=9000000,
            paid_amount=1100000, # 2 + 4 + 5
            is_settled=False,
            seller_id=seller.id,
            shamsi_year=1405,
            shamsi_month=6,
            shamsi_date_time='1405/06/10 - 12:00:00',
            shop_id=shop.id
        )
        db.session.add(test_inv)
        db.session.commit()
        
        fetched = Invoice.query.filter_by(invoice_number='TEST-SPLIT-999').first()
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.paid_pos, 2000000)
        self.assertEqual(fetched.paid_card, 4000000)
        self.assertEqual(fetched.paid_cash, 5000000)
        self.assertEqual(fetched.paid_cheque, 20000000)
        self.assertEqual(fetched.remaining_balance, 9000000)
        
        # پاکسازی رکورد تست
        db.session.delete(fetched)
        db.session.commit()
        print("✅ Multi-Payment (Split Payment) Comprehensive Test Passed Successfully!")

    def test_invoice_submission_robustness(self):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = 6
            sess['full_name'] = 'ابوالفضل زمانی'
            sess['role'] = 'seller'
            sess['shop_id'] = 1

        # ۱. تست ثبت فاکتور با ارقام کامادار و فارسی
        resp1 = client.post('/invoice/add', data={
            'doc_status': 'final',
            'customer_name': 'خریدار تست استحکام',
            'customer_phone': '09123334455',
            'invoice_number': 'TEST-ROBUST-1',
            'total_amount': '۲,۰۰۰,۰۰۰',
            'paid_pos': '۱,۰۰۰,۰۰۰',
            'paid_cash': '۱,۰۰۰,۰۰۰',
            'item_quantity[]': ['۲'],
            'item_price[]': ['۱,۰۰۰,۰۰۰']
        }, follow_redirects=False)
        self.assertEqual(resp1.status_code, 302)

        # ۲. تست شماره فاکتور تکراری - نباید خطای ۵۰۰ یا لاگین بدهد
        resp2 = client.post('/invoice/add', data={
            'doc_status': 'final',
            'customer_name': 'خریدار تست تکراری',
            'customer_phone': '09123334455',
            'invoice_number': 'TEST-ROBUST-1',
            'total_amount': '۲,۰۰۰,۰۰۰',
            'paid_pos': '۲,۰۰۰,۰۰۰'
        }, follow_redirects=True)
        self.assertEqual(resp2.status_code, 200)
        content2 = resp2.get_data(as_text=True)
        self.assertNotIn('ورود به سامانه', content2)
        self.assertIn('قبلاً در سامانه ثبت شده است', content2)

        # ۳. تست فاکتور با فیلد خالی - نباید خطای ۵۰۰ یا لاگین بدهد
        resp3 = client.post('/invoice/add', data={
            'doc_status': 'final',
            'customer_name': 'خریدار تست خالی',
            'customer_phone': '09123334455',
            'invoice_number': 'TEST-ROBUST-2',
            'total_amount': ''
        }, follow_redirects=True)
        self.assertEqual(resp3.status_code, 200)
        content3 = resp3.get_data(as_text=True)
        self.assertNotIn('ورود به سامانه', content3)
        self.assertIn('نمی‌تواند صفر یا خالی باشد', content3)

        # پاکسازی دیتابیس
        inv = Invoice.query.filter_by(invoice_number='TEST-ROBUST-1').first()
        if inv:
            InvoiceItem.query.filter_by(invoice_id=inv.id).delete()
            db.session.delete(inv)
            db.session.commit()
        print("✅ Invoice Submission Robustness & Anti-Logout Test Passed Successfully!")

if __name__ == '__main__':
    unittest.main()
