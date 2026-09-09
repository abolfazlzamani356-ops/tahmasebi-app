import unittest
from app import app, db
from models import User, Shop, InventoryItem, Invoice, InvoiceItem, Customer
from helpers import calculate_seller_exact_stats, parse_smart_invoice_text, get_inventory_ai_insights

class TahmasebiSystemTest(unittest.TestCase):
    def setUp(self):
        self.ctx = app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_smart_ai_parser(self):
        sample_text = "۲ عدد هود داتیس مدل 522 مخفی به آقای محمدی 09123456789 دادم کارت به کارت"
        parsed = parse_smart_invoice_text(sample_text, 1)
        self.assertTrue(parsed['success'])
        self.assertEqual(parsed['customer_phone'], '09123456789')
        self.assertEqual(parsed['payment_method'], 'card_to_card')
        print("✅ AI NLP Invoice Parser Test Passed!")

    def test_inventory_insights(self):
        insights = get_inventory_ai_insights()
        self.assertIn('total_buy_valuation', insights)
        self.assertIn('total_sell_valuation', insights)
        print("✅ Inventory AI Insights Test Passed!")

    def test_seller_stats(self):
        user = User.query.filter_by(username='zamani').first()
        self.assertIsNotNone(user)
        stats = calculate_seller_exact_stats(user.id, 1405, 6, user.commission_rate)
        self.assertIn('net_sales', stats)
        self.assertIn('settled_commission', stats)
        print("✅ Seller Commission & Payroll Stats Test Passed!")

if __name__ == '__main__':
    unittest.main()
