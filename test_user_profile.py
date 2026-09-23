import os
import io
import time
import base64
import pytest
from app import app, db, initialize_database, AVATARS_DIR
from models import User, Shop

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        with app.app_context():
            initialize_database()
        yield client

def test_user_profile_crud_and_avatar(client):
    with app.app_context():
        # اطمینان از وجود کاربر تستی
        test_user = User.query.filter_by(username='test_seller_prof').first()
        if not test_user:
            test_user = User(
                username='test_seller_prof',
                full_name='فروشنده تست پروفایل',
                role='seller',
                shop_id=1,
                commission_rate=1.5,
                base_salary=18_000_000
            )
            test_user.set_password('pass123')
            db.session.add(test_user)
        else:
            test_user.set_password('pass123')
        db.session.commit()
        user_id = test_user.id

    # ۱. ورود به سیستم با کاربر تستی
    res = client.post('/login', data={'username': 'test_seller_prof', 'password': 'pass123'}, follow_redirects=True)
    assert res.status_code == 200

    # ۲. مشاهده صفحه پروفایل
    res = client.get('/profile')
    assert res.status_code == 200
    assert 'پروفایل کاربری و پرونده پرسنلی'.encode('utf-8') in res.data
    assert 'فروشنده تست پروفایل'.encode('utf-8') in res.data

    # ۳. بروزرسانی اطلاعات پرونده هویتی و بانکی
    profile_data = {
        'action': 'update_info',
        'full_name': 'فروشنده تست پروفایل ویرایش',
        'national_id': '0012345678',
        'birth_date': '1375/04/10',
        'phone': '09129998877',
        'emergency_phone': '02188887766',
        'card_number': '6037997511112222',
        'sheba_number': '120170000000111122223333',
        'address': 'تهران، خیابان سهروردی شمالی، پلاک ۱۲'
    }
    res = client.post('/profile', data=profile_data, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        u = db.session.get(User, user_id)
        assert u.national_id == '0012345678'
        assert u.birth_date == '1375/04/10'
        assert u.phone == '09129998877'
        assert u.emergency_phone == '02188887766'
        assert u.sheba_number == 'IR120170000000111122223333'
        assert u.address == 'تهران، خیابان سهروردی شمالی، پلاک ۱۲'

    # ۴. تست کراپ و آپلود عکس آواتار با Base64
    # ساخت یک تصویر کوچک تستی (۱x۱ پیکسل JPEG معتبر)
    tiny_jpeg_b64 = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
    
    res = client.post('/api/profile/upload_avatar', json={'image_data': tiny_jpeg_b64})
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert 'avatar_url' in data

    with app.app_context():
        u = db.session.get(User, user_id)
        assert u.avatar is not None
        avatar_path = os.path.join(AVATARS_DIR, u.avatar)
        assert os.path.exists(avatar_path)

    # ۵. تست دریافت عکس از روت /uploads/avatars/
    avatar_url = data['avatar_url']
    res = client.get(avatar_url)
    assert res.status_code == 200

    # ۶. تست تغییر رمز عبور
    pwd_data = {
        'action': 'change_password',
        'old_password': 'pass123',
        'new_password': 'newsecretpass',
        'confirm_password': 'newsecretpass'
    }
    res = client.post('/profile', data=pwd_data, follow_redirects=True)
    assert res.status_code == 200

    # خروج و ورود با رمز جدید
    client.get('/logout')
    res = client.post('/login', data={'username': 'test_seller_prof', 'password': 'newsecretpass'}, follow_redirects=True)
    assert res.status_code == 200
    assert 'داشبورد'.encode('utf-8') in res.data

def test_admin_avatar_and_payroll_profile_rendering(client):
    # ۱. ورود به عنوان ادمین
    client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)

    # ۲. مشاهده داشبورد مدیریت و وجود لینک به پروفایل و آواتار مدیریت
    res = client.get('/admin')
    assert res.status_code == 200
    assert 'پنل مدیریت جامع فروشگاه‌های طهماسبی'.encode('utf-8') in res.data
    assert 'پروفایل من'.encode('utf-8') in res.data

    # ۳. مشاهده جدول حقوق و دستمزد و رندربندی مشخصات پرسنلی
    res = client.get('/admin/payroll')
    assert res.status_code == 200
    assert 'سامانه حقوق، دستمزد و فیش پرسنل'.encode('utf-8') in res.data
