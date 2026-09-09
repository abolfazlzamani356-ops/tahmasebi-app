from datetime import datetime
import json
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Shop(db.Model):
    __tablename__ = 'shops'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    
    users = db.relationship('User', backref='shop', lazy=True)
    invoices = db.relationship('Invoice', backref='shop', lazy=True)
    expenses = db.relationship('Expense', backref='shop', lazy=True)
    petty_deposits = db.relationship('PettyCashDeposit', backref='shop', lazy=True)
    inventory_items = db.relationship('InventoryItem', backref='shop', lazy=True)

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'phone': self.phone, 'address': self.address}

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    icon = db.Column(db.String(50), default='📦')

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(250), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(30), default='seller') # 'admin', 'seller', 'cashier', 'accountant'
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=True)
    commission_rate = db.Column(db.Float, default=1.0) # درصد پورسانت پایه
    base_salary = db.Column(db.BigInteger, default=0) # حقوق پایه ثابت ماهانه
    phone = db.Column(db.String(20), nullable=True)
    card_number = db.Column(db.String(30), nullable=True)
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
    store_phone = db.Column(db.String(50), default='021-12345678')
    store_warranty_text = db.Column(db.Text, default='کلیه اقلام دارای گارانتی اصالت کالا و ۱۰ روز مهلت تست فنی می‌باشند.')

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    invoices = db.relationship('Invoice', backref='customer', lazy=True)

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

    def to_dict(self):
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
            'buy_price': self.buy_price,
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
    status = db.Column(db.String(30), default='pending') # pending (در انتظار), passed (وصول شده), bounced (برگشت خورده)
    passed_shamsi_date = db.Column(db.String(30), nullable=True)
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
    shamsi_date_time = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
