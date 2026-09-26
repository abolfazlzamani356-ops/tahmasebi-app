import unittest
from unittest.mock import patch, MagicMock
from app import app, db
from models import User, Shop, Invoice, InvoiceItem, Settings, Customer
from helpers import send_invoice_sms

class TestSMSAndPublicInvoice(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.rollback()
        self.ctx.pop()

    def test_settings_sms_config_defaults(self):
        """تست پیش‌فرض‌های اتصال پنل پیامکی SMS.ir و کلید API"""
        settings = Settings.query.first() or Settings()
        self.assertIsNotNone(settings.sms_api_key)
        self.assertEqual(settings.sms_template_id, '355952')
        self.assertTrue(settings.sms_enabled)

    @patch('requests.post')
    def test_send_invoice_sms_success(self, mock_post):
        """تست ارسال موفق پیامک گارانتی با پارامترهای تاییدشده SMS.ir"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": 1,
            "message": "با موفقیت ارسال شد",
            "data": {"messageId": 12345678}
        }
        mock_post.return_value = mock_response

        shop = Shop.query.first()
        seller = User.query.filter_by(role='seller').first()

        inv = Invoice(
            invoice_number="SMS-TEST-9999",
            customer_name="علیرضا رضایی",
            customer_phone="09121234567",
            seller_id=seller.id if seller else 1,
            shop_id=shop.id if shop else 1,
            status='final',
            invoice_type='sale',
            total_amount=15000000,
            shamsi_year=1405,
            shamsi_month=7,
            shamsi_date_time="1405/07/04 - 11:30:00"
        )
        db.session.add(inv)
        db.session.commit()

        success, msg = send_invoice_sms(inv)
        self.assertTrue(success)
        self.assertIn("با موفقیت به 09121234567 ارسال شد", msg)
        self.assertTrue(inv.sms_sent)
        self.assertIsNotNone(inv.sms_sent_at)

        # بررسی ساختار درخواست ارسالی به وب‌سرویس SMS.ir
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://api.sms.ir/v1/send/verify")
        payload = kwargs['json']
        self.assertEqual(payload['mobile'], "09121234567")
        self.assertEqual(payload['templateId'], 355952)
        param_names = [p['name'] for p in payload['parameters']]
        self.assertIn('NAME', param_names)
        self.assertIn('INVOICE', param_names)
        self.assertIn('LINK', param_names)

        # پاکسازی
        db.session.delete(inv)
        db.session.commit()

    def test_public_invoice_view_route(self):
        """تست مسیر مشاهده و چاپ عمومی فاکتور مشتری بدون نیاز به احراز هویت"""
        shop = Shop.query.first()
        seller = User.query.filter_by(role='seller').first()

        inv = Invoice(
            invoice_number="PUB-VIEW-TEST-123",
            customer_name="خریدار محترم آنلاین",
            customer_phone="09391206006",
            seller_id=seller.id if seller else 1,
            shop_id=shop.id if shop else 1,
            status='final',
            invoice_type='sale',
            total_amount=25000000,
            shamsi_year=1405,
            shamsi_month=7,
            shamsi_date_time="1405/07/04 - 11:40:00"
        )
        db.session.add(inv)
        db.session.commit()

        # بدون لاگین فراخوانی شود
        resp = self.client.get(f'/invoice/view/{inv.invoice_number}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('PUB-VIEW-TEST-123', resp.get_data(as_text=True))
        self.assertIn('خریدار محترم آنلاین', resp.get_data(as_text=True))
        self.assertIn('krdcabin.com', resp.get_data(as_text=True))

        # پاکسازی
        db.session.delete(inv)
        db.session.commit()

if __name__ == '__main__':
    unittest.main()
