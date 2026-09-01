import os
import io
import json
import jdatetime
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'tahmasebi-mega-erp-v13-permanent-2026')

# رمز عبور مادر و نجات مدیریت برای مواقع فراموشی
MASTER_ADMIN_PASSWORD = 'king68abolfazl@68'

# مسیر دیتابیس برای ذخیره ابدی روی Volume یا لوکال
DATA_DIR = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', '/data')
if not os.path.exists(DATA_DIR):
    DATA_DIR = os.path.join(app.root_path, 'instance')
    os.makedirs(DATA_DIR, exist_ok=True)

db_path = os.path.join(DATA_DIR, 'tahmasebi_store_persistent.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

PERSIAN_MONTHS = {
    1: 'فروردین', 2: 'اردیبهشت', 3: 'خرداد',
    4: 'تیر', 5: 'مرداد', 6: 'شهریور',
    7: 'مهر', 8: 'آبان', 9: 'آذر',
    10: 'دی', 11: 'بهمن', 12: 'اسفند'
}

DEFAULT_CATEGORIES = [
    'هود', 'سینک', 'گاز صفحه‌ای', 'شیرآلات',
    'روشویی کابینتی', 'آینه و آینه بک‌لایت', 'علم دوش',
    'توالت فرنگی', 'توالت ایرانی', 'فلاش تانک', 'سایر و اکسسوری'
]

RETURN_REASONS = [
    'سایز و ابعاد نامناسب (سینک / گاز / روشویی)',
    'ایراد فنی یا ظاهری کارخانه',
    'انصراف خریدار از مدل انتخابی',
    'اشتباه فروشنده در ثبت سفارش',
    'سایر موارد'
]

# ==================== مدل‌های پایگاه داده ====================
class Shop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    users = db.relationship('User', backref='shop', lazy=True)
    invoices = db.relationship('Invoice', backref='shop', lazy=True)
    expenses = db.relationship('Expense', backref='shop', lazy=True)
    petty_deposits = db.relationship('PettyCashDeposit', backref='shop', lazy=True)
    inventory = db.relationship('InventoryItem', backref='shop', lazy=True)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='seller')
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'), nullable=True)
    commission_rate = db.Column(db.Float, default=1.0)
    is_active = db.Column(db.Boolean, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tier1_min = db.Column(db.BigInteger, default=1_000_000_000)
    tier1_bonus = db.Column(db.Float, default=0.25)
    tier2_min = db.Column(db.BigInteger, default=2_000_000_000)
    tier2_bonus = db.Column(db.Float, default=0.50)

class InventoryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'), nullable=False)
    stock_quantity = db.Column(db.Integer, default=5)
    min_alert_stock = db.Column(db.Integer, default=2)
    buy_price = db.Column(db.BigInteger, default=0)
    sell_price = db.Column(db.BigInteger, default=0)

class StockTransfer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(150), nullable=False)
    from_shop_id = db.Column(db.Integer, nullable=False)
    to_shop_id = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, default=1)
    status = db.Column(db.String(30), default='pending')
    requested_by = db.Column(db.String(100), nullable=False)
    shamsi_date_time = db.Column(db.String(40), nullable=False)

class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=True)
    categories_json = db.Column(db.Text, default='[]')
    items_desc = db.Column(db.Text, nullable=True)
    
    status = db.Column(db.String(20), default='final')
    proforma_valid_until = db.Column(db.String(30), nullable=True)
    
    invoice_type = db.Column(db.String(20), default='sale')
    return_reason = db.Column(db.String(150), nullable=True)
    
    payment_method = db.Column(db.String(30), default='pos')
    dest_card_number = db.Column(db.String(50), nullable=True)
    payment_tracking_code = db.Column(db.String(50), nullable=True)
    
    cheque_sayad = db.Column(db.String(50), nullable=True)
    cheque_bank = db.Column(db.String(100), nullable=True)
    cheque_due_date = db.Column(db.String(30), nullable=True)
    
    total_amount = db.Column(db.BigInteger, nullable=False)
    paid_amount = db.Column(db.BigInteger, default=0)
    due_settlement_date = db.Column(db.String(30), nullable=True)
    estimated_buy_cost = db.Column(db.BigInteger, default=0)
    
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    second_seller_id = db.Column(db.Integer, nullable=True)
    split_ratio = db.Column(db.Integer, default=100)
    customer_rating = db.Column(db.Integer, default=5)
    
    shamsi_year = db.Column(db.Integer, nullable=False)
    shamsi_month = db.Column(db.Integer, nullable=False)
    shamsi_date_time = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'), nullable=False)
    seller = db.relationship('User', foreign_keys=[seller_id])

class Cheque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=True)
    sayad_number = db.Column(db.String(50), nullable=False)
    bank_name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)
    due_shamsi_date = db.Column(db.String(30), nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=True)
    shop_id = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), default='pending')

class PettyCashDeposit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'), nullable=False)
    shamsi_year = db.Column(db.Integer, nullable=False)
    shamsi_month = db.Column(db.Integer, nullable=False)
    shamsi_date_time = db.Column(db.String(40), nullable=False)
    created_by = db.Column(db.String(100), nullable=False)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)
    category = db.Column(db.String(50), default='متفرقه')
    shamsi_year = db.Column(db.Integer, nullable=False)
    shamsi_month = db.Column(db.Integer, nullable=False)
    shamsi_date_time = db.Column(db.String(40), nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'), nullable=False)
    created_by = db.Column(db.String(100), nullable=False)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(200), nullable=False)
    user_name = db.Column(db.String(100), nullable=False)
    shamsi_date_time = db.Column(db.String(40), nullable=False)

def log_activity(action, user_name="سیستم"):
    now_str = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M:%S")
    log = AuditLog(action=action, user_name=user_name, shamsi_date_time=now_str)
    db.session.add(log)
    db.session.commit()

def calculate_seller_exact_stats(user_id, year, month, base_commission_rate, settings):
    invoices = Invoice.query.filter(
        (Invoice.seller_id == user_id) | (Invoice.second_seller_id == user_id),
        Invoice.shamsi_year == year,
        Invoice.shamsi_month == month,
        Invoice.status == 'final'
    ).all()

    net_sales = 0
    sales_count = 0
    returns_count = 0
    ratings = []

    for inv in invoices:
        ratio = 1.0
        if inv.second_seller_id:
            if inv.seller_id == user_id:
                ratio = (inv.split_ratio if inv.split_ratio is not None else 100) / 100.0
            else:
                ratio = (100 - (inv.split_ratio if inv.split_ratio is not None else 100)) / 100.0
        
        if inv.invoice_type == 'sale':
            net_sales += int(inv.total_amount * ratio)
            sales_count += 1
            if inv.customer_rating:
                ratings.append(inv.customer_rating)
        elif inv.invoice_type == 'return':
            net_sales -= int(inv.total_amount * ratio)
            returns_count += 1

    net_sales = max(net_sales, 0)
    bonus = 0.0
    if settings:
        if net_sales >= settings.tier2_min:
            bonus = settings.tier2_bonus
        elif net_sales >= settings.tier1_min:
            bonus = settings.tier1_bonus
    effective_rate = round(min(base_commission_rate + bonus, 5.0), 2)
    commission_amount = int((net_sales * effective_rate) / 100)
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 5.0

    return {
        'net_sales': net_sales,
        'sales_count': sales_count,
        'returns_count': returns_count,
        'effective_rate': effective_rate,
        'commission_amount': commission_amount,
        'avg_rating': avg_rating
    }

# ==================== قالب پایه ====================
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>مجموعه فروشگاه‌های تخصصی طهماسبی</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css" rel="stylesheet">
    <style>
        body { font-family: 'Vazirmatn', sans-serif; }
        @media print { .no-print { display: none !important; } }
        .blink { animation: blinker 1.5s linear infinite; }
        @keyframes blinker { 50% { opacity: 0.3; } }
    </style>
</head>
<body class="bg-slate-100 min-h-screen text-slate-800 flex flex-col justify-between">
    <div>
        <nav class="bg-slate-900 text-white shadow-xl p-4 sticky top-0 z-50 no-print border-b border-slate-700">
            <div class="container mx-auto flex justify-between items-center">
                <div class="flex items-center gap-3">
                    <span class="text-2xl">✨</span>
                    <div>
                        <a href="{{ url_for('index') }}" class="text-base md:text-xl font-black">مجموعه فروشگاه‌های تخصصی طهماسبی</a>
                        <p class="text-[10px] text-slate-400">سامانه جامع فروش، پورسانت، انبارداری و تنخواه شعب</p>
                    </div>
                </div>
                {% if session.get('user_id') %}
                <div class="flex items-center gap-3">
                    <span class="text-xs bg-slate-800 text-slate-200 px-3 py-1.5 rounded-xl border border-slate-700 font-bold">
                        👤 {{ session.get('full_name') }} ({{ 'مدیریت کل' if session.get('role') == 'admin' else 'فروشنده' }})
                    </span>
                    <a href="{{ url_for('logout') }}" class="text-xs bg-rose-600 hover:bg-rose-700 text-white px-3 py-1.5 rounded-xl transition font-bold shadow">خروج</a>
                </div>
                {% endif %}
            </div>
        </nav>
        
        <main class="container mx-auto p-4 md:p-6 max-w-7xl">
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="mb-4 p-4 rounded-2xl text-xs md:text-sm font-bold shadow-sm {% if category == 'error' %}bg-rose-50 text-rose-700 border border-rose-200{% else %}bg-emerald-50 text-emerald-700 border border-emerald-200{% endif %}">
                            {{ message }}
                        </div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            
            {% block content %}{% endblock %}
        </main>
    </div>

    <footer class="py-4 text-center text-xs text-gray-400 no-print border-t border-gray-200 mt-8">
        سامانه جامع فروشگاه‌های تخصصی طهماسبی • نسخه ۱۳.۰ کامل و بدون باگ
    </footer>

    <script>
        function formatNumber(input) {
            let value = input.value.replace(/\\D/g, '');
            if (value !== '') {
                input.value = Number(value).toLocaleString();
            }
        }
        function unformatOnSubmit(form) {
            const inputs = form.querySelectorAll('.currency-input');
            inputs.forEach(input => {
                input.value = input.value.replace(/,/g, '');
            });
        }
    </script>
</body>
</html>
"""

# ==================== صفحه ورود ====================
LOGIN_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', """
<div class="max-w-md mx-auto mt-12 bg-white p-8 rounded-3xl shadow-sm border border-gray-200">
    <div class="text-center mb-6">
        <div class="inline-block p-4 bg-slate-100 rounded-3xl mb-3 text-3xl">🏬</div>
        <h2 class="text-2xl font-black text-slate-800">فروشگاه‌های طهماسبی</h2>
        <p class="text-gray-500 text-xs mt-1">ورود به سامانه مدیریت فروش و پورسانت پرسنل</p>
    </div>
    <form method="POST">
        <div class="mb-4">
            <label class="block text-gray-700 text-xs mb-1.5 font-bold">نام کاربری:</label>
            <input type="text" name="username" required class="w-full p-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-slate-900 outline-none text-left font-bold" dir="ltr">
        </div>
        <div class="mb-6">
            <label class="block text-gray-700 text-xs mb-1.5 font-bold">رمز عبور:</label>
            <input type="password" name="password" required class="w-full p-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-slate-900 outline-none text-left font-bold" dir="ltr">
        </div>
        <button type="submit" class="w-full bg-slate-900 hover:bg-slate-800 text-white font-bold py-3.5 rounded-xl shadow-md transition">ورود به حساب کاربری</button>
    </form>
</div>
""")

# ==================== داشبورد فروشنده ====================
SELLER_DASHBOARD = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', """
<div class="flex flex-col md:flex-row justify-between items-center bg-white p-5 rounded-2xl border border-gray-200 mb-6 gap-4 shadow-sm">
    <div class="flex items-center gap-3">
        <span class="text-3xl">🎯</span>
        <div>
            <h2 class="font-black text-slate-800 text-lg">عملکرد ماه {{ current_month_name }} {{ current_year }}</h2>
            <p class="text-xs text-gray-500 font-medium">{{ user.shop.name }} • فروشنده: {{ user.full_name }}</p>
        </div>
    </div>
    <div class="flex items-center gap-3">
        <a href="#leaderboard" class="bg-amber-100 hover:bg-amber-200 text-amber-900 px-3 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5">
            <span>🏆</span> سکوی رقابت ماه
        </a>
        <form method="GET" class="flex items-center gap-2">
            <label class="text-xs font-bold text-gray-600">انتخاب ماه:</label>
            <select name="month" onchange="this.form.submit()" class="p-2 border rounded-xl text-xs font-bold bg-slate-50 outline-none">
                {% for m_num, m_name in months.items() %}
                    <option value="{{ m_num }}" {% if m_num == selected_month %}selected{% endif %}>{{ m_name }}</option>
                {% endfor %}
            </select>
        </form>
    </div>
</div>

<div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
    <div class="bg-white p-5 rounded-2xl shadow-sm border border-gray-200">
        <span class="text-gray-400 text-xs font-bold">فروش خالص شما در {{ current_month_name }}</span>
        <h3 class="text-2xl font-black text-slate-800 mt-2">{{ "{:,}".format(stats.net_sales) }} <span class="text-xs font-normal text-gray-400">تومان</span></h3>
        <span class="text-[10px] text-gray-400">({{ stats.sales_count }} فاکتور تایید شده)</span>
    </div>
    <div class="bg-white p-5 rounded-2xl shadow-sm border border-gray-200">
        <span class="text-gray-400 text-xs font-bold">تعداد مرجوعی‌ها</span>
        <h3 class="text-2xl font-black text-rose-600 mt-2">{{ stats.returns_count }} <span class="text-xs font-normal text-gray-400">مورد</span></h3>
        <span class="text-[10px] text-rose-400">کسر شده از جمع کل فروش</span>
    </div>
    <div class="bg-white p-5 rounded-2xl shadow-sm border border-gray-200">
        <span class="text-gray-400 text-xs font-bold">درصد مصوب + پاداش تارگت</span>
        <h3 class="text-2xl font-black text-blue-600 mt-2">{{ stats.effective_rate }}%</h3>
        <span class="text-[10px] text-blue-500 font-bold">
            {% if stats.effective_rate > user.commission_rate %}🎉 پاداش تارگت طهماسبی اعمال شد{% else %}نرخ مصوب پایه{% endif %}
        </span>
    </div>
    <div class="bg-white p-5 rounded-2xl shadow-sm border border-gray-200">
        <span class="text-gray-400 text-xs font-bold">پورسانت خالص دریافتی</span>
        <h3 class="text-2xl font-black text-emerald-600 mt-2">{{ "{:,}".format(stats.commission_amount) }} <span class="text-xs font-normal text-gray-400">تومان</span></h3>
        <span class="text-[10px] text-emerald-500 font-bold">مطابق با محاسبات پنل مدیریت</span>
    </div>
</div>

<div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
    <div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-200 h-fit">
        <h3 class="text-md font-bold text-slate-800 mb-4 border-b pb-3 flex items-center gap-2">
            <span>✍️</span> صدور فاکتور / پیش‌فاکتور / مرجوعی
        </h3>
        <form method="POST" action="{{ url_for('add_invoice') }}" onsubmit="unformatOnSubmit(this)">
            <div class="mb-3">
                <label class="block text-xs font-bold text-gray-600 mb-1">نوع سند:</label>
                <div class="grid grid-cols-3 gap-1 text-[11px]">
                    <label class="flex items-center justify-center p-2 rounded-xl border cursor-pointer has-[:checked]:bg-emerald-600 has-[:checked]:text-white font-bold">
                        <input type="radio" name="doc_status" value="final" checked class="hidden" onchange="handleDocTypeChange('final')">
                        <span>🛒 قطعی</span>
                    </label>
                    <label class="flex items-center justify-center p-2 rounded-xl border cursor-pointer has-[:checked]:bg-indigo-600 has-[:checked]:text-white font-bold">
                        <input type="radio" name="doc_status" value="proforma" class="hidden" onchange="handleDocTypeChange('proforma')">
                        <span>📑 پیش‌فاکتور</span>
                    </label>
                    <label class="flex items-center justify-center p-2 rounded-xl border cursor-pointer has-[:checked]:bg-rose-600 has-[:checked]:text-white font-bold">
                        <input type="radio" name="doc_status" value="return" class="hidden" onchange="handleDocTypeChange('return')">
                        <span>🔄 مرجوعی</span>
                    </label>
                </div>
            </div>

            <!-- باکس مهلت پیش فاکتور -->
            <div id="proformaDateBox" style="display: none;" class="mb-3 bg-indigo-50 p-2.5 rounded-xl border border-indigo-200">
                <label class="block text-[11px] font-bold text-indigo-800 mb-1">📅 مهلت اعتبار پیش‌فاکتور (تاریخ شمسی):</label>
                <input type="text" name="proforma_valid_until" placeholder="مثلاً: 1405/06/12 - تا ۴۸ ساعت" class="w-full p-2 border rounded-lg text-xs bg-white text-left font-bold" dir="ltr">
            </div>

            <!-- باکس علت مرجوعی -->
            <div id="returnReasonBox" style="display: none;" class="mb-3 bg-rose-50 p-2.5 rounded-xl border border-rose-200">
                <label class="block text-[11px] font-bold text-rose-800 mb-1">⚠️ علت دقیق مرجوعی کالا:</label>
                <select name="return_reason" class="w-full p-2 border border-rose-300 rounded-lg text-xs bg-white font-bold text-rose-700">
                    {% for reason in return_reasons %}
                    <option value="{{ reason }}">{{ reason }}</option>
                    {% endfor %}
                </select>
            </div>

            <div class="grid grid-cols-2 gap-2 mb-3">
                <div>
                    <label class="block text-xs font-bold text-gray-600 mb-1">شماره سند / فاکتور:</label>
                    <input type="text" name="invoice_number" required placeholder="1150" class="w-full p-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-slate-800 text-xs font-bold">
                </div>
                <div>
                    <label class="block text-xs font-bold text-gray-600 mb-1">نحوه تسویه:</label>
                    <select name="payment_method" id="paymentMethodSelect" onchange="togglePaymentInputs(this.value)" class="w-full p-2 border border-gray-300 rounded-xl text-xs bg-white font-medium">
                        <option value="pos">کارتخوان مغازه (POS)</option>
                        <option value="card_to_card">کارت به کارت / واریز حساب</option>
                        <option value="cash">نقدی</option>
                        <option value="deposit">بیعانه (مانده‌دار)</option>
                        <option value="cheque">چک صیادی</option>
                    </select>
                </div>
            </div>

            <!-- فیلدهای کارت به کارت -->
            <div id="cardTrackingBox" style="display: none;" class="mb-3 bg-blue-50 p-2.5 rounded-xl border border-blue-200 space-y-2">
                <div>
                    <label class="block text-[11px] font-bold text-blue-900 mb-1">💳 واریز به کدام شماره کارت طهماسبی (کارت مقصد)؟</label>
                    <input type="text" name="dest_card_number" placeholder="مثال: 6037... بنام طهماسبی" class="w-full p-2 border rounded-lg text-xs bg-white text-left font-bold" dir="ltr">
                </div>
                <div>
                    <label class="block text-[11px] font-bold text-blue-900 mb-1">شماره پیگیری فیش / ۴ رقم آخر کارت خریدار:</label>
                    <input type="text" name="payment_tracking_code" placeholder="مثال: پیگیری 489201" class="w-full p-2 border rounded-lg text-xs bg-white text-left font-bold" dir="ltr">
                </div>
            </div>

            <!-- فیلدهای چک صیادی -->
            <div id="chequeDirectBox" style="display: none;" class="mb-3 bg-indigo-50 p-3 rounded-xl border border-indigo-200 space-y-2">
                <span class="text-xs font-bold text-indigo-900 block border-b border-indigo-200 pb-1 flex items-center gap-1">
                    <span>🗓️</span> مشخصات چک صیادی مشتری:
                </span>
                <div>
                    <label class="block text-[10px] font-bold text-gray-700 mb-1">شناسه ۱۶ رقمی صیادی:</label>
                    <input type="text" name="cheque_sayad" placeholder="16 رقم شناسه صیاد" class="w-full p-2 border rounded-lg text-xs bg-white font-mono text-left font-bold text-indigo-800" dir="ltr">
                </div>
                <div class="grid grid-cols-2 gap-2">
                    <div>
                        <label class="block text-[10px] font-bold text-gray-700 mb-1">نام بانک و شعبه:</label>
                        <input type="text" name="cheque_bank" placeholder="مثلاً: صادرات مرکزی" class="w-full p-2 border rounded-lg text-xs bg-white">
                    </div>
                    <div>
                        <label class="block text-[10px] font-bold text-gray-700 mb-1">تاریخ سررسید چک:</label>
                        <input type="text" name="cheque_due_date" placeholder="1405/08/20" class="w-full p-2 border rounded-lg text-xs bg-white text-left font-bold text-amber-700" dir="ltr">
                    </div>
                </div>
            </div>

            <!-- فیلدهای بیعانه -->
            <div id="depositDetailsBox" style="display: none;" class="mb-3 bg-amber-50 p-2.5 rounded-xl border border-amber-200">
                <div class="grid grid-cols-2 gap-2">
                    <div>
                        <label class="block text-[11px] font-bold text-amber-900 mb-1">مبلغ بیعانه دریافتی:</label>
                        <input type="text" name="paid_amount" onkeyup="formatNumber(this)" placeholder="مبلغ نقد بیعانه" class="currency-input w-full p-2 border rounded-lg text-xs bg-white font-bold text-emerald-700">
                    </div>
                    <div>
                        <label class="block text-[11px] font-bold text-amber-900 mb-1">موعد تسویه مانده:</label>
                        <input type="text" name="due_settlement_date" placeholder="1405/06/20 (تحویل بار)" class="w-full p-2 border rounded-lg text-xs bg-white text-left font-bold" dir="ltr">
                    </div>
                </div>
            </div>

            <div class="grid grid-cols-2 gap-2 mb-3">
                <div>
                    <label class="block text-xs font-bold text-gray-600 mb-1">نام خریدار:</label>
                    <input type="text" name="customer_name" required placeholder="آقای رضایی" class="w-full p-2 border border-gray-300 rounded-xl text-xs font-medium">
                </div>
                <div>
                    <label class="block text-xs font-bold text-gray-600 mb-1">شماره همراه خریدار:</label>
                    <input type="text" name="customer_phone" placeholder="0912..." class="w-full p-2 border border-gray-300 rounded-xl text-xs text-left font-bold" dir="ltr">
                </div>
            </div>

            <div class="mb-3 bg-slate-50 p-2.5 rounded-xl border">
                <label class="block text-[11px] font-bold text-indigo-700 mb-1">🤝 فروش مشترک (تقسیم پورسانت):</label>
                <div class="grid grid-cols-2 gap-2">
                    <select name="second_seller_id" class="w-full p-1.5 border rounded-lg text-[11px] bg-white">
                        <option value="">فروش تکی (بدون همکار)</option>
                        {% for colleague in colleagues %}
                        <option value="{{ colleague.id }}">همکار: {{ colleague.full_name }}</option>
                        {% endfor %}
                    </select>
                    <select name="split_ratio" class="w-full p-1.5 border rounded-lg text-[11px] bg-white">
                        <option value="100">سهم کامل (۱۰۰٪)</option>
                        <option value="50">نصف-نصف (۵۰٪ - ۵۰٪)</option>
                        <option value="60">۶۰٪ من - ۴۰٪ همکار</option>
                        <option value="70">۷۰٪ من - ۳۰٪ همکار</option>
                    </select>
                </div>
            </div>

            <div class="mb-3">
                <label class="block text-xs font-bold text-gray-600 mb-1.5">اقلام فاکتور:</label>
                <div class="grid grid-cols-2 gap-1.5 max-h-32 overflow-y-auto p-2 border border-gray-200 rounded-xl bg-slate-50 text-[11px]">
                    {% for cat in all_categories %}
                    <label class="flex items-center gap-1.5 cursor-pointer hover:text-indigo-600">
                        <input type="checkbox" name="categories" value="{{ cat.name }}" class="rounded text-slate-800">
                        <span>{{ cat.name }}</span>
                    </label>
                    {% endfor %}
                </div>
            </div>

            <div class="mb-3">
                <label class="block text-xs font-bold text-gray-600 mb-1">مبلغ کل فاکتور (تومان):</label>
                <input type="text" name="total_amount" required onkeyup="formatNumber(this)" placeholder="مثال: 25,000,000" class="currency-input w-full p-2 border border-gray-300 rounded-xl text-xs font-bold text-emerald-700">
            </div>

            <div class="mb-3">
                <label class="block text-xs font-bold text-gray-600 mb-1">توضیحات و مدل کالاها:</label>
                <textarea name="items_desc" rows="2" placeholder="مدل دقیق گاز، سینک، هود، روشویی و..." class="w-full p-2 border rounded-xl text-xs"></textarea>
            </div>

            <div class="mb-4 flex items-center justify-between bg-amber-50 p-2 rounded-xl border border-amber-200">
                <span class="text-xs font-bold text-amber-800">⭐ رضایت خریدار:</span>
                <select name="customer_rating" class="p-1 border rounded-lg text-xs bg-white font-bold text-amber-600">
                    <option value="5">⭐⭐⭐⭐⭐ عالی (۵ ستاره)</option>
                    <option value="4">⭐⭐⭐⭐ خوب (۴ ستاره)</option>
                    <option value="3">⭐⭐⭐ متوسط (۳ ستاره)</option>
                </select>
            </div>

            <button type="submit" class="w-full bg-slate-900 hover:bg-slate-800 text-white font-bold py-2.5 rounded-xl shadow transition">ثبت نهایی سند</button>
        </form>

        <div class="mt-6 border-t pt-4">
            <h4 class="text-xs font-bold text-rose-700 mb-2">💸 ثبت هزینه جاری مغازه (خرج از تنخواه)</h4>
            <form method="POST" action="{{ url_for('add_expense') }}" onsubmit="unformatOnSubmit(this)">
                <div class="mb-2">
                    <input type="text" name="title" required placeholder="عنوان (کرایه وانت، نصاب و...)" class="w-full p-1.5 border rounded-lg text-xs">
                </div>
                <div class="flex gap-2 mb-2">
                    <input type="text" name="amount" required onkeyup="formatNumber(this)" placeholder="مبلغ (تومان)" class="currency-input w-full p-1.5 border rounded-lg text-xs font-bold">
                    <select name="category" class="p-1.5 border rounded-lg text-xs bg-white">
                        <option value="کرایه وانت و حمل">کرایه بار/وانت</option>
                        <option value="دستمزد نصاب">دستمزد نصاب</option>
                        <option value="ملزومات و پذیرایی">ملزومات مغازه</option>
                        <option value="سایر">سایر</option>
                    </select>
                </div>
                <button type="submit" class="w-full bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold py-1.5 rounded-lg transition">ثبت هزینه تنخواه</button>
            </form>
        </div>
    </div>

    <div class="lg:col-span-2 bg-white p-6 rounded-2xl shadow-sm border border-gray-200 overflow-x-auto">
        <h3 class="text-md font-bold text-slate-800 mb-4 border-b pb-3 flex items-center justify-between">
            <span>📑 کلیه اسناد شما در {{ current_month_name }}</span>
            <span class="text-xs text-gray-400 font-bold">فاکتورهای قطعی و پیش‌فاکتورها</span>
        </h3>
        <table class="w-full text-right border-collapse text-xs">
            <thead>
                <tr class="bg-gray-50 text-gray-600 font-bold">
                    <th class="p-2.5 border-b">شماره</th>
                    <th class="p-2.5 border-b">نوع سند</th>
                    <th class="p-2.5 border-b">خریدار</th>
                    <th class="p-2.5 border-b">مبلغ کل (تومان)</th>
                    <th class="p-2.5 border-b">نحوه تسویه / مانده</th>
                    <th class="p-2.5 border-b">رضایت</th>
                    <th class="p-2.5 border-b">زمان ثبت</th>
                    <th class="p-2.5 border-b">عملیات</th>
                </tr>
            </thead>
            <tbody>
                {% for inv in invoices %}
                <tr class="hover:bg-slate-50 border-b">
                    <td class="p-2.5 font-bold text-slate-800">{{ inv.invoice_number }}</td>
                    <td class="p-2.5">
                        {% if inv.status == 'proforma' %}
                            <span class="bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded font-bold text-[10px]">پیش‌فاکتور</span>
                            {% if inv.proforma_valid_until %}
                                <span class="text-[9px] text-gray-400 block font-normal">مهلت: {{ inv.proforma_valid_until }}</span>
                            {% endif %}
                        {% elif inv.invoice_type == 'return' %}
                            <span class="bg-rose-100 text-rose-700 px-2 py-0.5 rounded font-bold text-[10px]">مرجوعی</span>
                            {% if inv.return_reason %}
                                <span class="text-[9px] text-rose-600 block font-medium">علت: {{ inv.return_reason }}</span>
                            {% endif %}
                        {% else %}
                            <span class="bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded font-bold text-[10px]">قطعی</span>
                        {% endif %}
                    </td>
                    <td class="p-2.5 font-medium">{{ inv.customer_name }}</td>
                    <td class="p-2.5 font-bold {% if inv.invoice_type == 'return' %}text-rose-600{% else %}text-emerald-700{% endif %}">
                        {% if inv.invoice_type == 'return' %}-{% endif %}{{ "{:,}".format(inv.total_amount) }}
                    </td>
                    <td class="p-2.5">
                        {% if inv.payment_method == 'card_to_card' %}
                            <span class="bg-blue-100 text-blue-800 px-2 py-0.5 rounded text-[10px] font-bold">کارت به کارت</span>
                            {% if inv.dest_card_number %}<span class="text-[9px] text-blue-600 block">کارت مقصد: {{ inv.dest_card_number }}</span>{% endif %}
                        {% elif inv.payment_method == 'deposit' and inv.total_amount > (inv.paid_amount or 0) %}
                            <span class="text-amber-600 font-bold block">{{ "{:,}".format(inv.paid_amount or 0) }} بیعانه</span>
                            <span class="text-rose-500 text-[10px] block">مانده: {{ "{:,}".format(inv.total_amount - (inv.paid_amount or 0)) }}</span>
                            {% if inv.due_settlement_date %}
                                <span class="text-[9px] text-slate-500 block font-medium">موعد: {{ inv.due_settlement_date }}</span>
                            {% endif %}
                        {% elif inv.payment_method == 'cheque' %}
                            <span class="text-indigo-600 font-bold">چک صیادی</span>
                            {% if inv.cheque_sayad %}<span class="text-[9px] text-gray-500 block">صیادی: {{ inv.cheque_sayad }}</span>{% endif %}
                        {% else %}
                            <span class="text-gray-600">تسویه کامل</span>
                        {% endif %}
                    </td>
                    <td class="p-2.5 text-amber-500 font-bold">★ {{ inv.customer_rating }}</td>
                    <td class="p-2.5 text-gray-400 font-medium text-[11px]" dir="ltr">{{ inv.shamsi_date_time }}</td>
                    <td class="p-2.5">
                        <div class="flex items-center gap-1">
                            {% if inv.status == 'proforma' %}
                            <form method="POST" action="{{ url_for('convert_proforma', invoice_id=inv.id) }}">
                                <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white px-2 py-1 rounded text-[10px] font-bold">تبدیل به قطعی</button>
                            </form>
                            {% endif %}
                            {% if inv.payment_method == 'deposit' and inv.total_amount > (inv.paid_amount or 0) %}
                            <form method="POST" action="{{ url_for('settle_deposit', invoice_id=inv.id) }}">
                                <button type="submit" class="bg-emerald-600 hover:bg-emerald-700 text-white px-2 py-1 rounded text-[10px] font-bold">تسویه مانده</button>
                            </form>
                            {% endif %}
                            <a href="{{ url_for('print_invoice', invoice_id=inv.id) }}" target="_blank" class="text-indigo-600 hover:underline font-bold text-[11px]">🖨️ چاپ</a>
                        </div>
                    </td>
                </tr>
                {% else %}
                <tr><td colspan="8" class="text-center p-6 text-gray-400">هنوز سندی در این ماه ثبت نشده است.</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>

<!-- بخش انبارداری و هشدار کسری در پنل فروشنده -->
<div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-200 mb-8">
    <div class="flex justify-between items-center mb-4 border-b pb-3">
        <h3 class="text-md font-bold text-slate-800 flex items-center gap-2">
            <span>📦</span> موجودی انبار و درخواست انتقال بین دو شعبه طهماسبی
        </h3>
        <span class="text-xs text-indigo-600 font-bold">مشاهده زنده موجودی دو فروشگاه با چراغ هشدار کسری</span>
    </div>
    
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div class="bg-slate-50 p-4 rounded-xl border">
            <h4 class="text-xs font-bold text-indigo-700 mb-3">🔄 ارسال درخواست کالا از شعبه دیگر</h4>
            <form method="POST" action="{{ url_for('request_transfer') }}">
                <div class="mb-2">
                    <label class="block text-[11px] text-gray-600 mb-1">نام کالای درخواستی:</label>
                    <input type="text" name="item_name" required placeholder="مثلاً: سینک گرانیتی فونیکس" class="w-full p-2 border rounded-lg text-xs bg-white">
                </div>
                <div class="mb-2">
                    <label class="block text-[11px] text-gray-600 mb-1">از کدام شعبه منتقل شود؟</label>
                    <select name="from_shop_id" class="w-full p-2 border rounded-lg text-xs bg-white">
                        {% for s in other_shops %}
                        <option value="{{ s.id }}">{{ s.name }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="mb-3">
                    <label class="block text-[11px] text-gray-600 mb-1">تعداد:</label>
                    <input type="number" name="quantity" value="1" min="1" class="w-full p-2 border rounded-lg text-xs bg-white font-bold">
                </div>
                <button type="submit" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold py-2 rounded-lg transition">ثبت درخواست انتقال</button>
            </form>
        </div>

        <div class="lg:col-span-2 overflow-x-auto">
            <table class="w-full text-right border-collapse text-xs">
                <thead>
                    <tr class="bg-slate-100 text-slate-700 font-bold">
                        <th class="p-2 border-b">نام کالا</th>
                        <th class="p-2 border-b">دسته‌بندی</th>
                        <th class="p-2 border-b">شعبه</th>
                        <th class="p-2 border-b">موجودی</th>
                        <th class="p-2 border-b">وضعیت هشدار</th>
                    </tr>
                </thead>
                <tbody>
                    {% for item in inventory_items %}
                    <tr class="border-b hover:bg-slate-50">
                        <td class="p-2 font-bold text-slate-800">{{ item.name }}</td>
                        <td class="p-2 text-gray-500">{{ item.category }}</td>
                        <td class="p-2"><span class="bg-gray-100 px-2 py-0.5 rounded text-[10px]">{{ item.shop.name }}</span></td>
                        <td class="p-2 font-bold">{{ item.stock_quantity }} عدد</td>
                        <td class="p-2">
                            {% if item.stock_quantity <= item.min_alert_stock %}
                                <span class="bg-rose-500 text-white px-2 py-0.5 rounded-full text-[10px] font-bold blink">⚠️ کسری انبار</span>
                            {% else %}
                                <span class="bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full text-[10px] font-bold">موجود کافی</span>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>

<div id="leaderboard" class="bg-gradient-to-br from-slate-900 to-indigo-950 text-white p-6 rounded-3xl shadow-xl mb-8">
    <div class="text-center mb-6">
        <span class="text-3xl">🏆</span>
        <h3 class="text-lg font-black mt-1">سکوی قهرمانی و تابلوی زنده رقابت پرسنل طهماسبی</h3>
        <p class="text-xs text-slate-400">بر اساس بیشترین فروش خالص و بالاترین رضایت مشتریان در {{ current_month_name }}</p>
    </div>
    
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
        {% for rank_item in leaderboard %}
        <div class="bg-slate-800/80 backdrop-blur p-4 rounded-2xl border border-slate-700 text-center relative overflow-hidden">
            {% if loop.index == 1 %}
                <div class="absolute top-0 right-0 bg-amber-500 text-slate-950 text-[10px] font-black px-2 py-0.5 rounded-bl-lg">🥇 رتبه اول</div>
            {% elif loop.index == 2 %}
                <div class="absolute top-0 right-0 bg-slate-300 text-slate-950 text-[10px] font-black px-2 py-0.5 rounded-bl-lg">🥈 رتبه دوم</div>
            {% elif loop.index == 3 %}
                <div class="absolute top-0 right-0 bg-amber-700 text-white text-[10px] font-black px-2 py-0.5 rounded-bl-lg">🥉 رتبه سوم</div>
            {% endif %}
            
            <div class="text-2xl mb-1">
                {% if loop.index == 1 %}👑{% elif loop.index == 2 %}⭐{% elif loop.index == 3 %}🎖️{% else %}👤{% endif %}
            </div>
            <h4 class="font-bold text-sm text-slate-100">{{ rank_item.user.full_name }}</h4>
            <p class="text-[10px] text-slate-400 mb-2">{{ rank_item.user.shop.name }}</p>
            <div class="bg-slate-900/60 p-2 rounded-xl text-xs font-black text-emerald-400 mb-1">
                {{ "{:,}".format(rank_item.net_sales) }} تومان
            </div>
            <div class="text-[10px] text-amber-400 font-bold">میانگین رضایت: ★ {{ rank_item.avg_rating }}</div>
        </div>
        {% endfor %}
    </div>
</div>

<script>
    function handleDocTypeChange(type) {
        document.getElementById('proformaDateBox').style.display = (type === 'proforma') ? 'block' : 'none';
        document.getElementById('returnReasonBox').style.display = (type === 'return') ? 'block' : 'none';
    }

    function togglePaymentInputs(val) {
        document.getElementById('cardTrackingBox').style.display = (val === 'card_to_card') ? 'block' : 'none';
        document.getElementById('depositDetailsBox').style.display = (val === 'deposit') ? 'block' : 'none';
        document.getElementById('chequeDirectBox').style.display = (val === 'cheque') ? 'block' : 'none';
    }

    document.addEventListener('DOMContentLoaded', function() {
        var pSelect = document.getElementById('paymentMethodSelect');
        if (pSelect) { togglePaymentInputs(pSelect.value); }
    });
</script>
""")

# ==================== داشبورد مدیریت کل ====================
ADMIN_DASHBOARD = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', """
<div class="flex flex-col md:flex-row justify-between items-center bg-white p-5 rounded-2xl border border-gray-200 mb-6 gap-4 shadow-sm">
    <div>
        <h2 class="text-xl font-black text-slate-800 flex items-center gap-2">
            <span>👑</span> پنل مدیریت جامع فروشگاه‌های طهماسبی
        </h2>
        <p class="text-xs text-gray-500 mt-1">گزارش مالی دقیق، گردش تنخواه، انبارداری و لاگ‌های امنیتی در {{ selected_month_name }} {{ current_year }}</p>
    </div>
    
    <div class="flex flex-wrap items-center gap-2">
        <form method="GET" class="flex items-center gap-1.5">
            <select name="month" onchange="this.form.submit()" class="p-2 border rounded-xl text-xs font-bold bg-slate-50 outline-none">
                {% for m_num, m_name in months.items() %}
                    <option value="{{ m_num }}" {% if m_num == selected_month %}selected{% endif %}>{{ m_name }}</option>
                {% endfor %}
            </select>
        </form>

        <a href="{{ url_for('export_excel', month=selected_month) }}" class="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold px-3 py-2 rounded-xl shadow transition">📥 اکسل جامع</a>
        <a href="{{ url_for('download_backup') }}" class="bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold px-3 py-2 rounded-xl shadow transition">🛡️ بکاپ دیتابیس</a>
        <button onclick="document.getElementById('adminChangePasswordModal').classList.remove('hidden')" class="bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold px-3 py-2 rounded-xl transition">🔐 تغییر رمز مدیریت</button>
        <button onclick="document.getElementById('pettyDepositModal').classList.remove('hidden')" class="bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-bold px-3 py-2 rounded-xl transition">💵 شارژ تنخواه شعب</button>
        <button onclick="document.getElementById('settingsModal').classList.remove('hidden')" class="bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold px-3 py-2 rounded-xl transition">⚙️ تنظیم تارگت‌ها</button>
        <button onclick="document.getElementById('addUserModal').classList.remove('hidden')" class="bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold px-3 py-2 rounded-xl transition">➕ پرسنل جدید</button>
        <button onclick="document.getElementById('chequeModal').classList.remove('hidden')" class="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold px-3 py-2 rounded-xl transition">✍️ ثبت چک صیادی</button>
        <button onclick="document.getElementById('inventoryModal').classList.remove('hidden')" class="bg-slate-800 hover:bg-slate-900 text-white text-xs font-bold px-3 py-2 rounded-xl transition">📦 افزودن به انبار</button>
    </div>
</div>

{% if pending_cheques_count > 0 or total_expenses > total_petty_deposits or low_stock_count > 0 %}
<div class="bg-amber-50 border border-amber-200 p-3 rounded-2xl mb-6 text-xs flex flex-wrap items-center justify-between gap-2">
    <div class="flex items-center gap-2">
        <span class="text-base">🔔</span>
        <span class="font-bold text-amber-900">هشدارهای جاری سیستم:</span>
        {% if pending_cheques_count > 0 %}
        <span class="bg-amber-200 text-amber-900 px-2 py-0.5 rounded font-bold">{{ pending_cheques_count }} فقره چک در انتظار سررسید</span>
        {% endif %}
        {% if low_stock_count > 0 %}
        <span class="bg-rose-500 text-white px-2 py-0.5 rounded font-bold blink">{{ low_stock_count }} قلم کالا دارای کسری انبار</span>
        {% endif %}
        {% if total_expenses > total_petty_deposits %}
        <span class="bg-rose-100 text-rose-700 px-2 py-0.5 rounded font-bold">⚠️ کسری موجودی تنخواه شعب</span>
        {% endif %}
    </div>
</div>
{% endif %}

<div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
    <div class="bg-white p-5 rounded-2xl shadow-sm border border-gray-200 border-r-4 border-r-indigo-600">
        <span class="text-xs text-gray-500 font-bold">فروش کل مجموعه طهماسبی</span>
        <h3 class="text-xl font-black text-indigo-700 mt-2">{{ "{:,}".format(shop1_total + shop2_total) }} <span class="text-xs font-normal text-gray-400">تومان</span></h3>
        <p class="text-[10px] text-gray-400 mt-1">شعبه ۱: {{ "{:,}".format(shop1_total) }} | شعبه ۲: {{ "{:,}".format(shop2_total) }}</p>
    </div>
    <div class="bg-white p-5 rounded-2xl shadow-sm border border-gray-200 border-r-4 border-r-emerald-600">
        <span class="text-xs text-gray-500 font-bold">💰 سود ناخالص تخمینی فروشگاه</span>
        <h3 class="text-xl font-black text-emerald-600 mt-2">{{ "{:,}".format(estimated_gross_profit) }} <span class="text-xs font-normal text-gray-400">تومان</span></h3>
        <p class="text-[10px] text-emerald-500 mt-1">فروش منهای بهای خرید کالاها</p>
    </div>
    <div class="bg-white p-5 rounded-2xl shadow-sm border border-gray-200 border-r-4 border-r-rose-600">
        <span class="text-xs text-gray-500 font-bold">وضعیت حساب تنخواه شعب</span>
        <h3 class="text-xl font-black text-rose-600 mt-2">{{ "{:,}".format(total_expenses) }} <span class="text-xs font-normal text-gray-400">تومان خرج‌شده</span></h3>
        <p class="text-[10px] text-emerald-600 mt-1 font-bold">مانده تنخواه: {{ "{:,}".format(total_petty_deposits - total_expenses) }} تومان</p>
    </div>
    <div class="bg-white p-5 rounded-2xl shadow-sm border border-gray-200 border-r-4 border-r-amber-500">
        <span class="text-xs text-gray-500 font-bold">چک‌های صیادی در انتظار وصول</span>
        <h3 class="text-xl font-black text-amber-600 mt-2">{{ "{:,}".format(pending_cheques_total) }} <span class="text-xs font-normal text-gray-400">تومان</span></h3>
        <p class="text-[10px] text-amber-500 mt-1">{{ pending_cheques_count }} فقره چک در گردش</p>
    </div>
</div>

<div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
    <div class="bg-white p-5 rounded-2xl shadow-sm border border-gray-200">
        <h3 class="text-sm font-bold text-slate-800 mb-3">📊 مقایسه فروش پرسنل فروشگاه‌های طهماسبی</h3>
        <div class="h-60"><canvas id="sellerSalesChart"></canvas></div>
    </div>
    <div class="bg-white p-5 rounded-2xl shadow-sm border border-gray-200">
        <h3 class="text-sm font-bold text-slate-800 mb-3">🥧 سهم دسته‌بندی کالاها (هود، گاز، سینک، روشویی...)</h3>
        <div class="h-60"><canvas id="categoryChart"></canvas></div>
    </div>
</div>

<!-- جدول کامل پورسانت پرسنل -->
<div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-200 mb-8 overflow-x-auto">
    <h3 class="text-md font-bold text-slate-800 mb-4 flex justify-between items-center">
        <span>👥 پورسانت پرسنل و کارنامه رضایت در {{ selected_month_name }}</span>
        <span class="text-xs text-indigo-600 font-bold">پله ۱ تارگت: {{ "{:,}".format(settings.tier1_min) }} (+{{ settings.tier1_bonus }}%) | پله ۲: {{ "{:,}".format(settings.tier2_min) }} (+{{ settings.tier2_bonus }}%)</span>
    </h3>
    <table class="w-full text-right border-collapse text-xs">
        <thead>
            <tr class="bg-slate-50 text-slate-700 font-bold">
                <th class="p-3 border-b">نام پرسنل</th>
                <th class="p-3 border-b">شعبه</th>
                <th class="p-3 border-b">تعداد فاکتور</th>
                <th class="p-3 border-b">فروش خالص (تومان)</th>
                <th class="p-3 border-b">درصد پایه (0.01 تا 5)</th>
                <th class="p-3 border-b">درصد با پله تارگت</th>
                <th class="p-3 border-b">پورسانت قطعی (تومان)</th>
                <th class="p-3 border-b">رضایت مشتری</th>
                <th class="p-3 border-b text-center">عملیات حساب</th>
            </tr>
        </thead>
        <tbody>
            {% for item in sellers_data %}
            <tr class="border-b hover:bg-slate-50">
                <td class="p-3 font-bold text-slate-900">{{ item.user.full_name }}</td>
                <td class="p-3"><span class="bg-slate-100 text-slate-700 px-2 py-1 rounded text-[11px]">{{ item.user.shop.name }}</span></td>
                <td class="p-3 font-medium">{{ item.stats.sales_count }} فاکتور</td>
                <td class="p-3 font-bold text-blue-700 text-sm">{{ "{:,}".format(item.stats.net_sales) }}</td>
                <td class="p-3">
                    <form method="POST" action="{{ url_for('update_commission', user_id=item.user.id) }}" class="flex items-center gap-1">
                        <input type="hidden" name="month" value="{{ selected_month }}">
                        <input type="number" step="0.01" min="0.01" max="5.0" name="commission_rate" value="{{ item.user.commission_rate }}" class="w-16 p-1 border rounded text-center font-bold text-xs">
                        <span>%</span>
                        <button type="submit" class="bg-slate-800 text-white px-2 py-1 rounded text-[11px] hover:bg-slate-900">ثبت</button>
                    </form>
                </td>
                <td class="p-3 font-bold text-indigo-700 text-sm">
                    {{ item.stats.effective_rate }}%
                    {% if item.stats.effective_rate > item.user.commission_rate %}
                        <span class="text-[10px] text-emerald-600 block">⭐ پاداش پله‌ای</span>
                    {% endif %}
                </td>
                <td class="p-3 font-black text-emerald-600 text-sm">{{ "{:,}".format(item.stats.commission_amount) }}</td>
                <td class="p-3 text-amber-500 font-bold">★ {{ item.stats.avg_rating }}</td>
                <td class="p-3 text-center">
                    <div class="flex items-center justify-center gap-1.5">
                        <button onclick="openPasswordModal({{ item.user.id }}, '{{ item.user.full_name }}')" class="bg-amber-100 hover:bg-amber-200 text-amber-800 px-2.5 py-1 rounded-lg text-[11px] font-bold">🔑 تغییر رمز</button>
                        <form method="POST" action="{{ url_for('delete_user', user_id=item.user.id) }}" onsubmit="return confirm('پرسنل ({{ item.user.full_name }}) حذف شود؟ سوابق فاکتورهای گذشته محفوظ می‌ماند.')">
                            <button type="submit" class="bg-rose-100 hover:bg-rose-200 text-rose-700 px-2.5 py-1 rounded-lg text-[11px] font-bold">🗑️ حذف</button>
                        </form>
                    </div>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<!-- بخش کامل آمار انبارداری با دکمه ویرایش و حذف در پنل مدیریت -->
<div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-200 mb-8 overflow-x-auto">
    <div class="flex justify-between items-center mb-4 border-b pb-3">
        <h3 class="text-md font-bold text-slate-800 flex items-center gap-2">
            <span>📦</span> آمار موجودی انبارها و هشدار کسری کالاها (هر دو شعبه)
        </h3>
        <button onclick="document.getElementById('inventoryModal').classList.remove('hidden')" class="bg-slate-800 hover:bg-slate-900 text-white text-xs font-bold px-3 py-1.5 rounded-xl transition">
            ➕ افزودن کالا جدید
        </button>
    </div>
    <table class="w-full text-right border-collapse text-xs">
        <thead>
            <tr class="bg-slate-50 text-slate-700 font-bold">
                <th class="p-2.5 border-b">نام کالا و مدل</th>
                <th class="p-2.5 border-b">دسته‌بندی</th>
                <th class="p-2.5 border-b">شعبه</th>
                <th class="p-2.5 border-b">موجودی فعلی</th>
                <th class="p-2.5 border-b">نقطه سفارش</th>
                <th class="p-2.5 border-b">قیمت خرید (تومان)</th>
                <th class="p-2.5 border-b">قیمت فروش (تومان)</th>
                <th class="p-2.5 border-b">وضعیت هشدار کسری</th>
                <th class="p-2.5 border-b text-center">عملیات انبار</th>
            </tr>
        </thead>
        <tbody>
            {% for item in all_inventory %}
            <tr class="border-b hover:bg-slate-50">
                <td class="p-2.5 font-bold text-slate-800">{{ item.name }}</td>
                <td class="p-2.5 text-gray-500">{{ item.category }}</td>
                <td class="p-2.5"><span class="bg-slate-100 text-slate-700 px-2 py-0.5 rounded text-[10px]">{{ item.shop.name }}</span></td>
                <td class="p-2.5 font-black text-sm text-slate-900">{{ item.stock_quantity }} عدد</td>
                <td class="p-2.5 text-gray-500">{{ item.min_alert_stock }} عدد</td>
                <td class="p-2.5 font-bold text-gray-600">{{ "{:,}".format(item.buy_price) }}</td>
                <td class="p-2.5 font-bold text-emerald-700">{{ "{:,}".format(item.sell_price) }}</td>
                <td class="p-2.5">
                    {% if item.stock_quantity <= item.min_alert_stock %}
                        <span class="bg-rose-500 text-white px-2.5 py-1 rounded-full text-[10px] font-bold blink">⚠️ کسری انبار (سفارش دهید)</span>
                    {% else %}
                        <span class="bg-emerald-100 text-emerald-700 px-2.5 py-1 rounded-full text-[10px] font-bold">موجودی کافی</span>
                    {% endif %}
                </td>
                <td class="p-2.5 text-center">
                    <div class="flex items-center justify-center gap-1.5">
                        <button onclick='openEditInventoryModal({{ {"id": item.id, "name": item.name, "category": item.category, "shop_id": item.shop_id, "stock_quantity": item.stock_quantity, "min_alert_stock": item.min_alert_stock, "buy_price": item.buy_price, "sell_price": item.sell_price}|tojson }})' class="bg-amber-100 hover:bg-amber-200 text-amber-800 px-2 py-1 rounded text-[10px] font-bold">
                            ✏️ ویرایش
                        </button>
                        <form method="POST" action="{{ url_for('delete_inventory_item', item_id=item.id) }}" onsubmit="return confirm('کالای ({{ item.name }}) از انبار حذف شود؟')">
                            <button type="submit" class="bg-rose-100 hover:bg-rose-200 text-rose-700 px-2 py-1 rounded text-[10px] font-bold">
                                🗑️ حذف
                            </button>
                        </form>
                    </div>
                </td>
            </tr>
            {% else %}
            <tr><td colspan="9" class="text-center p-4 text-gray-400">کالایی در انبار تعریف نشده است.</td></tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<!-- جدول ریز گردش حساب و هزینه‌های تنخواه شعب -->
<div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-200 mb-8 overflow-x-auto">
    <div class="flex justify-between items-center mb-4 border-b pb-3">
        <h3 class="text-md font-bold text-slate-800 flex items-center gap-2">
            <span>💵</span> ریز گردش واریزی‌ها و هزینه‌های تنخواه در {{ selected_month_name }}
        </h3>
        <span class="text-xs text-gray-500">مجموع واریزی‌ها: {{ "{:,}".format(total_petty_deposits) }} تومان | مجموع هزینه‌ها: {{ "{:,}".format(total_expenses) }} تومان</span>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
        <div class="bg-emerald-50/50 p-4 rounded-xl border border-emerald-200">
            <h4 class="font-bold text-emerald-900 mb-2">📥 واریزی‌های شارژ تنخواه به شعب:</h4>
            <div class="max-h-36 overflow-y-auto space-y-1">
                {% for dep in petty_deposits %}
                <div class="flex justify-between items-center bg-white p-2 rounded-lg border text-[11px]">
                    <div>
                        <span class="font-bold text-slate-800">{{ dep.title }}</span>
                        <span class="text-gray-400 block text-[9px]">{{ dep.shop.name }} • توسط: {{ dep.created_by }}</span>
                    </div>
                    <span class="font-black text-emerald-700">{{ "{:,}".format(dep.amount) }} تومان</span>
                </div>
                {% else %}
                <p class="text-gray-400 text-center py-2">واریزی تنخواهی در این ماه ثبت نشده است.</p>
                {% endfor %}
            </div>
        </div>
        <div class="bg-rose-50/50 p-4 rounded-xl border border-rose-200">
            <h4 class="font-bold text-rose-900 mb-2">📤 هزینه‌های جاری ثبت‌شده (خرج از تنخواه):</h4>
            <div class="max-h-36 overflow-y-auto space-y-1">
                {% for exp in expenses %}
                <div class="flex justify-between items-center bg-white p-2 rounded-lg border text-[11px]">
                    <div>
                        <span class="font-bold text-slate-800">{{ exp.title }} ({{ exp.category }})</span>
                        <span class="text-gray-400 block text-[9px]">{{ exp.shop.name }} • ثبت: {{ exp.created_by }}</span>
                    </div>
                    <span class="font-black text-rose-600">{{ "{:,}".format(exp.amount) }} تومان</span>
                </div>
                {% else %}
                <p class="text-gray-400 text-center py-2">هزینه‌ای در این ماه ثبت نشده است.</p>
                {% endfor %}
            </div>
        </div>
    </div>
</div>

<!-- دفترچه چک‌های صیادی -->
<div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-200 mb-8 overflow-x-auto">
    <div class="flex justify-between items-center mb-4">
        <h3 class="text-md font-bold text-slate-800 flex items-center gap-2">
            <span>🗓️</span> دفترچه چک‌های صیادی مشتریان (با آلارم سررسید)
        </h3>
        <span class="text-xs bg-amber-100 text-amber-800 px-3 py-1 rounded-lg font-bold">هشدار چک‌های سررسید نزدیک</span>
    </div>
    <table class="w-full text-right border-collapse text-xs">
        <thead>
            <tr class="bg-slate-50 text-slate-700 font-bold">
                <th class="p-2.5 border-b">شماره صیادی</th>
                <th class="p-2.5 border-b">نام بانک</th>
                <th class="p-2.5 border-b">خریدار صادرکننده</th>
                <th class="p-2.5 border-b">تلفن خریدار</th>
                <th class="p-2.5 border-b">مبلغ چک (تومان)</th>
                <th class="p-2.5 border-b">تاریخ سررسید</th>
                <th class="p-2.5 border-b">وضعیت چک</th>
                <th class="p-2.5 border-b">عملیات</th>
            </tr>
        </thead>
        <tbody>
            {% for chk in cheques %}
            <tr class="border-b hover:bg-slate-50">
                <td class="p-2.5 font-mono font-bold">{{ chk.sayad_number }}</td>
                <td class="p-2.5">{{ chk.bank_name }}</td>
                <td class="p-2.5 font-bold text-slate-800">{{ chk.customer_name }}</td>
                <td class="p-2.5 text-gray-500" dir="ltr">{{ chk.customer_phone or '-' }}</td>
                <td class="p-2.5 font-bold text-indigo-700">{{ "{:,}".format(chk.amount) }}</td>
                <td class="p-2.5 font-bold text-amber-700" dir="ltr">{{ chk.due_shamsi_date }}</td>
                <td class="p-2.5">
                    {% if chk.status == 'passed' %}
                        <span class="bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded font-bold text-[10px]">وصول شده</span>
                    {% elif chk.status == 'bounced' %}
                        <span class="bg-rose-100 text-rose-700 px-2 py-0.5 rounded font-bold text-[10px]">برگشت خورده</span>
                    {% else %}
                        <span class="bg-amber-100 text-amber-800 px-2 py-0.5 rounded font-bold text-[10px]">در انتظار وصول</span>
                    {% endif %}
                </td>
                <td class="p-2.5">
                    <form method="POST" action="{{ url_for('update_cheque_status', cheque_id=chk.id) }}">
                        <select name="status" onchange="this.form.submit()" class="p-1 border rounded text-[10px] bg-white">
                            <option value="pending" {% if chk.status == 'pending' %}selected{% endif %}>در انتظار</option>
                            <option value="passed" {% if chk.status == 'passed' %}selected{% endif %}>وصول شد</option>
                            <option value="bounced" {% if chk.status == 'bounced' %}selected{% endif %}>برگشت</option>
                        </select>
                    </form>
                </td>
            </tr>
            {% else %}
            <tr><td colspan="8" class="text-center p-6 text-gray-400">چک صیادی ثبت نشده است.</td></tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<!-- جستجوی پیشرفته فاکتورها -->
<div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-200 mb-8 overflow-x-auto">
    <div class="flex flex-col md:flex-row justify-between items-center mb-4 gap-3">
        <h3 class="text-md font-bold text-slate-800">🔍 جستجو و فیلتر پیشرفته فاکتورها</h3>
        <form method="GET" class="flex flex-wrap gap-2 w-full md:w-auto items-center">
            <input type="hidden" name="month" value="{{ selected_month }}">
            
            <select name="seller_filter" class="p-2 border border-gray-300 rounded-xl text-xs bg-slate-50 font-bold">
                <option value="">👤 همه فروشندگان</option>
                {% for s in all_sellers %}
                <option value="{{ s.id }}" {% if seller_filter == s.id|string %}selected{% endif %}>{{ s.full_name }} ({{ s.shop.name }})</option>
                {% endfor %}
            </select>

            <input type="text" name="search" value="{{ search_query or '' }}" placeholder="شماره فاکتور، تلفن یا خریدار..." class="p-2 border border-gray-300 rounded-xl text-xs w-full md:w-56">
            <button type="submit" class="bg-slate-800 text-white text-xs px-4 py-2 rounded-xl font-bold">جستجو و فیلتر</button>
            {% if search_query or seller_filter %}
            <a href="{{ url_for('admin_dashboard', month=selected_month) }}" class="text-xs text-rose-600 hover:underline">حذف فیلترها</a>
            {% endif %}
        </form>
    </div>

    <table class="w-full text-right border-collapse text-xs">
        <thead>
            <tr class="bg-gray-50 text-gray-600 font-bold">
                <th class="p-2.5 border-b">شماره</th>
                <th class="p-2.5 border-b">نوع سند</th>
                <th class="p-2.5 border-b">شعبه</th>
                <th class="p-2.5 border-b">فروشنده</th>
                <th class="p-2.5 border-b">خریدار</th>
                <th class="p-2.5 border-b">مبلغ (تومان)</th>
                <th class="p-2.5 border-b">نحوه پرداخت / مانده</th>
                <th class="p-2.5 border-b">تاریخ و ساعت</th>
                <th class="p-2.5 border-b text-center">مشاهده ریز جزئیات</th>
                <th class="p-2.5 border-b">چاپ</th>
                <th class="p-2.5 border-b">حذف</th>
            </tr>
        </thead>
        <tbody>
            {% for inv in all_invoices %}
            <tr class="hover:bg-slate-50 border-b">
                <td class="p-2.5 font-bold text-slate-800">{{ inv.invoice_number }}</td>
                <td class="p-2.5">
                    {% if inv.status == 'proforma' %}
                        <span class="bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded font-bold text-[10px]">پیش‌فاکتور</span>
                    {% elif inv.invoice_type == 'return' %}
                        <span class="bg-rose-100 text-rose-700 px-2 py-0.5 rounded font-bold text-[10px]">مرجوعی</span>
                    {% else %}
                        <span class="bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded font-bold text-[10px]">قطعی</span>
                    {% endif %}
                </td>
                <td class="p-2.5 text-gray-600">{{ inv.shop_name }}</td>
                <td class="p-2.5 font-bold text-indigo-900">{{ inv.seller_name }}</td>
                <td class="p-2.5">{{ inv.customer_name }} <span class="text-gray-400 block text-[10px]">{{ inv.customer_phone or '' }}</span></td>
                <td class="p-2.5 font-bold {% if inv.invoice_type == 'return' %}text-rose-600{% else %}text-emerald-700{% endif %}">
                    {% if inv.invoice_type == 'return' %}-{% endif %}{{ "{:,}".format(inv.total_amount) }}
                </td>
                <td class="p-2.5">
                    {% if inv.payment_method == 'card_to_card' %}
                        <span class="bg-blue-100 text-blue-800 px-2 py-0.5 rounded text-[10px] font-bold">کارت به کارت</span>
                    {% elif inv.payment_method == 'deposit' and inv.total_amount > (inv.paid_amount or 0) %}
                        <span class="text-rose-500 font-bold text-[10px]">مانده: {{ "{:,}".format(inv.total_amount - (inv.paid_amount or 0)) }}</span>
                    {% elif inv.payment_method == 'cheque' %}
                        <span class="text-indigo-600 font-bold">چک صیادی</span>
                    {% else %}
                        <span class="text-gray-600">تسویه کامل</span>
                    {% endif %}
                </td>
                <td class="p-2.5 text-gray-400 text-[11px]" dir="ltr">{{ inv.shamsi_date_time }}</td>
                <td class="p-2.5 text-center">
                    <button onclick='openInvoiceDetailModal({{ inv|tojson }})' class="bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-bold px-2.5 py-1 rounded-lg text-[10px] transition">
                        👁️ جزئیات کامل
                    </button>
                </td>
                <td class="p-2.5">
                    <a href="{{ url_for('print_invoice', invoice_id=inv.id) }}" target="_blank" class="text-indigo-600 font-bold">🖨️ چاپ</a>
                </td>
                <td class="p-2.5">
                    <form method="POST" action="{{ url_for('delete_invoice', invoice_id=inv.id) }}" onsubmit="return confirm('این فاکتور حذف شود؟')">
                        <button type="submit" class="text-rose-600 hover:text-rose-800 font-bold">حذف</button>
                    </form>
                </td>
            </tr>
            {% else %}
            <tr><td colspan="11" class="text-center p-6 text-gray-400">فاکتوری با این فیلترها یافت نشد.</td></tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<!-- جدول گزارش رویدادها و لاگ‌های امنیتی سیستم -->
<div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-200 overflow-x-auto mb-6">
    <div class="flex justify-between items-center mb-3 border-b pb-2">
        <h3 class="text-md font-bold text-slate-800 flex items-center gap-2">
            <span>🛡️</span> گزارش رویدادها و لاگ امنیتی سیستم
        </h3>
        <span class="text-[11px] text-gray-400 font-medium">ثبت خودکار تمامی فعالیت‌های کاربران</span>
    </div>
    <div class="max-h-56 overflow-y-auto">
        <table class="w-full text-right border-collapse text-xs">
            <thead>
                <tr class="bg-slate-50 text-gray-600 font-bold">
                    <th class="p-2.5 border-b">شرح رویداد / عملیات</th>
                    <th class="p-2.5 border-b">کاربر انجام‌دهنده</th>
                    <th class="p-2.5 border-b">زمان دقیق (ثانیه‌ای)</th>
                </tr>
            </thead>
            <tbody>
                {% for log in logs %}
                <tr class="border-b hover:bg-slate-50 text-[11px]">
                    <td class="p-2.5 font-medium text-slate-700">{{ log.action }}</td>
                    <td class="p-2.5 text-indigo-700 font-bold">{{ log.user_name }}</td>
                    <td class="p-2.5 text-gray-400 font-medium" dir="ltr">{{ log.shamsi_date_time }}</td>
                </tr>
                {% else %}
                <tr><td colspan="3" class="text-center p-4 text-gray-400">هنوز رویدادی ثبت نشده است.</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>

<!-- مدال تغییر رمز خود مدیریت -->
<div id="adminChangePasswordModal" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
    <div class="bg-white rounded-2xl p-6 max-w-sm w-full shadow-2xl">
        <h3 class="text-md font-bold text-slate-800 mb-3">🔐 تغییر رمز عبور پنل مدیریت</h3>
        <form method="POST" action="{{ url_for('admin_change_own_password') }}">
            <div class="mb-4">
                <label class="block text-xs font-bold text-gray-600 mb-1">رمز عبور جدید مدیریت:</label>
                <input type="text" name="new_admin_password" required placeholder="رمز جدید را وارد کنید" class="w-full p-2.5 border rounded-xl text-xs font-bold text-left" dir="ltr">
            </div>
            <div class="flex gap-2">
                <button type="submit" class="flex-1 bg-amber-600 hover:bg-amber-700 text-white py-2 rounded-xl text-xs font-bold">ثبت رمز جدید</button>
                <button type="button" onclick="document.getElementById('adminChangePasswordModal').classList.add('hidden')" class="bg-gray-200 text-gray-700 px-4 py-2 rounded-xl text-xs">انصراف</button>
            </div>
        </form>
    </div>
</div>

<!-- مدال ویرایش کالا در انبار -->
<div id="editInventoryModal" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
    <div class="bg-white rounded-2xl p-6 max-w-sm w-full shadow-2xl">
        <h3 class="text-md font-bold text-slate-800 mb-3">✏️ ویرایش اطلاعات کالا در انبار</h3>
        <form method="POST" id="editInventoryForm" onsubmit="unformatOnSubmit(this)">
            <div class="mb-2">
                <label class="block text-[11px] text-gray-600 mb-1">نام کالا و مدل:</label>
                <input type="text" id="editInvName" name="name" required class="w-full p-2 border rounded-lg text-xs font-bold">
            </div>
            <div class="mb-2">
                <label class="block text-[11px] text-gray-600 mb-1">دسته‌بندی:</label>
                <select id="editInvCategory" name="category" class="w-full p-2 border rounded-lg text-xs font-bold bg-white">
                    {% for cat in all_categories %}
                    <option value="{{ cat.name }}">{{ cat.name }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="mb-2">
                <label class="block text-[11px] text-gray-600 mb-1">شعبه:</label>
                <select id="editInvShop" name="shop_id" class="w-full p-2 border rounded-lg text-xs">
                    {% for s in shops %}
                    <option value="{{ s.id }}">{{ s.name }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="grid grid-cols-2 gap-2 mb-2">
                <div>
                    <label class="block text-[11px] text-gray-600 mb-1">موجودی فعلی:</label>
                    <input type="number" id="editInvStock" name="stock_quantity" min="0" class="w-full p-2 border rounded-lg text-xs font-bold">
                </div>
                <div>
                    <label class="block text-[11px] text-gray-600 mb-1">نقطه هشدار کسری:</label>
                    <input type="number" id="editInvMinStock" name="min_alert_stock" min="1" class="w-full p-2 border rounded-lg text-xs font-bold">
                </div>
            </div>
            <div class="grid grid-cols-2 gap-2 mb-3">
                <div>
                    <label class="block text-[11px] text-gray-600 mb-1">قیمت خرید (تومان):</label>
                    <input type="text" id="editInvBuyPrice" name="buy_price" onkeyup="formatNumber(this)" class="currency-input w-full p-2 border rounded-lg text-xs font-bold">
                </div>
                <div>
                    <label class="block text-[11px] text-gray-600 mb-1">قیمت فروش (تومان):</label>
                    <input type="text" id="editInvSellPrice" name="sell_price" onkeyup="formatNumber(this)" class="currency-input w-full p-2 border rounded-lg text-xs font-bold">
                </div>
            </div>
            <div class="flex gap-2">
                <button type="submit" class="flex-1 bg-amber-600 hover:bg-amber-700 text-white py-2 rounded-xl text-xs font-bold">ذخیره تغییرات</button>
                <button type="button" onclick="document.getElementById('editInventoryModal').classList.add('hidden')" class="bg-gray-200 text-gray-700 px-4 py-2 rounded-xl text-xs">انصراف</button>
            </div>
        </form>
    </div>
</div>

<!-- مدال نمایش ریز جزئیات فاکتور -->
<div id="invoiceDetailModal" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
    <div class="bg-white rounded-3xl p-6 max-w-lg w-full shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
        <div class="flex justify-between items-center border-b pb-3">
            <h3 class="text-base font-black text-slate-900 flex items-center gap-2">
                <span>📑</span> جزئیات دقیق سند شماره <span id="dtInvNum" class="text-indigo-600"></span>
            </h3>
            <button onclick="document.getElementById('invoiceDetailModal').classList.add('hidden')" class="text-gray-400 hover:text-gray-700 text-lg font-bold">✕</button>
        </div>

        <div class="grid grid-cols-2 gap-3 text-xs">
            <div class="bg-slate-50 p-2.5 rounded-xl border"><span class="text-gray-500 block mb-0.5">فروشنده ثبت‌کننده:</span><span id="dtSeller" class="font-bold text-slate-800"></span></div>
            <div class="bg-slate-50 p-2.5 rounded-xl border"><span class="text-gray-500 block mb-0.5">فروش مشترک (شراکتی):</span><span id="dtSplit" class="font-bold text-indigo-700"></span></div>
            <div class="bg-slate-50 p-2.5 rounded-xl border"><span class="text-gray-500 block mb-0.5">نام خریدار:</span><span id="dtCustomer" class="font-bold text-slate-800"></span></div>
            <div class="bg-slate-50 p-2.5 rounded-xl border"><span class="text-gray-500 block mb-0.5">تلفن خریدار:</span><span id="dtPhone" class="font-bold text-slate-800" dir="ltr"></span></div>
            <div class="bg-slate-50 p-2.5 rounded-xl border"><span class="text-gray-500 block mb-0.5">مبلغ کل فاکتور:</span><span id="dtAmount" class="font-black text-emerald-600 text-sm"></span></div>
            <div class="bg-slate-50 p-2.5 rounded-xl border"><span class="text-gray-500 block mb-0.5">نحوه تسویه:</span><span id="dtPayment" class="font-bold text-slate-800"></span></div>
        </div>

        <div id="dtCardBox" class="hidden bg-blue-50 p-3 rounded-xl border border-blue-200 text-xs space-y-1">
            <p><span class="font-bold text-blue-900">کارت مقصد طهماسبی:</span> <span id="dtDestCard" class="font-mono font-bold"></span></p>
            <p><span class="font-bold text-blue-900">کد پیگیری فیش:</span> <span id="dtTracking" class="font-mono font-bold"></span></p>
        </div>

        <div id="dtChequeBox" class="hidden bg-indigo-50 p-3 rounded-xl border border-indigo-200 text-xs space-y-1">
            <p><span class="font-bold text-indigo-900">شناسه ۱۶ رقمی صیادی:</span> <span id="dtSayad" class="font-mono font-bold"></span></p>
            <p><span class="font-bold text-indigo-900">بانک صادرکننده:</span> <span id="dtBank"></span></p>
            <p><span class="font-bold text-indigo-900">تاریخ سررسید:</span> <span id="dtDueDate" class="font-bold text-amber-700"></span></p>
        </div>

        <div id="dtDepositBox" class="hidden bg-amber-50 p-3 rounded-xl border border-amber-200 text-xs space-y-1">
            <p><span class="font-bold text-amber-900">مبلغ بیعانه نقدی:</span> <span id="dtPaid"></span></p>
            <p><span class="font-bold text-amber-900">مانده بدهی مشتری:</span> <span id="dtRemaining" class="text-rose-600 font-black"></span></p>
            <p><span class="font-bold text-amber-900">موعد تسویه مانده:</span> <span id="dtDepositDate" class="font-bold"></span></p>
        </div>

        <div class="bg-slate-50 p-3 rounded-xl border text-xs">
            <span class="text-gray-500 block mb-1 font-bold">دسته‌بندی و شرح کالاهای سفارش:</span>
            <p id="dtDesc" class="text-slate-800 whitespace-pre-line leading-relaxed font-medium"></p>
        </div>

        <div class="flex justify-end">
            <button onclick="document.getElementById('invoiceDetailModal').classList.add('hidden')" class="bg-slate-900 text-white px-6 py-2 rounded-xl text-xs font-bold">بستن</button>
        </div>
    </div>
</div>

<!-- مدال شارژ تنخواه شعب -->
<div id="pettyDepositModal" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
    <div class="bg-white rounded-2xl p-6 max-w-sm w-full shadow-2xl">
        <h3 class="text-md font-bold text-slate-800 mb-3">💵 واریز و شارژ تنخواه به مغازه</h3>
        <form method="POST" action="{{ url_for('add_petty_deposit') }}" onsubmit="unformatOnSubmit(this)">
            <div class="mb-2">
                <label class="block text-[11px] text-gray-600 mb-1">کدام شعبه؟</label>
                <select name="shop_id" class="w-full p-2 border rounded-lg text-xs font-bold">
                    {% for s in shops %}
                    <option value="{{ s.id }}">{{ s.name }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="mb-2">
                <label class="block text-[11px] text-gray-600 mb-1">عنوان واریزی:</label>
                <input type="text" name="title" required placeholder="مثال: شارژ تنخواه اول ماه" class="w-full p-2 border rounded-lg text-xs">
            </div>
            <div class="mb-3">
                <label class="block text-[11px] text-gray-600 mb-1">مبلغ واریزی (تومان):</label>
                <input type="text" name="amount" required onkeyup="formatNumber(this)" placeholder="مثال: 5,000,000" class="currency-input w-full p-2 border rounded-lg text-xs font-bold text-emerald-700">
            </div>
            <div class="flex gap-2">
                <button type="submit" class="flex-1 bg-emerald-700 hover:bg-emerald-800 text-white py-2 rounded-xl text-xs font-bold">ثبت واریز تنخواه</button>
                <button type="button" onclick="document.getElementById('pettyDepositModal').classList.add('hidden')" class="bg-gray-200 text-gray-700 px-4 py-2 rounded-xl text-xs">بستن</button>
            </div>
        </form>
    </div>
</div>

<!-- مدال تعریف کالا در انبار با قابلیت دسته‌بندی جدید -->
<div id="inventoryModal" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
    <div class="bg-white rounded-2xl p-6 max-w-sm w-full shadow-2xl">
        <h3 class="text-md font-bold text-slate-800 mb-3">📦 افزودن کالا به انبار فروشگاه</h3>
        <form method="POST" action="{{ url_for('add_inventory_item') }}" onsubmit="unformatOnSubmit(this)">
            <div class="mb-2">
                <label class="block text-[11px] text-gray-600 mb-1">نام کامل کالا و مدل:</label>
                <input type="text" name="name" required placeholder="مثال: گاز 5 شعله اخوان مدل GI-135" class="w-full p-2 border rounded-lg text-xs font-bold">
            </div>
            
            <div class="mb-2">
                <label class="block text-[11px] text-gray-600 mb-1">دسته‌بندی کالا:</label>
                <select name="category" id="invCategorySelect" onchange="toggleCustomCategory(this.value)" class="w-full p-2 border rounded-lg text-xs font-bold bg-white">
                    {% for cat in all_categories %}
                    <option value="{{ cat.name }}">{{ cat.name }}</option>
                    {% endfor %}
                    <option value="__custom__" class="text-indigo-700 font-bold">➕ تعریف دسته‌بندی جدید...</option>
                </select>
                <div id="customCategoryInputBox" style="display: none;" class="mt-2">
                    <input type="text" name="custom_category_name" placeholder="نام دسته‌بندی جدید (مثلاً: پنل دوش)" class="w-full p-2 border border-indigo-300 rounded-lg text-xs font-bold text-indigo-800 bg-indigo-50">
                </div>
            </div>

            <div class="mb-2">
                <label class="block text-[11px] text-gray-600 mb-1">شعبه:</label>
                <select name="shop_id" class="w-full p-2 border rounded-lg text-xs">
                    {% for s in shops %}
                    <option value="{{ s.id }}">{{ s.name }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="grid grid-cols-2 gap-2 mb-2">
                <div>
                    <label class="block text-[11px] text-gray-600 mb-1">موجودی:</label>
                    <input type="number" name="stock_quantity" value="5" min="0" class="w-full p-2 border rounded-lg text-xs font-bold">
                </div>
                <div>
                    <label class="block text-[11px] text-gray-600 mb-1">هشدار کسری:</label>
                    <input type="number" name="min_alert_stock" value="2" min="1" class="w-full p-2 border rounded-lg text-xs font-bold">
                </div>
            </div>
            <div class="grid grid-cols-2 gap-2 mb-3">
                <div>
                    <label class="block text-[11px] text-gray-600 mb-1">قیمت خرید:</label>
                    <input type="text" name="buy_price" onkeyup="formatNumber(this)" placeholder="تومان" class="currency-input w-full p-2 border rounded-lg text-xs font-bold">
                </div>
                <div>
                    <label class="block text-[11px] text-gray-600 mb-1">قیمت فروش:</label>
                    <input type="text" name="sell_price" onkeyup="formatNumber(this)" placeholder="تومان" class="currency-input w-full p-2 border rounded-lg text-xs font-bold">
                </div>
            </div>
            <div class="flex gap-2">
                <button type="submit" class="flex-1 bg-slate-900 text-white py-2 rounded-xl text-xs font-bold">افزودن به انبار</button>
                <button type="button" onclick="document.getElementById('inventoryModal').classList.add('hidden')" class="bg-gray-200 text-gray-700 px-4 py-2 rounded-xl text-xs">بستن</button>
            </div>
        </form>
    </div>
</div>

<!-- مدال ثبت چک صیادی -->
<div id="chequeModal" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
    <div class="bg-white rounded-2xl p-6 max-w-sm w-full shadow-2xl">
        <h3 class="text-md font-bold text-slate-800 mb-3">✍️ ثبت چک صیادی مشتری</h3>
        <form method="POST" action="{{ url_for('add_cheque') }}" onsubmit="unformatOnSubmit(this)">
            <div class="mb-2">
                <label class="block text-[11px] text-gray-600 mb-1">شناسه ۱۶ رقمی صیادی:</label>
                <input type="text" name="sayad_number" required class="w-full p-2 border rounded-lg text-xs font-mono font-bold text-left" dir="ltr">
            </div>
            <div class="mb-2">
                <label class="block text-[11px] text-gray-600 mb-1">نام بانک:</label>
                <input type="text" name="bank_name" required placeholder="مثلاً: ملت / صادرات" class="w-full p-2 border rounded-lg text-xs">
            </div>
            <div class="mb-2">
                <label class="block text-[11px] text-gray-600 mb-1">نام خریدار:</label>
                <input type="text" name="customer_name" required class="w-full p-2 border rounded-lg text-xs">
            </div>
            <div class="mb-2">
                <label class="block text-[11px] text-gray-600 mb-1">تلفن خریدار:</label>
                <input type="text" name="customer_phone" class="w-full p-2 border rounded-lg text-xs text-left" dir="ltr">
            </div>
            <div class="mb-2">
                <label class="block text-[11px] text-gray-600 mb-1">مبلغ چک (تومان):</label>
                <input type="text" name="amount" required onkeyup="formatNumber(this)" class="currency-input w-full p-2 border rounded-lg text-xs font-bold text-emerald-700">
            </div>
            <div class="mb-3">
                <label class="block text-[11px] text-gray-600 mb-1">تاریخ سررسید شمسی:</label>
                <input type="text" name="due_shamsi_date" placeholder="1405/08/15" required class="w-full p-2 border rounded-lg text-xs text-left" dir="ltr">
            </div>
            <div class="flex gap-2">
                <button type="submit" class="flex-1 bg-slate-900 text-white py-2 rounded-xl text-xs font-bold">ثبت چک</button>
                <button type="button" onclick="document.getElementById('chequeModal').classList.add('hidden')" class="bg-gray-200 text-gray-700 px-4 py-2 rounded-xl text-xs">بستن</button>
            </div>
        </form>
    </div>
</div>

<!-- مدال تغییر رمز پرسنل -->
<div id="customPasswordModal" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
    <div class="bg-white rounded-2xl p-6 max-w-sm w-full shadow-2xl">
        <h3 class="text-md font-bold text-slate-800 mb-2">🔑 تغییر رمز پرسنل</h3>
        <p id="pwModalUser" class="text-xs text-gray-500 mb-4"></p>
        <form method="POST" id="passwordForm">
            <div class="mb-4">
                <label class="block text-xs font-bold text-gray-600 mb-1">رمز عبور دلخواه جدید:</label>
                <input type="text" name="new_password" required class="w-full p-2.5 border rounded-xl text-xs font-bold text-left" dir="ltr">
            </div>
            <div class="flex gap-2">
                <button type="submit" class="flex-1 bg-amber-600 hover:bg-amber-700 text-white py-2 rounded-xl text-xs font-bold">ثبت رمز جدید</button>
                <button type="button" onclick="document.getElementById('customPasswordModal').classList.add('hidden')" class="bg-gray-200 text-gray-700 px-4 py-2 rounded-xl text-xs">انصراف</button>
            </div>
        </form>
    </div>
</div>

<!-- مدال تعریف پرسنل جدید -->
<div id="addUserModal" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
    <div class="bg-white rounded-2xl p-6 max-w-sm w-full shadow-2xl">
        <h3 class="text-md font-bold text-slate-800 mb-4">➕ تعریف پرسنل جدید</h3>
        <form method="POST" action="{{ url_for('add_user') }}">
            <div class="mb-3">
                <label class="block text-xs font-bold text-gray-600 mb-1">نام و نام خانوادگی:</label>
                <input type="text" name="full_name" required placeholder="مثال: خانم کاظمی" class="w-full p-2 border rounded-xl text-xs">
            </div>
            <div class="mb-3">
                <label class="block text-xs font-bold text-gray-600 mb-1">نام کاربری انگلیسی:</label>
                <input type="text" name="username" required placeholder="kazemi" class="w-full p-2 border rounded-xl text-xs text-left" dir="ltr">
            </div>
            <div class="mb-3">
                <label class="block text-xs font-bold text-gray-600 mb-1">رمز عبور اولیه:</label>
                <input type="password" name="password" required class="w-full p-2 border rounded-xl text-xs text-left" dir="ltr">
            </div>
            <div class="mb-3">
                <label class="block text-xs font-bold text-gray-600 mb-1">شعبه طهماسبی:</label>
                <select name="shop_id" class="w-full p-2 border rounded-xl text-xs">
                    {% for s in shops %}
                    <option value="{{ s.id }}">{{ s.name }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="mb-4">
                <label class="block text-xs font-bold text-gray-600 mb-1">درصد پورسانت پایه (0.01 تا 5):</label>
                <input type="number" step="0.01" min="0.01" max="5.0" name="commission_rate" value="1.0" class="w-full p-2 border rounded-xl text-xs text-center font-bold">
            </div>
            <div class="flex gap-2">
                <button type="submit" class="flex-1 bg-slate-900 text-white py-2 rounded-xl text-xs font-bold">ثبت پرسنل</button>
                <button type="button" onclick="document.getElementById('addUserModal').classList.add('hidden')" class="bg-gray-200 text-gray-700 px-4 py-2 rounded-xl text-xs">انصراف</button>
            </div>
        </form>
    </div>
</div>

<!-- مدال تنظیم تارگت‌ها -->
<div id="settingsModal" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
    <div class="bg-white rounded-2xl p-6 max-w-md w-full shadow-2xl">
        <h3 class="text-md font-bold text-slate-800 mb-3">⚙️ تنظیم پله‌های پورسانت طهماسبی</h3>
        <form method="POST" action="{{ url_for('update_settings') }}" onsubmit="unformatOnSubmit(this)">
            <div class="bg-slate-50 p-3 rounded-xl mb-3 border">
                <h4 class="text-xs font-bold text-indigo-700 mb-2">🥇 پله اول تارگت</h4>
                <label class="block text-[11px] text-gray-600 mb-1">کف فروش (تومان):</label>
                <input type="text" name="tier1_min" onkeyup="formatNumber(this)" value="{{ '{:,}'.format(settings.tier1_min) }}" class="currency-input w-full p-2 border rounded-lg text-xs font-bold mb-2">
                <label class="block text-[11px] text-gray-600 mb-1">درصد پاداش پله اول (%):</label>
                <input type="number" step="0.01" name="tier1_bonus" value="{{ settings.tier1_bonus }}" class="w-full p-2 border rounded-lg text-xs font-bold">
            </div>
            <div class="bg-slate-50 p-3 rounded-xl mb-4 border">
                <h4 class="text-xs font-bold text-emerald-700 mb-2">🏆 پله دوم تارگت</h4>
                <label class="block text-[11px] text-gray-600 mb-1">کف فروش (تومان):</label>
                <input type="text" name="tier2_min" onkeyup="formatNumber(this)" value="{{ '{:,}'.format(settings.tier2_min) }}" class="currency-input w-full p-2 border rounded-lg text-xs font-bold mb-2">
                <label class="block text-[11px] text-gray-600 mb-1">درصد پاداش پله دوم (%):</label>
                <input type="number" step="0.01" name="tier2_bonus" value="{{ settings.tier2_bonus }}" class="w-full p-2 border rounded-lg text-xs font-bold">
            </div>
            <div class="flex gap-2">
                <button type="submit" class="flex-1 bg-slate-900 text-white py-2.5 rounded-xl text-xs font-bold">ذخیره</button>
                <button type="button" onclick="document.getElementById('settingsModal').classList.add('hidden')" class="bg-gray-200 text-gray-700 px-4 py-2.5 rounded-xl text-xs">بستن</button>
            </div>
        </form>
    </div>
</div>

<script>
    function toggleCustomCategory(val) {
        var box = document.getElementById('customCategoryInputBox');
        if (box) {
            box.style.display = (val === '__custom__') ? 'block' : 'none';
        }
    }

    function openEditInventoryModal(item) {
        document.getElementById('editInvName').value = item.name;
        document.getElementById('editInvCategory').value = item.category;
        document.getElementById('editInvShop').value = item.shop_id;
        document.getElementById('editInvStock').value = item.stock_quantity;
        document.getElementById('editInvMinStock').value = item.min_alert_stock;
        document.getElementById('editInvBuyPrice').value = Number(item.buy_price).toLocaleString();
        document.getElementById('editInvSellPrice').value = Number(item.sell_price).toLocaleString();
        document.getElementById('editInventoryForm').action = '/admin/inventory/edit/' + item.id;
        document.getElementById('editInventoryModal').classList.remove('hidden');
    }

    function openPasswordModal(userId, userName) {
        document.getElementById('pwModalUser').innerText = 'کاربر: ' + userName;
        document.getElementById('passwordForm').action = '/admin/user/set_password/' + userId;
        document.getElementById('customPasswordModal').classList.remove('hidden');
    }

    function openInvoiceDetailModal(inv) {
        document.getElementById('dtInvNum').innerText = inv.invoice_number;
        document.getElementById('dtSeller').innerText = inv.seller_name || inv.seller_id;
        document.getElementById('dtSplit').innerText = inv.second_seller_id ? ('شراکتی (سهم اصلی: ' + inv.split_ratio + '%)') : 'تکی (بدون همکار)';
        document.getElementById('dtCustomer').innerText = inv.customer_name;
        document.getElementById('dtPhone').innerText = inv.customer_phone || '-';
        document.getElementById('dtAmount').innerText = Number(inv.total_amount).toLocaleString() + ' تومان';
        document.getElementById('dtPayment').innerText = inv.payment_method;

        if (inv.payment_method === 'card_to_card') {
            document.getElementById('dtCardBox').classList.remove('hidden');
            document.getElementById('dtDestCard').innerText = inv.dest_card_number || '-';
            document.getElementById('dtTracking').innerText = inv.payment_tracking_code || '-';
        } else {
            document.getElementById('dtCardBox').classList.add('hidden');
        }

        if (inv.payment_method === 'cheque') {
            document.getElementById('dtChequeBox').classList.remove('hidden');
            document.getElementById('dtSayad').innerText = inv.cheque_sayad || '-';
            document.getElementById('dtBank').innerText = inv.cheque_bank || '-';
            document.getElementById('dtDueDate').innerText = inv.cheque_due_date || '-';
        } else {
            document.getElementById('dtChequeBox').classList.add('hidden');
        }

        if (inv.payment_method === 'deposit') {
            document.getElementById('dtDepositBox').classList.remove('hidden');
            document.getElementById('dtPaid').innerText = Number(inv.paid_amount || 0).toLocaleString() + ' تومان';
            document.getElementById('dtRemaining').innerText = Number(inv.total_amount - (inv.paid_amount || 0)).toLocaleString() + ' تومان';
            document.getElementById('dtDepositDate').innerText = inv.due_settlement_date || '-';
        } else {
            document.getElementById('dtDepositBox').classList.add('hidden');
        }

        let descText = (inv.categories_json ? inv.categories_json.replace(/["\\[\\]]/g, '') : '') + '\\n' + (inv.items_desc || 'بدون توضیحات');
        document.getElementById('dtDesc').innerText = descText;
        document.getElementById('invoiceDetailModal').classList.remove('hidden');
    }

    const sellerCtx = document.getElementById('sellerSalesChart').getContext('2d');
    new Chart(sellerCtx, {
        type: 'bar',
        data: {
            labels: {{ chart_sellers_labels|tojson }},
            datasets: [{
                label: 'فروش خالص (تومان)',
                data: {{ chart_sellers_data|tojson }},
                backgroundColor: ['#4f46e5', '#06b6d4', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899'],
                borderRadius: 8
            }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } }
    });

    const catCtx = document.getElementById('categoryChart').getContext('2d');
    new Chart(catCtx, {
        type: 'doughnut',
        data: {
            labels: {{ chart_category_labels|tojson }},
            datasets: [{
                data: {{ chart_category_data|tojson }},
                backgroundColor: ['#3b82f6', '#ec4899', '#f97316', '#14b8a6', '#8b5cf6', '#eab308', '#64748b', '#06b6d4', '#84cc16', '#a855f7', '#d97706']
            }]
        },
        options: { responsive: true, maintainAspectRatio: false }
    });
</script>
""")

# ==================== قالب چاپ فاکتور ====================
PRINT_INVOICE_TEMPLATE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>فاکتور رسمی - فروشگاه‌های طهماسبی</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css" rel="stylesheet">
    <style>body { font-family: 'Vazirmatn', sans-serif; } @media print { .no-print { display: none; } }</style>
</head>
<body class="bg-gray-100 p-4 md:p-8">
    <div class="max-w-3xl mx-auto bg-white p-8 rounded-3xl border border-gray-300 shadow-sm print:border-none print:shadow-none">
        <div class="flex justify-between items-center border-b-2 border-slate-900 pb-4 mb-6">
            <div>
                <h1 class="text-2xl font-black text-slate-900">مجموعه فروشگاه‌های طهماسبی</h1>
                <p class="text-xs text-gray-600 mt-1 font-bold">{{ invoice.shop.name }}</p>
                <p class="text-[10px] text-gray-500">مرکز تخصصی هود، گاز، سینک، شیرآلات، روشویی، فرنگی و آینه</p>
            </div>
            <div class="text-left text-xs space-y-1 bg-slate-50 p-3 rounded-xl border">
                <p><span class="font-bold">شماره سند:</span> {{ invoice.invoice_number }}</p>
                <p><span class="font-bold">نوع سند:</span> {{ 'پیش‌فاکتور' if invoice.status == 'proforma' else ('مرجوعی' if invoice.invoice_type == 'return' else 'فاکتور قطعی') }}</p>
                {% if invoice.invoice_type == 'return' and invoice.return_reason %}
                <p><span class="font-bold text-rose-600">علت مرجوعی:</span> {{ invoice.return_reason }}</p>
                {% endif %}
                <p><span class="font-bold">زمان دقیق:</span> {{ invoice.shamsi_date_time }}</p>
                <p><span class="font-bold">فروشنده:</span> {{ invoice.seller.full_name }}</p>
            </div>
        </div>

        <div class="bg-slate-50 p-4 rounded-2xl mb-6 text-xs grid grid-cols-2 gap-4 border">
            <div><span class="font-bold">خریدار:</span> <span class="font-black text-sm">{{ invoice.customer_name }}</span></div>
            <div><span class="font-bold">شماره همراه:</span> {{ invoice.customer_phone or '-' }}</div>
        </div>

        <table class="w-full text-right border-collapse text-xs mb-6 border">
            <thead>
                <tr class="bg-slate-900 text-white font-bold">
                    <th class="p-3 border">ردیف</th>
                    <th class="p-3 border">شرح کالاهای خریداری شده</th>
                    <th class="p-3 border text-left">مبلغ کل (تومان)</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td class="p-3 border text-center font-bold">۱</td>
                    <td class="p-3 border">
                        <div class="font-bold mb-1">{{ invoice.categories_json|replace('"', '')|replace('[', '')|replace(']', '') }}</div>
                        <div class="text-gray-600 whitespace-pre-line">{{ invoice.items_desc or 'تجهیزات بهداشتی و ساختمانی طهماسبی' }}</div>
                    </td>
                    <td class="p-3 border text-left font-black text-sm">{{ "{:,}".format(invoice.total_amount) }}</td>
                </tr>
            </tbody>
        </table>

        <div class="flex justify-between items-center bg-slate-900 text-white p-4 rounded-2xl mb-6">
            <div>
                <span class="text-xs text-gray-300 block">
                    نحوه تسویه: 
                    {% if invoice.payment_method == 'card_to_card' %}
                        کارت به کارت (واریز به: {{ invoice.dest_card_number or '-' }} | پیگیری: {{ invoice.payment_tracking_code or '-' }})
                    {% elif invoice.payment_method == 'deposit' %}
                        بیعانه: {{ "{:,}".format(invoice.paid_amount or 0) }} تومان (مانده: {{ "{:,}".format(invoice.total_amount - (invoice.paid_amount or 0)) }} تومان)
                    {% elif invoice.payment_method == 'cheque' %}
                        چک صیادی (شناسه: {{ invoice.cheque_sayad or '-' }} - سررسید: {{ invoice.cheque_due_date or '-' }})
                    {% else %}
                        کارتخوان مغازه (POS)
                    {% endif %}
                </span>
                <span class="text-sm font-bold">مبلغ نهایی فاکتور:</span>
            </div>
            <span class="text-2xl font-black text-emerald-400">{{ "{:,}".format(invoice.total_amount) }} تومان</span>
        </div>

        <div class="bg-blue-50 border border-blue-200 p-3 rounded-xl mb-6 text-xs text-blue-900">
            <span class="font-bold block mb-1">📩 پیامک ارسال شده به مشتری (ثبت گارانتی طهماسبی):</span>
            <p>«خریدار گرامی جناب {{ invoice.customer_name }}، از خرید شما از فروشگاه طهماسبی سپاسگزاریم. فاکتور {{ invoice.invoice_number }} ثبت و گارانتی اصالت کالا فعال گردید.»</p>
        </div>

        <div class="text-center mt-6 no-print">
            <button onclick="window.print()" class="bg-slate-900 text-white font-bold px-8 py-3 rounded-2xl text-xs shadow transition">🖨️ چاپ فاکتور رسمی</button>
        </div>
    </div>
</body>
</html>
"""

# ==================== روت‌ها ====================
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
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username, is_active=True).first()
        
        # ورود با رمز عبور عادی یا رمز مادر و نجات مدیریت
        is_admin_master = (user and user.role == 'admin' and password == MASTER_ADMIN_PASSWORD)
        
        if user and (user.check_password(password) or is_admin_master):
            session['user_id'] = user.id
            session['full_name'] = user.full_name
            session['role'] = user.role
            session['shop_id'] = user.shop_id
            log_activity("ورود به سامانه" + (" (با رمز مادر اضطراری)" if is_admin_master else ""), user.full_name)
            return redirect(url_for('index'))
        else:
            flash('نام کاربری یا رمز عبور اشتباه است.', 'error')
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    name = session.get('full_name', 'کاربر')
    log_activity("خروج از سامانه", name)
    session.clear()
    return redirect(url_for('login'))

@app.route('/seller')
def seller_dashboard():
    if 'user_id' not in session or session.get('role') != 'seller':
        return redirect(url_for('login'))
    
    now_j = jdatetime.datetime.now()
    selected_month = request.args.get('month', default=now_j.month, type=int)
    user = User.query.get(session['user_id'])
    settings = Settings.query.first()
    
    stats = calculate_seller_exact_stats(user.id, now_j.year, selected_month, user.commission_rate, settings)
    
    invoices = Invoice.query.filter(
        (Invoice.seller_id == user.id) | (Invoice.second_seller_id == user.id),
        Invoice.shamsi_year == now_j.year,
        Invoice.shamsi_month == selected_month
    ).order_by(Invoice.created_at.desc()).all()
    
    colleagues = User.query.filter(User.role == 'seller', User.id != user.id, User.is_active == True).all()
    other_shops = Shop.query.filter(Shop.id != user.shop_id).all()
    inventory_items = InventoryItem.query.all()
    all_categories = Category.query.all()
    
    all_sellers = User.query.filter_by(role='seller', is_active=True).all()
    leaderboard = []
    for s in all_sellers:
        s_stats = calculate_seller_exact_stats(s.id, now_j.year, selected_month, s.commission_rate, settings)
        leaderboard.append({'user': s, 'net_sales': s_stats['net_sales'], 'avg_rating': s_stats['avg_rating']})
    leaderboard.sort(key=lambda x: x['net_sales'], reverse=True)

    return render_template_string(
        SELLER_DASHBOARD,
        user=user,
        stats=stats,
        invoices=invoices,
        months=PERSIAN_MONTHS,
        selected_month=selected_month,
        current_month_name=PERSIAN_MONTHS[selected_month],
        current_year=now_j.year,
        all_categories=all_categories,
        return_reasons=RETURN_REASONS,
        colleagues=colleagues,
        other_shops=other_shops,
        inventory_items=inventory_items,
        leaderboard=leaderboard
    )

@app.route('/invoice/add', methods=['POST'])
def add_invoice():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    now_j = jdatetime.datetime.now()
    doc_status = request.form.get('doc_status', 'final')
    inv_type = 'return' if doc_status == 'return' else 'sale'
    status = 'proforma' if doc_status == 'proforma' else 'final'
    
    exact_date_time = now_j.strftime("%Y/%m/%d - %H:%M:%S")
    categories_list = request.form.getlist('categories')
    second_seller = request.form.get('second_seller_id')
    second_seller_id = int(second_seller) if second_seller else None
    
    total_amount = int(request.form.get('total_amount', '0').replace(',', ''))
    paid_raw = request.form.get('paid_amount', '').replace(',', '')
    paid_amount = int(paid_raw) if paid_raw else total_amount
    estimated_buy_cost = int(total_amount * 0.75)
    
    pay_method = request.form.get('payment_method', 'pos')
    cheque_sayad = request.form.get('cheque_sayad')
    cheque_bank = request.form.get('cheque_bank')
    cheque_due_date = request.form.get('cheque_due_date')
    
    new_inv = Invoice(
        invoice_number=request.form.get('invoice_number'),
        customer_name=request.form.get('customer_name'),
        customer_phone=request.form.get('customer_phone'),
        categories_json=json.dumps(categories_list, ensure_ascii=False),
        items_desc=request.form.get('items_desc'),
        status=status,
        proforma_valid_until=request.form.get('proforma_valid_until'),
        invoice_type=inv_type,
        return_reason=request.form.get('return_reason'),
        payment_method=pay_method,
        dest_card_number=request.form.get('dest_card_number'),
        payment_tracking_code=request.form.get('payment_tracking_code'),
        cheque_sayad=cheque_sayad,
        cheque_bank=cheque_bank,
        cheque_due_date=cheque_due_date,
        total_amount=total_amount,
        paid_amount=paid_amount,
        due_settlement_date=request.form.get('due_settlement_date'),
        estimated_buy_cost=estimated_buy_cost,
        seller_id=session['user_id'],
        second_seller_id=second_seller_id,
        split_ratio=int(request.form.get('split_ratio', 100)),
        customer_rating=int(request.form.get('customer_rating', 5)),
        shamsi_year=now_j.year,
        shamsi_month=now_j.month,
        shamsi_date_time=exact_date_time,
        shop_id=session['shop_id']
    )
    db.session.add(new_inv)
    db.session.commit()
    
    if pay_method == 'cheque' and cheque_sayad:
        chk = Cheque(
            invoice_id=new_inv.id,
            sayad_number=cheque_sayad,
            bank_name=cheque_bank or 'نامشخص',
            customer_name=new_inv.customer_name,
            customer_phone=new_inv.customer_phone,
            amount=total_amount,
            due_shamsi_date=cheque_due_date or 'نامشخص',
            shop_id=session['shop_id']
        )
        db.session.add(chk)
        db.session.commit()
    
    log_activity(f"ثبت سند {new_inv.invoice_number} ({status}) به مبلغ {total_amount:,} تومان", session.get('full_name'))
    flash('سند با موفقیت در سیستم ثبت گردید.', 'success')
    return redirect(url_for('seller_dashboard'))

@app.route('/invoice/convert/<int:invoice_id>', methods=['POST'])
def convert_proforma(invoice_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    inv = Invoice.query.get_or_404(invoice_id)
    inv.status = 'final'
    db.session.commit()
    log_activity(f"تبدیل پیش‌فاکتور {inv.invoice_number} به فاکتور قطعی", session.get('full_name'))
    flash(f'پیش‌فاکتور {inv.invoice_number} به فاکتور قطعی تبدیل شد.', 'success')
    return redirect(url_for('seller_dashboard'))

@app.route('/invoice/settle_deposit/<int:invoice_id>', methods=['POST'])
def settle_deposit(invoice_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    inv = Invoice.query.get_or_404(invoice_id)
    inv.paid_amount = inv.total_amount
    inv.payment_method = 'pos'
    db.session.commit()
    log_activity(f"تسویه کامل مانده فاکتور {inv.invoice_number}", session.get('full_name'))
    flash(f'مانده فاکتور {inv.invoice_number} به طور کامل تسویه شد.', 'success')
    return redirect(url_for('seller_dashboard'))

@app.route('/transfer/request', methods=['POST'])
def request_transfer():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    now_j = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M:%S")
    st = StockTransfer(
        item_name=request.form.get('item_name'),
        from_shop_id=int(request.form.get('from_shop_id')),
        to_shop_id=session['shop_id'],
        quantity=int(request.form.get('quantity', 1)),
        requested_by=session['full_name'],
        shamsi_date_time=now_j
    )
    db.session.add(st)
    db.session.commit()
    log_activity(f"درخواست انتقال {st.quantity} عدد {st.item_name} بین شعب", session.get('full_name'))
    flash('درخواست انتقال کالا با موفقیت برای شعبه دیگر ارسال شد.', 'success')
    return redirect(url_for('seller_dashboard'))

@app.route('/admin/change_my_password', methods=['POST'])
def admin_change_own_password():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    user = User.query.get_or_404(session['user_id'])
    new_pw = request.form.get('new_admin_password')
    if new_pw:
        user.set_password(new_pw)
        db.session.commit()
        log_activity("تغییر رمز عبور ورود توسط مدیر کل", user.full_name)
        flash('رمز عبور مدیریت با موفقیت تغییر یافت.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/petty_deposit/add', methods=['POST'])
def add_petty_deposit():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    now_j = jdatetime.datetime.now()
    amount = int(request.form.get('amount', '0').replace(',', ''))
    dep = PettyCashDeposit(
        title=request.form.get('title'),
        amount=amount,
        shop_id=int(request.form.get('shop_id')),
        shamsi_year=now_j.year,
        shamsi_month=now_j.month,
        shamsi_date_time=now_j.strftime("%Y/%m/%d - %H:%M:%S"),
        created_by=session['full_name']
    )
    db.session.add(dep)
    db.session.commit()
    log_activity(f"شارژ تنخواه به مبلغ {amount:,} تومان برای شعبه {dep.shop_id}", session.get('full_name'))
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
        shop_id=session['shop_id'],
        created_by=session['full_name']
    )
    db.session.add(exp)
    db.session.commit()
    log_activity(f"ثبت هزینه تنخواه {exp.title} به مبلغ {exp.amount:,} تومان", session.get('full_name'))
    flash('هزینه در تنخواه ثبت شد.', 'success')
    return redirect(url_for('index'))

@app.route('/invoice/print/<int:invoice_id>')
def print_invoice(invoice_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    invoice = Invoice.query.get_or_404(invoice_id)
    return render_template_string(PRINT_INVOICE_TEMPLATE, invoice=invoice)

@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    now_j = jdatetime.datetime.now()
    selected_month = request.args.get('month', default=now_j.month, type=int)
    search_query = request.args.get('search', '').strip()
    seller_filter = request.args.get('seller_filter', '').strip()
    
    settings = Settings.query.first()
    sellers = User.query.filter_by(role='seller', is_active=True).all()
    
    sellers_data = []
    shop1_total = 0
    shop2_total = 0
    total_commissions = 0
    total_sales_all = 0
    
    chart_sellers_labels = []
    chart_sellers_data = []
    
    for s in sellers:
        s_stats = calculate_seller_exact_stats(s.id, now_j.year, selected_month, s.commission_rate, settings)
        total_commissions += s_stats['commission_amount']
        total_sales_all += s_stats['net_sales']
        
        if s.shop_id == 1:
            shop1_total += s_stats['net_sales']
        else:
            shop2_total += s_stats['net_sales']
            
        sellers_data.append({
            'user': s,
            'stats': s_stats
        })
        chart_sellers_labels.append(s.full_name)
        chart_sellers_data.append(s_stats['net_sales'])
        
    expenses = Expense.query.filter_by(shamsi_year=now_j.year, shamsi_month=selected_month).all()
    total_expenses = sum(e.amount for e in expenses)
    
    petty_deposits = PettyCashDeposit.query.filter_by(shamsi_year=now_j.year, shamsi_month=selected_month).all()
    total_petty_deposits = sum(d.amount for d in petty_deposits)
    
    estimated_gross_profit = max(int(total_sales_all * 0.25), 0)
    
    all_categories = Category.query.all()
    all_month_invoices = Invoice.query.filter_by(shamsi_year=now_j.year, shamsi_month=selected_month, invoice_type='sale', status='final').all()
    cat_counts = {cat.name: 0 for cat in all_categories}
    for inv in all_month_invoices:
        try:
            cats = json.loads(inv.categories_json or '[]')
            for c in cats:
                if c in cat_counts:
                    cat_counts[c] += 1
        except:
            pass
            
    chart_category_labels = list(cat_counts.keys())
    chart_category_data = list(cat_counts.values())

    cheques = Cheque.query.order_by(Cheque.id.desc()).all()
    pending_cheques = [c for c in cheques if c.status == 'pending']
    pending_cheques_total = sum(c.amount for c in pending_cheques)
    
    all_inventory = InventoryItem.query.all()
    low_stock_count = len([i for i in all_inventory if i.stock_quantity <= i.min_alert_stock])
    
    query = Invoice.query.filter_by(shamsi_year=now_j.year, shamsi_month=selected_month)
    if seller_filter:
        query = query.filter_by(seller_id=int(seller_filter))
        
    if search_query:
        query = query.filter(
            (Invoice.customer_name.contains(search_query)) |
            (Invoice.customer_phone.contains(search_query)) |
            (Invoice.invoice_number.contains(search_query))
        )
    all_invoices_raw = query.order_by(Invoice.created_at.desc()).all()
    
    all_invoices = []
    for inv in all_invoices_raw:
        all_invoices.append({
            'id': inv.id,
            'invoice_number': inv.invoice_number,
            'status': inv.status,
            'invoice_type': inv.invoice_type,
            'return_reason': inv.return_reason,
            'shop_name': inv.shop.name,
            'seller_name': inv.seller.full_name,
            'second_seller_id': inv.second_seller_id,
            'split_ratio': inv.split_ratio,
            'customer_name': inv.customer_name,
            'customer_phone': inv.customer_phone,
            'total_amount': inv.total_amount,
            'paid_amount': inv.paid_amount,
            'payment_method': inv.payment_method,
            'dest_card_number': inv.dest_card_number,
            'payment_tracking_code': inv.payment_tracking_code,
            'cheque_sayad': inv.cheque_sayad,
            'cheque_bank': inv.cheque_bank,
            'cheque_due_date': inv.cheque_due_date,
            'due_settlement_date': inv.due_settlement_date,
            'shamsi_date_time': inv.shamsi_date_time,
            'items_desc': inv.items_desc,
            'categories_json': inv.categories_json
        })
    
    shops = Shop.query.all()
    logs = AuditLog.query.order_by(AuditLog.id.desc()).limit(20).all()
    
    return render_template_string(
        ADMIN_DASHBOARD,
        sellers_data=sellers_data,
        all_sellers=sellers,
        seller_filter=seller_filter,
        shop1_total=shop1_total,
        shop2_total=shop2_total,
        total_commissions=total_commissions,
        total_expenses=total_expenses,
        total_petty_deposits=total_petty_deposits,
        petty_deposits=petty_deposits,
        expenses=expenses,
        estimated_gross_profit=estimated_gross_profit,
        cheques=cheques,
        pending_cheques_count=len(pending_cheques),
        pending_cheques_total=pending_cheques_total,
        all_inventory=all_inventory,
        low_stock_count=low_stock_count,
        months=PERSIAN_MONTHS,
        selected_month=selected_month,
        selected_month_name=PERSIAN_MONTHS[selected_month],
        current_year=now_j.year,
        shops=shops,
        all_categories=all_categories,
        chart_sellers_labels=chart_sellers_labels,
        chart_sellers_data=chart_sellers_data,
        chart_category_labels=chart_category_labels,
        chart_category_data=chart_category_data,
        all_invoices=all_invoices,
        search_query=search_query,
        settings=settings,
        logs=logs
    )

@app.route('/admin/commission/<int:user_id>', methods=['POST'])
def update_commission(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    user = User.query.get_or_404(user_id)
    month = request.form.get('month', 1)
    rate = float(request.form.get('commission_rate', 1.0))
    if 0.01 <= rate <= 5.0:
        user.commission_rate = round(rate, 2)
        db.session.commit()
        log_activity(f"تغییر درصد پایه {user.full_name} به {user.commission_rate}%", session.get('full_name'))
        flash(f'درصد پایه {user.full_name} به {user.commission_rate}% تغییر یافت.', 'success')
    return redirect(url_for('admin_dashboard', month=month))

@app.route('/admin/user/set_password/<int:user_id>', methods=['POST'])
def set_custom_password(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    user = User.query.get_or_404(user_id)
    user.set_password(request.form.get('new_password'))
    db.session.commit()
    log_activity(f"تغییر رمز کاربر {user.full_name}", session.get('full_name'))
    flash(f'رمز عبور جدید برای {user.full_name} ثبت شد.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/user/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    user = User.query.get_or_404(user_id)
    user.is_active = False
    db.session.commit()
    log_activity(f"حذف پرسنل {user.full_name}", session.get('full_name'))
    flash(f'پرسنل {user.full_name} با موفقیت حذف گردید.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/invoice/delete/<int:invoice_id>', methods=['POST'])
def delete_invoice(invoice_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    inv = Invoice.query.get_or_404(invoice_id)
    inv_num = inv.invoice_number
    db.session.delete(inv)
    db.session.commit()
    log_activity(f"حذف فاکتور شماره {inv_num}", session.get('full_name'))
    flash(f'فاکتور شماره {inv_num} حذف شد.', 'success')
    return redirect(url_for('admin_dashboard'))

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
    log_activity("به‌روزرسانی پله‌های تارگت پورسانت", session.get('full_name'))
    flash('تنظیمات پله‌های تارگت پورسانت به‌روزرسانی شد.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/user/add', methods=['POST'])
def add_user():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    username = request.form.get('username').strip()
    if User.query.filter_by(username=username).first():
        flash('این نام کاربری تکراری است.', 'error')
        return redirect(url_for('admin_dashboard'))
    new_user = User(
        username=username,
        full_name=request.form.get('full_name'),
        role='seller',
        shop_id=int(request.form.get('shop_id')),
        commission_rate=float(request.form.get('commission_rate', 1.0))
    )
    new_user.set_password(request.form.get('password'))
    db.session.add(new_user)
    db.session.commit()
    log_activity(f"تعریف پرسنل جدید ({new_user.full_name})", session.get('full_name'))
    flash('پرسنل جدید با موفقیت ثبت شد.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/cheque/add', methods=['POST'])
def add_cheque():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    amount = int(request.form.get('amount', '0').replace(',', ''))
    chk = Cheque(
        sayad_number=request.form.get('sayad_number'),
        bank_name=request.form.get('bank_name'),
        customer_name=request.form.get('customer_name'),
        customer_phone=request.form.get('customer_phone'),
        amount=amount,
        due_shamsi_date=request.form.get('due_shamsi_date'),
        shop_id=session.get('shop_id', 1)
    )
    db.session.add(chk)
    db.session.commit()
    log_activity(f"ثبت چک صیادی به مبلغ {chk.amount:,} تومان", session.get('full_name'))
    flash('چک صیادی با موفقیت در دفترچه ثبت شد.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/cheque/status/<int:cheque_id>', methods=['POST'])
def update_cheque_status(cheque_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    chk = Cheque.query.get_or_404(cheque_id)
    chk.status = request.form.get('status')
    db.session.commit()
    flash('وضعیت چک به‌روزرسانی شد.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/inventory/add', methods=['POST'])
def add_inventory_item():
    if 'user_id' not in session or session.get('role') != 'admin':
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
        shop_id=int(request.form.get('shop_id')),
        stock_quantity=int(request.form.get('stock_quantity', 5)),
        min_alert_stock=int(request.form.get('min_alert_stock', 2)),
        buy_price=int(buy_raw) if buy_raw else 0,
        sell_price=int(sell_raw) if sell_raw else 0
    )
    db.session.add(item)
    db.session.commit()
    log_activity(f"افزودن کالای {item.name} در دسته {category_val} به انبار", session.get('full_name'))
    flash(f'کالای {item.name} با موفقیت در انبار ثبت گردید.', 'success')
    return redirect(url_for('admin_dashboard'))

# ویرایش کالا در انبار
@app.route('/admin/inventory/edit/<int:item_id>', methods=['POST'])
def edit_inventory_item(item_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    item = InventoryItem.query.get_or_404(item_id)
    item.name = request.form.get('name')
    item.category = request.form.get('category')
    item.shop_id = int(request.form.get('shop_id'))
    item.stock_quantity = int(request.form.get('stock_quantity', 0))
    item.min_alert_stock = int(request.form.get('min_alert_stock', 2))
    buy_raw = request.form.get('buy_price', '').replace(',', '')
    sell_raw = request.form.get('sell_price', '').replace(',', '')
    item.buy_price = int(buy_raw) if buy_raw else 0
    item.sell_price = int(sell_raw) if sell_raw else 0
    db.session.commit()
    log_activity(f"ویرایش کالای {item.name} در انبار", session.get('full_name'))
    flash(f'اطلاعات کالای {item.name} به‌روزرسانی شد.', 'success')
    return redirect(url_for('admin_dashboard'))

# حذف کالا از انبار
@app.route('/admin/inventory/delete/<int:item_id>', methods=['POST'])
def delete_inventory_item(item_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    item = InventoryItem.query.get_or_404(item_id)
    item_name = item.name
    db.session.delete(item)
    db.session.commit()
    log_activity(f"حذف کالای {item_name} از انبار", session.get('full_name'))
    flash(f'کالای {item_name} از انبار حذف گردید.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/backup')
def download_backup():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    now_str = jdatetime.datetime.now().strftime("%Y%m%d_%H%M")
    log_activity("دانلود فایل بکاپ دیتابیس", session.get('full_name'))
    return send_file(db_path, as_attachment=True, download_name=f"Backup_Tahmasebi_{now_str}.db")

@app.route('/admin/export/excel')
def export_excel():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    now_j = jdatetime.datetime.now()
    month = request.args.get('month', default=now_j.month, type=int)
    month_name = PERSIAN_MONTHS[month]
    settings = Settings.query.first()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"پورسانت {month_name}"
    ws.views.sheetView[0].rightToLeft = True

    headers = ['نام پرسنل', 'شعبه طهماسبی', 'تعداد اسناد', 'فروش خالص (تومان)', 'درصد پایه', 'درصد با پله تارگت', 'مبلغ پورسانت (تومان)']
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
        s_stats = calculate_seller_exact_stats(s.id, now_j.year, month, s.commission_rate, settings)
        ws.append([s.full_name, s.shop.name, s_stats['sales_count'], s_stats['net_sales'], f"{s.commission_rate}%", f"{s_stats['effective_rate']}%", s_stats['commission_amount']])

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 5, 14)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"Tahmasebi_Report_{month_name}_{now_j.year}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

with app.app_context():
    db.create_all()
    
    for cat_name in DEFAULT_CATEGORIES:
        if not Category.query.filter_by(name=cat_name).first():
            db.session.add(Category(name=cat_name))
    db.session.commit()
    
    if not Settings.query.first():
        db.session.add(Settings())
        db.session.commit()
        
    if not Shop.query.first():
        shop1 = Shop(name='فروشگاه طهماسبی - شعبه ۱ (مرکزی)')
        shop2 = Shop(name='فروشگاه طهماسبی - شعبه ۲')
        db.session.add_all([shop1, shop2])
        db.session.commit()

        admin = User(username='admin', full_name='مدیریت کل (طهماسبی)', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)

        u1 = User(username='naqdi', full_name='خانم نقدی', role='seller', shop_id=shop1.id, commission_rate=1.0)
        u1.set_password('123456')
        u2 = User(username='amiri', full_name='خانم امیری', role='seller', shop_id=shop1.id, commission_rate=1.0)
        u2.set_password('123456')
        u3 = User(username='bidrigh', full_name='خانم بیدریغ', role='seller', shop_id=shop2.id, commission_rate=1.2)
        u3.set_password('123456')
        u4 = User(username='hajilou', full_name='خانم حاجیلو', role='seller', shop_id=shop2.id, commission_rate=0.8)
        u4.set_password('123456')
        u5 = User(username='zamani', full_name='ابوالفضل زمانی', role='seller', shop_id=shop1.id, commission_rate=5.0)
        u5.set_password('123456')
        db.session.add_all([u1, u2, u3, u4, u5])
        db.session.commit()

        items = [
            InventoryItem(name='هود داتیس مدل 522 مخفی', category='هود', shop_id=shop1.id, stock_quantity=1, min_alert_stock=2, buy_price=6500000, sell_price=8900000),
            InventoryItem(name='گاز 5 شعله اخوان مدل GI-135', category='گاز صفحه‌ای', shop_id=shop1.id, stock_quantity=6, min_alert_stock=2, buy_price=7200000, sell_price=9800000),
            InventoryItem(name='سینک گرانیتی فونیکس دو لگن', category='سینک', shop_id=shop2.id, stock_quantity=4, min_alert_stock=2, buy_price=5400000, sell_price=7500000),
            InventoryItem(name='روشویی کابینتی ضدآب فول‌ست', category='روشویی کابینتی', shop_id=shop2.id, stock_quantity=1, min_alert_stock=2, buy_price=4200000, sell_price=6800000)
        ]
        db.session.add_all(items)
        db.session.commit()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
