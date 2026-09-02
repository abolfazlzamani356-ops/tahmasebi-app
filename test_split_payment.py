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

if __name__ == '__main__':
    unittest.main()
