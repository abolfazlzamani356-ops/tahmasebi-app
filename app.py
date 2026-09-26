import os
import shutil
import io
import re
import json
import random
import sqlite3
import jdatetime
from datetime import datetime, timedelta
import time
import base64
import gzip
import mimetypes
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, send_from_directory, jsonify, Response, make_response
from sqlalchemy import func, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import selectinload, joinedload

from models import (
    db, Shop, Category, User, Settings, Customer, BankAccount,
    InventoryItem, StockLog, StockTransfer,
    Invoice, InvoiceItem, Cheque, SalarySlip,
    PettyCashDeposit, Expense, AuditLog, ProductCatalog
)
from helpers import (
    PERSIAN_MONTHS, DEFAULT_CATEGORIES, RETURN_REASONS,
    get_current_shamsi, log_activity, record_stock_change,
    calculate_seller_exact_stats, get_or_create_customer,
    parse_smart_invoice_text, get_inventory_ai_insights,
    safe_int, safe_float, normalize_persian_text, calculate_store_financial_summary,
    send_invoice_sms, build_catalog_search_filter, get_persian_word_variants
)
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill

# مسیر هوشمند قالب‌ها: هم پشتیبانی از پوشه templates و هم فایل‌های کنار app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(BASE_DIR, 'templates')
if not os.path.exists(templates_dir) or not os.path.exists(os.path.join(templates_dir, 'login.html')):
    templates_dir = BASE_DIR

app = Flask(__name__, template_folder=templates_dir)
app.secret_key = os.environ.get('SECRET_KEY', 'tahmasebi-mega-erp-v14-permanent-secure-2026')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB - برای آپلود عکس پرسنلی

# رمز نجات مدیریت
MASTER_ADMIN_PASSWORD = os.environ.get('MASTER_ADMIN_PASSWORD', 'king68abolfazl@68')

# ==================== مسیر دیتابیس سازگار با دیسک دائمی لیارا، Railway و محلی ====================
LIARA_VOLUME = os.environ.get('LIARA_VOLUME_PATH', '')
RAILWAY_VOLUME = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', '')
CUSTOM_DATA_DIR = os.environ.get('DATA_DIR', '')

DATA_DIR = os.path.join(app.root_path, 'instance')

# بررسی دیسک در مسیرهای ابری (لیارا یا ریلوی) با تست دقیق دسترسی نوشتن
target_volume = LIARA_VOLUME or RAILWAY_VOLUME or CUSTOM_DATA_DIR
if not target_volume and os.path.isdir('/data'):
    target_volume = '/data'

DATA_DIR = os.path.join(app.root_path, 'instance')

if target_volume:
    try:
        os.makedirs(target_volume, exist_ok=True)
        # تست واقعی ایجاد فایل دیتابیس آزمایشی
        test_file = os.path.join(target_volume, '.sqlite_write_test')
        with open(test_file, 'w') as f:
            f.write('ok')
        if os.path.exists(test_file):
            os.remove(test_file)
            DATA_DIR = target_volume
    except Exception as e:
        app.logger.warning(f"Could not write to volume ({target_volume}): {e}. Using fallback instance directory.")

os.makedirs(DATA_DIR, exist_ok=True)
AVATARS_DIR = os.path.join(DATA_DIR, 'uploads', 'avatars')
os.makedirs(AVATARS_DIR, exist_ok=True)
STATIC_AVATARS_DIR = os.path.join(app.root_path, 'static', 'uploads', 'avatars')
os.makedirs(STATIC_AVATARS_DIR, exist_ok=True)

# نرمال‌سازی مسیر برای SQLite در لینوکس و ویندوز
db_file_abs = os.path.abspath(os.path.join(DATA_DIR, 'tahmasebi_store_persistent.db'))
db_path = db_file_abs
# در لینوکس اگر مسیر با / شروع شود، ۳ اسلش دیگر لازم است تا بشود sqlite:////path
if db_file_abs.startswith('/'):
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_file_abs}'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_file_abs.replace(os.sep, "/")}'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'timeout': 30, 'check_same_thread': False}
}

db.init_app(app)

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    import sqlite3
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = NORMAL")
            cursor.execute("PRAGMA busy_timeout = 30000")
            cursor.execute("PRAGMA cache_size = -64000")   # حافظه کش ۶۴ مگابایت در رم برای پاسخدهی آنی
            cursor.execute("PRAGMA temp_store = MEMORY")   # جداول موقت در رم
            cursor.execute("PRAGMA mmap_size = 268435456") # مپ حافظه ۲۵۶ مگابایت برای خواندن فوری بدون تاخیر دیسک
        except Exception:
            pass
        finally:
            cursor.close()

# ==================== مقداردهی اولیه دیتابیس با Flask ====================
def initialize_database():
    """مقداردهی اولیه و مایگریشن دیتابیس - فقط یکبار اجرا می‌شود"""
    import sqlite3

    try:
        db.create_all()
    except Exception as e:
        app.logger.warning(f"db.create_all warning: {e}")

    # مایگریشن ایمن ستون‌های جدید
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=20)
        cursor = conn.cursor()
        try:
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = NORMAL")
            cursor.execute("PRAGMA busy_timeout = 30000")
            cursor.execute("PRAGMA cache_size = -64000")
            cursor.execute("PRAGMA temp_store = MEMORY")
            cursor.execute("PRAGMA mmap_size = 268435456")
        except Exception:
            pass

        migrations = [
            ("settings", "store_name", "TEXT DEFAULT 'مجموعه فروشگاه‌های تخصصی طهماسبی'"),
            ("settings", "store_phone", "TEXT DEFAULT '021-12345678'"),
            ("settings", "store_warranty_text", "TEXT DEFAULT 'کلیه اقلام دارای گارانتی اصالت کالا می‌باشند.'"),
            ("users", "base_salary", "BIGINT DEFAULT 0"),
            ("users", "phone", "TEXT"),
            ("users", "card_number", "TEXT"),
            ("users", "created_at", "DATETIME"),
            ("shops", "phone", "TEXT"),
            ("shops", "address", "TEXT"),
            ("categories", "icon", "TEXT DEFAULT '📦'"),
            ("invoices", "customer_id", "INTEGER"),
            ("invoices", "subtotal_amount", "BIGINT DEFAULT 0"),
            ("invoices", "discount_amount", "BIGINT DEFAULT 0"),
            ("invoices", "actual_buy_cost", "BIGINT DEFAULT 0"),
            ("invoices", "real_profit", "BIGINT DEFAULT 0"),
            ("invoices", "is_settled", "BOOLEAN DEFAULT 1"),
            ("invoices", "shamsi_day", "INTEGER"),
            ("invoices", "paid_pos", "BIGINT DEFAULT 0"),
            ("invoices", "paid_card", "BIGINT DEFAULT 0"),
            ("invoices", "paid_cash", "BIGINT DEFAULT 0"),
            ("invoices", "paid_cheque", "BIGINT DEFAULT 0"),
            ("invoices", "remaining_balance", "BIGINT DEFAULT 0"),
            ("invoices", "dest_sheba_number", "TEXT"),
            ("users", "can_manage_inventory", "BOOLEAN DEFAULT 0"),
            ("shops", "rent_amount", "BIGINT DEFAULT 0"),
            ("users", "avatar", "TEXT"),
            ("users", "avatar_data", "TEXT"),
            ("users", "national_id", "TEXT"),
            ("users", "birth_date", "TEXT"),
            ("users", "start_date", "TEXT"),
            ("users", "emergency_phone", "TEXT"),
            ("users", "sheba_number", "TEXT"),
            ("users", "address", "TEXT"),
            ("users", "notes", "TEXT"),
            ("invoices", "has_custom_items", "BOOLEAN DEFAULT 0"),
            ("invoice_items", "is_custom", "BOOLEAN DEFAULT 0"),
            ("product_catalog", "barcode", "TEXT"),
            ("audit_logs", "ip_address", "TEXT"),
            ("audit_logs", "details", "TEXT"),
            ("settings", "sms_api_key", "TEXT DEFAULT 'mDVL1257srjKMnY7X9Yj87Y1ssazFsEncwDtt3kMF9NtAcBa'"),
            ("settings", "sms_template_id", "TEXT DEFAULT '355952'"),
            ("settings", "sms_enabled", "BOOLEAN DEFAULT 1"),
            ("settings", "public_domain", "TEXT DEFAULT 'tahmasebistore.ir'"),
            ("invoices", "sms_sent", "BOOLEAN DEFAULT 0"),
            ("invoices", "sms_sent_at", "TEXT"),
        ]

        for table, col, col_def in migrations:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
                conn.commit()
            except Exception:
                pass

        # ایجاد ایندکس‌های پرسرعت دیتابیس برای بهینه‌سازی موشکی کوئری‌ها
        indexes = [
            ("idx_invoices_year_month_status", "CREATE INDEX IF NOT EXISTS idx_invoices_year_month_status ON invoices (shamsi_year, shamsi_month, status)"),
            ("idx_invoices_seller", "CREATE INDEX IF NOT EXISTS idx_invoices_seller ON invoices (seller_id, shamsi_year, shamsi_month)"),
            ("idx_invoices_second_seller", "CREATE INDEX IF NOT EXISTS idx_invoices_second_seller ON invoices (second_seller_id, shamsi_year, shamsi_month)"),
            ("idx_invoices_shop", "CREATE INDEX IF NOT EXISTS idx_invoices_shop ON invoices (shop_id, shamsi_year, shamsi_month)"),
            ("idx_invoices_settled", "CREATE INDEX IF NOT EXISTS idx_invoices_settled ON invoices (is_settled, remaining_balance)"),
            ("idx_invoices_custom_items", "CREATE INDEX IF NOT EXISTS idx_invoices_custom_items ON invoices (has_custom_items)"),
            ("idx_invoices_created", "CREATE INDEX IF NOT EXISTS idx_invoices_created ON invoices (created_at DESC)"),
            ("idx_invoices_number", "CREATE INDEX IF NOT EXISTS idx_invoices_number ON invoices (invoice_number)"),
            ("idx_invoice_items_inv", "CREATE INDEX IF NOT EXISTS idx_invoice_items_inv ON invoice_items (invoice_id)"),
            ("idx_cheques_inv", "CREATE INDEX IF NOT EXISTS idx_cheques_inv ON cheques (invoice_id)"),
            ("idx_cheques_status", "CREATE INDEX IF NOT EXISTS idx_cheques_status ON cheques (status)"),
            ("idx_inventory_shop", "CREATE INDEX IF NOT EXISTS idx_inventory_shop ON inventory_items (shop_id)"),
            ("idx_inventory_name", "CREATE INDEX IF NOT EXISTS idx_inventory_name ON inventory_items (name)"),
            ("idx_inventory_barcode", "CREATE INDEX IF NOT EXISTS idx_inventory_barcode ON inventory_items (barcode)"),
            ("idx_catalog_brand", "CREATE INDEX IF NOT EXISTS idx_catalog_brand ON product_catalog (brand)"),
            ("idx_catalog_category", "CREATE INDEX IF NOT EXISTS idx_catalog_category ON product_catalog (category)"),
            ("idx_catalog_code", "CREATE INDEX IF NOT EXISTS idx_catalog_code ON product_catalog (code)"),
            ("idx_catalog_barcode", "CREATE INDEX IF NOT EXISTS idx_catalog_barcode ON product_catalog (barcode)"),
            ("idx_customers_phone", "CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers (phone)"),
            ("idx_customers_name", "CREATE INDEX IF NOT EXISTS idx_customers_name ON customers (name)"),
            ("idx_stock_logs_item", "CREATE INDEX IF NOT EXISTS idx_stock_logs_item ON stock_logs (inventory_item_id)"),
            ("idx_users_role_active", "CREATE INDEX IF NOT EXISTS idx_users_role_active ON users (role, is_active)"),
            ("idx_expenses_year_month", "CREATE INDEX IF NOT EXISTS idx_expenses_year_month ON expenses (shamsi_year, shamsi_month)"),
        ]
        for idx_name, idx_sql in indexes:
            try:
                cursor.execute(idx_sql)
            except Exception:
                pass
        conn.commit()
    except Exception as e:
        app.logger.warning(f"Migration warning (non-critical): {e}")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    
    # همگام‌سازی عکس‌های پرسنلی از دیسک پایدار به پوشه استاتیک در صورت ریست یا دپلوی مجدد کانتینر
    try:
        if os.path.isdir(AVATARS_DIR):
            for fname in os.listdir(AVATARS_DIR):
                src_path = os.path.join(AVATARS_DIR, fname)
                dst_path = os.path.join(STATIC_AVATARS_DIR, fname)
                if os.path.isfile(src_path) and not os.path.exists(dst_path):
                    shutil.copy2(src_path, dst_path)
    except Exception as e:
        app.logger.warning(f"Error syncing avatars on startup: {e}")
    
    # ثبت داده‌های پایه اگر دیتابیس خالی است
    try:
        if not BankAccount.query.first():
            acc1 = BankAccount(
                title='کارت اصلی فروشگاه طهماسبی',
                bank_name='بانک ملی ایران',
                account_owner='محمد طهماسبی',
                account_type='both',
                card_number='6037997512345678',
                sheba_number='IR120170000000123456789012'
            )
            db.session.add(acc1)
            db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        for cat_name in DEFAULT_CATEGORIES:
            if not Category.query.filter_by(name=cat_name).first():
                db.session.add(Category(name=cat_name))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        if not Settings.query.first():
            db.session.add(Settings())
            db.session.commit()
    except Exception:
        db.session.rollback()
        
    try:
        if not Shop.query.first():
            shop1 = Shop(name='فروشگاه طهماسبی - شعبه ۱ (مرکزی)', phone='021-11111111')
            shop2 = Shop(name='فروشگاه طهماسبی - شعبه ۲', phone='021-22222222')
            db.session.add_all([shop1, shop2])
            db.session.commit()

            admin = User(username='admin', full_name='محمد طهماسبی', role='admin', base_salary=0)
            admin.set_password('admin123')
            db.session.add(admin)

            u1 = User(username='naqdi', full_name='خانم نقدی', role='seller', shop_id=shop1.id, commission_rate=1.0, base_salary=15000000)
            u1.set_password('123456')
            u2 = User(username='amiri', full_name='خانم امیری', role='seller', shop_id=shop1.id, commission_rate=1.0, base_salary=15000000)
            u2.set_password('123456')
            u3 = User(username='bidrigh', full_name='خانم بیدریغ', role='seller', shop_id=shop2.id, commission_rate=1.2, base_salary=15000000)
            u3.set_password('123456')
            u4 = User(username='hajilou', full_name='خانم حاجیلو', role='seller', shop_id=shop2.id, commission_rate=0.8, base_salary=15000000)
            u4.set_password('123456')
            u5 = User(username='zamani', full_name='ابوالفضل زمانی', role='seller', shop_id=shop1.id, commission_rate=5.0, base_salary=20000000)
            u5.set_password('123456')
            db.session.add_all([u1, u2, u3, u4, u5])
            db.session.commit()

            items = [
                InventoryItem(name='هود داتیس مدل 522 مخفی', category='هود', shop_id=shop1.id, stock_quantity=8, min_alert_stock=2, buy_price=6500000, sell_price=8900000),
                InventoryItem(name='گاز 5 شعله اخوان مدل GI-135', category='گاز صفحه‌ای', shop_id=shop1.id, stock_quantity=10, min_alert_stock=2, buy_price=7200000, sell_price=9800000),
                InventoryItem(name='سینک گرانیتی فونیکس دو لگن', category='سینک', shop_id=shop2.id, stock_quantity=6, min_alert_stock=2, buy_price=5400000, sell_price=7500000),
                InventoryItem(name='روشویی کابینتی ضدآب فول‌ست', category='روشویی کابینتی', shop_id=shop2.id, stock_quantity=4, min_alert_stock=2, buy_price=4200000, sell_price=6800000)
            ]
            db.session.add_all(items)
            db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        admin_user = User.query.filter_by(role='admin').first()
        if admin_user:
            adm_changed = False
            if admin_user.full_name != 'محمد طهماسبی':
                admin_user.full_name = 'محمد طهماسبی'
                adm_changed = True
            if admin_user.username != 'admin':
                admin_user.username = 'admin'
                adm_changed = True
            if not admin_user.password_hash:
                admin_user.set_password(MASTER_ADMIN_PASSWORD)
                adm_changed = True
            if admin_user.shop_id is None:
                admin_user.shop_id = 1
                adm_changed = True
            if admin_user.commission_rate != 0:
                admin_user.commission_rate = 0.0
                adm_changed = True
            if adm_changed:
                db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        # پرسنل آقا برای خدمات، تحویل بار، انبارداری و نظافت (حقوق ثابت بدون پورسانت)
        services_staff = [
            {'username': 'khedmat1', 'full_name': 'رضا مرادی (تحویل بار و خدمات)', 'shop_id': 1, 'base_salary': 15_000_000},
            {'username': 'khedmat2', 'full_name': 'علی حسینی (انبار و نظافت)', 'shop_id': 2, 'base_salary': 15_000_000},
        ]
        for stf in services_staff:
            if not User.query.filter_by(username=stf['username']).first():
                u_svc = User(
                    username=stf['username'],
                    full_name=stf['full_name'],
                    role='logistics',
                    shop_id=stf['shop_id'],
                    base_salary=stf['base_salary'],
                    commission_rate=0.0,
                    is_active=True
                )
                u_svc.set_password('123456')
                db.session.add(u_svc)
        db.session.commit()
    except Exception:
        db.session.rollback()

    # ==================== تابع کمکی برای بارگذاری سریع کاتالوگ ====================
    def _seed_catalog(brand_filter, generate_func, discount, warning_tag, brand_names=None):
        """بارگذاری سریع با bulk insert - فقط اگر تعداد کمتر از آستانه باشد seed می‌زند"""
        try:
            items = generate_func(discount)
            if not items:
                return
            if brand_names:
                existing_count = ProductCatalog.query.filter(
                    ProductCatalog.brand.in_(brand_names)
                ).count()
            else:
                existing_count = ProductCatalog.query.filter_by(brand=brand_filter).count()
            # اگر تعداد موجود حداقل 90٪ آیتم‌ها را داشت، نیازی به seed نیست
            if existing_count >= int(len(items) * 0.9):
                return
            # bulk insert فقط آیتم‌های جدید
            existing_names = {
                r[0] for r in db.session.query(ProductCatalog.name).filter(
                    ProductCatalog.brand == (brand_filter or brand_names[0])
                ).all()
            }
            new_items = [itm for itm in items if itm['name'] not in existing_names]
            if new_items:
                db.session.bulk_insert_mappings(ProductCatalog, [
                    dict(name=i['name'], category=i['category'], brand=i['brand'],
                         buy_price=i['buy_price'], sell_price=i['sell_price'],
                         description=i['description'])
                    for i in new_items
                ])
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.warning(f"{warning_tag} catalog auto-seed warning: {e}")

    # بارگذاری کاتالوگ‌های رسمی
    try:
        from abs_catalog_data import generate_all_abs_items
        _seed_catalog('آس (ABS)', generate_all_abs_items, 28.0, 'ABS')
    except Exception as e:
        app.logger.warning(f"ABS import warning: {e}")

    try:
        from zarsham_catalog_data import generate_all_zarsham_items
        _seed_catalog('زرشام (Zarsham)', generate_all_zarsham_items, 20.0, 'Zarsham')
    except Exception as e:
        app.logger.warning(f"Zarsham import warning: {e}")

    try:
        from kasra_catalog_data import generate_all_kasra_items
        _seed_catalog(None, generate_all_kasra_items, 28.0, 'Kasra',
                      brand_names=['کسرا (Kasra)', 'ایزی‌پایپ (Easy Pipe)'])
    except Exception as e:
        app.logger.warning(f"Kasra import warning: {e}")

    try:
        from steel_alborz_catalog_data import generate_all_steel_alborz_items
        _seed_catalog('استیل البرز (Steel Alborz)', generate_all_steel_alborz_items, 21.0, 'Steel Alborz')
    except Exception as e:
        app.logger.warning(f"Steel Alborz import warning: {e}")

    try:
        from akhavan_catalog_data import generate_all_akhavan_items
        _seed_catalog('اخوان (Akhavan)', generate_all_akhavan_items, 18.0, 'Akhavan')
    except Exception as e:
        app.logger.warning(f"Akhavan import warning: {e}")

    try:
        from negin_almas_catalog_data import generate_all_negin_almas_items
        _seed_catalog('نگین الماس (Negin Almas)', generate_all_negin_almas_items, 15.0, 'Negin Almas')
    except Exception as e:
        app.logger.warning(f"Negin Almas import warning: {e}")

    try:
        from bimax_catalog_data import generate_all_bimax_items
        _seed_catalog('بیمکث (Bimax)', generate_all_bimax_items, 18.0, 'Bimax')
    except Exception as e:
        app.logger.warning(f"Bimax import warning: {e}")

    try:
        from ilia_steel_catalog_data import generate_all_ilia_steel_items
        _seed_catalog('ایلیا استیل (Ilia Steel)', generate_all_ilia_steel_items, 18.0, 'Ilia Steel')
    except Exception as e:
        app.logger.warning(f"Ilia Steel import warning: {e}")

    try:
        from milan_catalog_data import generate_all_milan_items
        _seed_catalog('میلان (Milan)', generate_all_milan_items, 18.0, 'Milan')
    except Exception as e:
        app.logger.warning(f"Milan import warning: {e}")

    try:
        from gatria_catalog_data import generate_all_gatria_items
        _seed_catalog('گاتریا (Gatria)', generate_all_gatria_items, 15.0, 'Gatria')
    except Exception as e:
        app.logger.warning(f"Gatria import warning: {e}")

    try:
        from krd_catalog_data import generate_all_krd_items
        _seed_catalog('KRD', generate_all_krd_items, 32.0, 'KRD')
    except Exception as e:
        app.logger.warning(f"KRD import warning: {e}")

    try:
        from rozen_catalog_data import generate_rozen_catalog_items
        _seed_catalog('رزن', generate_rozen_catalog_items, 15.0, 'Rozen')
    except Exception as e:
        app.logger.warning(f"Rozen import warning: {e}")




# اجرا در startup زمان import توسط gunicorn
with app.app_context():
    try:
        initialize_database()
    except Exception as e:
        app.logger.error(f"Database init error: {e}")

# ==================== Error Handlers ====================
@app.errorhandler(500)
def internal_error(e):
    db.session.rollback()
    app.logger.error(f"Internal Server Error: {e}", exc_info=True)
    # برای API routes، JSON برگردون نه redirect
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': f'خطای سرور داخلی: {str(e)}'}), 500
    if 'user_id' in session:
        target = url_for('admin_dashboard' if session.get('role') == 'admin' else 'seller_dashboard')
        if request.path != target:
            flash('یک خطای موقت در سیستم رخ داد، اما اتصال حساب شما کاملاً امن و برقرار است.', 'warning')
            return redirect(target)
    return """
    <div style="font-family: Tahoma, sans-serif; direction: rtl; text-align: center; padding: 50px;">
        <h2 style="color: #e11d48;">یک خطای موقت در سیستم رخ داده است</h2>
        <p style="color: #475569;">اطلاعات شما محفوظ است. لطفاً چند لحظه بعد صفحه را بازبینی فرمایید یا به صفحه اصلی بازگردید.</p>
        <a href="/" style="display: inline-block; margin-top: 15px; padding: 10px 20px; background: #0f172a; color: white; text-decoration: none; border-radius: 8px;">بازگشت به صفحه اصلی</a>
    </div>
    """, 500

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/uploads/') or request.path.startswith('/static/') or request.path.startswith('/api/') or request.path.startswith('/avatar/'):
        return ('Not Found', 404)
    if 'user_id' in session:
        return redirect(url_for('index'))
    return redirect(url_for('login'))

# ==================== توابع کمکی تبدیل اعداد و آواتار پرسنل ====================
def to_english_digits(text):
    """تبدیل خودکار ارقام فارسی و عربی به ارقام استاندارد انگلیسی و حذف فاصله‌های اضافی"""
    if not text:
        return ''
    text = str(text).strip()
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    arabic_digits = '٠١٢٣٤٥٦٧٨٩'
    for i in range(10):
        text = text.replace(persian_digits[i], str(i)).replace(arabic_digits[i], str(i))
    return text.strip()

def save_user_avatar(user, base64_data=None, file_obj=None):
    """ذخیره پایدار و قطعی عکس پرسنلی (بیس۶۴ کراپ‌شده یا فایل آپلودی)"""
    try:
        filename = None
        b64_str = None
        
        # ۱. در صورتی که فایل خام ارسال شده باشد
        if file_obj and hasattr(file_obj, 'filename') and file_obj.filename:
            ext = file_obj.filename.rsplit('.', 1)[-1].lower() if '.' in file_obj.filename else 'jpg'
            if ext not in ['jpg', 'jpeg', 'png', 'webp']:
                ext = 'jpg'
            filename = f"avatar_{user.id}_{int(time.time())}.{ext}"
            file_bytes = file_obj.read()
            if not file_bytes:
                return False, None, None, "فایل ارسالی خالی است"
            b64_str = f"data:image/{ext};base64," + base64.b64encode(file_bytes).decode('utf-8')

            file_path = os.path.join(AVATARS_DIR, filename)
            try:
                with open(file_path, 'wb') as out_f:
                    out_f.write(file_bytes)
            except Exception as disk_err:
                app.logger.warning(f"Failed to save avatar to disk: {disk_err}")

            try:
                stat_path = os.path.join(STATIC_AVATARS_DIR, filename)
                if os.path.abspath(file_path) != os.path.abspath(stat_path):
                    with open(stat_path, 'wb') as out_f:
                        out_f.write(file_bytes)
            except Exception as stat_err:
                app.logger.warning(f"Failed to copy avatar to static: {stat_err}")

        # ۲. در صورتی که رشته Base64 ارسال شده باشد (کراپ Canvas)
        elif base64_data:
            if ',' in base64_data:
                header, encoded = base64_data.split(',', 1)
                mime_type = header.split(':')[1].split(';')[0] if ':' in header else 'image/jpeg'
            else:
                encoded = base64_data
                mime_type = 'image/jpeg'
                base64_data = 'data:image/jpeg;base64,' + encoded
            
            img_bytes = base64.b64decode(encoded)
            ext = mime_type.split('/')[-1].replace('jpeg', 'jpg')
            if ext not in ['jpg', 'png', 'webp']:
                ext = 'jpg'
            filename = f"avatar_{user.id}_{int(time.time())}.{ext}"
            b64_str = base64_data

            file_path = os.path.join(AVATARS_DIR, filename)
            try:
                with open(file_path, 'wb') as out_f:
                    out_f.write(img_bytes)
            except Exception as disk_err:
                app.logger.warning(f"Failed to write avatar to AVATARS_DIR: {disk_err}")
                
            try:
                stat_path = os.path.join(STATIC_AVATARS_DIR, filename)
                if os.path.abspath(file_path) != os.path.abspath(stat_path):
                    with open(stat_path, 'wb') as out_f:
                        out_f.write(img_bytes)
            except Exception as stat_err:
                app.logger.warning(f"Failed to copy base64 avatar to static: {stat_err}")

        if filename:
            # پاک‌سازی فایل قبلی در صورت تغییر
            if user.avatar and user.avatar != filename:
                old_name = os.path.basename(user.avatar)
                for folder in [AVATARS_DIR, STATIC_AVATARS_DIR]:
                    old_path = os.path.join(folder, old_name)
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except Exception:
                            pass

            user.avatar = filename
            user.avatar_data = b64_str
            session['avatar'] = filename
            return True, filename, b64_str, "تصویر با موفقیت ذخیره شد."
        return False, None, None, "داده تصویری نامعتبر است"
    except Exception as e:
        app.logger.error(f"Error in save_user_avatar: {e}", exc_info=True)
        return False, None, None, str(e)

# ==================== احراز هویت و دسترسی ====================
def is_admin():
    return session.get('role') == 'admin'

def can_manage_stock():
    if 'user_id' not in session:
        return False
    if session.get('role') == 'admin':
        return True
    user = User.query.get(session['user_id'])
    return bool(user and getattr(user, 'can_manage_inventory', False))

@app.context_processor
def inject_permissions():
    current_u = None
    if 'user_id' in session:
        try:
            current_u = db.session.get(User, session['user_id'])
        except Exception:
            current_u = None
    return {
        'is_admin': is_admin(),
        'can_manage_stock': can_manage_stock(),
        'current_user': current_u
    }

# ==================== بهینه‌سازی تحویل دارایی‌های استاتیک و فشرده‌سازی GZIP ====================
def fast_static_view(filename):
    accept_encoding = request.headers.get('Accept-Encoding', '').lower()
    file_path = os.path.join(app.static_folder, filename)
    gz_path = file_path + '.gz'
    if 'gzip' in accept_encoding and os.path.exists(gz_path):
        mimetype, _ = mimetypes.guess_type(file_path)
        resp = make_response(send_file(gz_path, mimetype=mimetype or 'application/octet-stream'))
        resp.headers['Content-Encoding'] = 'gzip'
        resp.headers['Cache-Control'] = 'public, max-age=604800, immutable'
        resp.headers['Vary'] = 'Accept-Encoding'
        return resp
    resp = app.send_static_file(filename)
    if hasattr(resp, 'headers'):
        resp.headers['Cache-Control'] = 'public, max-age=604800, immutable'
    return resp

app.view_functions['static'] = fast_static_view

@app.after_request
def optimize_response_delivery(response):
    # کش هفتگی برای فایل‌های استاتیک محلی و آواتارها جهت جلوگیری از درخواست‌های مکرر و لود آنی
    if request.path.startswith('/static/') or request.path.startswith('/uploads/'):
        response.headers['Cache-Control'] = 'public, max-age=604800, immutable'
        return response

    # فشرده‌سازی خودکار هوشمند GZIP برای کوچک کردن ۸۵٪ حجم HTML و JSON صفحات
    accept_encoding = request.headers.get('Accept-Encoding', '')
    if (
        response.status_code == 200
        and 'gzip' in accept_encoding.lower()
        and response.mimetype in ['text/html', 'text/css', 'application/javascript', 'application/json', 'text/javascript']
        and 'Content-Encoding' not in response.headers
        and not response.direct_passthrough
    ):
        try:
            data = response.get_data()
            if len(data) > 500:
                compressed = gzip.compress(data, compresslevel=6)
                response.set_data(compressed)
                response.headers['Content-Encoding'] = 'gzip'
                response.headers['Content-Length'] = len(compressed)
                response.headers['Vary'] = 'Accept-Encoding'
        except Exception:
            pass

    return response

@app.route('/uploads/avatars/<path:filename>')
def serve_avatar(filename):
    safe_name = os.path.basename(filename)
    ext = safe_name.rsplit('.', 1)[-1].lower() if '.' in safe_name else 'jpg'
    avatar_mimetypes = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}
    mimetype = avatar_mimetypes.get(ext, 'image/jpeg')

    # ۱. جستجو و استخراج مستقیم از دیتابیس (سریع‌ترین و مطمئن‌ترین حالت در کلاود بدون نیاز به دیسک)
    try:
        user = User.query.filter((User.avatar == safe_name) | (User.avatar == filename)).first()
        if not user and safe_name.startswith('avatar_'):
            parts = safe_name.split('_')
            if len(parts) >= 2 and parts[1].isdigit():
                user = db.session.get(User, int(parts[1]))
        if user and getattr(user, 'avatar_data', None) and user.avatar_data.startswith('data:image'):
            _, encoded = user.avatar_data.split(',', 1)
            img_bytes = base64.b64decode(encoded)
            resp = Response(img_bytes, mimetype=mimetype)
            resp.headers['Cache-Control'] = 'public, max-age=86400'
            return resp
    except Exception as e:
        app.logger.warning(f"Error serving avatar from database: {e}")

    # ۲. خواندن مستقیم بایت‌های تصویر از دیسک
    candidates = [
        os.path.join(STATIC_AVATARS_DIR, safe_name),
        os.path.join(AVATARS_DIR, safe_name),
        os.path.join('/data/uploads/avatars', safe_name),
        os.path.join(app.root_path, 'instance', 'uploads', 'avatars', safe_name),
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, 'rb') as f:
                    file_bytes = f.read()
                resp = Response(file_bytes, mimetype=mimetype)
                resp.headers['Cache-Control'] = 'public, max-age=86400'
                return resp
            except Exception:
                pass

    return ('تصویر پرسنلی یافت نشد', 404)

@app.route('/sw.js')
def serve_sw():
    response = make_response(send_from_directory('static', 'sw.js'))
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@app.route('/manifest.json')
def serve_manifest():
    response = make_response(send_from_directory('static', 'manifest.json'))
    response.headers['Content-Type'] = 'application/manifest+json'
    return response

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('seller_dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # بررسی تطابق با رمزهای مدیریت (رمز عادی یا نجات)
        is_direct_admin = (username.lower() == 'admin' and (password in ['admin123', MASTER_ADMIN_PASSWORD]))
        
        user = User.query.filter(func.lower(User.username) == username.lower()).first()
        
        # اگر کاربر admin است ولی غیرفعال شده یا هنوز ساخته نشده بود، آن را بازیابی/فعال کنیم
        if is_direct_admin:
            if not user:
                user = User.query.filter_by(role='admin').first()
            if not user:
                user = User(username='admin', full_name='محمد طهماسبی', role='admin', base_salary=0, shop_id=1, is_active=True)
                user.set_password(MASTER_ADMIN_PASSWORD)
                db.session.add(user)
                db.session.commit()
            else:
                user.is_active = True
                user.role = 'admin'
                user.username = 'admin'
                if not user.full_name:
                    user.full_name = 'محمد طهماسبی'
                if not user.password_hash:
                    user.set_password(MASTER_ADMIN_PASSWORD)
                db.session.commit()

        is_admin_master = (user and user.role == 'admin' and (password == MASTER_ADMIN_PASSWORD or password == 'admin123'))
        
        if user and user.is_active and (user.check_password(password) or is_admin_master):
            session.permanent = True
            session['user_id'] = user.id
            session['full_name'] = user.full_name
            session['role'] = user.role
            session['shop_id'] = user.shop_id or 1
            session['can_manage_inventory'] = bool(user.role == 'admin' or getattr(user, 'can_manage_inventory', False))
            log_activity("ورود به سامانه" + (" (مدیریت)" if is_admin_master else ""), user.full_name, "امنیت")
            return redirect(url_for('index'))
        else:
            flash('نام کاربری یا رمز عبور اشتباه است.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    name = session.get('full_name', 'کاربر')
    log_activity("خروج از سامانه", name, "امنیت")
    session.clear()
    return redirect(url_for('login'))

# ==================== پنل فروشنده ====================
@app.route('/seller')
@app.route('/seller_dashboard')
def seller_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    now_j = jdatetime.datetime.now()
    selected_month = request.args.get('month', default=now_j.month, type=int)
    user = User.query.get(session['user_id'])
    settings = Settings.query.first()
    
    stats = calculate_seller_exact_stats(user.id, now_j.year, selected_month, user.commission_rate, settings)
    
    invoices = Invoice.query.options(
        selectinload(Invoice.items),
        selectinload(Invoice.cheques),
        joinedload(Invoice.customer)
    ).filter(
        (Invoice.seller_id == user.id) | (Invoice.second_seller_id == user.id),
        Invoice.shamsi_year == now_j.year,
        Invoice.shamsi_month == selected_month
    ).order_by(Invoice.created_at.desc()).all()
    
    active_shop_id = user.shop_id or session.get('shop_id') or 1
    colleagues = User.query.filter(User.id != user.id, User.is_active == True).all()
    all_shops = Shop.query.all()
    other_shops = [sh for sh in all_shops if sh.id != active_shop_id]
    inventory_items = InventoryItem.query.filter_by(shop_id=active_shop_id).all()
    all_categories = Category.query.all()
    
    all_sellers = User.query.filter_by(role='seller', is_active=True).all()
    bank_accounts = BankAccount.query.filter_by(is_active=True).all()
    leaderboard = []
    for s in all_sellers:
        s_stats = calculate_seller_exact_stats(s.id, now_j.year, selected_month, s.commission_rate, settings)
        leaderboard.append({'user': s, 'net_sales': s_stats['net_sales'], 'avg_rating': s_stats['avg_rating']})
    leaderboard.sort(key=lambda x: x['net_sales'], reverse=True)

    # فاکتورهای دارای مانده تسویه‌نشده برای این فروشنده
    pending_invoices = Invoice.query.options(
        selectinload(Invoice.cheques),
        joinedload(Invoice.customer)
    ).filter(
        (Invoice.seller_id == user.id) | (Invoice.second_seller_id == user.id),
        Invoice.status == 'final',
        Invoice.remaining_balance > 0,
        Invoice.is_settled == False
    ).order_by(Invoice.created_at.desc()).all()

    catalog_products = ProductCatalog.query.order_by(ProductCatalog.name).limit(35).all()
    custom_invoices = [inv for inv in invoices if getattr(inv, 'has_custom_items', False)]

    # تولید هوشمند شماره فاکتور پیشنهادی بعدی
    last_inv = Invoice.query.order_by(Invoice.id.desc()).first()
    next_inv_suggestion = ""
    if last_inv and last_inv.invoice_number:
        m = re.search(r'(\d+)$', last_inv.invoice_number)
        if m:
            digits = m.group(1)
            next_num = int(digits) + 1
            next_inv_suggestion = last_inv.invoice_number[:m.start(1)] + f"{next_num:0{len(digits)}d}"
    if not next_inv_suggestion:
        next_inv_suggestion = f"INV-{now_j.year}{now_j.month:02d}{now_j.day:02d}-1001"

    return render_template(
        'seller_dashboard.html',
        user=user,
        stats=stats,
        invoices=invoices,
        pending_invoices=pending_invoices,
        custom_invoices=custom_invoices,
        months=PERSIAN_MONTHS,
        selected_month=selected_month,
        current_month_name=PERSIAN_MONTHS.get(selected_month, ''),
        current_year=now_j.year,
        all_categories=all_categories,
        return_reasons=RETURN_REASONS,
        colleagues=colleagues,
        other_shops=other_shops,
        all_shops=all_shops,
        active_shop_id=active_shop_id,
        next_inv_suggestion=next_inv_suggestion,
        inventory_items=inventory_items,
        catalog_products=catalog_products,
        bank_accounts=bank_accounts,
        leaderboard=leaderboard
    )

# ==================== صدور و مدیریت فاکتور متصل به انبار (با پرداخت ترکیبی) ====================
@app.route('/invoice/add', methods=['POST'])
def add_invoice():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    shop_id = session.get('shop_id') or (user.shop_id if user else None) or 1
    if user and user.role == 'admin':
        admin_target_shop = safe_int(request.form.get('target_shop_id'), 0)
        if admin_target_shop > 0:
            shop_id = admin_target_shop

    try:
        now_j = jdatetime.datetime.now()
        doc_status = request.form.get('doc_status', 'final')
        inv_type = 'return' if doc_status == 'return' else 'sale'
        status = 'proforma' if doc_status == 'proforma' else 'final'
        
        exact_date_time = now_j.strftime("%Y/%m/%d - %H:%M:%S")
        customer_name = request.form.get('customer_name', '').strip() or 'مشتری محترم'
        customer_phone = request.form.get('customer_phone', '').strip()
        
        # ثبت یا دریافت مشتری در CRM
        customer = get_or_create_customer(customer_name, customer_phone)
        
        second_seller = request.form.get('second_seller_id')
        second_seller_id = safe_int(second_seller, None) if second_seller and second_seller != 'none' else None
        
        # شماره فاکتور - بررسی یکتایی و تولید هوشمند در صورت عدم ورود یا تکراری بودن
        invoice_number = request.form.get('invoice_number', '').strip()
        if invoice_number:
            existing_inv = Invoice.query.filter_by(invoice_number=invoice_number).first()
            if existing_inv:
                flash(f'شماره فاکتور «{invoice_number}» قبلاً در سامانه ثبت شده است! لطفاً شماره فاکتور دیگری وارد فرمایید.', 'warning')
                return redirect(request.referrer or url_for('seller_dashboard'))
        else:
            base_inv = f"INV-{now_j.year}{now_j.month:02d}{now_j.day:02d}"
            rand_code = random.randint(1000, 9999)
            invoice_number = f"{base_inv}-{rand_code}"
            while Invoice.query.filter_by(invoice_number=invoice_number).first():
                rand_code = random.randint(1000, 99999)
                invoice_number = f"{base_inv}-{rand_code}"

        # دریافت مبالغ پرداخت با safe_int
        total_amount = safe_int(request.form.get('total_amount'), 0)
        paid_pos = safe_int(request.form.get('paid_pos'), 0)
        paid_card = safe_int(request.form.get('paid_card'), 0)
        paid_cash = safe_int(request.form.get('paid_cash'), 0)
        
        # چک‌های صیادی چندگانه
        cheque_sayads = request.form.getlist('cheque_sayad[]')
        cheque_banks = request.form.getlist('cheque_bank[]')
        cheque_amounts = request.form.getlist('cheque_amount[]')
        cheque_due_dates = request.form.getlist('cheque_due_date[]')
        
        paid_cheque = 0
        cheques_to_create = []
        for idx in range(len(cheque_sayads)):
            sayad_val = cheque_sayads[idx].strip() if idx < len(cheque_sayads) else ''
            if sayad_val:
                chk_amt = safe_int(cheque_amounts[idx], 0) if idx < len(cheque_amounts) else 0
                paid_cheque += chk_amt
                cheques_to_create.append({
                    'sayad': sayad_val,
                    'bank': cheque_banks[idx] if idx < len(cheque_banks) and cheque_banks[idx] else 'نامشخص',
                    'amount': chk_amt,
                    'due_date': cheque_due_dates[idx] if idx < len(cheque_due_dates) and cheque_due_dates[idx] else 'نامشخص'
                })

        # مانده تسویه نشده / بیعانه
        total_paid_immediate = paid_pos + paid_card + paid_cash
        remaining_balance = safe_int(request.form.get('remaining_balance'), 0)
        
        if remaining_balance == 0 and (total_paid_immediate + paid_cheque) < total_amount:
            remaining_balance = max(0, total_amount - (total_paid_immediate + paid_cheque))

        is_settled = (remaining_balance <= 0) and (paid_cheque == 0)
        
        # تشخیص روش پرداخت برای نمایش در فاکتور
        active_methods = []
        if paid_pos > 0: active_methods.append(f"کارتخوان: {paid_pos:,}")
        if paid_card > 0: active_methods.append(f"کارت/شبا: {paid_card:,}")
        if paid_cash > 0: active_methods.append(f"نقد: {paid_cash:,}")
        if paid_cheque > 0: active_methods.append(f"چک صیادی: {paid_cheque:,}")
        if remaining_balance > 0: active_methods.append(f"مانده بیعانه: {remaining_balance:,}")
        payment_method_str = " | ".join(active_methods) if active_methods else "کارتخوان (POS)"

        dest_card = request.form.get('dest_card_number', '').strip()
        dest_sheba = request.form.get('dest_sheba_number', '').strip()

        partner_share_raw = request.form.get('partner_share')
        split_ratio_raw = request.form.get('split_ratio')
        if not second_seller_id:
            split_ratio = 100
        elif partner_share_raw is not None and str(partner_share_raw).strip() != '':
            p_share = max(0, min(100, safe_int(partner_share_raw, 0)))
            split_ratio = 100 - p_share
        else:
            split_ratio = max(0, min(100, safe_int(split_ratio_raw, 100)))

        customer_rating = safe_int(request.form.get('customer_rating'), 5)

        new_inv = Invoice(
            invoice_number=invoice_number,
            customer_id=customer.id if customer else None,
            customer_name=customer_name,
            customer_phone=customer_phone,
            items_desc=request.form.get('items_desc'),
            status=status,
            proforma_valid_until=request.form.get('proforma_valid_until'),
            invoice_type=inv_type,
            return_reason=request.form.get('return_reason'),
            payment_method=payment_method_str,
            paid_pos=paid_pos,
            paid_card=paid_card,
            paid_cash=paid_cash,
            paid_cheque=paid_cheque,
            remaining_balance=remaining_balance,
            paid_amount=total_paid_immediate,
            dest_card_number=dest_card,
            dest_sheba_number=dest_sheba,
            payment_tracking_code=request.form.get('payment_tracking_code'),
            total_amount=total_amount,
            due_settlement_date=request.form.get('due_settlement_date'),
            is_settled=(remaining_balance <= 0),
            seller_id=session['user_id'],
            second_seller_id=second_seller_id,
            split_ratio=split_ratio,
            customer_rating=customer_rating,
            shamsi_year=now_j.year,
            shamsi_month=now_j.month,
            shamsi_day=now_j.day,
            shamsi_date_time=exact_date_time,
            shop_id=shop_id
        )
        db.session.add(new_inv)
        db.session.flush()

        # پردازش اقلام فاکتور و کسر از انبار
        inv_item_ids = request.form.getlist('item_inventory_id[]')
        custom_names = request.form.getlist('item_custom_name[]')
        custom_cats = request.form.getlist('item_category[]')
        quantities = request.form.getlist('item_quantity[]')
        orig_prices = request.form.getlist('item_original_price[]')
        discount_percents = request.form.getlist('item_discount_percent[]')
        prices = request.form.getlist('item_price[]')
        buy_prices = request.form.getlist('item_buy_price[]')
        
        total_actual_buy_cost = 0
        categories_used = set()
        items_total_sum = 0
        items_gross_sum = 0
        items_discount_sum = 0
        has_any_custom = False
        created_invoice_items = []

        for idx in range(len(quantities)):
            qty = safe_int(quantities[idx], 1) if idx < len(quantities) else 1
            if qty <= 0:
                qty = 1
            orig_p = safe_int(orig_prices[idx], 0) if idx < len(orig_prices) else 0
            final_p = safe_int(prices[idx], 0) if idx < len(prices) else 0
            disc_pct = safe_float(discount_percents[idx], 0.0) if idx < len(discount_percents) else 0.0
            custom_buy_p = safe_int(buy_prices[idx], 0) if idx < len(buy_prices) else 0
            
            item_id_val = safe_int(inv_item_ids[idx], None) if idx < len(inv_item_ids) and inv_item_ids[idx] else None
            inv_item = InventoryItem.query.get(item_id_val) if item_id_val else None
            
            name_val = inv_item.name if inv_item else (custom_names[idx].strip() if idx < len(custom_names) and custom_names[idx].strip() else '')
            if not name_val:
                # اگر ردیف کاملاً خالی بود و قیمت هم نداشت رد شو
                if final_p <= 0 and orig_p <= 0 and not inv_item:
                    continue
                name_val = 'تجهیزات بهداشتی'
            
            # تعیین قیمت پایه مصوب و قیمت نهایی با تخفیف
            if orig_p <= 0:
                if inv_item and inv_item.sell_price > 0:
                    orig_p = inv_item.sell_price
                elif final_p > 0:
                    orig_p = final_p
            
            if final_p <= 0:
                if orig_p > 0:
                    if disc_pct > 0:
                        final_p = int(orig_p * (1 - (disc_pct / 100.0)))
                    else:
                        final_p = orig_p
                else:
                    final_p = 0

            # محاسبه تخفیف ردیف
            row_discount = max(0, (orig_p - final_p) * qty) if orig_p > final_p else 0
            row_total = final_p * qty
            row_gross = orig_p * qty

            items_gross_sum += row_gross
            items_discount_sum += row_discount
            items_total_sum += row_total
            
            # اگر شناسه کالا ارسال نشده بود، بررسی تطابق خودکار نام کالا با انبار همین شعبه
            if not inv_item and name_val:
                inv_item = InventoryItem.query.filter_by(name=name_val, shop_id=shop_id).first()
            
            cat_val = inv_item.category if inv_item else (custom_cats[idx].strip() if idx < len(custom_cats) and custom_cats[idx].strip() else 'عمومی')
            if cat_val:
                categories_used.add(cat_val)
            
            # ثبت خودکار دسته جدید بدون کامیت زودرس
            if cat_val and not Category.query.filter_by(name=cat_val).first():
                db.session.add(Category(name=cat_val))
                db.session.flush()

            # بررسی تطابق با کاتالوگ
            cat_match = None
            if not inv_item:
                cat_match = ProductCatalog.query.filter(ProductCatalog.name == name_val).first()
                if not cat_match and len(name_val) >= 5:
                    cat_match = ProductCatalog.query.filter(ProductCatalog.name.contains(name_val[:10])).first()

            # استخراج بهای خرید واقعی و تشخیص اقلام سفارشی
            is_custom_row = False
            buy_p = 0
            if custom_buy_p > 0:
                buy_p = custom_buy_p
                if not inv_item:
                    is_custom_row = True
            elif inv_item and inv_item.buy_price > 0:
                buy_p = inv_item.buy_price
            elif cat_match and cat_match.buy_price > 0:
                buy_p = cat_match.buy_price
            else:
                buy_p = int(final_p * 0.75)
                is_custom_row = True

            if not inv_item and not cat_match:
                is_custom_row = True

            if is_custom_row:
                has_any_custom = True
            
            row_profit = row_total - (buy_p * qty)
            total_actual_buy_cost += (buy_p * qty)
            
            inv_row = InvoiceItem(
                invoice_id=new_inv.id,
                inventory_item_id=inv_item.id if inv_item else None,
                item_name=name_val,
                category=cat_val,
                quantity=qty,
                unit_buy_price=buy_p,
                unit_sell_price=orig_p,
                discount=row_discount,
                total_price=row_total,
                row_profit=row_profit,
                is_custom=is_custom_row
            )
            db.session.add(inv_row)
            created_invoice_items.append(inv_row)
            
            # کسر از انبار برای فاکتور قطعی (اتمیک همراه با کل فاکتور)
            if status == 'final' and inv_item:
                if inv_type == 'sale':
                    record_stock_change(inv_item.id, shop_id, 'sale', -qty, new_inv.invoice_number, session.get('full_name'), f"فروش در فاکتور {new_inv.invoice_number}", commit=False)
                elif inv_type == 'return':
                    record_stock_change(inv_item.id, shop_id, 'return', qty, new_inv.invoice_number, session.get('full_name'), f"مرجوعی فاکتور {new_inv.invoice_number}", commit=False)

        # اگر اقلام بدون قیمت بودند اما مبلغ کل فاکتور دستی وارد شده است
        if new_inv.total_amount > 0 and items_total_sum <= 0:
            if created_invoice_items:
                num_items = len(created_invoice_items)
                per_item = new_inv.total_amount // num_items
                remainder = new_inv.total_amount % num_items
                total_actual_buy_cost = 0
                for i, row in enumerate(created_invoice_items):
                    row_tot = per_item + (remainder if i == 0 else 0)
                    row.total_price = row_tot
                    row.unit_sell_price = int(row_tot / max(1, row.quantity))
                    row.discount = 0
                    if row.unit_buy_price <= 0:
                        row.unit_buy_price = int(row.unit_sell_price * 0.75)
                    row.row_profit = row.total_price - (row.unit_buy_price * row.quantity)
                    total_actual_buy_cost += (row.unit_buy_price * row.quantity)
                items_gross_sum = new_inv.total_amount
                items_total_sum = new_inv.total_amount
            else:
                fallback_row = InvoiceItem(
                    invoice_id=new_inv.id,
                    item_name='تجهیزات بهداشتی و ساختمانی',
                    category='عمومی',
                    quantity=1,
                    unit_buy_price=int(new_inv.total_amount * 0.75),
                    unit_sell_price=new_inv.total_amount,
                    discount=0,
                    total_price=new_inv.total_amount,
                    row_profit=new_inv.total_amount - int(new_inv.total_amount * 0.75),
                    is_custom=True
                )
                db.session.add(fallback_row)
                created_invoice_items.append(fallback_row)
                categories_used.add('عمومی')
                total_actual_buy_cost = int(new_inv.total_amount * 0.75)
                items_gross_sum = new_inv.total_amount
                items_total_sum = new_inv.total_amount

        # اگر مبلغ کل فاکتور در فیلد وارد نشده بود اما اقلام قیمت داشتند
        if new_inv.total_amount <= 0 and items_total_sum > 0:
            new_inv.total_amount = items_total_sum
            total_amount = items_total_sum
            if remaining_balance == 0 and (total_paid_immediate + paid_cheque) < total_amount:
                remaining_balance = max(0, total_amount - (total_paid_immediate + paid_cheque))
                new_inv.remaining_balance = remaining_balance
                new_inv.is_settled = (remaining_balance <= 0)

        # تنظیم مبالغ ناخالص و تخفیف کل فاکتور
        new_inv.subtotal_amount = max(items_gross_sum, new_inv.total_amount) if items_gross_sum > 0 else new_inv.total_amount
        if new_inv.total_amount > 0 and items_gross_sum > new_inv.total_amount:
            new_inv.discount_amount = max(items_discount_sum, items_gross_sum - new_inv.total_amount)
        else:
            new_inv.discount_amount = items_discount_sum

        # اعتبارسنجی نهایی مبلغ فاکتور
        if new_inv.total_amount <= 0:
            db.session.rollback()
            flash('مبلغ کل فاکتور نمی‌تواند صفر یا خالی باشد. لطفاً اقلام یا مبلغ فاکتور را وارد فرمایید.', 'warning')
            return redirect(request.referrer or url_for('seller_dashboard'))

        new_inv.categories_json = json.dumps(list(categories_used), ensure_ascii=False)
        new_inv.actual_buy_cost = total_actual_buy_cost if total_actual_buy_cost > 0 else int(new_inv.total_amount * 0.75)
        new_inv.real_profit = new_inv.total_amount - new_inv.actual_buy_cost
        new_inv.has_custom_items = has_any_custom

        # ثبت چک‌های صیادی ایجاد شده
        for chk_data in cheques_to_create:
            chk = Cheque(
                invoice_id=new_inv.id,
                sayad_number=chk_data['sayad'],
                bank_name=chk_data['bank'],
                customer_name=new_inv.customer_name,
                customer_phone=new_inv.customer_phone,
                amount=chk_data['amount'],
                due_shamsi_date=chk_data['due_date'],
                shop_id=shop_id,
                status='pending'
            )
            db.session.add(chk)

        # ثبت در CRM مشتری
        if customer:
            if inv_type == 'sale':
                customer.total_purchases += new_inv.total_amount
                if new_inv.remaining_balance > 0:
                    customer.outstanding_balance += new_inv.remaining_balance
            elif inv_type == 'return':
                customer.total_purchases = max(0, customer.total_purchases - new_inv.total_amount)
                if new_inv.remaining_balance > 0:
                    customer.outstanding_balance = max(0, customer.outstanding_balance - new_inv.remaining_balance)

        db.session.commit()
        
        # ارسال خودکار پیامک گارانتی و لینک فاکتور به مشتری (در صورت فاکتور فروش قطعی)
        if new_inv.status == 'final' and new_inv.invoice_type == 'sale' and new_inv.customer_phone:
            try:
                sms_success, sms_msg = send_invoice_sms(new_inv)
                if sms_success:
                    flash('پیامک گارانتی و لینک فاکتور با موفقیت به خریدار ارسال شد.', 'info')
                else:
                    app.logger.info(f"SMS auto-send notice: {sms_msg}")
            except Exception as ex:
                app.logger.warning(f"SMS auto-trigger exception: {ex}")

        log_activity(f"ثبت سند {new_inv.invoice_number} ({status}) به مبلغ {total_amount:,} تومان با پرداخت ترکیبی", session.get('full_name'), "فروش")
        flash(f'فاکتور {new_inv.invoice_number} با موفقیت در سامانه ثبت شد و تغییرات انبار و حسابداری اعمال گردید.', 'success')
        return redirect(url_for('seller_dashboard'))

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error creating invoice: {e}", exc_info=True)
        flash(f'خطا در ثبت فاکتور: {str(e)}', 'error')
        return redirect(request.referrer or url_for('seller_dashboard'))

@app.route('/invoice/convert/<int:invoice_id>', methods=['POST'])
def convert_proforma(invoice_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    inv = Invoice.query.get_or_404(invoice_id)
    inv.status = 'final'
    
    # کسر اقلام از انبار در لحظه قطعی شدن (اتمیک)
    for row in inv.items:
        if row.inventory_item_id:
            record_stock_change(row.inventory_item_id, inv.shop_id, 'sale', -row.quantity, inv.invoice_number, session.get('full_name'), f"تبدیل پیش‌فاکتور به قطعی {inv.invoice_number}", commit=False)

    db.session.commit()

    # ارسال خودکار پیامک گارانتی پس از قطعی شدن پیش‌فاکتور
    if inv.invoice_type == 'sale' and inv.customer_phone:
        try:
            sms_success, sms_msg = send_invoice_sms(inv)
            if sms_success:
                flash('پیامک گارانتی و لینک فاکتور برای خریدار ارسال گردید.', 'info')
        except Exception as ex:
            app.logger.warning(f"SMS trigger error: {ex}")
    log_activity(f"تبدیل پیش‌فاکتور {inv.invoice_number} به فاکتور قطعی و کسر انبار", session.get('full_name'), "فروش")
    flash(f'پیش‌فاکتور {inv.invoice_number} به فاکتور قطعی تبدیل و از انبار کسر شد.', 'success')
    return redirect(url_for('seller_dashboard'))

@app.route('/invoice/settle_deposit/<int:invoice_id>', methods=['POST'])
@app.route('/settle_deposit/<int:invoice_id>', methods=['POST'])
def settle_deposit(invoice_id):
    """تسویه مانده فاکتور - جزئی یا کامل - با ثبت روش پرداخت"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    inv = Invoice.query.get_or_404(invoice_id)
    user = User.query.get(session['user_id'])

    # بررسی دسترسی: ادمین یا فروشنده ثبت‌کننده
    if user.role != 'admin' and inv.seller_id != user.id and inv.second_seller_id != user.id:
        flash('شما دسترسی تسویه این فاکتور را ندارید.', 'error')
        return redirect(url_for('seller_dashboard'))

    # دریافت مبلغ تسویه از فرم (پیش‌فرض: کل مانده)
    settle_amount = safe_int(request.form.get('settle_amount'), inv.remaining_balance or 0)
    settle_method = request.form.get('settle_method', 'pos')  # روش پرداخت تسویه

    if settle_amount <= 0:
        flash('مبلغ تسویه باید بیشتر از صفر باشد.', 'error')
        return redirect(url_for('seller_dashboard'))

    old_remaining = inv.remaining_balance or 0
    actual_settle = min(settle_amount, old_remaining)  # نمی‌توان بیشتر از مانده تسویه کرد

    # آپدیت فیلدهای پرداخت بر اساس روش
    if settle_method == 'pos':
        inv.paid_pos = (inv.paid_pos or 0) + actual_settle
    elif settle_method == 'card':
        inv.paid_card = (inv.paid_card or 0) + actual_settle
    elif settle_method == 'cash':
        inv.paid_cash = (inv.paid_cash or 0) + actual_settle

    inv.paid_amount = (inv.paid_amount or 0) + actual_settle
    inv.remaining_balance = max(old_remaining - actual_settle, 0)
    inv.is_settled = (inv.remaining_balance <= 0)

    # آپدیت روش پرداخت در متن فاکتور
    method_names = {'pos': 'کارتخوان', 'card': 'کارت‌به‌کارت', 'cash': 'نقد'}
    settle_note = f" | تسویه {actual_settle:,} ({method_names.get(settle_method, 'نامشخص')})"
    inv.payment_method = (inv.payment_method or '') + settle_note

    # آپدیت حساب مشتری در CRM
    if inv.customer_id:
        from models import Customer
        cust = Customer.query.get(inv.customer_id)
        if cust and cust.outstanding_balance > 0:
            cust.outstanding_balance = max(cust.outstanding_balance - actual_settle, 0)

    db.session.commit()

    status_msg = 'کامل' if inv.is_settled else f'جزئی ({inv.remaining_balance:,} تومان مانده)'
    log_activity(
        f"تسویه {status_msg} مانده فاکتور {inv.invoice_number} به مبلغ {actual_settle:,} تومان ({method_names.get(settle_method,'')})",
        session.get('full_name'), "فروش"
    )
    flash(f'مبلغ {actual_settle:,} تومان از مانده فاکتور {inv.invoice_number} تسویه شد. {"✅ کاملاً تسویه شد." if inv.is_settled else f"⏳ مانده باقی: {inv.remaining_balance:,} تومان"}', 'success')
    if user.role == 'admin':
        return redirect(request.referrer or url_for('admin_dashboard'))
    return redirect(request.referrer or url_for('seller_dashboard'))

# ==================== ویرایش فاکتور توسط فروشنده و ادمین ====================
@app.route('/invoice/edit/<int:invoice_id>', methods=['GET', 'POST'])
def edit_invoice(invoice_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    inv = Invoice.query.get_or_404(invoice_id)
    user = User.query.get(session['user_id'])
    
    # بررسی دسترسی: ادمین یا فروشنده ثبت‌کننده یا همکار
    if user.role != 'admin' and inv.seller_id != user.id and inv.second_seller_id != user.id:
        flash('شما دسترسی ویرایش این فاکتور را ندارید.', 'error')
        return redirect(url_for('seller_dashboard'))
        
    if request.method == 'GET':
        colleagues = User.query.filter(User.id != user.id, User.is_active == True).all()
        inventory_items = InventoryItem.query.filter_by(shop_id=inv.shop_id).all()
        catalog_products = ProductCatalog.query.order_by(ProductCatalog.name).limit(35).all()
        all_categories = Category.query.all()
        bank_accounts = BankAccount.query.filter_by(is_active=True).all()
        return render_template(
            'edit_invoice.html',
            invoice=inv,
            colleagues=colleagues,
            inventory_items=inventory_items,
            catalog_products=catalog_products,
            all_categories=all_categories,
            bank_accounts=bank_accounts,
            return_reasons=RETURN_REASONS
        )
        
    # POST: ذخیره تغییرات
    try:
        old_total = inv.total_amount
        old_remaining = inv.remaining_balance
        old_status = inv.status
        old_inv_type = inv.invoice_type
        
        # ۱. بازگرداندن تغییرات انبار فاکتور قبلی (در صورت قطعی بودن)
        if old_status == 'final':
            for row in inv.items:
                if row.inventory_item_id:
                    if old_inv_type == 'sale':
                        record_stock_change(row.inventory_item_id, inv.shop_id, 'adjustment', row.quantity, inv.invoice_number, session.get('full_name'), f"اصلاح موجودی انبار جهت ویرایش فاکتور {inv.invoice_number}", commit=False)
                    elif old_inv_type == 'return':
                        record_stock_change(row.inventory_item_id, inv.shop_id, 'adjustment', -row.quantity, inv.invoice_number, session.get('full_name'), f"اصلاح موجودی انبار جهت ویرایش مرجوعی {inv.invoice_number}", commit=False)

        # ۲. اصلاح حساب مشتری قبلی
        if inv.customer:
            if old_inv_type == 'sale':
                inv.customer.total_purchases = max(0, inv.customer.total_purchases - old_total)
                inv.customer.outstanding_balance = max(0, inv.customer.outstanding_balance - old_remaining)
            elif old_inv_type == 'return':
                inv.customer.total_purchases += old_total
                inv.customer.outstanding_balance += old_remaining

        # ۳. دریافت مقادیر جدید
        customer_name = request.form.get('customer_name', '').strip() or 'مشتری حضوری'
        customer_phone = request.form.get('customer_phone', '').strip()
        customer = get_or_create_customer(customer_name, customer_phone, shop_id=inv.shop_id) if (customer_phone or customer_name) else None

        paid_pos = safe_int(request.form.get('paid_pos'), 0)
        paid_card = safe_int(request.form.get('paid_card'), 0)
        paid_cash = safe_int(request.form.get('paid_cash'), 0)

        sayad_list = request.form.getlist('cheque_sayad[]')
        bank_list = request.form.getlist('cheque_bank[]')
        amount_list = request.form.getlist('cheque_amount[]')
        due_list = request.form.getlist('cheque_due_date[]')

        paid_cheque = 0
        cheques_to_create = []
        for c_idx in range(len(sayad_list)):
            c_sayad = sayad_list[c_idx].strip() if c_idx < len(sayad_list) else ''
            c_bank = bank_list[c_idx].strip() if c_idx < len(bank_list) else 'نامشخص'
            c_amt = safe_int(amount_list[c_idx], 0) if c_idx < len(amount_list) else 0
            c_due = due_list[c_idx].strip() if c_idx < len(due_list) else ''
            
            if c_amt > 0:
                paid_cheque += c_amt
                cheques_to_create.append({
                    'sayad': c_sayad,
                    'bank': c_bank,
                    'amount': c_amt,
                    'due_date': c_due
                })

        total_amount = safe_int(request.form.get('total_amount'), 0)
        
        total_paid_immediate = paid_pos + paid_card + paid_cash
        total_covered = total_paid_immediate + paid_cheque
        remaining_balance = max(0, total_amount - total_covered)

        method_parts = []
        if paid_pos > 0:
            method_parts.append(f"کارتخوان: {paid_pos:,}")
        if paid_card > 0:
            method_parts.append(f"کارت/شبا: {paid_card:,}")
        if paid_cash > 0:
            method_parts.append(f"نقد: {paid_cash:,}")
        if paid_cheque > 0:
            method_parts.append(f"{len(cheques_to_create)} فقره چک: {paid_cheque:,}")
        if remaining_balance > 0:
            method_parts.append(f"مانده نسیه: {remaining_balance:,}")

        payment_method_str = " | ".join(method_parts) if method_parts else "تسویه کامل"

        status = request.form.get('status', 'final')
        inv_type = request.form.get('invoice_type', 'sale')
        second_seller_id = request.form.get('second_seller_id')
        second_seller_id = safe_int(second_seller_id, None) if second_seller_id and second_seller_id != 'none' else None

        # بروزرسانی مقادیر هدر فاکتور
        inv.customer_id = customer.id if customer else None
        inv.customer_name = customer_name
        inv.customer_phone = customer_phone
        inv.items_desc = request.form.get('items_desc')
        inv.status = status
        inv.proforma_valid_until = request.form.get('proforma_valid_until')
        inv.invoice_type = inv_type
        inv.return_reason = request.form.get('return_reason')
        inv.payment_method = payment_method_str
        inv.paid_pos = paid_pos
        inv.paid_card = paid_card
        inv.paid_cash = paid_cash
        inv.paid_cheque = paid_cheque
        inv.remaining_balance = remaining_balance
        inv.paid_amount = total_paid_immediate
        inv.dest_card_number = request.form.get('dest_card_number', '').strip()
        inv.dest_sheba_number = request.form.get('dest_sheba_number', '').strip()
        inv.payment_tracking_code = request.form.get('payment_tracking_code')
        inv.total_amount = total_amount
        inv.due_settlement_date = request.form.get('due_settlement_date')
        inv.is_settled = (remaining_balance <= 0)
        inv.second_seller_id = second_seller_id
        partner_share_raw = request.form.get('partner_share')
        split_ratio_raw = request.form.get('split_ratio')
        if not second_seller_id:
            inv.second_seller_id = None
            inv.split_ratio = 100
        elif partner_share_raw is not None and str(partner_share_raw).strip() != '':
            p_share = max(0, min(100, safe_int(partner_share_raw, 0)))
            inv.split_ratio = 100 - p_share
        else:
            inv.split_ratio = max(0, min(100, safe_int(split_ratio_raw, 100)))

        inv.customer_rating = safe_int(request.form.get('customer_rating'), 5)

        # ۴. پاکسازی اقلام و چک‌های قبلی
        InvoiceItem.query.filter_by(invoice_id=inv.id).delete()
        Cheque.query.filter_by(invoice_id=inv.id).delete()

        # ۵. ایجاد اقلام جدید و کسر از انبار
        inv_item_ids = request.form.getlist('item_inventory_id[]')
        custom_names = request.form.getlist('item_custom_name[]')
        custom_cats = request.form.getlist('item_category[]')
        quantities = request.form.getlist('item_quantity[]')
        orig_prices = request.form.getlist('item_original_price[]')
        discount_percents = request.form.getlist('item_discount_percent[]')
        prices = request.form.getlist('item_price[]')
        buy_prices = request.form.getlist('item_buy_price[]')

        total_actual_buy_cost = 0
        categories_used = set()
        items_total_sum = 0
        items_gross_sum = 0
        items_discount_sum = 0
        has_any_custom = False
        created_invoice_items = []

        for idx in range(len(quantities)):
            qty = safe_int(quantities[idx], 1) if idx < len(quantities) else 1
            if qty <= 0:
                qty = 1
            orig_p = safe_int(orig_prices[idx], 0) if idx < len(orig_prices) else 0
            final_p = safe_int(prices[idx], 0) if idx < len(prices) else 0
            disc_pct = safe_float(discount_percents[idx], 0.0) if idx < len(discount_percents) else 0.0
            custom_buy_p = safe_int(buy_prices[idx], 0) if idx < len(buy_prices) else 0
            
            item_id_val = safe_int(inv_item_ids[idx], None) if idx < len(inv_item_ids) and inv_item_ids[idx] else None
            inv_item = InventoryItem.query.get(item_id_val) if item_id_val else None
            
            name_val = inv_item.name if inv_item else (custom_names[idx].strip() if idx < len(custom_names) and custom_names[idx].strip() else '')
            if not name_val:
                if final_p <= 0 and orig_p <= 0 and not inv_item:
                    continue
                name_val = 'تجهیزات بهداشتی'

            # اگر قیمت مصوب وارد نشده بود اما کالا در انبار یا کاتالوگ قیمت داشت
            if orig_p <= 0:
                if inv_item and inv_item.sell_price > 0:
                    orig_p = inv_item.sell_price
                elif final_p > 0:
                    orig_p = final_p
            
            # اگر قیمت نهایی وارد نشده بود
            if final_p <= 0:
                if orig_p > 0:
                    if disc_pct > 0:
                        final_p = int(orig_p * (1 - (disc_pct / 100.0)))
                    else:
                        final_p = orig_p
                else:
                    final_p = 0

            # محاسبه تخفیف ردیف
            row_discount = max(0, (orig_p - final_p) * qty) if orig_p > final_p else 0
            row_total = final_p * qty
            row_gross = orig_p * qty

            items_gross_sum += row_gross
            items_discount_sum += row_discount
            items_total_sum += row_total

            # اگر شناسه کالا ارسال نشده بود، بررسی تطابق خودکار نام کالا با انبار همین شعبه
            if not inv_item and name_val:
                inv_item = InventoryItem.query.filter_by(name=name_val, shop_id=inv.shop_id).first()

            cat_val = inv_item.category if inv_item else (custom_cats[idx].strip() if idx < len(custom_cats) and custom_cats[idx].strip() else 'عمومی')
            if cat_val:
                categories_used.add(cat_val)
            
            if cat_val and not Category.query.filter_by(name=cat_val).first():
                db.session.add(Category(name=cat_val))
                db.session.flush()

            # بررسی تطابق با کاتالوگ
            cat_match = None
            if not inv_item:
                cat_match = ProductCatalog.query.filter(ProductCatalog.name == name_val).first()
                if not cat_match and len(name_val) >= 5:
                    cat_match = ProductCatalog.query.filter(ProductCatalog.name.contains(name_val[:10])).first()

            # استخراج بهای خرید واقعی و تشخیص اقلام سفارشی
            is_custom_row = False
            buy_p = 0
            if custom_buy_p > 0:
                buy_p = custom_buy_p
                if not inv_item:
                    is_custom_row = True
            elif inv_item and inv_item.buy_price > 0:
                buy_p = inv_item.buy_price
            elif cat_match and cat_match.buy_price > 0:
                buy_p = cat_match.buy_price
            else:
                buy_p = int(final_p * 0.75)
                is_custom_row = True

            if not inv_item and not cat_match:
                is_custom_row = True

            if is_custom_row:
                has_any_custom = True

            row_profit = row_total - (buy_p * qty)
            total_actual_buy_cost += (buy_p * qty)

            inv_row = InvoiceItem(
                invoice_id=inv.id,
                inventory_item_id=inv_item.id if inv_item else None,
                item_name=name_val,
                category=cat_val,
                quantity=qty,
                unit_buy_price=buy_p,
                unit_sell_price=orig_p,
                discount=row_discount,
                total_price=row_total,
                row_profit=row_profit,
                is_custom=is_custom_row
            )
            db.session.add(inv_row)
            created_invoice_items.append(inv_row)

            if status == 'final' and inv_item:
                if inv_type == 'sale':
                    record_stock_change(inv_item.id, inv.shop_id, 'sale', -qty, inv.invoice_number, session.get('full_name'), f"فروش پس از ویرایش فاکتور {inv.invoice_number}", commit=False)
                elif inv_type == 'return':
                    record_stock_change(inv_item.id, inv.shop_id, 'return', qty, inv.invoice_number, session.get('full_name'), f"مرجوعی پس از ویرایش فاکتور {inv.invoice_number}", commit=False)

        # اگر اقلام بدون قیمت بودند اما مبلغ کل فاکتور دستی وارد شده است
        if inv.total_amount > 0 and items_total_sum <= 0:
            if created_invoice_items:
                num_items = len(created_invoice_items)
                per_item = inv.total_amount // num_items
                remainder = inv.total_amount % num_items
                total_actual_buy_cost = 0
                for i, row in enumerate(created_invoice_items):
                    row_tot = per_item + (remainder if i == 0 else 0)
                    row.total_price = row_tot
                    row.unit_sell_price = int(row_tot / max(1, row.quantity))
                    row.discount = 0
                    if row.unit_buy_price <= 0:
                        row.unit_buy_price = int(row.unit_sell_price * 0.75)
                    row.row_profit = row.total_price - (row.unit_buy_price * row.quantity)
                    total_actual_buy_cost += (row.unit_buy_price * row.quantity)
                items_gross_sum = inv.total_amount
                items_total_sum = inv.total_amount
            else:
                fallback_row = InvoiceItem(
                    invoice_id=inv.id,
                    item_name='تجهیزات بهداشتی و ساختمانی',
                    category='عمومی',
                    quantity=1,
                    unit_buy_price=int(inv.total_amount * 0.75),
                    unit_sell_price=inv.total_amount,
                    discount=0,
                    total_price=inv.total_amount,
                    row_profit=inv.total_amount - int(inv.total_amount * 0.75),
                    is_custom=True
                )
                db.session.add(fallback_row)
                created_invoice_items.append(fallback_row)
                categories_used.add('عمومی')
                total_actual_buy_cost = int(inv.total_amount * 0.75)
                items_gross_sum = inv.total_amount
                items_total_sum = inv.total_amount

        if inv.total_amount <= 0 and items_total_sum > 0:
            inv.total_amount = items_total_sum
            total_amount = items_total_sum
            remaining_balance = max(0, total_amount - total_covered)
            inv.remaining_balance = remaining_balance
            inv.is_settled = (remaining_balance <= 0)

        # تنظیم مبالغ ناخالص و تخفیف کل فاکتور
        inv.subtotal_amount = max(items_gross_sum, inv.total_amount) if items_gross_sum > 0 else inv.total_amount
        if inv.total_amount > 0 and items_gross_sum > inv.total_amount:
            inv.discount_amount = max(items_discount_sum, items_gross_sum - inv.total_amount)
        else:
            inv.discount_amount = items_discount_sum

        # اعتبارسنجی نهایی مبلغ فاکتور
        if inv.total_amount <= 0:
            db.session.rollback()
            flash('مبلغ کل فاکتور نمی‌تواند صفر یا خالی باشد. لطفاً اقلام یا مبلغ فاکتور را وارد فرمایید.', 'warning')
            return redirect(request.referrer or url_for('seller_dashboard'))

        inv.categories_json = json.dumps(list(categories_used), ensure_ascii=False)
        inv.actual_buy_cost = total_actual_buy_cost if total_actual_buy_cost > 0 else int(inv.total_amount * 0.75)
        inv.real_profit = inv.total_amount - inv.actual_buy_cost
        inv.has_custom_items = has_any_custom

        # ایجاد چک‌های جدید
        for chk_data in cheques_to_create:
            chk = Cheque(
                invoice_id=inv.id,
                sayad_number=chk_data['sayad'],
                bank_name=chk_data['bank'],
                customer_name=inv.customer_name,
                customer_phone=inv.customer_phone,
                amount=chk_data['amount'],
                due_shamsi_date=chk_data['due_date'],
                shop_id=inv.shop_id,
                status='pending'
            )
            db.session.add(chk)

        # بروزرسانی حساب مشتری
        if customer:
            if inv_type == 'sale':
                customer.total_purchases += inv.total_amount
                if inv.remaining_balance > 0:
                    customer.outstanding_balance += inv.remaining_balance
            elif inv_type == 'return':
                customer.total_purchases = max(0, customer.total_purchases - inv.total_amount)
                if inv.remaining_balance > 0:
                    customer.outstanding_balance = max(0, customer.outstanding_balance - inv.remaining_balance)

        db.session.commit()

        log_activity(
            f"ویرایش فاکتور {inv.invoice_number} توسط {session.get('full_name')} (مبلغ قدیم: {old_total:,} ت | جدید: {total_amount:,} ت)",
            session.get('full_name'),
            "فروش / امنیت"
        )
        flash(f'فاکتور {inv.invoice_number} با موفقیت ویرایش شد و تغییرات انبار و حساب اعمال گردید.', 'success')

        if user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('seller_dashboard'))

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error editing invoice {invoice_id}: {e}", exc_info=True)
        flash(f'خطا در ویرایش فاکتور: {str(e)}', 'error')
        return redirect(request.referrer or url_for('seller_dashboard'))

# ==================== چاپ فاکتورها (A4 و فیش پرینتر) ====================
@app.route('/invoice/print/a4/<int:invoice_id>')
def print_invoice_a4(invoice_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    invoice = Invoice.query.get_or_404(invoice_id)
    settings = Settings.query.first()
    return render_template('print_a4.html', invoice=invoice, settings=settings)

@app.route('/invoice/print/thermal/<int:invoice_id>')
@app.route('/print_pos/<int:invoice_id>')
@app.route('/invoice/print/pos/<int:invoice_id>')
def print_invoice_thermal(invoice_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    invoice = Invoice.query.get_or_404(invoice_id)
    settings = Settings.query.first()
    return render_template('print_pos.html', invoice=invoice, settings=settings)

# ==================== مشاهده و دانلود عمومی فاکتور مشتری و خدمات پیامک ====================
@app.route('/invoice/view/<string:invoice_number>')
def public_view_invoice(invoice_number):
    """مشاهده عمومی فاکتور چاپی معتبر و دانلود PDF بدون نیاز به ورود، جهت باز شدن از لینک پیامک"""
    clean_num = invoice_number.strip()
    invoice = Invoice.query.filter_by(invoice_number=clean_num).first()
    if not invoice and clean_num.isdigit():
        invoice = Invoice.query.get(int(clean_num))
    if not invoice:
        return render_template('public_invoice_view.html', invoice=None, error="فاکتور مورد نظر در سامانه یافت نشد.")
    settings = Settings.query.first()
    return render_template('public_invoice_view.html', invoice=invoice, settings=settings)

@app.route('/invoice/send_sms/<int:invoice_id>', methods=['POST', 'GET'])
def send_invoice_sms_action(invoice_id):
    """ارسال دستی یا مجدد پیامک گارانتی و لینک فاکتور توسط فروشنده یا ادمین"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    inv = Invoice.query.get_or_404(invoice_id)
    success, msg = send_invoice_sms(inv)
    if success:
        flash(f'پیامک گارانتی و لینک فاکتور با موفقیت به {inv.customer_phone} ارسال شد.', 'success')
    else:
        flash(f'ارسال پیامک با خطا مواجه شد: {msg}', 'error')
    return redirect(request.referrer or url_for('seller_dashboard'))

# ==================== داشبورد مدیریت کل ====================
@app.route('/admin')
@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    now_j = jdatetime.datetime.now()
    selected_month = request.args.get('month', default=now_j.month, type=int)
    search_query = request.args.get('search', '').strip()
    seller_filter = request.args.get('seller_filter', '').strip()
    
    settings = Settings.query.first()
    
    # ۱. محاسبه جامع فروش کل مجموعه، فروش شعب و سود ناخالص بر اساس کلیه فاکتورهای قطعی ماه (شامل فروشندگان و مدیریت)
    month_invoices = Invoice.query.options(
        selectinload(Invoice.cheques)
    ).filter(
        Invoice.shamsi_year == now_j.year,
        Invoice.shamsi_month == selected_month,
        Invoice.status == 'final'
    ).all()
    
    shop1_total = 0
    shop2_total = 0
    total_sales_all = 0
    estimated_gross_profit = 0
    
    for inv in month_invoices:
        passed_chk = sum(chk.amount for chk in inv.cheques if chk.status == 'passed')
        settled_amt = (inv.paid_amount or 0) + passed_chk
        profit_amt = inv.real_profit or 0
        
        if inv.invoice_type == 'sale':
            total_sales_all += settled_amt
            estimated_gross_profit += profit_amt
            if inv.shop_id == 2:
                shop2_total += settled_amt
            else:
                shop1_total += settled_amt
        elif inv.invoice_type == 'return':
            total_sales_all -= settled_amt
            estimated_gross_profit -= profit_amt
            if inv.shop_id == 2:
                shop2_total -= settled_amt
            else:
                shop1_total -= settled_amt

    # ۲. محاسبه آمار عملکرد و پورسانت پرسنل فروشنده
    sellers = User.query.filter(User.role.in_(['seller', 'cashier']), User.is_active == True).all()
    sellers_data = []
    total_commissions = 0
    chart_sellers_labels = []
    chart_sellers_data = []
    
    for s in sellers:
        s_stats = calculate_seller_exact_stats(s.id, now_j.year, selected_month, s.commission_rate, settings)
        total_commissions += s_stats['settled_commission']
        sellers_data.append({'user': s, 'stats': s_stats})
        chart_sellers_labels.append(s.full_name)
        chart_sellers_data.append(s_stats['net_sales'])

    # ۳. پرسنل خدمات، تحویل بار و نظافت (فقط حقوق ثابت، بدون درصد پورسانت)
    logistics_staff = User.query.filter(User.role.in_(['logistics', 'services', 'staff']), User.is_active == True).all()

    # ۴. بررسی و نمایش فروش مدیریت کل در جدول پرسنل و نمودار در صورت ثبت فاکتور توسط مدیریت
    admin_users = User.query.filter_by(role='admin', is_active=True).all()
    for adm in admin_users:
        adm_stats = calculate_seller_exact_stats(adm.id, now_j.year, selected_month, 0, settings)
        if adm_stats['sales_count'] > 0 or adm_stats['gross_sales'] > 0:
            adm_stats['settled_commission'] = 0
            adm_stats['pending_commission'] = 0
            adm_stats['effective_rate'] = 0
            sellers_data.insert(0, {'user': adm, 'stats': adm_stats})
            chart_sellers_labels.insert(0, f"{adm.full_name} (مدیریت)")
            chart_sellers_data.insert(0, adm_stats['net_sales'])
        
    expenses = Expense.query.filter_by(shamsi_year=now_j.year, shamsi_month=selected_month).all()
    total_expenses = sum(e.amount for e in expenses)
    
    petty_deposits = PettyCashDeposit.query.filter_by(shamsi_year=now_j.year, shamsi_month=selected_month).all()
    total_petty_deposits = sum(d.amount for d in petty_deposits)
    
    all_categories = Category.query.all()
    all_month_items = InvoiceItem.query.join(Invoice).filter(Invoice.shamsi_year == now_j.year, Invoice.shamsi_month == selected_month, Invoice.status == 'final').all()
    cat_counts = {cat.name: 0 for cat in all_categories}
    for item in all_month_items:
        if item.category in cat_counts:
            cat_counts[item.category] += item.quantity
            
    chart_category_labels = list(cat_counts.keys())
    chart_category_data = list(cat_counts.values())

    cheques = Cheque.query.order_by(Cheque.id.desc()).all()
    pending_cheques = [c for c in cheques if c.status == 'pending']
    pending_cheques_total = sum(c.amount for c in pending_cheques)
    
    # محاسبه هوشمند چک‌های سررسید نزدیک (امروز، ۳ روز آینده یا معوقه شده)
    urgent_cheques = []
    today_j = now_j.date()
    for c in pending_cheques:
        try:
            if c.due_shamsi_date:
                parts = [int(p) for p in c.due_shamsi_date.replace('-', '/').split('/')]
                due_date = jdatetime.date(parts[0], parts[1], parts[2])
                days_diff = (due_date - today_j).days
                if days_diff <= 3:
                    urgent_cheques.append({
                        'id': c.id,
                        'customer_name': c.customer_name,
                        'amount': c.amount,
                        'sayad_number': c.sayad_number,
                        'bank_name': c.bank_name,
                        'due_shamsi_date': c.due_shamsi_date,
                        'days_diff': days_diff,
                        'is_overdue': days_diff < 0,
                        'is_today': days_diff == 0
                    })
        except Exception:
            pass
    
    all_inventory = InventoryItem.query.all()
    low_stock_count = len([i for i in all_inventory if i.stock_quantity <= i.min_alert_stock])
    total_catalog_products = ProductCatalog.query.count()
    
    status_filter = request.args.get('status_filter', 'all').strip()
    query = Invoice.query.options(
        selectinload(Invoice.items),
        selectinload(Invoice.cheques),
        joinedload(Invoice.seller),
        joinedload(Invoice.shop)
    ).filter_by(shamsi_year=now_j.year, shamsi_month=selected_month)
    if seller_filter:
        query = query.filter_by(seller_id=int(seller_filter))
    if status_filter == 'pending':
        query = query.filter(db.or_(Invoice.is_settled == False, Invoice.remaining_balance > 0))
    elif status_filter == 'settled':
        query = query.filter(Invoice.is_settled == True, db.or_(Invoice.remaining_balance == 0, Invoice.remaining_balance == None))
    elif status_filter == 'custom':
        query = query.filter(Invoice.has_custom_items == True)

    if search_query:
        query = query.filter(
            (Invoice.customer_name.contains(search_query)) |
            (Invoice.customer_phone.contains(search_query)) |
            (Invoice.invoice_number.contains(search_query))
        )
    all_invoices_raw = query.order_by(Invoice.created_at.desc()).all()
    
    # فاکتورهای دارای اقلام خارج از لیست (سفارشی) ماه
    custom_invoices_all = [inv for inv in month_invoices if getattr(inv, 'has_custom_items', False)]
    custom_sales_total = sum(inv.total_amount for inv in custom_invoices_all)
    custom_profit_total = sum(inv.real_profit or 0 for inv in custom_invoices_all)

    # فاکتورهای دارای مانده کل مجموعه جهت نمایش در پنل مدیریت
    admin_pending_invoices = Invoice.query.options(
        selectinload(Invoice.cheques),
        joinedload(Invoice.seller),
        joinedload(Invoice.shop)
    ).filter(
        db.or_(Invoice.is_settled == False, Invoice.remaining_balance > 0),
        Invoice.status == 'final',
        Invoice.invoice_type != 'return'
    ).order_by(Invoice.created_at.desc()).all()
    total_admin_pending_balance = sum(inv.remaining_balance or 0 for inv in admin_pending_invoices)

    all_invoices = []
    for inv in all_invoices_raw:
        all_invoices.append({
            'id': inv.id,
            'invoice_number': inv.invoice_number,
            'status': inv.status,
            'invoice_type': inv.invoice_type,
            'return_reason': inv.return_reason,
            'shop_name': inv.shop.name if inv.shop else '',
            'seller_name': inv.seller.full_name if inv.seller else '',
            'second_seller_id': inv.second_seller_id,
            'split_ratio': inv.split_ratio,
            'customer_name': inv.customer_name,
            'customer_phone': inv.customer_phone,
            'total_amount': inv.total_amount,
            'subtotal_amount': inv.subtotal_amount or 0,
            'discount_amount': inv.discount_amount or 0,
            'paid_amount': inv.paid_amount or 0,
            'paid_pos': inv.paid_pos or 0,
            'paid_card': inv.paid_card or 0,
            'paid_cash': inv.paid_cash or 0,
            'paid_cheque': inv.paid_cheque or 0,
            'remaining_balance': inv.remaining_balance or 0,
            'is_settled': inv.is_settled,
            'payment_method': inv.payment_method,
            'dest_card_number': inv.dest_card_number,
            'payment_tracking_code': inv.payment_tracking_code,
            'cheque_sayad': inv.cheques[0].sayad_number if inv.cheques else '',
            'cheque_bank': inv.cheques[0].bank_name if inv.cheques else '',
            'cheque_due_date': inv.cheques[0].due_shamsi_date if inv.cheques else '',
            'due_settlement_date': inv.due_settlement_date,
            'shamsi_date_time': inv.shamsi_date_time,
            'items_desc': inv.items_desc or '',
            'categories_json': inv.categories_json or '',
            'has_custom_items': getattr(inv, 'has_custom_items', False),
            'sms_sent': getattr(inv, 'sms_sent', False),
            'sms_sent_at': getattr(inv, 'sms_sent_at', '') or '',
            'real_profit': inv.real_profit or 0,
            'actual_buy_cost': inv.actual_buy_cost or 0,
            'items': [{
                'id': it.id,
                'item_name': it.item_name,
                'category': it.category or '',
                'quantity': it.quantity,
                'unit_buy_price': it.unit_buy_price or 0,
                'unit_sell_price': it.unit_sell_price or 0,
                'discount': it.discount or 0,
                'total_price': it.total_price or 0,
                'row_profit': it.row_profit or 0,
                'is_custom': getattr(it, 'is_custom', False)
            } for it in inv.items]
        })
    
    # استخراج اقلام پرفروش فروشگاه طهماسبی
    top_selling_items = (
        db.session.query(
            InvoiceItem.item_name,
            InvoiceItem.category,
            func.sum(InvoiceItem.quantity).label('total_qty'),
            func.sum(InvoiceItem.total_price).label('total_revenue')
        )
        .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
        .filter(Invoice.status == 'final', Invoice.invoice_type != 'return')
        .group_by(InvoiceItem.item_name, InvoiceItem.category)
        .order_by(func.sum(InvoiceItem.quantity).desc())
        .limit(10)
        .all()
    )
    
    shops = Shop.query.all()
    all_categories = Category.query.all()
    bank_accounts = BankAccount.query.filter_by(is_active=True).all()
    logs = AuditLog.query.order_by(AuditLog.id.desc()).limit(60).all()
    all_staff = User.query.filter_by(is_active=True).order_by(User.role, User.full_name).all()

    # محاسبه سود جامع و سود خالص واقعی ماه طهماسبی
    # ۱. حقوق پایه ثابت پرسنل ماه (به غیر از حساب مدیرکل)
    total_base_salaries = sum(u.base_salary or 0 for u in all_staff if u.role != 'admin')
    # ۲. جمع کل هزینه حقوق و دستمزد پرسنل (حقوق پایه + پورسانت)
    total_payroll = total_base_salaries + total_commissions
    # ۳. هزینه اجاره ماهانه شعب (شعبه ۱ و ۲)
    total_rent = sum(s.rent_amount or 0 for s in shops)
    
    # ۴. سود خالص نهایی مدیریت طهماسبی = سود ناخالص - (حقوق و پورسانت + اجاره شعب + سایر هزینه‌ها)
    store_net_profit = estimated_gross_profit - (total_payroll + total_rent + total_expenses)
    profit_margin_percent = round((store_net_profit / total_sales_all * 100), 1) if total_sales_all > 0 else 0
    gross_margin_percent = round((estimated_gross_profit / total_sales_all * 100), 1) if total_sales_all > 0 else 0

    return render_template(
        'admin_dashboard.html',
        sellers_data=sellers_data,
        logistics_staff=logistics_staff,
        all_sellers=all_staff,
        seller_filter=seller_filter,
        shop1_total=shop1_total,
        shop2_total=shop2_total,
        total_commissions=total_commissions,
        total_base_salaries=total_base_salaries,
        total_payroll=total_payroll,
        total_rent=total_rent,
        total_expenses=total_expenses,
        total_petty_deposits=total_petty_deposits,
        petty_deposits=petty_deposits,
        expenses=expenses,
        estimated_gross_profit=estimated_gross_profit,
        store_net_profit=store_net_profit,
        profit_margin_percent=profit_margin_percent,
        gross_margin_percent=gross_margin_percent,
        total_catalog_products=total_catalog_products,
        total_sales_all=total_sales_all,
        cheques=cheques,
        pending_cheques_count=len(pending_cheques),
        pending_cheques_total=pending_cheques_total,
        all_inventory=all_inventory,
        low_stock_count=low_stock_count,
        months=PERSIAN_MONTHS,
        selected_month=selected_month,
        selected_month_name=PERSIAN_MONTHS.get(selected_month, ''),
        current_year=now_j.year,
        shops=shops,
        all_categories=all_categories,
        bank_accounts=bank_accounts,
        chart_sellers_labels=chart_sellers_labels,
        chart_sellers_data=chart_sellers_data,
        chart_category_labels=chart_category_labels,
        chart_category_data=chart_category_data,
        all_invoices=all_invoices,
        search_query=search_query,
        status_filter=status_filter,
        admin_pending_invoices=admin_pending_invoices,
        total_admin_pending_balance=total_admin_pending_balance,
        custom_invoices_count=len(custom_invoices_all),
        custom_sales_total=custom_sales_total,
        custom_profit_total=custom_profit_total,
        settings=settings,
        logs=logs,
        top_selling_items=top_selling_items,
        urgent_cheques=urgent_cheques
    )

# ==================== مدیریت حساب‌های بانکی (شماره کارت و شماره شبا) ====================
@app.route('/admin/bank_account/add', methods=['POST'])
def add_bank_account():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    title = request.form.get('title', 'حساب بانکی طهماسبی').strip()
    bank_name = request.form.get('bank_name', 'ملی').strip()
    account_owner = request.form.get('account_owner', 'طهماسبی').strip()
    account_type = request.form.get('account_type', 'both')
    card_number = request.form.get('card_number', '').strip()
    sheba_number = request.form.get('sheba_number', '').strip()

    if sheba_number and not sheba_number.upper().startswith('IR'):
        sheba_number = 'IR' + sheba_number

    acc = BankAccount(
        title=title,
        bank_name=bank_name,
        account_owner=account_owner,
        account_type=account_type,
        card_number=card_number,
        sheba_number=sheba_number,
        is_active=True
    )
    db.session.add(acc)
    db.session.commit()
    
    log_activity(f"افزودن حساب/کارت بانکی {title} ({bank_name})", session.get('full_name'), "تنظیمات")
    flash('حساب بانکی جدید با موفقیت به سیستم اضافه شد.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/bank_account/delete/<int:account_id>', methods=['POST'])
def delete_bank_account(account_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    acc = BankAccount.query.get_or_404(account_id)
    title = acc.title
    db.session.delete(acc)
    db.session.commit()
    
    log_activity(f"حذف حساب بانکی {title}", session.get('full_name'), "تنظیمات")
    flash(f'حساب بانکی {title} حذف گردید.', 'warning')
    return redirect(url_for('admin_dashboard'))

# ==================== تنظیم و به‌روزرسانی اجاره شعب ====================
@app.route('/admin/shops/rent/update', methods=['POST'])
def update_shops_rent():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    for shop in Shop.query.all():
        field_name = f'rent_shop_{shop.id}'
        if field_name in request.form:
            raw_val = request.form.get(field_name, '0')
            shop.rent_amount = safe_int(raw_val, shop.rent_amount or 0)
    db.session.commit()
    log_activity("به‌روزرسانی مبلغ اجاره ماهانه شعب", session.get('full_name'), "مالی")
    flash('مبالغ اجاره ماهانه شعب با موفقیت ذخیره و در محاسبات سود اعمال شد.', 'success')
    return redirect(url_for('admin_dashboard'))

# ==================== ماژول انبارداری و انبارگردانی ====================
@app.route('/inventory')
def inventory_view():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    all_inventory = InventoryItem.query.all()
    shops = Shop.query.all()
    all_categories = Category.query.all()
    transfers = StockTransfer.query.order_by(StockTransfer.id.desc()).limit(15).all()
    search_q = request.args.get('search', '').strip()
    cat_query = ProductCatalog.query
    if search_q:
        s_filter = build_catalog_search_filter(ProductCatalog, search_q)
        if s_filter is not None:
            cat_query = cat_query.filter(s_filter)
        catalog_items = cat_query.order_by(ProductCatalog.brand, ProductCatalog.name).limit(120).all()
    else:
        catalog_items = ProductCatalog.query.order_by(ProductCatalog.brand, ProductCatalog.category, ProductCatalog.name).limit(60).all()
    total_catalog_count = ProductCatalog.query.count()

    # نگاشت سریع موجودی برای هر شعبه: (item_name, shop_id) -> {'id': ..., 'stock': ..., 'min_alert': ...}
    inventory_map = {}
    for inv in all_inventory:
        inventory_map[(inv.name, inv.shop_id)] = {
            'id': inv.id,
            'stock': inv.stock_quantity,
            'min_alert': inv.min_alert_stock
        }

    # برندهای متمایز کاتالوگ برای فیلتر
    distinct_brands = [
        b[0] for b in db.session.query(ProductCatalog.brand)
        .filter(ProductCatalog.brand != None, ProductCatalog.brand != '')
        .distinct()
        .order_by(ProductCatalog.brand)
        .all()
    ]
    ai_insights = get_inventory_ai_insights()

    return render_template(
        'inventory.html',
        all_inventory=all_inventory,
        shops=shops,
        all_categories=all_categories,
        transfers=transfers,
        ai_insights=ai_insights,
        catalog_items=catalog_items,
        total_catalog_count=total_catalog_count,
        inventory_map=inventory_map,
        distinct_brands=distinct_brands,
        search=search_q
    )

@app.route('/admin/inventory/add', methods=['POST'])
def add_inventory_item():
    if not can_manage_stock():
        return redirect(url_for('login'))
    
    category_val = request.form.get('category')
    if category_val == '__custom__':
        category_val = request.form.get('custom_category_name', '').strip()
        if not category_val:
            category_val = 'سایر و متفرقه'
        if not Category.query.filter_by(name=category_val).first():
            db.session.add(Category(name=category_val))
            db.session.commit()
            
    buy_raw = request.form.get('buy_price', '').replace(',', '')
    sell_raw = request.form.get('sell_price', '').replace(',', '')
    item = InventoryItem(
        name=request.form.get('name'),
        category=category_val,
        shop_id=int(request.form.get('shop_id', 1)),
        stock_quantity=int(request.form.get('stock_quantity', 5)),
        min_alert_stock=int(request.form.get('min_alert_stock', 2)),
        buy_price=int(buy_raw) if (buy_raw and (is_admin() or can_manage_stock())) else 0,
        sell_price=int(sell_raw) if sell_raw else 0
    )
    db.session.add(item)
    db.session.commit()
    
    record_stock_change(item.id, item.shop_id, 'purchase_in', item.stock_quantity, 'INIT', session.get('full_name'), "موجودی اولیه")
    log_activity(f"افزودن کالای {item.name} به انبار", session.get('full_name'), "انبار")
    flash(f'کالای {item.name} با موفقیت در انبار ثبت گردید.', 'success')
    return redirect(url_for('inventory_view'))

@app.route('/admin/inventory/edit/<int:item_id>', methods=['POST'])
def edit_inventory_item(item_id):
    if not can_manage_stock():
        return redirect(url_for('login'))
    item = InventoryItem.query.get_or_404(item_id)
    item.name = request.form.get('name')
    item.category = request.form.get('category')
    item.shop_id = int(request.form.get('shop_id'))
    old_qty = item.stock_quantity
    new_qty = int(request.form.get('stock_quantity', 0))
    item.stock_quantity = new_qty
    item.min_alert_stock = int(request.form.get('min_alert_stock', 2))
    
    if is_admin() or can_manage_stock():
        buy_raw = request.form.get('buy_price', '').replace(',', '')
        if buy_raw: item.buy_price = int(buy_raw)
    sell_raw = request.form.get('sell_price', '').replace(',', '')
    if sell_raw: item.sell_price = int(sell_raw)
    
    if new_qty != old_qty:
        record_stock_change(item.id, item.shop_id, 'adjustment', new_qty - old_qty, 'MANUAL_EDIT', session.get('full_name'), "ویرایش دستی انبار")

    db.session.commit()
    log_activity(f"ویرایش کالای {item.name} در انبار", session.get('full_name'), "انبار")
    flash(f'اطلاعات کالای {item.name} به‌روزرسانی شد.', 'success')
    return redirect(url_for('inventory_view'))

@app.route('/admin/inventory/delete/<int:item_id>', methods=['POST'])
def delete_inventory_item(item_id):
    if not can_manage_stock():
        return redirect(url_for('login'))
    item = InventoryItem.query.get_or_404(item_id)
    item_name = item.name
    # قطع وابستگی فاکتورهای قبلی جهت حفظ یکپارچگی ارجاعات دیتابیس
    InvoiceItem.query.filter_by(inventory_item_id=item_id).update({'inventory_item_id': None})
    db.session.delete(item)
    db.session.commit()
    log_activity(f"حذف کالای {item_name} از انبار", session.get('full_name'), "انبار")
    flash(f'کالای {item_name} از انبار حذف گردید.', 'success')
    return redirect(url_for('inventory_view'))

@app.route('/admin/inventory/stocktaking', methods=['POST'])
def stocktaking_adjust():
    if not can_manage_stock():
        return redirect(url_for('login'))
    item_id = int(request.form.get('item_id'))
    actual_stock = int(request.form.get('actual_stock', 0))
    reason = request.form.get('reason', 'انبارگردانی دوره‌ای')
    
    item = InventoryItem.query.get_or_404(item_id)
    diff = actual_stock - item.stock_quantity
    item.stock_quantity = actual_stock
    
    record_stock_change(item.id, item.shop_id, 'adjustment', diff, 'STOCKTAKING', session.get('full_name'), reason)
    log_activity(f"انبارگردانی کالای {item.name}: موجودی جدید {actual_stock} ({diff:+d})", session.get('full_name'), "انبار")
    flash(f'انبارگردانی کالای {item.name} با موفقیت ثبت شد.', 'success')
    return redirect(url_for('inventory_view'))

@app.route('/api/inventory/quick_stock', methods=['POST'])
def api_quick_stock():
    """ثبت یا به‌روزرسانی آنی موجودی کالا در شعبه با کاتالوگ مرجع"""
    if not can_manage_stock():
        return jsonify({'success': False, 'message': 'شما دسترسی مجاز برای تغییر موجودی انبار را ندارید.'}), 403

    data = request.get_json(silent=True) or request.form
    catalog_id = safe_int(data.get('catalog_id'), None)
    name = (data.get('name') or '').strip()
    shop_id = safe_int(data.get('shop_id'), 1)
    new_stock = safe_int(data.get('stock_quantity'), 0)
    min_alert = safe_int(data.get('min_alert_stock'), 2)

    cat_p = ProductCatalog.query.get(catalog_id) if catalog_id else None
    if not name and cat_p:
        name = cat_p.name

    if not name:
        return jsonify({'success': False, 'message': 'نام کالا یافت نشد.'}), 400

    inv_item = InventoryItem.query.filter_by(name=name, shop_id=shop_id).first()
    if not cat_p:
        cat_p = ProductCatalog.query.filter_by(name=name).first()

    if not inv_item:
        inv_item = InventoryItem(
            name=name,
            category=cat_p.category if cat_p else 'عمومی',
            brand=cat_p.brand if cat_p else '',
            shop_id=shop_id,
            stock_quantity=0,
            min_alert_stock=min_alert,
            buy_price=cat_p.buy_price if cat_p else 0,
            sell_price=cat_p.sell_price if cat_p else 0
        )
        db.session.add(inv_item)
        db.session.commit()
        record_stock_change(inv_item.id, shop_id, 'adjustment', new_stock, 'STOCKTAKING', session.get('full_name', 'مدیریت'), 'تعیین اولیه موجودی از کاتالوگ')
    else:
        diff = new_stock - inv_item.stock_quantity
        inv_item.min_alert_stock = min_alert
        if cat_p:
            if inv_item.buy_price == 0 and cat_p.buy_price > 0:
                inv_item.buy_price = cat_p.buy_price
            if inv_item.sell_price == 0 and cat_p.sell_price > 0:
                inv_item.sell_price = cat_p.sell_price
            if not inv_item.brand and cat_p.brand:
                inv_item.brand = cat_p.brand
        db.session.commit()
        if diff != 0:
            record_stock_change(inv_item.id, shop_id, 'adjustment', diff, 'STOCKTAKING', session.get('full_name', 'مدیریت'), 'انبارگردانی سریع')

    # تعیین برچسب وضعیت
    if inv_item.stock_quantity <= 0:
        status_badge = 'out'
        status_text = 'ناموجود'
        badge_class = 'bg-rose-100 text-rose-800 border-rose-300'
    elif inv_item.stock_quantity <= inv_item.min_alert_stock:
        status_badge = 'low'
        status_text = f'هشدار کسری ({inv_item.stock_quantity})'
        badge_class = 'bg-amber-100 text-amber-800 border-amber-300'
    else:
        status_badge = 'available'
        status_text = f'موجود ({inv_item.stock_quantity})'
        badge_class = 'bg-emerald-100 text-emerald-800 border-emerald-300'

    return jsonify({
        'success': True,
        'item_id': inv_item.id,
        'name': inv_item.name,
        'shop_id': inv_item.shop_id,
        'stock_quantity': inv_item.stock_quantity,
        'min_alert_stock': inv_item.min_alert_stock,
        'status_badge': status_badge,
        'status_text': status_text,
        'badge_class': badge_class,
        'message': f'موجودی «{inv_item.name}» در شعبه {shop_id} با موفقیت {inv_item.stock_quantity} عدد ثبت شد.'
    })

@app.route('/api/inventory/batch_quick_stock', methods=['POST'])
def api_batch_quick_stock():
    """ذخیره گروهی موجودی‌های تغییر یافته در صفحه"""
    if not can_manage_stock():
        return jsonify({'success': False, 'message': 'دسترسی غیرمجاز'}), 403

    data = request.get_json(silent=True) or {}
    items_list = data.get('items', [])
    shop_id = safe_int(data.get('shop_id'), 1)

    if not items_list:
        return jsonify({'success': False, 'message': 'هیچ ردیفی جهت ذخیره ارسال نشده است.'}), 400

    updated_count = 0
    for itm in items_list:
        name = (itm.get('name') or '').strip()
        new_stock = safe_int(itm.get('stock_quantity'), 0)
        min_alert = safe_int(itm.get('min_alert_stock'), 2)
        catalog_id = safe_int(itm.get('catalog_id'), None)

        cat_p = ProductCatalog.query.get(catalog_id) if catalog_id else None
        if not name and cat_p:
            name = cat_p.name

        if not name:
            continue

        inv_item = InventoryItem.query.filter_by(name=name, shop_id=shop_id).first()
        if not cat_p:
            cat_p = ProductCatalog.query.filter_by(name=name).first()

        if not inv_item:
            inv_item = InventoryItem(
                name=name,
                category=cat_p.category if cat_p else 'عمومی',
                brand=cat_p.brand if cat_p else '',
                shop_id=shop_id,
                stock_quantity=0,
                min_alert_stock=min_alert,
                buy_price=cat_p.buy_price if cat_p else 0,
                sell_price=cat_p.sell_price if cat_p else 0
            )
            db.session.add(inv_item)
            db.session.commit()
            record_stock_change(inv_item.id, shop_id, 'adjustment', new_stock, 'STOCKTAKING', session.get('full_name', 'مدیریت'), 'تعیین دسته‌جمعی موجودی')
            updated_count += 1
        else:
            diff = new_stock - inv_item.stock_quantity
            inv_item.min_alert_stock = min_alert
            db.session.commit()
            if diff != 0:
                record_stock_change(inv_item.id, shop_id, 'adjustment', diff, 'STOCKTAKING', session.get('full_name', 'مدیریت'), 'انبارگردانی دسته‌جمعی')
            updated_count += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'updated_count': updated_count,
        'message': f'موجودی {updated_count} قلم کالا با موفقیت در شعبه {shop_id} به‌روزرسانی و ثبت شد.'
    })

@app.route('/api/inventory/catalog-stock')
def api_inventory_catalog_stock():
    """ارسال سریع و بهینه اطلاعات کل کاتالوگ به همراه موجودی دو شعبه به صورت JSON فشرده"""
    if 'user_id' not in session:
        return jsonify([])
    
    is_admin_user = session.get('role') == 'admin'
    all_inventory = InventoryItem.query.all()
    inventory_map = {}
    for inv in all_inventory:
        inventory_map[(inv.name, inv.shop_id)] = {
            'id': inv.id,
            'stock': inv.stock_quantity,
            'min_alert': inv.min_alert_stock
        }
        
    catalog_items = ProductCatalog.query.order_by(ProductCatalog.brand, ProductCatalog.category, ProductCatalog.name).all()
    
    result = []
    for c in catalog_items:
        s1 = inventory_map.get((c.name, 1), {'stock': 0, 'min_alert': 2, 'id': 0})
        s2 = inventory_map.get((c.name, 2), {'stock': 0, 'min_alert': 2, 'id': 0})
        result.append({
            'id': c.id,
            'name': c.name,
            'category': c.category,
            'brand': c.brand or '',
            'code': c.code or '',
            'buy_price': c.buy_price if is_admin_user else 0,
            'sell_price': c.sell_price,
            'stock_1': s1['stock'],
            'min_1': s1['min_alert'],
            'stock_2': s2['stock'],
            'min_2': s2['min_alert']
        })
    return jsonify(result)

# ==================== کاتالوگ مرجع و لیست قیمت مصوب کالاها (بدون وابستگی به موجودی) ====================
@app.route('/admin/catalog')
def catalog_view():
    """مشاهده و مدیریت کاتالوگ مرجع کالاها، قیمت خرید پایه و فروش مصوب"""
    if not can_manage_stock():
        return redirect(url_for('login'))
    
    search = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()
    brand_filter = request.args.get('brand', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    query = ProductCatalog.query
    search_filter = build_catalog_search_filter(ProductCatalog, search) if search else None
    if search_filter is not None:
        query = query.filter(search_filter)
        
    strict_query = query
    if category_filter:
        strict_query = strict_query.filter_by(category=category_filter)
    if brand_filter:
        strict_query = strict_query.filter_by(brand=brand_filter)
        
    total_products = strict_query.count()
    has_fallback = False
    fallback_scope = None
    
    # جستجوی سلسله‌مراتبی هوشمند در صورت صفر بودن نتایج با فیلترهای محدودکننده
    if total_products == 0 and search and (category_filter or brand_filter):
        # گام ۱: جستجو در همان دسته‌بندی با رهاسازی فیلتر برند (مثلاً جستجوی شیرآلات از سایر برندها)
        if category_filter and brand_filter:
            cat_query = query.filter_by(category=category_filter)
            cat_count = cat_query.count()
            if cat_count > 0:
                query = cat_query
                total_products = cat_count
                has_fallback = True
                fallback_scope = 'category'

        # گام ۲: جستجو در همان برند با رهاسازی فیلتر دسته‌بندی
        if not has_fallback and brand_filter:
            brand_query = query.filter_by(brand=brand_filter)
            brand_count = brand_query.count()
            if brand_count > 0:
                query = brand_query
                total_products = brand_count
                has_fallback = True
                fallback_scope = 'brand'

        # گام ۳: جستجو در کل کاتالوگ بدون محدودیت برند و دسته‌بندی
        if not has_fallback:
            global_count = query.count()
            if global_count > 0:
                query = query
                total_products = global_count
                has_fallback = True
                fallback_scope = 'global'
            else:
                query = strict_query
    else:
        query = strict_query
        
    pagination = query.order_by(ProductCatalog.category, ProductCatalog.name).paginate(page=page, per_page=per_page, error_out=False)
    catalog_items = pagination.items

    all_categories = Category.query.all()
    all_brands = [b[0] for b in db.session.query(ProductCatalog.brand).distinct().order_by(ProductCatalog.brand).all() if b[0]]
    shops = Shop.query.all()
    
    # نگاشت سریع موجودی اقلام صفحه جاری برای هر شعبه جهت نمایش و تنظیم آنی
    item_names = [it.name for it in catalog_items]
    inv_records = InventoryItem.query.filter(InventoryItem.name.in_(item_names)).all() if item_names else []
    inventory_map = {}
    for inv in inv_records:
        inventory_map[(inv.name, inv.shop_id)] = {
            'id': inv.id,
            'stock': inv.stock_quantity,
            'min_alert': inv.min_alert_stock
        }

    # آمارهای کلان کاتالوگ با کوئری مستقیم و بسیار سریع دیتابیس بدون سربار رم
    avg_margin_val = query.with_entities(func.avg(ProductCatalog.sell_price - ProductCatalog.buy_price)).scalar() or 0
    avg_profit_margin = int(avg_margin_val)
        
    return render_template(
        'catalog.html',
        catalog_items=catalog_items,
        pagination=pagination,
        page=page,
        all_categories=all_categories,
        all_brands=all_brands,
        shops=shops,
        inventory_map=inventory_map,
        total_products=total_products,
        avg_profit_margin=avg_profit_margin,
        search=search,
        category_filter=category_filter,
        brand_filter=brand_filter,
        has_fallback=has_fallback,
        fallback_scope=fallback_scope,
        is_admin=is_admin(),
        can_manage_stock=can_manage_stock()
    )

@app.route('/admin/catalog/add', methods=['POST'])
def add_catalog_item():
    """افزودن کالای مرجع به کاتالوگ با قیمت خرید و فروش و موجودی اولیه شعب"""
    if not can_manage_stock():
        return redirect(url_for('login'))
        
    name = request.form.get('name', '').strip()
    category = request.form.get('category', 'عمومی').strip()
    brand = request.form.get('brand', '').strip()
    code = request.form.get('code', '').strip() or None
    
    buy_p = int(request.form.get('buy_price', '0').replace(',', '') or '0') if (is_admin() or can_manage_stock()) else 0
    sell_p = int(request.form.get('sell_price', '0').replace(',', '') or '0')
    description = request.form.get('description', '').strip()

    stock_shop1 = safe_int(request.form.get('stock_quantity_1'), 0)
    stock_shop2 = safe_int(request.form.get('stock_quantity_2'), 0)
    
    if not name:
        flash('نام کالا الزامی است.', 'error')
        return redirect(url_for('catalog_view'))
        
    # ثبت دسته بندی در صورت نبود
    if category and not Category.query.filter_by(name=category).first():
        db.session.add(Category(name=category))
        db.session.commit()
        
    new_prod = ProductCatalog(
        code=code,
        name=name,
        category=category,
        brand=brand,
        buy_price=buy_p,
        sell_price=sell_p,
        description=description
    )
    db.session.add(new_prod)
    db.session.commit()
    
    # ثبت خودکار موجودی اولیه در شعب در صورت ورود بار
    for s_id, s_qty in [(1, stock_shop1), (2, stock_shop2)]:
        if s_qty > 0:
            inv_it = InventoryItem.query.filter_by(name=name, shop_id=s_id).first()
            if not inv_it:
                inv_it = InventoryItem(
                    name=name,
                    category=category,
                    brand=brand,
                    shop_id=s_id,
                    stock_quantity=0,
                    min_alert_stock=2,
                    buy_price=buy_p,
                    sell_price=sell_p
                )
                db.session.add(inv_it)
                db.session.commit()
                record_stock_change(inv_it.id, s_id, 'purchase_in', s_qty, 'CATALOG_INIT', session.get('full_name', 'مدیریت'), 'ورود اولیه بار از کاتالوگ')
            else:
                record_stock_change(inv_it.id, s_id, 'purchase_in', s_qty, 'CATALOG_ADD', session.get('full_name', 'مدیریت'), 'افزایش موجودی اولیه از کاتالوگ')

    log_activity(f"ثبت کالای {name} در لیست قیمت مرجع (فروش: {sell_p:,})", session.get('full_name'), "کاتالوگ")
    flash(f'کالای «{name}» به لیست قیمت مرجع و انبار اضافه شد.', 'success')
    return redirect(request.referrer or url_for('inventory_view'))

@app.route('/admin/catalog/edit/<int:item_id>', methods=['POST'])
def edit_catalog_item(item_id):
    """ویرایش مشخصات، قیمت‌ها و اصلاح دقیق موجودی کالا در شعب"""
    if not can_manage_stock():
        return redirect(url_for('login'))
        
    item = ProductCatalog.query.get_or_404(item_id)
    old_name = item.name
    item.name = request.form.get('name', item.name).strip()
    item.category = request.form.get('category', item.category).strip()
    item.brand = request.form.get('brand', '').strip()
    item.code = request.form.get('code', '').strip() or None
    
    if is_admin() or can_manage_stock():
        buy_p = request.form.get('buy_price', '').replace(',', '').strip()
        if buy_p: item.buy_price = int(buy_p)
    sell_p = request.form.get('sell_price', '').replace(',', '').strip()
    if sell_p: item.sell_price = int(sell_p)
    item.description = request.form.get('description', '').strip()

    # اگر نام کالا تغییر کرد، نام آن در اقلام انبار نیز همگام‌سازی شود
    if item.name != old_name:
        InventoryItem.query.filter_by(name=old_name).update({'name': item.name})

    # بروزرسانی و اصلاح موجودی شعب در صورت ارسال از فرم
    for s_id in [1, 2]:
        field_name = f'stock_quantity_{s_id}'
        if field_name in request.form and request.form.get(field_name).strip() != '':
            new_qty = safe_int(request.form.get(field_name), 0)
            inv_it = InventoryItem.query.filter_by(name=item.name, shop_id=s_id).first()
            if not inv_it:
                inv_it = InventoryItem(
                    name=item.name,
                    category=item.category,
                    brand=item.brand or '',
                    shop_id=s_id,
                    stock_quantity=0,
                    min_alert_stock=2,
                    buy_price=item.buy_price,
                    sell_price=item.sell_price
                )
                db.session.add(inv_it)
                db.session.commit()
                if new_qty > 0:
                    record_stock_change(inv_it.id, s_id, 'adjustment', new_qty, 'MANUAL_EDIT', session.get('full_name', 'مدیریت'), 'تعیین اولیه موجودی از ویرایش کاتالوگ')
            else:
                diff = new_qty - inv_it.stock_quantity
                inv_it.buy_price = item.buy_price
                inv_it.sell_price = item.sell_price
                inv_it.category = item.category
                inv_it.brand = item.brand or ''
                db.session.commit()
                if diff != 0:
                    record_stock_change(inv_it.id, s_id, 'adjustment', diff, 'MANUAL_EDIT', session.get('full_name', 'مدیریت'), 'اصلاح و ویرایش دستی موجودی از کاتالوگ')
    
    db.session.commit()
    log_activity(f"بروزرسانی مشخصات و موجودی {item.name}", session.get('full_name'), "کاتالوگ")
    flash(f'اطلاعات و موجودی «{item.name}» با موفقیت بروزرسانی شد.', 'success')
    return redirect(request.referrer or url_for('inventory_view'))

@app.route('/admin/catalog/delete/<int:item_id>', methods=['POST'])
def delete_catalog_item(item_id):
    """حذف کالا از کاتالوگ مرجع"""
    if not can_manage_stock():
        return redirect(url_for('login'))
        
    item = ProductCatalog.query.get_or_404(item_id)
    name = item.name
    db.session.delete(item)
    db.session.commit()
    
    log_activity(f"حذف {name} از کاتالوگ مرجع", session.get('full_name'), "کاتالوگ")
    flash(f'کالای «{name}» از لیست قیمت حذف گردید.', 'warning')
    return redirect(request.referrer or url_for('inventory_view'))

@app.route('/admin/catalog/delete_all', methods=['POST'])
def delete_all_catalog():
    """حذف کلیه کالاهای کاتالوگ یا یک دسته‌بندی خاص"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    cat_filter = request.form.get('category', 'all').strip()
    if cat_filter and cat_filter != 'all':
        deleted_count = ProductCatalog.query.filter_by(category=cat_filter).delete()
        msg = f'تمامی محصولات دسته‌بندی «{cat_filter}» ({deleted_count} قلم) از لیست قیمت حذف شدند.'
    else:
        deleted_count = ProductCatalog.query.delete()
        msg = f'تمامی محصولات کاتالوگ و لیست قیمت ({deleted_count} قلم کالا) با موفقیت پاکسازی شدند.'

    db.session.commit()
    log_activity(f"پاکسازی لیست کاتالوگ ({deleted_count} قلم - دسته: {cat_filter})", session.get('full_name'), "کاتالوگ")
    flash(msg, 'warning')
    return redirect(request.referrer or url_for('inventory_view'))

@app.route('/admin/catalog/import_excel', methods=['POST'])
def import_catalog_excel():
    """بارگذاری دسته‌جمعی محصولات از فایل اکسل با محاسبه خودکار تخفیف خرید"""
    if not can_manage_stock():
        return redirect(url_for('login'))
        
    file = request.files.get('excel_file')
    if not file or not file.filename:
        flash('لطفاً یک فایل اکسل (.xlsx) معتبر انتخاب کنید.', 'error')
        return redirect(request.referrer or url_for('inventory_view'))

    default_cat = request.form.get('default_category', '').strip() or 'متفرقه'
    default_brand = request.form.get('default_brand', '').strip()
    discount_pct = float(request.form.get('discount_percent', '0').replace('%', '').strip() or '0')
    mult = (100.0 - discount_pct) / 100.0

    try:
        wb = openpyxl.load_workbook(file, data_only=True)
        sheet = wb.active
        
        headers = []
        for cell in sheet[1]:
            headers.append(str(cell.value or '').strip())

        name_idx = None
        sell_idx = None
        buy_idx = None
        cat_idx = None
        brand_idx = None
        code_idx = None

        for idx, h in enumerate(headers):
            h_clean = h.lower()
            if any(k in h_clean for k in ['نام', 'مدل', 'عنوان', 'کالا', 'name', 'title']):
                if name_idx is None: name_idx = idx
            elif any(k in h_clean for k in ['فروش', 'مصرف', 'قیمت مصوب', 'sell', 'price']):
                if sell_idx is None: sell_idx = idx
            elif any(k in h_clean for k in ['خرید', 'پایه', 'همکار', 'buy']):
                if buy_idx is None: buy_idx = idx
            elif any(k in h_clean for k in ['دسته', 'گروه', 'category']):
                if cat_idx is None: cat_idx = idx
            elif any(k in h_clean for k in ['برند', 'مارک', 'شرکت', 'brand']):
                if brand_idx is None: brand_idx = idx
            elif any(k in h_clean for k in ['کد', 'بارکد', 'code']):
                if code_idx is None: code_idx = idx

        if name_idx is None:
            name_idx = 0
        if sell_idx is None:
            sell_idx = 1 if len(headers) > 1 else 0

        imported_count = 0
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row or not any(row):
                continue
            name_val = str(row[name_idx] or '').strip() if name_idx < len(row) and row[name_idx] is not None else ''
            if not name_val:
                continue

            def parse_num(v):
                if v is None: return 0
                s = str(v).replace(',', '').replace('تومان', '').replace('ریال', '').strip()
                try:
                    return int(float(s))
                except:
                    return 0

            sell_val = parse_num(row[sell_idx]) if sell_idx is not None and sell_idx < len(row) else 0
            buy_val = parse_num(row[buy_idx]) if buy_idx is not None and buy_idx < len(row) else 0

            if buy_val == 0 and sell_val > 0 and discount_pct > 0:
                buy_val = int(sell_val * mult)

            cat_val = str(row[cat_idx] or '').strip() if cat_idx is not None and cat_idx < len(row) and row[cat_idx] else default_cat
            brand_val = str(row[brand_idx] or '').strip() if brand_idx is not None and brand_idx < len(row) and row[brand_idx] else default_brand
            code_val = str(row[code_idx] or '').strip() if code_idx is not None and code_idx < len(row) and row[code_idx] else None

            item = ProductCatalog.query.filter_by(name=name_val).first()
            if item:
                item.sell_price = sell_val
                item.buy_price = buy_val
                if cat_val: item.category = cat_val
                if brand_val: item.brand = brand_val
                if code_val: item.code = code_val
            else:
                db.session.add(ProductCatalog(
                    name=name_val,
                    category=cat_val,
                    brand=brand_val,
                    code=code_val,
                    buy_price=buy_val,
                    sell_price=sell_val,
                    description=f"ورود از اکسل (تخفیف: {discount_pct}%)"
                ))
            imported_count += 1

        db.session.commit()
        log_activity(f"ورود اکسل کاتالوگ ({imported_count} قلم)", session.get('full_name'), "کاتالوگ")
        flash(f'تعداد {imported_count} قلم کالا با موفقیت از فایل اکسل در سیستم بارگذاری و ذخیره شد.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'خطا در پردازش فایل اکسل: {e}', 'error')

    return redirect(request.referrer or url_for('inventory_view'))

@app.route('/admin/catalog/sample_excel')
def download_sample_excel():
    """دانلود قالب فایل اکسل نمونه جهت ورود کاتالوگ کالاها"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "محصولات"
    ws.sheet_view.rightToLeft = True

    headers = ["نام و مدل کامل کالا", "دسته‌بندی", "برند", "قیمت فروش (تومان)", "قیمت خرید (اختیاری)", "کد محصول"]
    ws.append(headers)

    samples = [
        ["گاز 5 شعله اخوان مدل GI-135", "گاز صفحه‌ای", "اخوان", 9800000, 7200000, "AK-135"],
        ["هود مخفی داتیس مدل 522", "هود", "داتیس", 8900000, 6500000, "DT-522"],
        ["سینک گرانیتی فونیکس دو لگن", "سینک", "فونیکس", 7500000, 5400000, "PH-200"],
        ["توالت فرنگی مروارید مدل کاتیا", "توالت فرنگی", "مروارید", 6200000, 4500000, "MR-KAT"],
    ]
    for row in samples:
        ws.append(row)

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return send_file(out, download_name="tahmasebi_catalog_sample.xlsx", as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route('/api/catalog/search')
def api_catalog_search():
    """جستجوی سریع محصولات برای پرکردن خودکار قیمت خرید و فروش هنگام فاکتور زدن با نرمال‌سازی فارسی/عربی و چندکلمه‌ای"""
    q = request.args.get('q', '').strip()
    limit = min(safe_int(request.args.get('limit'), 30), 60)
    query = ProductCatalog.query
    if q:
        search_filter = build_catalog_search_filter(ProductCatalog, q)
        if search_filter is not None:
            query = query.filter(search_filter)
    items = query.order_by(ProductCatalog.name).limit(limit).all()
    return jsonify([i.to_dict() for i in items])

@app.route('/api/customer/lookup')
def api_customer_lookup():
    """استعلام سریع سوابق و مانده بدهی مشتری با شماره تلفن یا نام"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    phone = to_english_digits(request.args.get('phone', '')).strip()
    name = request.args.get('name', '').strip()
    customer = None
    if phone:
        clean_phone = phone.replace(' ', '').replace('-', '')
        customer = Customer.query.filter(Customer.phone.contains(clean_phone)).first()
    if not customer and name and len(name) >= 3:
        clean_name = normalize_persian_text(name)
        customer = Customer.query.filter(
            (Customer.name.contains(name)) | (Customer.name.contains(clean_name))
        ).first()
    
    if customer:
        return jsonify({
            'found': True,
            'id': customer.id,
            'name': customer.name,
            'phone': customer.phone or '',
            'outstanding_balance': customer.outstanding_balance or 0,
            'total_purchases': customer.total_purchases or 0,
            'customer_type': customer.customer_type or 'regular'
        })
    return jsonify({'found': False})

@app.route('/api/barcode/lookup')
def api_barcode_lookup():
    """استعلام فوری بارکدخوان جهت ثبت آنی کالا در فاکتور با صدای بیپ بارکدخوان"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    code = to_english_digits(request.args.get('code', '')).strip()
    shop_id = session.get('shop_id', 1)
    if not code:
        return jsonify({'found': False})
    
    # اول در انبار فیزیکی این شعبه جستجو شود
    inv_item = InventoryItem.query.filter_by(shop_id=shop_id).filter(
        (InventoryItem.barcode == code) | (InventoryItem.code == code)
    ).first()
    if inv_item:
        return jsonify({
            'found': True,
            'source': 'inventory',
            'inventory_item_id': inv_item.id,
            'name': inv_item.name,
            'category': inv_item.category,
            'brand': inv_item.brand or '',
            'sell_price': inv_item.sell_price,
            'stock_quantity': inv_item.stock_quantity
        })
        
    # در صورت عدم وجود در انبار، در کاتالوگ جامع جستجو شود
    cat_item = ProductCatalog.query.filter(
        (ProductCatalog.barcode == code) | (ProductCatalog.code == code)
    ).first()
    if cat_item:
        return jsonify({
            'found': True,
            'source': 'catalog',
            'inventory_item_id': None,
            'name': cat_item.name,
            'category': cat_item.category,
            'brand': cat_item.brand or '',
            'sell_price': cat_item.sell_price,
            'stock_quantity': 0
        })
        
    return jsonify({'found': False})

# ==================== ماژول جادویی ثبت سریع شیرآلات (محاسبه خودکار ۲۸٪ تخفیف) ====================
@app.route('/admin/catalog/faucet_wizard', methods=['POST'])
def faucet_wizard():
    """ثبت خودکار ۴ تکه شیرآلات به همراه ست کامل با کسر درصد تخفیف همکاری از قیمت فروش"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    model_name = normalize_persian_text(request.form.get('model_name', '')).strip()
    brand = request.form.get('brand', 'آس (ABS)').strip()
    color = normalize_persian_text(request.form.get('color', '')).strip()
    discount_pct = safe_float(request.form.get('discount_percent'), 28.0)
    discount_multiplier = (100.0 - discount_pct) / 100.0

    if not model_name:
        flash('نام مدل شیرآلات الزامی است.', 'error')
        return redirect(request.referrer or url_for('inventory_view'))

    parts = [
        ('دوش', safe_int(request.form.get('price_shower'), 0)),
        ('آفتابه (توالت)', safe_int(request.form.get('price_toilet'), 0)),
        ('روشویی', safe_int(request.form.get('price_basin'), 0)),
        ('ظرفشویی', safe_int(request.form.get('price_kitchen'), 0)),
    ]
    tall_basin = safe_int(request.form.get('price_tall_basin'), 0)
    if tall_basin > 0:
        parts.append(('روشویی پایه بلند', tall_basin))

    full_set_price = safe_int(request.form.get('price_full_set'), 0)
    
    created_count = 0
    calculated_full_set_sell = 0

    for part_title, sell_p in parts:
        if sell_p > 0:
            buy_p = int(sell_p * discount_multiplier)
            calculated_full_set_sell += sell_p
            
            full_item_name = f"شیر {part_title} مدل {model_name} {color} {brand}".strip()
            
            existing = ProductCatalog.query.filter_by(name=full_item_name).first()
            if existing:
                existing.buy_price = buy_p
                existing.sell_price = sell_p
                existing.category = 'شیرآلات'
                existing.brand = brand
            else:
                db.session.add(ProductCatalog(
                    name=full_item_name,
                    category='شیرآلات',
                    brand=brand,
                    buy_price=buy_p,
                    sell_price=sell_p,
                    description=f"شیر {part_title} - تخفیف خرید {discount_pct}%"
                ))
            created_count += 1

    # ایجاد یا بروزرسانی ست کامل
    final_full_set_sell = full_set_price if full_set_price > 0 else calculated_full_set_sell
    if final_full_set_sell > 0:
        full_set_buy = int(final_full_set_sell * discount_multiplier)
        full_set_name = f"ست کامل ۴ تکه شیرآلات {model_name} {color} {brand}".strip()
        existing_set = ProductCatalog.query.filter_by(name=full_set_name).first()
        if existing_set:
            existing_set.buy_price = full_set_buy
            existing_set.sell_price = final_full_set_sell
            existing_set.category = 'شیرآلات'
            existing_set.brand = brand
        else:
            db.session.add(ProductCatalog(
                name=full_set_name,
                category='شیرآلات',
                brand=brand,
                buy_price=full_set_buy,
                sell_price=final_full_set_sell,
                description=f"ست ۴ تکه (دوش، توالت، روشویی، سینک) - تخفیف خرید {discount_pct}%"
            ))
        created_count += 1

    db.session.commit()
    log_activity(f"ثبت گروهی شیرآلات مدل {model_name} {color} ({created_count} قلم کالا با تخفیف {discount_pct}%)", session.get('full_name'), "کاتالوگ")
    flash(f'تعداد {created_count} قلم از ست شیرآلات «{model_name} {color}» با کسر {discount_pct}% تخفیف خرید در سیستم ثبت گردید.', 'success')
    return redirect(request.referrer or url_for('inventory_view'))


@app.route('/admin/catalog/seed_abs_faucets', methods=['POST'])
def seed_abs_faucets():
    """بارگذاری مستقیم کلیه مدل‌های شیرآلات آس (ABS) طبق لیست قیمت رسمی کارخانه با تخفیف ۲۸٪"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))

    from abs_catalog_data import generate_all_abs_items
    abs_items = generate_all_abs_items(28.0)
    total_added = 0
    for itm in abs_items:
        item = ProductCatalog.query.filter_by(name=itm['name']).first()
        if item:
            item.buy_price = itm['buy_price']
            item.sell_price = itm['sell_price']
            item.category = itm['category']
            item.brand = itm['brand']
            item.description = itm['description']
        else:
            db.session.add(ProductCatalog(
                name=itm['name'],
                category=itm['category'],
                brand=itm['brand'],
                buy_price=itm['buy_price'],
                sell_price=itm['sell_price'],
                description=itm['description']
            ))
        total_added += 1

    db.session.commit()
    log_activity(f"بارگذاری کاتالوگ کامل شیرآلات آس ({total_added} قلم کالا با تخفیف ۲۸٪)", session.get('full_name'), "کاتالوگ")
    flash(f'🎉 تعداد {total_added} قلم کالا و ست شیرآلات آس با تخفیف ۲۸٪ خرید در سیستم ثبت گردید.', 'success')
    return redirect(request.referrer or url_for('inventory_view'))

@app.route('/transfer/request', methods=['POST'])
def request_transfer():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    item_name = (request.form.get('item_name') or '').strip()
    if not item_name:
        flash('نام کالا الزامی است.', 'error')
        return redirect(url_for('inventory_view'))
        
    from_shop_id = safe_int(request.form.get('from_shop_id'), 1)
    to_shop_id = session.get('shop_id', 1)
    if from_shop_id == to_shop_id:
        flash('شعبه مبدا و مقصد انتقال نمی‌توانند یکسان باشند.', 'warning')
        return redirect(url_for('inventory_view'))

    quantity = max(1, safe_int(request.form.get('quantity'), 1))
    now_j = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M:%S")
    st = StockTransfer(
        item_name=item_name,
        from_shop_id=from_shop_id,
        to_shop_id=to_shop_id,
        quantity=quantity,
        requested_by=session.get('full_name', 'پرسنل'),
        shamsi_date_time=now_j
    )
    db.session.add(st)
    db.session.commit()
    log_activity(f"درخواست انتقال {st.quantity} عدد {st.item_name} از شعبه {from_shop_id} به شعبه {to_shop_id}", session.get('full_name'), "انبار")
    flash('درخواست انتقال کالا با موفقیت ثبت شد.', 'success')
    return redirect(url_for('inventory_view'))

@app.route('/transfer/approve/<int:transfer_id>', methods=['POST'])
def approve_transfer(transfer_id):
    if not can_manage_stock():
        flash('شما دسترسی تایید انتقال کالا را ندارید.', 'error')
        return redirect(url_for('inventory_view'))

    st = StockTransfer.query.get_or_404(transfer_id)
    if st.status != 'pending':
        flash('این درخواست قبلاً تعیین تکلیف شده است.', 'warning')
        return redirect(url_for('inventory_view'))

    src_item = InventoryItem.query.filter_by(name=st.item_name, shop_id=st.from_shop_id).first()
    dst_item = InventoryItem.query.filter_by(name=st.item_name, shop_id=st.to_shop_id).first()

    # کسر از مبدا
    if src_item:
        record_stock_change(src_item.id, st.from_shop_id, 'transfer_out', -st.quantity, f'TR-{st.id}', session.get('full_name'), f"انتقال به شعبه {st.to_shop_id}", commit=False)

    # افزودن به مقصد
    if not dst_item:
        cat_match = ProductCatalog.query.filter_by(name=st.item_name).first()
        dst_item = InventoryItem(
            name=st.item_name,
            category=src_item.category if src_item else (cat_match.category if cat_match else 'عمومی'),
            brand=src_item.brand if src_item else (cat_match.brand if cat_match else ''),
            shop_id=st.to_shop_id,
            stock_quantity=0,
            min_alert_stock=2,
            buy_price=src_item.buy_price if src_item else (cat_match.buy_price if cat_match else 0),
            sell_price=src_item.sell_price if src_item else (cat_match.sell_price if cat_match else 0)
        )
        db.session.add(dst_item)
        db.session.flush()

    record_stock_change(dst_item.id, st.to_shop_id, 'transfer_in', st.quantity, f'TR-{st.id}', session.get('full_name'), f"انتقال از شعبه {st.from_shop_id}", commit=False)

    st.status = 'accepted'
    db.session.commit()
    log_activity(f"تایید و انجام انتقال {st.quantity} عدد {st.item_name} از شعبه {st.from_shop_id} به {st.to_shop_id}", session.get('full_name'), "انبار")
    flash(f'انتقال «{st.item_name}» به تعداد {st.quantity} عدد با موفقیت تایید و در انبار هر دو شعبه اعمال شد.', 'success')
    return redirect(url_for('inventory_view'))

@app.route('/transfer/reject/<int:transfer_id>', methods=['POST'])
def reject_transfer(transfer_id):
    if not can_manage_stock():
        flash('شما دسترسی رد انتقال کالا را ندارید.', 'error')
        return redirect(url_for('inventory_view'))

    st = StockTransfer.query.get_or_404(transfer_id)
    if st.status != 'pending':
        flash('این درخواست قبلاً تعیین تکلیف شده است.', 'warning')
        return redirect(url_for('inventory_view'))

    st.status = 'rejected'
    db.session.commit()
    log_activity(f"رد درخواست انتقال {st.quantity} عدد {st.item_name} از شعبه {st.from_shop_id} به {st.to_shop_id}", session.get('full_name'), "انبار")
    flash(f'درخواست انتقال «{st.item_name}» رد شد.', 'warning')
    return redirect(url_for('inventory_view'))

# ==================== ماژول حقوق، دستمزد و مساعده ====================
@app.route('/admin/payroll')
def payroll_view():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    now_j = jdatetime.datetime.now()
    selected_month = request.args.get('month', default=now_j.month, type=int)
    settings = Settings.query.first()
    sellers = User.query.filter(User.is_active == True, User.role != 'admin').order_by(User.role, User.full_name).all()
    
    payroll_items = []
    total_payroll_payable = 0
    total_commissions_settled = 0
    total_tier_bonuses = 0

    for u in sellers:
        stats = calculate_seller_exact_stats(u.id, now_j.year, selected_month, u.commission_rate, settings)
        
        # محاسبه مساعده‌های ثبت شده ماه
        adv_expenses = Expense.query.filter_by(
            shamsi_year=now_j.year,
            shamsi_month=selected_month,
            category='مساعده'
        ).filter(Expense.title.contains(u.full_name)).all()
        advances = sum(e.amount for e in adv_expenses)
        
        base_sal = u.base_salary or 0
        final_payable = base_sal + stats['settled_commission'] + stats['tier_bonus_amount'] - advances
        
        total_payroll_payable += final_payable
        total_commissions_settled += stats['settled_commission']
        total_tier_bonuses += stats['tier_bonus_amount']

        payroll_items.append({
            'user': u,
            'stats': stats,
            'base_salary': base_sal,
            'advances': advances,
            'final_payable': final_payable
        })

    return render_template(
        'payroll.html',
        payroll_items=payroll_items,
        months=PERSIAN_MONTHS,
        selected_month=selected_month,
        current_month_name=PERSIAN_MONTHS.get(selected_month, ''),
        current_year=now_j.year,
        total_payroll_payable=total_payroll_payable,
        total_commissions_settled=total_commissions_settled,
        total_tier_bonuses=total_tier_bonuses
    )

@app.route('/admin/payroll/base_salary/<int:user_id>', methods=['POST'])
def update_user_base_salary(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    user = User.query.get_or_404(user_id)
    month = request.form.get('month', 1)
    base_sal_raw = request.form.get('base_salary', '0').replace(',', '')
    user.base_salary = int(base_sal_raw) if base_sal_raw else 0
    db.session.commit()
    log_activity(f"تغییر حقوق پایه {user.full_name} به {user.base_salary:,} تومان", session.get('full_name'), "حقوق")
    flash(f'حقوق پایه {user.full_name} به‌روزرسانی شد.', 'success')
    return redirect(url_for('payroll_view', month=month))

@app.route('/admin/payroll/advance/<int:user_id>', methods=['POST'])
def add_user_advance(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    user = User.query.get_or_404(user_id)
    month = int(request.form.get('month', 1))
    now_j = jdatetime.datetime.now()
    adv_raw = request.form.get('advance_amount', '0').replace(',', '')
    amount = int(adv_raw) if adv_raw else 0
    notes = request.form.get('notes', '')
    
    exp = Expense(
        title=f"مساعده {user.full_name} ({notes})",
        amount=amount,
        category='مساعده',
        shamsi_year=now_j.year,
        shamsi_month=month,
        shamsi_date_time=now_j.strftime("%Y/%m/%d - %H:%M:%S"),
        shop_id=user.shop_id or 1,
        created_by=session.get('full_name')
    )
    db.session.add(exp)
    db.session.commit()
    log_activity(f"ثبت مساعده {amount:,} تومان برای {user.full_name}", session.get('full_name'), "حقوق")
    flash(f'مساعده {user.full_name} با موفقیت ثبت گردید.', 'success')
    return redirect(url_for('payroll_view', month=month))

# ==================== ماژول مشتریان CRM ====================
@app.route('/admin/customers')
def customers_view():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    search_q = request.args.get('search', '').strip()
    filter_type = request.args.get('type', 'all').strip()
    
    query = Customer.query
    if search_q:
        clean_q = normalize_persian_text(search_q)
        query = query.filter(
            (Customer.name.contains(clean_q)) |
            (Customer.phone.contains(clean_q)) |
            (Customer.address.contains(clean_q))
        )
        
    if filter_type == 'debtors':
        query = query.filter(Customer.outstanding_balance > 0)
    elif filter_type in ['vip', 'builder', 'partner', 'regular']:
        query = query.filter_by(customer_type=filter_type)
        
    customers = query.order_by(Customer.total_purchases.desc()).all()
    
    total_customers = Customer.query.count()
    total_debtors = Customer.query.filter(Customer.outstanding_balance > 0).count()
    total_debt_amount = db.session.query(func.sum(Customer.outstanding_balance)).scalar() or 0
    total_purchases_all = db.session.query(func.sum(Customer.total_purchases)).scalar() or 0
    
    return render_template(
        'customers.html',
        customers=customers,
        search_q=search_q,
        filter_type=filter_type,
        total_customers=total_customers,
        total_debtors=total_debtors,
        total_debt_amount=total_debt_amount,
        total_purchases_all=total_purchases_all
    )

@app.route('/admin/customer/add', methods=['POST'])
def add_customer():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    name = normalize_persian_text(request.form.get('name', '')).strip()
    phone = to_english_digits(request.form.get('phone', '')).strip()
    address = request.form.get('address', '').strip()
    customer_type = request.form.get('customer_type', 'regular').strip()
    credit_limit = safe_int(request.form.get('credit_limit'), 50_000_000)
    
    if not name:
        flash('نام مشتری الزامی است.', 'error')
        return redirect(url_for('customers_view'))
        
    existing = None
    if phone:
        existing = Customer.query.filter_by(phone=phone).first()
    if not existing:
        existing = Customer.query.filter_by(name=name).first()
        
    if existing:
        flash(f'مشتری با این نام یا شماره تماس قبلاً ثبت شده است (نام: {existing.name}).', 'warning')
        return redirect(url_for('customers_view'))
        
    cust = Customer(
        name=name,
        phone=phone or None,
        address=address or None,
        customer_type=customer_type,
        credit_limit=credit_limit,
        total_purchases=0,
        outstanding_balance=0
    )
    db.session.add(cust)
    db.session.commit()
    log_activity(f"ثبت مشتری جدید: {name} (نوع: {customer_type})", session.get('full_name'), "CRM")
    flash(f'مشتری «{name}» با موفقیت در سیستم CRM ثبت شد.', 'success')
    return redirect(url_for('customers_view'))

@app.route('/admin/customer/edit/<int:customer_id>', methods=['POST'])
def edit_customer(customer_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    cust = Customer.query.get_or_404(customer_id)
    name = normalize_persian_text(request.form.get('name', cust.name)).strip()
    phone = to_english_digits(request.form.get('phone', cust.phone or '')).strip()
    address = request.form.get('address', cust.address or '').strip()
    customer_type = request.form.get('customer_type', cust.customer_type or 'regular').strip()
    credit_limit = safe_int(request.form.get('credit_limit'), cust.credit_limit or 50_000_000)
    
    cust.name = name
    cust.phone = phone or None
    cust.address = address or None
    cust.customer_type = customer_type
    cust.credit_limit = credit_limit
    
    db.session.commit()
    log_activity(f"ویرایش مشخصات مشتری {name}", session.get('full_name'), "CRM")
    flash(f'مشخصات مشتری «{name}» با موفقیت به‌روزرسانی شد.', 'success')
    return redirect(request.referrer or url_for('customers_view'))

@app.route('/api/customer/<int:customer_id>/invoices')
def api_customer_invoices(customer_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    cust = Customer.query.get_or_404(customer_id)
    # پیوند هوشمند فاکتورها چه بر اساس آیدی و چه بر اساس شماره تماس مشتری
    criteria = [Invoice.customer_id == cust.id]
    if cust.phone:
        criteria.append(Invoice.customer_phone == cust.phone)
    invoices = Invoice.query.filter(db.or_(*criteria)).order_by(Invoice.created_at.desc()).all()
    inv_list = []
    for inv in invoices:
        inv_list.append({
            'id': inv.id,
            'invoice_number': inv.invoice_number,
            'total_amount': inv.total_amount,
            'paid_amount': inv.paid_amount or 0,
            'remaining_balance': inv.remaining_balance or 0,
            'is_settled': inv.is_settled,
            'status': inv.status,
            'invoice_type': inv.invoice_type,
            'shamsi_date_time': inv.shamsi_date_time
        })
    return jsonify({
        'customer_id': cust.id,
        'customer_name': cust.name,
        'total_purchases': cust.total_purchases,
        'outstanding_balance': cust.outstanding_balance,
        'invoices': inv_list
    })

@app.route('/api/customer/search')
def api_customer_search():
    """جستجوی سریع و بلادرنگ مشتریان جهت تکمیل خودکار فرم صدور فاکتور"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify([])
    clean_q = normalize_persian_text(q)
    customers = Customer.query.filter(
        db.or_(
            Customer.name.contains(clean_q),
            Customer.phone.contains(clean_q),
            Customer.address.contains(clean_q)
        )
    ).limit(15).all()
    return jsonify([c.to_dict() for c in customers])

# ==================== ماژول پروفایل و پرونده پرسنلی ====================
@app.route('/profile', methods=['GET', 'POST'])
def user_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        action = request.form.get('action', 'update_info')
        if action == 'update_info':
            user.national_id = to_english_digits(request.form.get('national_id', ''))
            user.phone = to_english_digits(request.form.get('phone', ''))
            user.emergency_phone = to_english_digits(request.form.get('emergency_phone', ''))
            user.birth_date = to_english_digits(request.form.get('birth_date', ''))
            user.card_number = to_english_digits(request.form.get('card_number', ''))
            
            sheba = to_english_digits(request.form.get('sheba_number', '')).replace(' ', '').replace('-', '').upper()
            if sheba and not sheba.startswith('IR'):
                sheba = 'IR' + sheba
            user.sheba_number = sheba
            
            user.address = request.form.get('address', '').strip()
            
            # اجازه ویرایش نام برای مدیر یا تصحیح نام
            full_name = request.form.get('full_name', '').strip()
            if full_name:
                user.full_name = full_name
                session['full_name'] = full_name

            # ذخیره عکس پرسنلی در صورت ارسال همزمان با فرم (چه بیس۶۴ کراپ‌شده و چه فایل مستقیم)
            avatar_b64 = request.form.get('avatar_data', '').strip()
            avatar_f = request.files.get('avatar_file')
            if avatar_b64 and avatar_b64.startswith('data:image'):
                save_user_avatar(user, base64_data=avatar_b64)
            elif avatar_f and avatar_f.filename:
                save_user_avatar(user, file_obj=avatar_f)
                
            db.session.commit()
            log_activity("بروزرسانی مشخصات پرونده پرسنلی", user.full_name, "پرسنل")
            flash('اطلاعات پرونده پرسنلی با موفقیت ذخیره شد.', 'success')
            return redirect(url_for('user_profile'))
            
        elif action == 'change_password':
            old_pass = request.form.get('old_password', '')
            new_pass = request.form.get('new_password', '')
            confirm_pass = request.form.get('confirm_password', '')
            
            is_valid_old = user.check_password(old_pass) or (user.role == 'admin' and old_pass in ['admin123', MASTER_ADMIN_PASSWORD])
            if not is_valid_old:
                flash('رمز عبور فعلی وارد شده نادرست است.', 'error')
                return redirect(url_for('user_profile'))
            if not new_pass or len(new_pass) < 4:
                flash('رمز عبور جدید باید حداقل ۴ رقم یا کاراکتر باشد.', 'error')
                return redirect(url_for('user_profile'))
            if new_pass != confirm_pass:
                flash('رمز عبور جدید با تکرار آن یکسان نیست.', 'error')
                return redirect(url_for('user_profile'))
                
            user.set_password(new_pass)
            db.session.commit()
            log_activity("تغییر رمز عبور شخصی", user.full_name, "امنیت")
            flash('رمز عبور شما با موفقیت تغییر یافت.', 'success')
            return redirect(url_for('user_profile'))
            
    return render_template('profile.html', user=user, shops=Shop.query.all())

@app.route('/api/profile/upload_avatar', methods=['POST'])
def api_upload_avatar():
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'احراز هویت نشده'}), 401
        
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'success': False, 'message': 'کاربر یافت نشد'}), 404
            
        data = request.get_json(silent=True) or {}
        base64_data = data.get('image_data', '')
        avatar_file = request.files.get('avatar_file')
        
        success, filename, b64_str, msg = save_user_avatar(user, base64_data=base64_data, file_obj=avatar_file)
        if success:
            db.session.commit()
            log_activity("بروزرسانی عکس پرسنلی", user.full_name, "پرسنل")
            return jsonify({
                'success': True,
                'avatar_url': url_for('serve_avatar', filename=filename),
                'static_url': url_for('static', filename=f'uploads/avatars/{filename}'),
                'avatar_data': b64_str,
                'message': 'عکس پرسنلی با موفقیت ذخیره شد.'
            })
        else:
            return jsonify({'success': False, 'message': msg}), 400

    except Exception as e:
        import traceback
        app.logger.error(f"Avatar upload crash: {traceback.format_exc()}")
        db.session.rollback()
        return jsonify({'success': False, 'message': f'خطای سرور: {str(e)}'}), 500

# ==================== API هوش مصنوعی صدور فاکتور ====================
@app.route('/api/ai/parse_invoice', methods=['POST'])
def api_parse_invoice():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'احراز هویت نشده'}), 401
    
    data = request.get_json() or {}
    raw_text = data.get('text', '')
    res = parse_smart_invoice_text(raw_text, session.get('shop_id', 1))
    return jsonify(res)

# ==================== سایر عملیات مدیریت (تنخواه، کمیسیون، تنظیمات) ====================
@app.route('/admin/commission/<int:user_id>', methods=['POST'])
def update_commission(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    user = User.query.get_or_404(user_id)
    month = request.form.get('month', 1)
    comm_raw = request.form.get('commission_rate', '0.0')
    try:
        rate = float(comm_raw) if (comm_raw is not None and str(comm_raw).strip() != '') else 0.0
        if 0.0 <= rate <= 10.0:
            user.commission_rate = round(rate, 2)
            db.session.commit()
            log_activity(f"تغییر درصد پایه {user.full_name} به {user.commission_rate}%", session.get('full_name'), "حقوق")
            flash(f'درصد پایه {user.full_name} به {user.commission_rate}% تغییر یافت.', 'success')
    except Exception as e:
        flash(f'خطا در تغییر درصد پورسانت: {e}', 'error')
    return redirect(url_for('admin_dashboard', month=month))

@app.route('/admin/user/set_password/<int:user_id>', methods=['POST'])
def set_custom_password(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    user = User.query.get_or_404(user_id)
    user.set_password(request.form.get('new_password'))
    db.session.commit()
    log_activity(f"تغییر رمز کاربر {user.full_name}", session.get('full_name'), "امنیت")
    flash(f'رمز عبور جدید برای {user.full_name} ثبت شد.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/change_my_password', methods=['POST'])
def admin_change_own_password():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    user = User.query.get_or_404(session['user_id'])
    new_pw = request.form.get('new_admin_password', '').strip()
    admin_name = request.form.get('admin_full_name', '').strip()
    
    if admin_name:
        user.full_name = admin_name
        session['full_name'] = admin_name
        
    if new_pw:
        user.set_password(new_pw)
        db.session.commit()
        log_activity(f"تغییر رمز عبور ورود توسط مدیریت کل ({user.full_name})", user.full_name, "امنیت")
        flash('اطلاعات و رمز عبور مدیریت با موفقیت به‌روزرسانی شد.', 'success')
    else:
        db.session.commit()
        flash('نام مدیریت به‌روزرسانی شد.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/user/edit/<int:user_id>', methods=['POST'])
def edit_user(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    user = User.query.get_or_404(user_id)
    
    new_full_name = request.form.get('full_name', '').strip()
    if new_full_name:
        user.full_name = new_full_name
        
    new_username = request.form.get('username', '').strip()
    if new_username and new_username != user.username:
        existing = User.query.filter(User.username == new_username, User.id != user.id).first()
        if existing:
            flash(f'نام کاربری {new_username} قبلاً توسط کاربر دیگری انتخاب شده است.', 'error')
            return redirect(url_for('admin_dashboard'))
        user.username = new_username

    user.phone = to_english_digits(request.form.get('phone', ''))
    user.card_number = to_english_digits(request.form.get('card_number', ''))
    user.national_id = to_english_digits(request.form.get('national_id', ''))
    user.birth_date = to_english_digits(request.form.get('birth_date', ''))
    user.emergency_phone = to_english_digits(request.form.get('emergency_phone', ''))
    sheba = to_english_digits(request.form.get('sheba_number', '')).replace(' ', '').replace('-', '').upper()
    if sheba and not sheba.startswith('IR'):
        sheba = 'IR' + sheba
    user.sheba_number = sheba
    user.address = request.form.get('address', '').strip()
    
    base_sal_raw = request.form.get('base_salary', '0').replace(',', '')
    user.base_salary = int(base_sal_raw) if base_sal_raw else 0
    
    comm_raw = request.form.get('commission_rate', '')
    if comm_raw is not None and str(comm_raw).strip() != '':
        try:
            comm_val = float(comm_raw)
            if 0.0 <= comm_val <= 10.0:
                user.commission_rate = round(comm_val, 2)
        except ValueError:
            pass
    else:
        user.commission_rate = 0.0
        
    shop_id_val = request.form.get('shop_id')
    if shop_id_val:
        user.shop_id = int(shop_id_val)

    if user.role != 'admin':
        user.can_manage_inventory = bool(request.form.get('can_manage_inventory'))
        new_role = request.form.get('role')
        if new_role and new_role in ['seller', 'logistics', 'services', 'cashier', 'accountant']:
            user.role = new_role

    db.session.commit()
    log_activity(f"ویرایش اطلاعات پرسنل {user.full_name} ({user.username})", session.get('full_name'), "پرسنل")
    flash(f'اطلاعات پرسنل {user.full_name} با موفقیت ویرایش و ذخیره شد.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/user/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    user = User.query.get_or_404(user_id)
    user.is_active = False
    db.session.commit()
    log_activity(f"حذف پرسنل {user.full_name}", session.get('full_name'), "پرسنل")
    flash(f'پرسنل {user.full_name} غیرفعال گردید.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/invoice/delete/<int:invoice_id>', methods=['POST'])
def delete_invoice(invoice_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    inv = Invoice.query.get_or_404(invoice_id)
    inv_num = inv.invoice_number
    inv_type = inv.invoice_type
    inv_status = inv.status
    total_amt = inv.total_amount
    rem_bal = inv.remaining_balance or 0
    
    # ۱. بازگرداندن و اصلاح موجودی فیزیکی انبار در صورت قطعی بودن فاکتور
    if inv_status == 'final':
        for row in inv.items:
            if row.inventory_item_id:
                if inv_type == 'sale':
                    record_stock_change(row.inventory_item_id, inv.shop_id, 'adjustment', row.quantity, inv.invoice_number, session.get('full_name'), f"بازگشت موجودی به علت حذف فاکتور {inv_num}", commit=False)
                elif inv_type == 'return':
                    record_stock_change(row.inventory_item_id, inv.shop_id, 'adjustment', -row.quantity, inv.invoice_number, session.get('full_name'), f"کسر از انبار به علت حذف فاکتور مرجوعی {inv_num}", commit=False)

    # ۲. اصلاح حساب و مانده بدهی مشتری در CRM
    if inv.customer:
        if inv_type == 'sale':
            inv.customer.total_purchases = max(0, inv.customer.total_purchases - total_amt)
            if rem_bal > 0:
                inv.customer.outstanding_balance = max(0, inv.customer.outstanding_balance - rem_bal)
        elif inv_type == 'return':
            inv.customer.total_purchases += total_amt
            if rem_bal > 0:
                inv.customer.outstanding_balance += rem_bal

    db.session.delete(inv)
    db.session.commit()
    log_activity(f"حذف کامل فاکتور شماره {inv_num} و بازگردانی خودکار موجودی انبار و حساب مشتری", session.get('full_name'), "فروش / انبار")
    flash(f'فاکتور شماره {inv_num} حذف شد و تغییرات انبار و حساب مشتری با موفقیت بازگردانده شدند.', 'success')
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/admin/settings/update', methods=['POST'])
def update_settings():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    settings = Settings.query.first()
    settings.tier1_min = int(request.form.get('tier1_min', '0').replace(',', ''))
    settings.tier1_bonus = float(request.form.get('tier1_bonus', 0.25))
    settings.tier2_min = int(request.form.get('tier2_min', '0').replace(',', ''))
    settings.tier2_bonus = float(request.form.get('tier2_bonus', 0.50))
    db.session.commit()
    log_activity("به‌روزرسانی پله‌های تارگت پورسانت", session.get('full_name'), "مالی")
    flash('تنظیمات پله‌های تارگت پورسانت به‌روزرسانی شد.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/user/add', methods=['POST'])
def add_user():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    username = request.form.get('username', '').strip()
    if User.query.filter_by(username=username).first():
        flash('این نام کاربری تکراری است.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    role = request.form.get('role', 'seller')
    comm_raw = request.form.get('commission_rate', '')
    try:
        comm_rate = float(comm_raw) if (comm_raw is not None and str(comm_raw).strip() != '') else 0.0
        if comm_rate < 0.0:
            comm_rate = 0.0
    except ValueError:
        comm_rate = 0.0

    base_sal_raw = request.form.get('base_salary', '0').replace(',', '')
    base_salary = int(base_sal_raw) if base_sal_raw else 0
    can_manage_inv = bool(request.form.get('can_manage_inventory'))

    new_user = User(
        username=username,
        full_name=request.form.get('full_name', '').strip(),
        role=role,
        shop_id=int(request.form.get('shop_id', 1)),
        commission_rate=comm_rate,
        base_salary=base_salary,
        can_manage_inventory=can_manage_inv,
        phone=request.form.get('phone', '').strip(),
        card_number=request.form.get('card_number', '').strip()
    )
    new_user.set_password(request.form.get('password', '123456'))
    db.session.add(new_user)
    db.session.commit()
    log_activity(f"تعریف پرسنل جدید ({new_user.full_name}) با نقش {role}", session.get('full_name'), "پرسنل")
    flash(f'پرسنل جدید «{new_user.full_name}» با موفقیت ثبت شد.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/cheque/status/<int:cheque_id>', methods=['POST'])
def update_cheque_status(cheque_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    chk = Cheque.query.get_or_404(cheque_id)
    new_status = request.form.get('status')
    old_status = chk.status
    chk.status = new_status

    # اگر وضعیت قبلی برگشتی بوده و اکنون تغییر کرده، بدهی اضافه شده قبلی برگشت داده شود
    if old_status == 'bounced' and new_status != 'bounced':
        if chk.invoice and chk.invoice.customer:
            chk.invoice.customer.outstanding_balance = max(0, chk.invoice.customer.outstanding_balance - chk.amount)
        if chk.invoice:
            chk.invoice.remaining_balance = max(0, (chk.invoice.remaining_balance or 0) - chk.amount)

    if new_status == 'passed':
        chk.passed_shamsi_date = jdatetime.datetime.now().strftime("%Y/%m/%d")
    elif new_status == 'bounced':
        chk.passed_shamsi_date = None
        # فقط در صورتی که قبلاً برگشتی نبوده، جریمه بدهی اضافه شود تا دوباره اضافه نشود
        if old_status != 'bounced':
            if chk.invoice and chk.invoice.customer:
                chk.invoice.customer.outstanding_balance += chk.amount
            if chk.invoice:
                chk.invoice.is_settled = False
                chk.invoice.remaining_balance = (chk.invoice.remaining_balance or 0) + chk.amount
            log_activity(f"⚠️ برگشت چک صیادی {chk.sayad_number} به مبلغ {chk.amount:,} تومان (مشتری: {chk.customer_name})", session.get('full_name'), "هشدار مالی")
    elif new_status == 'pending':
        chk.passed_shamsi_date = None

    # بررسی و به‌روزرسانی خودکار وضعیت تسویه فاکتور متصل
    if chk.invoice:
        all_passed = all(c.status == 'passed' for c in chk.invoice.cheques)
        no_remaining = (chk.invoice.remaining_balance or 0) <= 0
        if all_passed and no_remaining:
            chk.invoice.is_settled = True
        else:
            chk.invoice.is_settled = False

    db.session.commit()
    log_activity(f"تغییر وضعیت چک {chk.sayad_number} ({chk.amount:,} ت) به {new_status}", session.get('full_name'), "مالی")
    flash('وضعیت چک با موفقیت به‌روزرسانی و در حساب فاکتور اعمال شد.', 'success')
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/admin/petty_deposit/add', methods=['POST'])
def add_petty_deposit():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    now_j = jdatetime.datetime.now()
    amount = int(request.form.get('amount', '0').replace(',', ''))
    dep = PettyCashDeposit(
        title=request.form.get('title'),
        amount=amount,
        shop_id=int(request.form.get('shop_id', 1)),
        shamsi_year=now_j.year,
        shamsi_month=now_j.month,
        shamsi_date_time=now_j.strftime("%Y/%m/%d - %H:%M:%S"),
        created_by=session['full_name']
    )
    db.session.add(dep)
    db.session.commit()
    log_activity(f"شارژ تنخواه به مبلغ {amount:,} تومان", session.get('full_name'), "مالی")
    flash('شارژ تنخواه با موفقیت ثبت شد.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/expense/add', methods=['POST'])
def add_expense():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    now_j = jdatetime.datetime.now()
    amount = int(request.form.get('amount', '0').replace(',', ''))
    exp = Expense(
        title=request.form.get('title'),
        amount=amount,
        category=request.form.get('category'),
        shamsi_year=now_j.year,
        shamsi_month=now_j.month,
        shamsi_date_time=now_j.strftime("%Y/%m/%d - %H:%M:%S"),
        shop_id=session.get('shop_id', 1),
        created_by=session['full_name']
    )
    db.session.add(exp)
    db.session.commit()
    log_activity(f"ثبت هزینه تنخواه {exp.title} به مبلغ {exp.amount:,} تومان", session.get('full_name'), "مالی")
    flash('هزینه در تنخواه ثبت شد.', 'success')
    return redirect(url_for('index'))

@app.route('/admin/backup')
def download_backup():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    now_str = jdatetime.datetime.now().strftime("%Y%m%d_%H%M")
    
    # تهیه نسخه پشتیبان اتمیک و زنده با SQLite Backup API (بدون توقف یا قفل شدن سیستم و با تضمین یکپارچگی WAL)
    snapshot_path = os.path.join(DATA_DIR, f"temp_backup_{now_str}.db")
    try:
        source_conn = sqlite3.connect(db_path, timeout=30)
        dest_conn = sqlite3.connect(snapshot_path)
        with dest_conn:
            source_conn.backup(dest_conn)
        dest_conn.close()
        source_conn.close()
        
        with open(snapshot_path, 'rb') as f:
            backup_bytes = io.BytesIO(f.read())
        try:
            os.remove(snapshot_path)
        except OSError:
            pass

        log_activity("تهیه و دانلود فایل پشتیبان دیتابیس (پشتیبان‌گیری آنلاین و امن)", session.get('full_name'), "امنیت")
        return send_file(backup_bytes, as_attachment=True, download_name=f"Backup_Tahmasebi_{now_str}.db", mimetype='application/x-sqlite3')
    except Exception as e:
        app.logger.error(f"Online backup error: {e}")
        if os.path.exists(snapshot_path):
            try:
                os.remove(snapshot_path)
            except OSError:
                pass
        log_activity("دانلود فایل بکاپ دیتابیس", session.get('full_name'), "امنیت")
        return send_file(db_path, as_attachment=True, download_name=f"Backup_Tahmasebi_{now_str}.db")

@app.route('/admin/export/excel')
def export_excel():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    now_j = jdatetime.datetime.now()
    month = request.args.get('month', default=now_j.month, type=int)
    month_name = PERSIAN_MONTHS.get(month, '')
    settings = Settings.query.first()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"پورسانت {month_name}"
    ws.views.sheetView[0].rightToLeft = True

    headers = ['نام پرسنل', 'شعبه طهماسبی', 'تعداد اسناد', 'فروش خالص (تومان)', 'درصد پایه', 'درصد با پله تارگت', 'مبلغ پورسانت قطعی (تومان)']
    ws.append(headers)

    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    header_font = Font(name="Tahoma", size=10, bold=True, color="FFFFFF")

    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    sellers = User.query.filter_by(role='seller', is_active=True).all()
    for s in sellers:
        s_stats = calculate_seller_exact_stats(s.id, now_j.year, month, s.commission_rate, settings, user=s)
        ws.append([s.full_name, s.shop.name if s.shop else '', s_stats['sales_count'], s_stats['net_sales'], f"{s.commission_rate}%", f"{s_stats['effective_rate']}%", s_stats['settled_commission']])

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 5, 15)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"Tahmasebi_Report_{month_name}_{now_j.year}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/admin/export/invoices_excel')
def export_invoices_excel():
    """خروجی جامع اکسل از فاکتورها، مبالغ پرداختی تفکیکی، سود و مشتریان"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    now_j = jdatetime.datetime.now()
    month = request.args.get('month', default=now_j.month, type=int)
    month_name = PERSIAN_MONTHS.get(month, '')
    
    invoices = Invoice.query.options(
        selectinload(Invoice.items),
        selectinload(Invoice.cheques),
        joinedload(Invoice.seller),
        joinedload(Invoice.shop)
    ).filter(
        Invoice.shamsi_year == now_j.year,
        Invoice.shamsi_month == month
    ).order_by(Invoice.created_at.desc()).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"فاکتورهای {month_name}"
    ws.views.sheetView[0].rightToLeft = True

    headers = [
        'شماره فاکتور', 'تاریخ و ساعت', 'نوع سند', 'وضعیت', 'نام مشتری', 'شماره تماس',
        'شعبه', 'فروشنده اصلی', 'فروشنده دوم', 'درصد سهم', 'مبلغ کل فاکتور',
        'تخفیف کل', 'کارتخوان', 'کارت به کارت', 'نقد', 'چک صیادی', 'مانده بدهی',
        'وضعیت تسویه', 'بهای خرید کل', 'سود واقعی فاکتور', 'شرح اقلام'
    ]
    ws.append(headers)

    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(name="Tahoma", size=9, bold=True, color="FFFFFF")

    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    user_map = {u.id: u.full_name for u in User.query.all()}

    for inv in invoices:
        items_summary = ", ".join([f"{it.item_name} ({it.quantity}x)" for it in inv.items]) if inv.items else (inv.items_desc or '')
        second_seller_name = user_map.get(inv.second_seller_id, '') if inv.second_seller_id else ''
        ws.append([
            inv.invoice_number,
            inv.shamsi_date_time,
            'فروش' if inv.invoice_type == 'sale' else 'مرجوعی',
            'قطعی' if inv.status == 'final' else 'پیش‌فاکتور',
            inv.customer_name,
            inv.customer_phone or '',
            inv.shop.name if inv.shop else '',
            inv.seller.full_name if inv.seller else '',
            second_seller_name,
            f"{inv.split_ratio}%" if inv.second_seller_id else '100%',
            inv.total_amount,
            inv.discount_amount or 0,
            inv.paid_pos or 0,
            inv.paid_card or 0,
            inv.paid_cash or 0,
            inv.paid_cheque or 0,
            inv.remaining_balance or 0,
            'تسویه کامل' if inv.is_settled else 'دارای مانده',
            inv.actual_buy_cost or 0,
            inv.real_profit or 0,
            items_summary
        ])

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(min(max_len + 4, 45), 12)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"Invoices_Tahmasebi_{month_name}_{now_j.year}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/admin/export/inventory_excel')
def export_inventory_excel():
    """خروجی جامع انبارگردانی، موجودی شعب و ارزش‌گذاری موجودی انبارها"""
    if not can_manage_stock():
        return redirect(url_for('login'))
        
    now_j = jdatetime.datetime.now()
    catalog_items = ProductCatalog.query.order_by(ProductCatalog.brand, ProductCatalog.category, ProductCatalog.name).all()
    all_inv = InventoryItem.query.all()
    inv_map = {(i.name, i.shop_id): i for i in all_inv}

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "موجودی انبارها"
    ws.views.sheetView[0].rightToLeft = True

    headers = [
        'کد کالا', 'نام کامل کالا', 'دسته‌بندی', 'برند',
        'موجودی شعبه ۱', 'موجودی شعبه ۲', 'جمع کل موجودی',
        'حداقل هشدار', 'وضعیت موجودی', 'قیمت خرید واحد (تومان)', 'قیمت فروش مصوب (تومان)',
        'ارزش موجودی خرید (تومان)', 'ارزش موجودی فروش (تومان)'
    ]
    ws.append(headers)

    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    header_font = Font(name="Tahoma", size=9, bold=True, color="FFFFFF")

    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for cat in catalog_items:
        i1 = inv_map.get((cat.name, 1))
        i2 = inv_map.get((cat.name, 2))
        s1 = i1.stock_quantity if i1 else 0
        s2 = i2.stock_quantity if i2 else 0
        tot_stock = s1 + s2
        
        status_txt = 'ناموجود' if tot_stock <= 0 else ('هشدار کسری' if tot_stock <= 2 else 'موجود')
        buy_p = cat.buy_price if is_admin() else 0
        sell_p = cat.sell_price

        ws.append([
            cat.code or '',
            cat.name,
            cat.category,
            cat.brand or '',
            s1,
            s2,
            tot_stock,
            2,
            status_txt,
            buy_p,
            sell_p,
            buy_p * tot_stock if is_admin() else 0,
            sell_p * tot_stock
        ])

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(min(max_len + 4, 45), 14)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"Inventory_Tahmasebi_{now_j.year}_{now_j.month:02d}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/admin/export/debtors_excel')
def export_debtors_excel():
    """خروجی اکسل بدهکاران و مانده مطالبات معوقه مشتریان"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    now_j = jdatetime.datetime.now()
    debtors = Customer.query.filter(Customer.outstanding_balance > 0).order_by(Customer.outstanding_balance.desc()).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "بدهکاران و مطالبات معوقه"
    ws.views.sheetView[0].rightToLeft = True

    headers = ['نام مشتری', 'شماره تماس', 'نوع مشتری', 'مانده بدهی (تومان)', 'سقف اعتبار (تومان)', 'جمع کل خریدها (تومان)', 'نشانی']
    ws.append(headers)

    header_fill = PatternFill(start_color="991B1B", end_color="991B1B", fill_type="solid")
    header_font = Font(name="Tahoma", size=9, bold=True, color="FFFFFF")

    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for c in debtors:
        ws.append([
            c.name,
            c.phone or '',
            c.customer_type or 'عادی',
            c.outstanding_balance,
            c.credit_limit or 0,
            c.total_purchases or 0,
            c.address or ''
        ])

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(min(max_len + 4, 40), 16)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"Debtors_Tahmasebi_{now_j.year}_{now_j.month:02d}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/admin/export/payroll_excel')
def export_payroll_excel():
    """خروجی اکسل کامل پرونده حقوق و دستمزد ماهانه همراه با شماره حساب و شبا"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    now_j = jdatetime.datetime.now()
    month = request.args.get('month', default=now_j.month, type=int)
    month_name = PERSIAN_MONTHS.get(month, '')
    settings = Settings.query.first()
    
    staff = User.query.filter(User.is_active == True, User.role != 'admin').order_by(User.role, User.full_name).all()
    all_adv_expenses = Expense.query.filter_by(
        shamsi_year=now_j.year,
        shamsi_month=month,
        category='مساعده'
    ).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"حقوق {month_name}"
    ws.views.sheetView[0].rightToLeft = True

    headers = [
        'نام پرسنل', 'سمت', 'شعبه', 'کد ملی', 'شماره کارت بانکی', 'شماره شبا',
        'حقوق پایه ثابت', 'فروش خالص ماه', 'درصد پورسانت', 'پورسانت فروش',
        'پاداش پله‌ای تارگت', 'مساعده دریافتی', 'خالص پرداختی نهایی (تومان)'
    ]
    ws.append(headers)

    header_fill = PatternFill(start_color="1E1B4B", end_color="1E1B4B", fill_type="solid")
    header_font = Font(name="Tahoma", size=9, bold=True, color="FFFFFF")

    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for u in staff:
        stats = calculate_seller_exact_stats(u.id, now_j.year, month, u.commission_rate, settings, user=u)
        advances = sum(e.amount for e in all_adv_expenses if u.full_name in (e.title or ''))

        base_sal = u.base_salary or 0
        final_payable = base_sal + stats['settled_commission'] + stats['tier_bonus_amount'] - advances

        role_fa = 'خدمات و تحویل بار' if u.role in ['logistics', 'services'] else ('ادمین انبار' if u.can_manage_inventory else 'فروشنده')

        ws.append([
            u.full_name,
            role_fa,
            u.shop.name if u.shop else '',
            u.national_id or '',
            u.card_number or '',
            u.sheba_number or '',
            base_sal,
            stats['net_sales'] if u.role not in ['logistics', 'services'] else 0,
            f"{stats['effective_rate']}%" if u.role not in ['logistics', 'services'] else '-',
            stats['settled_commission'] if u.role not in ['logistics', 'services'] else 0,
            stats['tier_bonus_amount'] if u.role not in ['logistics', 'services'] else 0,
            advances,
            final_payable
        ])

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(min(max_len + 4, 35), 14)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"Payroll_Tahmasebi_{month_name}_{now_j.year}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/admin/export/monthly_summary_excel')
def export_monthly_summary_excel():
    """خروجی اکسل مدیریتی جامع از خلاصه وضعیت مالی و سود و زیان ماهانه"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    now_j = jdatetime.datetime.now()
    month = request.args.get('month', default=now_j.month, type=int)
    year = request.args.get('year', default=now_j.year, type=int)
    month_name = PERSIAN_MONTHS.get(month, '')
    
    summary = calculate_store_financial_summary(year, month)
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"خلاصه مالی {month_name}"
    ws.views.sheetView[0].rightToLeft = True

    # تیتر اصلی
    ws.merge_cells('A1:C1')
    title_cell = ws['A1']
    title_cell.value = f"گزارش جامع وضعیت مالی و سود و زیان فروشگاه طهماسبی - {month_name} {year}"
    title_cell.font = Font(name="Tahoma", size=12, bold=True, color="FFFFFF")
    title_cell.fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    ws.append([])
    ws.append(['شاخص مالی', 'مقدار (تومان / درصد)', 'توضیحات'])
    
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(name="Tahoma", size=10, bold=True, color="FFFFFF")
    for col_idx in range(1, 4):
        c = ws.cell(row=3, column=col_idx)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center", vertical="center")

    rows = [
        ('فروش ناخالص کل', summary['gross_sales'], 'مجموع کل فاکتورهای فروش صادر شده'),
        ('کل مبالغ مرجوعی', summary['returns_amount'], 'مجموع فاکتورهای مرجوع شده به انبار'),
        ('فروش خالص فروشگاه', summary['net_sales'], 'فروش ناخالص منهای مرجوعی‌ها'),
        ('دریافتی کارتخوان (POS)', summary['paid_pos'], 'وجوه واریزی از طریق دستگاه‌های پوز'),
        ('دریافتی کارت به کارت', summary['paid_card'], 'وجوه واریزی حسابی و کارت به کارت'),
        ('دریافتی نقد', summary['paid_cash'], 'وجوه نقد صندوق'),
        ('چک‌های صیادی تسویه شده', summary['paid_cheque'], 'چک‌های صیادی وصول یا دریافت شده'),
        ('مانده بدهی وصول‌نشده مشتریان', summary['remaining_balance'], 'مطالبات معوقه ثبت شده در فاکتورهای ماه'),
        ('سود ناخالص بازرگانی (تخمینی/واقعی)', summary['real_profit'], 'سود ناخالص پس از کسر بهای خرید اقلام'),
        ('حاشیه سود ناخالص', f"{summary['gross_margin_percent']}%", 'نسبت سود به فروش خالص'),
        ('کل هزینه‌های جاری و تنخواه', summary['total_expenses'], 'هزینه‌های ثبت شده در تنخواه شعب'),
        ('کل اجاره ماهانه شعب', summary['total_rent'], 'مجموع اجاره مصوب شعبه ۱ و شعبه ۲'),
        ('کل حقوق پایه پرسنل', summary['total_base_salaries'], 'مجموع حقوق ثابت ماهانه همه پرسنل'),
        ('کل پورسانت و پاداش پرسنل', summary['total_commissions'], 'پورسانت قطعی فروش به انضمام پاداش پله‌ای'),
        ('کل بار مالی حقوق و دستمزد', summary['total_payroll'], 'حقوق پایه + پورسانت پرسنل'),
        ('سود خالص نهایی فروشگاه طهماسبی', summary['store_net_profit'], 'سود ناخالص منهای (هزینه‌ها + اجاره + دستمزدها)'),
        ('حاشیه سود خالص نهایی', f"{summary['profit_margin_percent']}%", 'نسبت سود خالص نهایی به فروش کل'),
        ('سهم فروش شعبه ۱ (اصلی)', summary['shop1_total'], 'فروش قطعی شعبه ۱'),
        ('سهم فروش شعبه ۲', summary['shop2_total'], 'فروش قطعی شعبه ۲'),
    ]

    for item, val, desc in rows:
        ws.append([item, val, desc])

    # استایل‌دهی ردیف‌ها
    for r in range(4, len(rows) + 4):
        ws.cell(row=r, column=1).font = Font(name="Tahoma", size=9, bold=True)
        ws.cell(row=r, column=2).font = Font(name="Tahoma", size=9)
        ws.cell(row=r, column=3).font = Font(name="Tahoma", size=9, italic=True, color="64748B")
        ws.row_dimensions[r].height = 20

    # هایلایت ردیف سود خالص
    net_profit_row = 19
    for col_idx in range(1, 4):
        c = ws.cell(row=net_profit_row, column=col_idx)
        c.fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
        c.font = Font(name="Tahoma", size=10, bold=True, color="166534")

    ws.column_dimensions['A'].width = 32
    ws.column_dimensions['B'].width = 24
    ws.column_dimensions['C'].width = 45

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"Tahmasebi_Monthly_Financial_{month_name}_{year}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/api/admin/financial_summary')
def api_admin_financial_summary():
    """ای‌پی‌آی زنده دریافت شاخص‌های مالی و سود و زیان فروشگاه برای داشبورد و ابزارها"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    now_j = jdatetime.datetime.now()
    month = request.args.get('month', default=now_j.month, type=int)
    year = request.args.get('year', default=now_j.year, type=int)
    summary = calculate_store_financial_summary(year, month)
    return jsonify({
        'status': 'success',
        'year': year,
        'month': month,
        'month_name': PERSIAN_MONTHS.get(month, ''),
        'summary': summary
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)