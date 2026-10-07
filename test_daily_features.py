import pytest
import jdatetime
from app import app, db
from models import User, Shop, Invoice, PurchaseInvoice, DailyShiftReport

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        yield client

def test_daily_branch_sales_and_purchases(client):
    with app.app_context():
        # دریافت ادمین و شعبه
        admin = User.query.filter_by(role='admin').first()
        shop = Shop.query.first() or Shop(name="شعبه مرکزی تست", rent_amount=0)
        if not shop.id:
            db.session.add(shop)
            db.session.commit()
            
        now_j = jdatetime.datetime.now()
        
        # ۱. تست لاگین به عنوان ادمین
        with client.session_transaction() as sess:
            sess['user_id'] = admin.id
            sess['role'] = 'admin'
            sess['full_name'] = admin.full_name
            sess['shop_id'] = shop.id
            sess['tenant_id'] = 1

        # ۲. ایجاد فاکتور خرید انبار با کسر از دخل مغازه
        pur = PurchaseInvoice(
            purchase_number=f"TEST-PUR-{now_j.year}{now_j.month:02d}{now_j.day:02d}-9999",
            supplier_name="انبار سنگ تست",
            title="خرید ۱۶ تن سنگ تراورتن",
            total_amount=16000000,
            payment_source='shop_cash',
            shop_id=shop.id,
            user_id=admin.id,
            shamsi_year=now_j.year,
            shamsi_month=now_j.month,
            shamsi_day=now_j.day,
            shamsi_date_time=now_j.strftime("%Y/%m/%d - %H:%M:%S")
        )
        db.session.add(pur)
        db.session.commit()
        
        # ۳. تست استعلام api_shift_summary_today
        res_summary = client.get('/api/shift/summary_today')
        assert res_summary.status_code == 200
        data = res_summary.get_json()
        assert data['success'] is True
        assert data['today_purchases_cash'] >= 16000000

        # ۴. تست ثبت گزارش کار فروشنده (بستن دخل)
        res_report = client.post('/shift/submit_report', data={
            'reported_pos_amount': '5000000',
            'reported_cash_amount': '2000000',
            'reported_card_amount': '0',
            'reported_cheques_amount': '0',
            'reported_cheques_count': '0',
            'notes': 'تست بستن شیفت پایان روز'
        }, follow_redirects=True)
        assert res_report.status_code == 200

        # ۵. تایید گزارش توسط مدیریت
        report_record = DailyShiftReport.query.filter_by(user_id=admin.id, shamsi_year=now_j.year, shamsi_day=now_j.day).first()
        assert report_record is not None
        assert report_record.reported_pos_amount == 5000000
        assert report_record.cash_expenses_deducted >= 16000000
        
        # پاکسازی رکورد تست
        db.session.delete(report_record)
        db.session.delete(pur)
        db.session.commit()
