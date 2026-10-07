import pytest
import os
import json
import io
from unittest.mock import patch, MagicMock
from app import app, db
from models import User, Shop, Customer, ProductCatalog, InventoryItem, Invoice, InvoiceItem, Cheque, Settings
from helpers import (
    call_gemini_unified,
    ai_business_copilot,
    ai_suggest_cross_sell,
    ai_extract_product_from_box,
    ai_customer_credit_risk,
    ai_audit_store_anomalies
)

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        yield client

def test_models_ai_columns():
    """ستون‌های جدید هوش مصنوعی در مدل‌های Customer و Invoice"""
    with app.app_context():
        assert hasattr(Customer, 'ai_credit_score')
        assert hasattr(Customer, 'ai_risk_tier')
        assert hasattr(Customer, 'ai_risk_summary')
        assert hasattr(Invoice, 'ai_audit_flags')

def test_ai_suggest_cross_sell_rules():
    """تست موتور قوانین پیشنهاد اقلام مکمل سبد خرید (Pillar 2)"""
    with app.app_context():
        # تست پیشنهاد برای کابینت روشویی
        res = ai_suggest_cross_sell(['کابینت روشویی مروارید سایز ۶۰'], ['روشویی کابینتی'])
        assert res['success'] is True
        names = [s['name'] for s in res['suggestions']]
        assert any('روشویی' in n or 'سیفون' in n or 'آینه' in n for n in names)

        # تست پیشنهاد برای توالت فرنگی
        res_toilet = ai_suggest_cross_sell(['توالت فرنگی مروارید مدل کاتیا'], ['توالت فرنگی'])
        assert res_toilet['success'] is True
        names_toilet = [s['name'] for s in res_toilet['suggestions']]
        assert any('بوگیر' in n or 'پیسوار' in n or 'توالت' in n for n in names_toilet)

        # تست پیشنهاد برای سینک ظرفشویی
        res_sink = ai_suggest_cross_sell(['سینک توکار اخوان فانتزی'], ['سینک'])
        assert res_sink['success'] is True
        names_sink = [s['name'] for s in res_sink['suggestions']]
        assert any('شیر' in n or 'سیفون' in n or 'سبد' in n for n in names_sink)

def test_ai_customer_credit_risk_scoring():
    """تست اعتبارسنجی هوشمند خریدار و صدور پیش‌نویس پیامک (Pillar 4)"""
    with app.app_context():
        cust = Customer.query.filter_by(phone="09129998877").first()
        if not cust:
            cust = Customer(
                name="مشتری تست ریسک اعتباری",
                phone="09129998877",
                credit_limit=50_000_000,
                outstanding_balance=12_000_000
            )
            db.session.add(cust)
            db.session.commit()
        else:
            cust.outstanding_balance = 12_000_000
            db.session.commit()

        # ثبت یک چک صیادی پاس شده
        chk = Cheque(
            sayad_number="1234567890123456",
            bank_name="ملی",
            customer_name=cust.name,
            customer_phone=cust.phone,
            amount=5000000,
            due_shamsi_date="1404/07/20",
            shop_id=1,
            status="passed"
        )
        db.session.add(chk)
        db.session.commit()

        risk = ai_customer_credit_risk(cust.id)
        assert risk['success'] is True
        assert risk['score'] >= 50
        assert risk['tier'] in ['A+', 'A', 'B', 'C']
        assert "12,000,000" in risk['sms_draft']
        assert cust.ai_credit_score == risk['score']
        assert cust.ai_risk_tier == risk['tier']

def test_ai_audit_store_anomalies_detection():
    """تست دیده‌بان ممیزی و کشف خطای فروش زیر قیمت خرید و تخفیف غیرعادی (Pillar 5)"""
    with app.app_context():
        user = User.query.filter_by(username="admin").first()
        if not user:
            user = User(username="admin", role="admin", full_name="مدیر سیستم")
            user.set_password("admin123")
            db.session.add(user)
            db.session.commit()

        # پاکسازی رکورد تست قبلی در صورت وجود
        existing = Invoice.query.filter_by(invoice_number="INV-LOSS-TEST-001").first()
        if existing:
            InvoiceItem.query.filter_by(invoice_id=existing.id).delete()
            db.session.delete(existing)
            db.session.commit()

        # ایجاد فاکتور تست با فروش زیر قیمت خرید (زیان)
        loss_inv = Invoice(
            invoice_number="INV-LOSS-TEST-001",
            customer_name="مشتری تست زیان",
            total_amount=1_000_000,
            status="final",
            invoice_type="sale",
            seller_id=user.id,
            shop_id=1,
            shamsi_year=1405,
            shamsi_month=7,
            shamsi_day=10,
            shamsi_date_time="1405/07/10 10:00"
        )
        db.session.add(loss_inv)
        db.session.flush()

        item = InvoiceItem(
            invoice_id=loss_inv.id,
            item_name="شیرآلات زیان‌ده تست",
            category="شیرآلات",
            quantity=1,
            unit_buy_price=1_500_000, # خرید ۱.۵ میلیون
            unit_sell_price=1_000_000, # فروش ۱ میلیون (۵۰۰ هزار زیان)
            total_price=1_000_000,
            row_profit=-500_000
        )
        db.session.add(item)
        db.session.commit()

        audit_res = ai_audit_store_anomalies(limit=10)
        anomalies_list = audit_res.get('anomalies', []) if isinstance(audit_res, dict) else audit_res
        assert len(anomalies_list) > 0
        loss_found = any(a['invoice_number'] == "INV-LOSS-TEST-001" and a['type'] == 'loss_sale' for a in anomalies_list)
        assert loss_found is True

def test_api_ai_copilot_endpoint(client):
    """تست اندپوینت دستیار هوشمند بیزنس کوپایلوت (Pillar 1)"""
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(username="admin", role="admin", full_name="مدیر سیستم")
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()

        with client.session_transaction() as sess:
            sess['user_id'] = admin.id
            sess['role'] = 'admin'
            sess['full_name'] = 'مدیر سیستم'

        with patch('helpers.call_gemini_unified') as mock_gemini:
            mock_gemini.return_value = {
                'success': True,
                'text': 'گزارش تحلیلی فروشگاه طهماسبی: فروش امروز عالی بوده است.',
                'model': 'gemini-3.8-flash'
            }

            resp = client.post('/api/ai/copilot', json={'query': 'وضعیت امروز فروشگاه'})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert 'فروش امروز' in data['reply']

def test_api_ai_suggest_cross_sell_endpoint(client):
    """تست اندپوینت API پیشنهاد اقلام مکمل"""
    with app.app_context():
        user = User.query.first()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['role'] = user.role

        resp = client.post('/api/ai/suggest_cross_sell', json={
            'items': ['روشویی کابینتی مدل رویال'],
            'categories': ['روشویی کابینتی']
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['suggestions']) > 0

def test_api_ai_customer_risk_endpoint(client):
    """تست اندپوینت دریافت رادار ریسک مشتری"""
    with app.app_context():
        user = User.query.first()
        cust = Customer.query.first()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['role'] = user.role

        resp = client.get(f'/api/ai/customer_risk/{cust.id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'tier' in data
        assert 'score' in data
        assert 'sms_draft' in data

def test_api_ai_audit_anomalies_endpoint(client):
    """تست اندپوینت دیده‌بان ممیزی برای مدیریت"""
    with app.app_context():
        admin = User.query.filter_by(role="admin").first()
        with client.session_transaction() as sess:
            sess['user_id'] = admin.id
            sess['role'] = 'admin'

        resp = client.get('/api/ai/audit_anomalies')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'anomalies' in data
