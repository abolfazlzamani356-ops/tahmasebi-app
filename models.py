from datetime import datetime
import json
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Tenant(db.Model):
    """مدل چندفروشگاهی / مشترکین پلتفرم (SaaS Multi-Tenancy)"""
    __tablename__ = 'tenants'
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True) # مثلا tahmasebi یا alborz-store
    name = db.Column(db.String(150), nullable=False) # نام رسمی فروشگاه
    owner_name = db.Column(db.String(120), nullable=False) # نام مدیر / مالک
    owner_phone = db.Column(db.String(30), nullable=False, index=True) # شماره همراه مدیر
    owner_email = db.Column(db.String(120), nullable=True)
    
    # پلن و وضعیت اشتراک
    plan_tier = db.Column(db.String(30), default='trial') # trial, silver, gold, enterprise
    status = db.Column(db.String(30), default='active') # active, expired, suspended, pending
    is_master = db.Column(db.Boolean, default=False) # آیا فروشگاه اصلی پلتفرم (طهماسبی) است؟
    
    # محدودیت‌ها
    max_shops = db.Column(db.Integer, default=2) # حداکثر شعب مجاز
    max_users = db.Column(db.Integer, default=5) # حداکثر پرسنل مجاز
    
    # تاریخ‌ها
    trial_ends_at = db.Column(db.DateTime, nullable=True) # پایان دوره آزمایشی رایگان
    subscription_ends_at = db.Column(db.DateTime, nullable=True) # پایان دوره اشتراک
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # ارتباطات
    shops = db.relationship('Shop', backref='tenant', lazy=True)
    users = db.relationship('User', backref='tenant', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'slug': self.slug,
            'name': self.name,
            'owner_name': self.owner_name,
            'owner_phone': self.owner_phone,
            'plan_tier': self.plan_tier,
            'status': self.status,
            'is_master': self.is_master,
            'max_shops': self.max_shops,
            'max_users': self.max_users
        }

class Shop(db.Model):
    __tablename__ = 'shops'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, default=1)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    rent_amount = db.Column(db.BigInteger, default=0) # اجاره ماهانه شعبه (تومان)
    
    users = db.relationship('User', backref='shop', lazy=True)
    invoices = db.relationship('Invoice', backref='shop', lazy=True)
    expenses = db.relationship('Expense', backref='shop', lazy=True)
    petty_deposits = db.relationship('PettyCashDeposit', backref='shop', lazy=True)
    inventory_items = db.relationship('InventoryItem', backref='shop', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'address': self.address,
            'rent_amount': self.rent_amount or 0
        }

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    icon = db.Column(db.String(50), default='📦')

class ProductCatalog(db.Model):
    """کاتالوگ مرجع و لیست قیمت پایه کالاها (بدون وابستگی به انبار و تعداد)"""
    __tablename__ = 'product_catalog'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=True, unique=True) # کد محصول یا بارکد
    barcode = db.Column(db.String(50), nullable=True, index=True) # بارکد استاندارد کالا
    name = db.Column(db.String(150), nullable=False) # نام کامل کالا
    category = db.Column(db.String(100), nullable=False) # دسته (هود، گاز، سینک و...)
    brand = db.Column(db.String(100), nullable=True) # برند
    buy_price = db.Column(db.BigInteger, default=0, nullable=False) # قیمت خرید مرجع (تومان)
    sell_price = db.Column(db.BigInteger, default=0, nullable=False) # قیمت فروش مصوب (تومان)
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code or '',
            'barcode': self.barcode or '',
            'name': self.name,
            'category': self.category,
            'brand': self.brand or '',
            'buy_price': self.buy_price,
            'sell_price': self.sell_price,
            'profit_margin': self.sell_price - self.buy_price
        }

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(250), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(30), default='seller') # 'admin', 'seller', 'cashier', 'accountant'
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, default=1)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=True)
    commission_rate = db.Column(db.Float, default=1.0) # درصد پورسانت پایه
    base_salary = db.Column(db.BigInteger, default=0) # حقوق پایه ثابت ماهانه
    phone = db.Column(db.String(20), nullable=True)
    card_number = db.Column(db.String(30), nullable=True)
    can_manage_inventory = db.Column(db.Boolean, default=False) # دسترسی ویژه ادمین انبار و کاتالوگ
    avatar = db.Column(db.String(255), nullable=True) # نام فایل عکس پرسنلی در uploads/avatars
    avatar_data = db.Column(db.Text, nullable=True) # ذخیره مستقیم بیس۶۴ تصویر در دیتابیس جهت تضمین قطعی نمایش ابری
    national_id = db.Column(db.String(20), nullable=True) # کد ملی ۱۰ رقمی
    birth_date = db.Column(db.String(30), nullable=True) # تاریخ تولد شمسی
    start_date = db.Column(db.String(30), nullable=True) # تاریخ شروع به کار / استخدام
    emergency_phone = db.Column(db.String(30), nullable=True) # شماره تماس اضطراری
    sheba_number = db.Column(db.String(50), nullable=True) # شماره شبا بانکی
    address = db.Column(db.String(255), nullable=True) # نشانی محل سکونت
    notes = db.Column(db.Text, nullable=True) # یادداشت‌ها و سوابق پرسنلی
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Settings(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    tier1_min = db.Column(db.BigInteger, default=1_000_000_000) # تارگت پله ۱
    tier1_bonus = db.Column(db.Float, default=0.25)             # پاداش پله ۱ درصد
    tier2_min = db.Column(db.BigInteger, default=2_000_000_000) # تارگت پله ۲
    tier2_bonus = db.Column(db.Float, default=0.50)             # پاداش پله ۲ درصد
    store_name = db.Column(db.String(150), default='مجموعه فروشگاه‌های تخصصی طهماسبی')
    store_slogan = db.Column(db.String(255), default='تجهیزات مدرن ساختمانی و شیرآلات بهداشتی لوکس')
    store_phone = db.Column(db.String(50), default='021-12345678')
    store_address = db.Column(db.String(255), default='کرج، میدان آزادگان، بلوار مطهری')
    store_instagram = db.Column(db.String(100), default='@tahmasebistore')
    store_website = db.Column(db.String(100), default='tahmasebistore.ir')
    store_logo_data = db.Column(db.Text, nullable=True) # لوگو یا مهر فروشگاه به صورت بیس۶۴
    store_warranty_text = db.Column(db.Text, default='کلیه اقلام دارای گارانتی اصالت کالا و ۱۰ روز مهلت تست فنی می‌باشند.')
    default_invoice_prefix = db.Column(db.String(20), default='INV')
    invoice_footer_note = db.Column(db.Text, default='از حسن انتخاب شما سپاسگزاریم. کلیه اقلام دارای گارانتی اصالت کالا می‌باشند.')
    sms_api_key = db.Column(db.String(255), default='mDVL1257srjKMnY7X9Yj87Y1ssazFsEncwDtt3kMF9NtAcBa')
    sms_template_id = db.Column(db.String(50), default='355952')
    sms_enabled = db.Column(db.Boolean, default=True)
    public_domain = db.Column(db.String(100), default='tahmasebistore.ir')
    gemini_api_key = db.Column(db.String(255), nullable=True) # کلید API گوگل هوش مصنوعی (Google AI Studio)
    gemini_model = db.Column(db.String(50), default='gemini-3.8-flash') # مدل پیش‌فرض هوش مصنوعی (Gemini 3.8 Flash)
    gemini_base_url = db.Column(db.String(255), default='https://tahmasebi-app.onrender.com/api/ai/proxy') # آدرس پایه API یا ریورس پروکسی گذر از تحریم لیارا


class BankAccount(db.Model):
    __tablename__ = 'bank_accounts'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False) # مثلا: کارت اصلی طهماسبی
    bank_name = db.Column(db.String(100), nullable=False) # مثلا: بانک ملی
    account_owner = db.Column(db.String(120), nullable=False) # بنام: حاج ابوالفضل طهماسبی
    account_type = db.Column(db.String(30), default='card') # card, sheba, both
    card_number = db.Column(db.String(50), nullable=True) # 6037...
    sheba_number = db.Column(db.String(60), nullable=True) # IR...
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'bank_name': self.bank_name,
            'account_owner': self.account_owner,
            'account_type': self.account_type,
            'card_number': self.card_number or '',
            'sheba_number': self.sheba_number or ''
        }

class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), unique=True, nullable=True)
    address = db.Column(db.String(255), nullable=True)
    customer_type = db.Column(db.String(30), default='regular') # regular, vip, builder, partner
    credit_limit = db.Column(db.BigInteger, default=50_000_000) # سقف اعتبار نسیه
    total_purchases = db.Column(db.BigInteger, default=0) # جمع کل خریدها
    outstanding_balance = db.Column(db.BigInteger, default=0) # مانده بدهی دفتری
    ai_credit_score = db.Column(db.Integer, default=100) # امتیاز اعتباری هوشمند (0 تا 100)
    ai_risk_tier = db.Column(db.String(20), default='A') # سطح ریسک هوش مصنوعی: A+, A, B, C
    ai_risk_summary = db.Column(db.Text, nullable=True) # خلاصه تحلیل اعتباری هوش مصنوعی
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    invoices = db.relationship('Invoice', backref='customer', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone or '',
            'address': self.address or '',
            'customer_type': self.customer_type or 'regular',
            'credit_limit': self.credit_limit or 0,
            'total_purchases': self.total_purchases or 0,
            'outstanding_balance': self.outstanding_balance or 0,
            'ai_credit_score': self.ai_credit_score or 100,
            'ai_risk_tier': self.ai_risk_tier or 'A',
            'ai_risk_summary': self.ai_risk_summary or ''
        }

class InventoryItem(db.Model):
    __tablename__ = 'inventory_items'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=True)
    barcode = db.Column(db.String(50), nullable=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    brand = db.Column(db.String(100), nullable=True) # مثلا اخوان، داتیس، فونیکس
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    stock_quantity = db.Column(db.Integer, default=0) # موجودی فیزیکی واقعی
    min_alert_stock = db.Column(db.Integer, default=2) # حداقل موجودی هشدار کسری
    buy_price = db.Column(db.BigInteger, default=0) # بهای تمام شده خرید (تومان)
    sell_price = db.Column(db.BigInteger, default=0) # قیمت فروش رسمی (تومان)
    location_in_store = db.Column(db.String(100), nullable=True) # قفسه یا ردیف انبار

    stock_logs = db.relationship('StockLog', backref='item', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, include_buy_price=True):
        return {
            'id': self.id,
            'code': self.code or '',
            'barcode': self.barcode or '',
            'name': self.name,
            'category': self.category,
            'brand': self.brand or '',
            'shop_id': self.shop_id,
            'shop_name': self.shop.name if self.shop else '',
            'stock_quantity': self.stock_quantity,
            'min_alert_stock': self.min_alert_stock,
            'buy_price': self.buy_price if include_buy_price else 0,
            'sell_price': self.sell_price,
            'is_low_stock': self.stock_quantity <= self.min_alert_stock
        }

class StockLog(db.Model):
    __tablename__ = 'stock_logs'
    id = db.Column(db.Integer, primary_key=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_items.id'), nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    change_type = db.Column(db.String(40), nullable=False) # sale, return, purchase_in, transfer_in, transfer_out, adjustment
    quantity_changed = db.Column(db.Integer, nullable=False) # مثلا -2 یا +5
    stock_after = db.Column(db.Integer, nullable=False)
    reference_id = db.Column(db.String(100), nullable=True) # شماره فاکتور یا کد سند
    description = db.Column(db.String(255), nullable=True)
    user_name = db.Column(db.String(100), nullable=False)
    shamsi_date_time = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class StockTransfer(db.Model):
    __tablename__ = 'stock_transfers'
    id = db.Column(db.Integer, primary_key=True)
    inventory_item_id = db.Column(db.Integer, nullable=True)
    item_name = db.Column(db.String(150), nullable=False)
    from_shop_id = db.Column(db.Integer, nullable=False)
    to_shop_id = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, default=1)
    status = db.Column(db.String(30), default='pending') # pending, accepted, rejected
    requested_by = db.Column(db.String(100), nullable=False)
    shamsi_date_time = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Invoice(db.Model):
    __tablename__ = 'invoices'
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), nullable=False, unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    customer_name = db.Column(db.String(120), nullable=False)
    customer_phone = db.Column(db.String(30), nullable=True)
    
    status = db.Column(db.String(20), default='final') # final, proforma, canceled
    invoice_type = db.Column(db.String(20), default='sale') # sale, return
    return_reason = db.Column(db.String(150), nullable=True)
    proforma_valid_until = db.Column(db.String(30), nullable=True)
    
    # مبالغ و حسابداری واقعی
    subtotal_amount = db.Column(db.BigInteger, default=0) # جمع ناخالص
    discount_amount = db.Column(db.BigInteger, default=0) # تخفیف کل
    total_amount = db.Column(db.BigInteger, nullable=False) # مبلغ نهایی فاکتور
    actual_buy_cost = db.Column(db.BigInteger, default=0) # بهای تمام شده واقعی بر اساس اقلام انبار
    real_profit = db.Column(db.BigInteger, default=0) # سود واقعی = total_amount - actual_buy_cost
    
    # نحوه تسویه و وضعیت مانده (پشتیبانی کامل از پرداخت ترکیبی چندگانه)
    payment_method = db.Column(db.String(50), default='mixed') # mixed, pos, card_to_card, cash, deposit, cheque
    paid_pos = db.Column(db.BigInteger, default=0) # مبلغ کارتخوان
    paid_card = db.Column(db.BigInteger, default=0) # مبلغ کارت به کارت
    paid_cash = db.Column(db.BigInteger, default=0) # مبلغ نقد دریافتی
    paid_cheque = db.Column(db.BigInteger, default=0) # مبلغ کل چک‌های صیادی
    remaining_balance = db.Column(db.BigInteger, default=0) # مانده بدهی / تسویه نشده
    paid_amount = db.Column(db.BigInteger, default=0) # جمع کل پرداخت‌های نقد/کارت/واریز
    
    due_settlement_date = db.Column(db.String(30), nullable=True) # موعد تسویه مانده
    is_settled = db.Column(db.Boolean, default=True) # آیا کاملا تسویه شده
    
    # فیلدهای تکمیلی کارت به کارت، شبا و پیگیری
    dest_card_number = db.Column(db.String(50), nullable=True)
    dest_sheba_number = db.Column(db.String(60), nullable=True)
    payment_tracking_code = db.Column(db.String(50), nullable=True)
    
    # فروشندگان و تسهیم
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    second_seller_id = db.Column(db.Integer, nullable=True)
    split_ratio = db.Column(db.Integer, default=100) # سهم فروشنده اصلی درصد
    customer_rating = db.Column(db.Integer, default=5)
    
    items_desc = db.Column(db.Text, nullable=True) # خلاصه توضیحات متنی
    categories_json = db.Column(db.Text, default='[]')
    
    # تاریخ و شعبه
    shamsi_year = db.Column(db.Integer, nullable=False)
    shamsi_month = db.Column(db.Integer, nullable=False)
    shamsi_day = db.Column(db.Integer, nullable=True)
    shamsi_date_time = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    has_custom_items = db.Column(db.Boolean, default=False, index=True) # آیا فاکتور دارای اقلام سفارشی/خارج از کاتالوگ است
    sms_sent = db.Column(db.Boolean, default=False) # آیا پیامک گارانتی ارسال شده است
    sms_sent_at = db.Column(db.String(40), nullable=True) # زمان ارسال پیامک
    paper_invoice_image = db.Column(db.String(255), nullable=True) # نام فایل عکس فاکتور کاغذی/دفتری
    ai_audit_flags = db.Column(db.Text, nullable=True) # هشدارهای ممیزی و مغایرت هوش مصنوعی
    seller = db.relationship('User', foreign_keys=[seller_id])
    
    items = db.relationship('InvoiceItem', backref='invoice', lazy=True, cascade='all, delete-orphan')
    cheques = db.relationship('Cheque', backref='invoice', lazy=True, cascade='all, delete-orphan')

class InvoiceItem(db.Model):
    __tablename__ = 'invoice_items'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_items.id'), nullable=True)
    item_name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(100), nullable=True)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    unit_buy_price = db.Column(db.BigInteger, default=0) # قیمت خرید واحد در زمان صدور
    unit_sell_price = db.Column(db.BigInteger, default=0) # قیمت فروش واحد
    discount = db.Column(db.BigInteger, default=0) # تخفیف ردیف
    total_price = db.Column(db.BigInteger, nullable=False) # جمع ردیف = (unit_sell_price * quantity) - discount
    row_profit = db.Column(db.BigInteger, default=0) # سود ردیف = total_price - (unit_buy_price * quantity)
    is_custom = db.Column(db.Boolean, default=False) # آیا کالا سفارشی یا خارج از انبار/کاتالوگ است

    inventory_item = db.relationship('InventoryItem', foreign_keys=[inventory_item_id])

class Cheque(db.Model):
    __tablename__ = 'cheques'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=True)
    sayad_number = db.Column(db.String(50), nullable=False) # شناسه ۱۶ رقمی صیاد
    bank_name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)
    due_shamsi_date = db.Column(db.String(30), nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(30), nullable=True)
    shop_id = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), default='pending') # pending (در انتظار), passed (وصول شده), bounced (برگشت خورده), assigned (واگذار شده)
    passed_shamsi_date = db.Column(db.String(30), nullable=True)
    payee_name = db.Column(db.String(100), nullable=True) # تحویل گیرنده / واگذار شده به
    notes = db.Column(db.String(255), nullable=True) # یادداشت چک
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SalarySlip(db.Model):
    __tablename__ = 'salary_slips'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    shamsi_year = db.Column(db.Integer, nullable=False)
    shamsi_month = db.Column(db.Integer, nullable=False)
    base_salary = db.Column(db.BigInteger, default=0) # حقوق پایه
    net_sales = db.Column(db.BigInteger, default=0) # کل فروش ماه
    effective_rate = db.Column(db.Float, default=1.0) # درصد پورسانت
    commission_amount = db.Column(db.BigInteger, default=0) # مبلغ پورسانت قطعی
    tier_bonus_amount = db.Column(db.BigInteger, default=0) # پاداش تارگت پله‌ای
    advances_deduction = db.Column(db.BigInteger, default=0) # کسر مساعده
    other_bonuses = db.Column(db.BigInteger, default=0) # سایر پاداش‌ها
    other_deductions = db.Column(db.BigInteger, default=0) # سایر کسورات/جریمه
    final_payable = db.Column(db.BigInteger, default=0) # خالص دریافتی پرسنل
    is_paid = db.Column(db.Boolean, default=False) # پرداخت شده
    paid_date = db.Column(db.String(40), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])

class PettyCashDeposit(db.Model):
    __tablename__ = 'petty_cash_deposits'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    shamsi_year = db.Column(db.Integer, nullable=False)
    shamsi_month = db.Column(db.Integer, nullable=False)
    shamsi_date_time = db.Column(db.String(40), nullable=False)
    created_by = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)
    category = db.Column(db.String(50), default='متفرقه') # کرایه وانت، نصاب، پذیرایی، متفرقه
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    shamsi_year = db.Column(db.Integer, nullable=False)
    shamsi_month = db.Column(db.Integer, nullable=False)
    shamsi_date_time = db.Column(db.String(40), nullable=False)
    created_by = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(255), nullable=False)
    user_name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), default='عمومی') # فروش، انبار، حقوق، امنیت
    ip_address = db.Column(db.String(50), nullable=True) # آدرس IP کاربر جهت امنیت
    details = db.Column(db.Text, nullable=True) # جزئیات تکمیلی لاگ
    shamsi_date_time = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CustomWorkshopOrder(db.Model):
    """مدل سفارشات ساخت کارگاهی کابینت، روشویی، آینه و باکس سفارشی فروشگاه طهماسبی"""
    __tablename__ = 'custom_workshop_orders'
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False, index=True) # e.g. ORD-1405-0101
    
    # اطلاعات فروشنده و شعبه
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    
    # اطلاعات مشتری
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    customer_name = db.Column(db.String(120), nullable=False) # مثلا آقای رضوی
    customer_phone = db.Column(db.String(30), nullable=True)
    
    # اطلاعات فنی محصول سفارشی
    product_type = db.Column(db.String(60), nullable=False, default='کابین روشویی') # کابین روشویی، باکس، آینه، ست کامل، کابین توکار، کابین سرامیکی، متفرقه
    model_name = db.Column(db.String(100), nullable=True) # مثلا آرشام، آندره، هلیا، ماربل، دایمون، بلوا
    quantity = db.Column(db.Integer, default=1, nullable=False) # تعداد سفارش ساخت (پیش‌فرض ۱)
    
    # ابعاد دقیق (سانتی‌متر)
    width = db.Column(db.Integer, nullable=True) # طول / عرض مثلا ۶۰
    depth = db.Column(db.Integer, nullable=True) # عمق مثلا ۴۰
    height = db.Column(db.Integer, nullable=True) # ارتفاع مثلا ۴۰ یا ۶۰
    dimensions_text = db.Column(db.String(100), nullable=True) # مثلا "۶۰×۴۰ ارتفاع ۶۰"
    
    # مشخصات رنگ و متریال
    body_color = db.Column(db.String(80), nullable=True) # مثلا سفید، طوسی بتن، مشکی، گرین راش
    door_color = db.Column(db.String(80), nullable=True) # مثلا سفید استپ، طوسی بتن، سرمه‌ای
    sheet_thickness = db.Column(db.String(60), default='ورق ۱۶ میل PVC ضدآب') # ورق ۱۶ میل، ورق ۱۲ میل، سرامیک
    hinge_type = db.Column(db.String(80), default='لولای تمام استیل آرام‌بند') # لولای تمام استیل، آرام‌بند، مگنتی
    door_drawer_config = db.Column(db.String(100), nullable=True) # مثلا ۲ درب، ۲ کشو، درب و کشو، درب بغل بازشو
    
    # ملحقات (آینه، باکس، سنگ)
    mirror_details = db.Column(db.String(150), nullable=True) # مثلا آینه ۴۰×۶۰ عمودی، آینه گرد ۶۰، بک‌لایت تاچ
    box_details = db.Column(db.String(150), nullable=True) # مثلا باکس همراه ۴۰×۳۰، بدنه سفید درب طوسی بتن
    sink_type = db.Column(db.String(100), nullable=True) # کاسه روکار، سنگ توکار، بدون سنگ، سنگ سرامیکی
    
    # وضعیت و اولویت
    status = db.Column(db.String(30), default='pending', index=True) # pending, approved, in_production, ready, delivered, cancelled
    priority = db.Column(db.String(20), default='normal') # normal, urgent, emergency
    
    # زمان‌بندی
    promised_delivery_date = db.Column(db.String(40), nullable=True) # تاریخ تعهد تحویل به مشتری (شمسی مثلا ۱۴۰۵/۰۷/۰۹)
    shamsi_date = db.Column(db.String(40), nullable=False) # تاریخ ثبت سفارش
    shamsi_year = db.Column(db.Integer, nullable=False)
    shamsi_month = db.Column(db.Integer, nullable=False)
    delivered_at = db.Column(db.String(40), nullable=True) # تاریخ واقعی تحویل
    
    # تصاویر نمونه و نقشه (تا ۳ عکس، فایل یا base64)
    image_1 = db.Column(db.Text, nullable=True) # عکس نمونه روبیکا / طرح
    image_2 = db.Column(db.Text, nullable=True) # عکس نقشه یا کروکی
    image_3 = db.Column(db.Text, nullable=True) # عکس تکمیلی
    
    # یادداشت‌های کارگاهی و حساس
    special_notes = db.Column(db.Text, nullable=True) # نکات حساس ساخت
    assigned_worker = db.Column(db.String(100), nullable=True) # استادکار / مسئول کارگاه (مثلا آقای حسینی)
    admin_notes = db.Column(db.Text, nullable=True) # یادداشت داخلی مدیریت
    
    # مالی (اختیاری یا متصل به فاکتور)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=True)
    estimated_cost = db.Column(db.BigInteger, default=0) # بهای ساخت برآوردی کارگاه (تومان)
    customer_price = db.Column(db.BigInteger, default=0) # قیمت اعلام شده به مشتری (تومان)
    prepaid_amount = db.Column(db.BigInteger, default=0) # بیعانه دریافتی
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # ارتباطات
    seller = db.relationship('User', foreign_keys=[seller_id], backref='custom_orders')
    shop = db.relationship('Shop', foreign_keys=[shop_id])
    customer = db.relationship('Customer', foreign_keys=[customer_id])
    invoice = db.relationship('Invoice', foreign_keys=[invoice_id])

    def to_dict(self):
        dim_str = self.dimensions_text
        if not dim_str and (self.width or self.depth or self.height):
            parts = []
            if self.width: parts.append(f"عرض {self.width}")
            if self.depth: parts.append(f"عمق {self.depth}")
            if self.height: parts.append(f"ارتفاع {self.height}")
            dim_str = " × ".join(parts)
            
        return {
            'id': self.id,
            'order_number': self.order_number,
            'seller_id': self.seller_id,
            'seller_name': self.seller.full_name if self.seller else '',
            'shop_id': self.shop_id,
            'shop_name': self.shop.name if self.shop else '',
            'customer_name': self.customer_name,
            'customer_phone': self.customer_phone or '',
            'product_type': self.product_type,
            'model_name': self.model_name or '',
            'quantity': self.quantity if self.quantity is not None else 1,
            'dimensions_text': dim_str or '',
            'body_color': self.body_color or '',
            'door_color': self.door_color or '',
            'sheet_thickness': self.sheet_thickness or '',
            'hinge_type': self.hinge_type or '',
            'door_drawer_config': self.door_drawer_config or '',
            'mirror_details': self.mirror_details or '',
            'box_details': self.box_details or '',
            'sink_type': self.sink_type or '',
            'status': self.status,
            'priority': self.priority,
            'promised_delivery_date': self.promised_delivery_date or '',
            'shamsi_date': self.shamsi_date,
            'special_notes': self.special_notes or '',
            'assigned_worker': self.assigned_worker or '',
            'admin_notes': self.admin_notes or '',
            'estimated_cost': self.estimated_cost or 0,
            'customer_price': self.customer_price or 0,
            'prepaid_amount': self.prepaid_amount or 0,
            'remaining_balance': (self.customer_price or 0) - (self.prepaid_amount or 0),
            'width': self.width or 0,
            'depth': self.depth or 0,
            'height': self.height or 0,
            'image_1': self.image_1 or '',
            'image_2': self.image_2 or '',
            'image_3': self.image_3 or '',
            'has_image': bool(self.image_1 or self.image_2 or self.image_3)
        }
