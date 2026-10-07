import pytest
import os
import shutil
from app import app, db, perform_system_backup, send_backup_email
from models import User, Settings

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        yield client

def test_backup_system_and_drive_copy():
    with app.app_context():
        # تست تهیه بکاپ اتمیک
        res = perform_system_backup(label="test_30min")
        assert res['success'] is True
        assert os.path.exists(res['path'])
        assert res['size'] > 0
        assert "Backup_Tahmasebi_test_30min_" in res['filename']

        # تست کپی روی مسیر درایو
        test_drive_dir = os.path.join(app.root_path, 'instance', 'test_external_drive')
        os.makedirs(test_drive_dir, exist_ok=True)
        
        settings = Settings.query.first()
        if not settings:
            settings = Settings()
            db.session.add(settings)
        settings.backup_drive_path = test_drive_dir
        settings.backup_interval_minutes = 30
        db.session.commit()

        res_drive = perform_system_backup(label="test_drive")
        assert res_drive['success'] is True
        assert res_drive.get('drive_copied') is True
        assert os.path.exists(res_drive.get('drive_dest'))

        # پاکسازی پوشه تست
        shutil.rmtree(test_drive_dir, ignore_errors=True)

def test_backup_email_flow(client):
    with app.app_context():
        # اطمینان از دسترسی ادمین
        admin = User.query.filter_by(role='admin').first()
        with client.session_transaction() as sess:
            sess['user_id'] = admin.id
            sess['role'] = 'admin'
            sess['full_name'] = admin.full_name

        # بررسی route لیست بکاپ‌ها
        res_list = client.get('/api/admin/backups/list')
        assert res_list.status_code == 200
        data = res_list.get_json()
        assert data['success'] is True
        assert len(data['backups']) > 0

        # تست فراخوانی api ایجاد بکاپ
        res_create = client.post('/api/admin/backups/create')
        assert res_create.status_code == 200
        c_data = res_create.get_json()
        assert c_data['success'] is True
        assert 'Backup_Tahmasebi_instant_' in c_data['backup']['filename']
