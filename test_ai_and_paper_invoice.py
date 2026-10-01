import pytest
import os
import json
import io
from unittest.mock import patch, MagicMock
from werkzeug.datastructures import FileStorage
from app import app, db, save_paper_invoice_file
from models import User, Shop, Customer, ProductCatalog, InventoryItem, Invoice, InvoiceItem, Settings
from helpers import ai_scan_paper_invoice

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        yield client

def test_models_have_ai_and_paper_invoice_fields():
    """تست وجود فیلدهای عکس فاکتور کاغذی و تنظیمات هوش مصنوعی در مدل‌ها"""
    with app.app_context():
        # بررسی مدل Invoice
        assert hasattr(Invoice, 'paper_invoice_image'), "فیلد paper_invoice_image در Invoice یافت نشد"
        
        # بررسی مدل Settings
        assert hasattr(Settings, 'gemini_api_key'), "فیلد gemini_api_key در Settings یافت نشد"
        assert hasattr(Settings, 'gemini_model'), "فیلد gemini_model در Settings یافت نشد"

def test_api_invoice_details(client):
    """تست اندپوینت جزئیات فاکتور برای مودال مقایسه دفتری و دیجیتال"""
    with app.app_context():
        user = User.query.filter_by(username="admin").first()
        if not user:
            user = User(username="admin", role="admin", full_name="مدیر سیستم")
            user.set_password("admin123")
            db.session.add(user)
            db.session.commit()
            
        test_inv = Invoice(
            invoice_number="INV-AI-TEST-999",
            customer_name="مشتری تست مقایسه",
            customer_phone="09120001122",
            subtotal_amount=5000000,
            discount_amount=200000,
            total_amount=4800000,
            payment_method="cash",
            seller_id=user.id,
            shop_id=1,
            shamsi_year=1403,
            shamsi_month=7,
            shamsi_day=15,
            shamsi_date_time="1403/07/15 12:00",
            paper_invoice_image="sample_slip.jpg"
        )
        # اگر فاکتور قبلی با همین شماره هست حذف کنیم
        old_inv = Invoice.query.filter_by(invoice_number="INV-AI-TEST-999").first()
        if old_inv:
            InvoiceItem.query.filter_by(invoice_id=old_inv.id).delete()
            db.session.delete(old_inv)
            db.session.commit()

        db.session.add(test_inv)
        db.session.commit()
        
        item1 = InvoiceItem(
            invoice_id=test_inv.id,
            item_name="کابین و روشویی لوکس طهماسبی",
            quantity=1,
            unit_sell_price=3000000,
            total_price=3000000
        )
        item2 = InvoiceItem(
            invoice_id=test_inv.id,
            item_name="ست ۴ تکه شیرآلات قهرمان",
            quantity=1,
            unit_sell_price=2000000,
            total_price=2000000
        )
        db.session.add_all([item1, item2])
        db.session.commit()
        inv_id = test_inv.id
        admin_user_id = user.id

    with client.session_transaction() as sess:
        sess['user_id'] = admin_user_id
        sess['role'] = 'admin'

    res = client.get(f'/api/invoice/{inv_id}/details')
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data['invoice']['invoice_number'] == "INV-AI-TEST-999"
    assert data['invoice']['paper_invoice_image'] == "sample_slip.jpg"
    assert len(data['invoice']['items']) >= 2

def test_ai_scan_missing_image_and_key(client):
    """تست پاسخ‌های ولیدیشن اندپوینت اسکن فاکتور هوش مصنوعی"""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'seller'

    # ۱. ارسال بدون تصویر
    res1 = client.post('/api/ai/scan_invoice', data={})
    assert res1.status_code == 400
    assert res1.get_json()['error'] == 'no_image'

    # ۲. ارسال با تصویر اما کلید تنظیم نشده
    with app.app_context():
        sett = Settings.query.first()
        old_key = sett.gemini_api_key if sett else None
        if sett:
            sett.gemini_api_key = None
            db.session.commit()

    try:
        test_file = (io.BytesIO(b"fake image data"), "test.jpg")
        res2 = client.post('/api/ai/scan_invoice', data={'invoice_image': test_file}, content_type='multipart/form-data')
        assert res2.status_code == 400
        data2 = res2.get_json()
        assert data2['error'] == 'no_api_key'
        assert "کلید API" in data2['message']
    finally:
        # بازگردانی کلید در صورت وجود
        with app.app_context():
            if sett and old_key:
                sett.gemini_api_key = old_key
                db.session.commit()

def test_save_paper_invoice_file_and_serve(client):
    """تست ذخیره‌سازی عکس فاکتور و سرو فایل از طریق روت اختصاصی"""
    dummy_bytes = b"fake-jpg-content-for-testing"
    storage_file = FileStorage(
        stream=io.BytesIO(dummy_bytes),
        filename="my_handwritten_invoice.jpg",
        content_type="image/jpeg"
    )

    saved_name = save_paper_invoice_file(storage_file)
    assert saved_name is not None
    assert saved_name.endswith('.jpg')

    # درخواست دریافت فایل ذخیره‌شده
    res = client.get(f'/uploads/invoices/{saved_name}')
    assert res.status_code == 200
    assert res.data == dummy_bytes

def test_mock_gemini_scan_success():
    """تست تحلیل ساخت‌یافته هوش مصنوعی با ماک کردن پاسخ گوگل"""
    mock_gemini_response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps({
                                "customer_name": "حاج احمد حسینی",
                                "customer_phone": "09121112233",
                                "date": "1403/07/15",
                                "items": [
                                    {
                                        "name": "کابین روشویی لوتوس همراه با کاسه سنگ پرشین",
                                        "category": "روشویی کابینتی",
                                        "quantity": 1,
                                        "unit_price": 4500000,
                                        "total_price": 4500000,
                                        "is_bundle": True,
                                        "description": "همراه با سنگ"
                                    },
                                    {
                                        "name": "ست ۴ عددی شیرآلات شودر مدل بیزانس",
                                        "category": "شیرآلات",
                                        "quantity": 1,
                                        "unit_price": 12000000,
                                        "total_price": 12000000,
                                        "is_bundle": True,
                                        "description": "ست کامل دستشویی و حمام"
                                    }
                                ],
                                "subtotal_amount": 16500000,
                                "discount_amount": 500000,
                                "grand_total": 16000000,
                                "payment_note": "کارت",
                                "raw_notes": "فاکتور دست‌نویس تخفیف داده شد"
                            })
                        }
                    ]
                }
            }
        ]
    }

    with patch('requests.post') as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_gemini_response
        mock_post.return_value = mock_resp

        with app.app_context():
            result = ai_scan_paper_invoice(b"dummy_bytes", "image/jpeg", api_key="test_key")
        assert result['success'] is True
        data = result['data']
        assert data["customer_name"] == "حاج احمد حسینی"
        assert data["customer_phone"] == "09121112233"
        assert len(data["items"]) == 2
        assert data["items"][0]["is_bundle"] is True
        assert data["subtotal_amount"] == 16500000
        assert data["discount_amount"] == 500000
        assert data["grand_total"] == 16000000

def test_api_test_gemini_endpoint(client):
    """تست اندپوینت تست اتصال به هوش مصنوعی با کلید نامعتبر و شبیه‌سازی موفق"""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'admin'

    # کلید نامعتبر شبیه‌سازی خطا از سمت گوگل
    with patch('requests.post') as mock_post, patch('google.genai.Client') as mock_client:
        mock_client.side_effect = Exception("SDK error fallback")
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = '{"error": {"message": "API key not valid"}}'
        mock_post.return_value = mock_resp

        res = client.post('/api/ai/test_gemini', json={'gemini_api_key': 'fake_bad_key', 'gemini_model': 'gemini-3.8-flash'})
        assert res.status_code == 400
        assert res.get_json()['success'] is False
        assert "API key not valid" in res.get_json()['message']

    # کلید معتبر شبیه‌سازی موفق
    with patch('requests.post') as mock_post, patch('google.genai.Client') as mock_client:
        mock_client.side_effect = Exception("SDK fallback")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        res = client.post('/api/ai/test_gemini', json={'gemini_api_key': 'valid_key_test', 'gemini_model': 'gemini-3.8-flash'})
        assert res.status_code == 200
        assert res.get_json()['success'] is True
        assert "با موفقیت برقرار شد" in res.get_json()['message']
