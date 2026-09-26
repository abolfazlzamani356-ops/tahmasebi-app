import unittest
import time
from app import app, db
from models import User, Shop, Invoice, Settings
from helpers import calculate_seller_exact_stats

class TestPartnershipAndZeroCommission(unittest.TestCase):
    def setUp(self):
        self.ctx = app.app_context()
        self.ctx.push()
        self.client = app.test_client()

    def tearDown(self):
        self.ctx.pop()

    def test_zero_commission_staff_lifecycle(self):
        admin = User.query.filter_by(role='admin').first()
        with self.client.session_transaction() as sess:
            sess['user_id'] = admin.id
            sess['role'] = 'admin'
            sess['full_name'] = admin.full_name

        uname = f"zc_staff_{int(time.time())}"
        resp = self.client.post('/admin/user/add', data={
            'username': uname,
            'full_name': 'پرسنل خدمات بدون پورسانت',
            'password': 'password123',
            'role': 'seller',
            'shop_id': 1,
            'base_salary': '18,000,000',
            'commission_rate': '0.0'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        user = User.query.filter_by(username=uname).first()
        self.assertIsNotNone(user)
        self.assertEqual(user.commission_rate, 0.0)
        self.assertEqual(user.base_salary, 18000000)

        # Edit commission to 0.0 explicitly
        user.commission_rate = 2.0
        db.session.commit()
        resp_edit = self.client.post(f'/admin/user/edit/{user.id}', data={
            'full_name': user.full_name,
            'username': user.username,
            'commission_rate': '0.0',
            'base_salary': '19,000,000',
            'shop_id': 1,
            'role': 'seller'
        }, follow_redirects=True)
        self.assertEqual(resp_edit.status_code, 200)
        db.session.refresh(user)
        self.assertEqual(user.commission_rate, 0.0)

        # Update commission via quick route to 0
        user.commission_rate = 1.0
        db.session.commit()
        resp_comm = self.client.post(f'/admin/commission/{user.id}', data={
            'month': 7,
            'commission_rate': '0'
        }, follow_redirects=True)
        self.assertEqual(resp_comm.status_code, 200)
        db.session.refresh(user)
        self.assertEqual(user.commission_rate, 0.0)

        # Calculate stats for 0% commission staff: must be exactly 0
        stats = calculate_seller_exact_stats(user.id, 1405, 7, user.commission_rate)
        self.assertEqual(stats['effective_rate'], 0.0)
        self.assertEqual(stats['commission_amount'], 0)
        self.assertEqual(stats['settled_commission'], 0)

    def test_invoice_partnership_and_single_sale(self):
        seller1 = User.query.filter_by(role='seller').first()
        seller2 = User.query.filter(User.role == 'seller', User.id != seller1.id).first()

        with self.client.session_transaction() as sess:
            sess['user_id'] = seller1.id
            sess['role'] = 'seller'
            sess['full_name'] = seller1.full_name
            sess['shop_id'] = seller1.shop_id or 1

        inv_num = f"INV-TEST-{int(time.time())}"
        inv = Invoice(
            invoice_number=inv_num,
            customer_name='مشتری تست شراکت',
            customer_phone='09121112233',
            seller_id=seller1.id,
            second_seller_id=seller2.id if seller2 else None,
            split_ratio=50,
            status='final',
            invoice_type='sale',
            total_amount=10000000,
            paid_amount=10000000,
            paid_pos=10000000,
            remaining_balance=0,
            is_settled=True,
            shop_id=seller1.shop_id or 1,
            shamsi_year=1405,
            shamsi_month=7,
            shamsi_day=4,
            shamsi_date_time='1405/07/04 - 12:00:00'
        )
        db.session.add(inv)
        db.session.commit()

        # 1. Edit to single sale: must set second_seller_id=None and split_ratio=100
        resp = self.client.post(f'/invoice/edit/{inv.id}', data={
            'invoice_type': 'sale',
            'status': 'final',
            'customer_name': 'مشتری تست تکی',
            'customer_phone': '09121112233',
            'second_seller_id': 'none',
            'partner_share': '0',
            'split_ratio': '100',
            'paid_pos': '10,000,000',
            'total_amount': '10,000,000'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        db.session.refresh(inv)
        self.assertIsNone(inv.second_seller_id)
        self.assertEqual(inv.split_ratio, 100)

        # 2. Edit to joint sale with 35% to partner (primary gets 65%)
        if seller2:
            resp_joint = self.client.post(f'/invoice/edit/{inv.id}', data={
                'invoice_type': 'sale',
                'status': 'final',
                'customer_name': 'مشتری تست شریک',
                'customer_phone': '09121112233',
                'second_seller_id': str(seller2.id),
                'partner_share': '35',
                'paid_pos': '10,000,000',
                'total_amount': '10,000,000'
            }, follow_redirects=True)
            self.assertEqual(resp_joint.status_code, 200)
            db.session.refresh(inv)
            self.assertEqual(inv.second_seller_id, seller2.id)
            self.assertEqual(inv.split_ratio, 65)
