import pytest
from app import app, db
from models import User, Shop, Invoice, InvoiceItem, ProductCatalog, Settings
from helpers import calculate_seller_exact_stats
import jdatetime

def test_admin_invoice_and_dashboard_stats():
    with app.app_context():
        # Setup test data
        admin = User.query.filter_by(role='admin').first()
        if not admin:
            admin = User(username='admin', full_name='محمد طهماسبی', role='admin', shop_id=1, commission_rate=0.0)
            admin.set_password('admin1234')
            db.session.add(admin)
            db.session.commit()
        else:
            admin.shop_id = 1
            admin.commission_rate = 0.0
            db.session.commit()

        shop1 = Shop.query.get(1)
        if not shop1:
            shop1 = Shop(name='شعبه ۱', phone='123')
            db.session.add(shop1)
            db.session.commit()

        now_j = jdatetime.datetime.now()
        settings = Settings.query.first()

        # Admin stats should have 0 commission
        stats = calculate_seller_exact_stats(admin.id, now_j.year, now_j.month, 0.0, settings)
        assert stats['settled_commission'] == 0
        assert stats['effective_rate'] == 0.0

        # Simulate admin creating an invoice for 8,000,000
        test_inv = Invoice(
            invoice_number='TEST-ADM-001054',
            customer_name='خریدار نمونه',
            status='final',
            invoice_type='sale',
            total_amount=8000000,
            paid_amount=8000000,
            paid_pos=8000000,
            is_settled=True,
            seller_id=admin.id,
            shop_id=1,
            shamsi_year=now_j.year,
            shamsi_month=now_j.month,
            shamsi_day=now_j.day,
            shamsi_date_time=now_j.strftime("%Y/%m/%d - %H:%M:%S"),
            actual_buy_cost=6000000,
            real_profit=2000000
        )
        db.session.add(test_inv)
        db.session.commit()

        # Check admin stats again
        stats_after = calculate_seller_exact_stats(admin.id, now_j.year, now_j.month, 0.0, settings)
        assert stats_after['sales_count'] >= 1
        assert stats_after['gross_sales'] >= 8000000
        assert stats_after['settled_commission'] == 0
        assert stats_after['effective_rate'] == 0.0

        # Test admin dashboard endpoint with test_client
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = admin.id
            sess['full_name'] = admin.full_name
            sess['role'] = 'admin'
            sess['shop_id'] = 1

        res = client.get(f'/admin?month={now_j.month}')
        assert res.status_code == 200
        html = res.data.decode('utf-8')
        # Total sales must be non-zero and include the 8,000,000
        assert "8,000,000" in html

        # Cleanup test invoice
        db.session.delete(test_inv)
        db.session.commit()
