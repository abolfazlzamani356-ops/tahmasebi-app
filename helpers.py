import re
import json
import jdatetime
from datetime import datetime
from sqlalchemy import or_, and_
from sqlalchemy.orm import selectinload
from models import (
    db, User, Invoice, InvoiceItem, InventoryItem, StockLog, AuditLog,
    Settings, SalarySlip, Customer, Cheque, ProductCatalog,
    Shop, Expense, PettyCashDeposit
)

PERSIAN_MONTHS = {
    1: 'فروردین', 2: 'اردیبهشت', 3: 'خرداد',
    4: 'تیر', 5: 'مرداد', 6: 'شهریور',
    7: 'مهر', 8: 'آبان', 9: 'آذر',
    10: 'دی', 11: 'بهمن', 12: 'اسفند'
}

DEFAULT_CATEGORIES = [
    'هود', 'سینک', 'گاز صفحه‌ای', 'شیرآلات', 'شیرآلات توکار',
    'فر توکار', 'مایکروویو',
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

def normalize_persian_text(text, unify_alif=False):
    """
    نرمال‌سازی پیشرفته و جامع متون فارسی و عربی جهت جستجوی بدون خطای کاتالوگ، انبار و مشتریان
    """
    if not text:
        return ''
    s = str(text)
    # اصلاح ی و ک عربی و الف مقصوره به فارسی
    s = s.replace('ي', 'ی').replace('ك', 'ک').replace('ى', 'ی')
    # اصلاح انواع ه و ة
    s = s.replace('ة', 'ه').replace('ۀ', 'ه')
    # حذف اعراب و تشدیدهای عربی
    s = re.sub(r'[\u064b-\u065f\u0670]', '', s)
    # یکنواخت‌سازی نیم‌فاصله و حذف کاراکترهای نامرئی
    s = s.replace('\u200c', ' ').replace('\u200e', '').replace('\u200f', '').replace('\ufeff', '')
    # تبدیل ارقام فارسی و عربی به انگلیسی
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    arabic_digits = '٠١٢٣٤٥٦٧٨٩'
    for i in range(10):
        s = s.replace(persian_digits[i], str(i)).replace(arabic_digits[i], str(i))
    if unify_alif:
        s = s.replace('آ', 'ا').replace('أ', 'ا').replace('إ', 'ا')
    # حذف فاصله‌های متوالی
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

def get_persian_word_variants(word):
    """
    تولید انواع شکل‌های املایی کلمه (با کلاه و بدون کلاه، ی عربی/فارسی، ک عربی/فارسی، پسوند یی/ی، بدون نیم‌فاصله)
    جهت جستجوی فراگیر و منعطف در دیتابیس
    """
    if not word:
        return []
    base = normalize_persian_text(word)
    if not base:
        return []
    variants = set()
    variants.add(base)
    variants.add(base.lower())
    variants.add(base.upper())
    
    # الف با و بدون کلاه
    alif_unify = base.replace('آ', 'ا').replace('أ', 'ا').replace('إ', 'ا')
    variants.add(alif_unify)
    variants.add(alif_unify.lower())
    if 'ا' in base:
        variants.add(base.replace('ا', 'آ'))
    
    # بدون فاصله و با نیم‌فاصله
    variants.add(base.replace(' ', ''))
    variants.add(base.replace(' ', '\u200c'))
    variants.add(alif_unify.replace(' ', ''))
    variants.add(alif_unify.replace(' ', '\u200c'))
    
    # ریشه‌یابی و حذف پسوندهای رایج فارسی (مثال: ایتالیایی -> ایتالیا و ایتالی)
    for sfx in ['هایی', 'های', 'ها', 'یی', 'ی', 'ان', 'ات']:
        if base.endswith(sfx) and len(base) > len(sfx) + 1:
            stem = base[:-len(sfx)]
            variants.add(stem)
            variants.add(stem.replace('آ', 'ا'))
            if sfx == 'یی':
                variants.add(stem + 'ا')
            if sfx in ['یی', 'ی'] and stem.endswith('ا') and len(stem) > 2:
                variants.add(stem[:-1])
                variants.add(stem[:-1] + 'ی')
    if base.endswith('ا') and len(base) > 2:
        variants.add(base + 'یی')
        variants.add(base + 'ی')
    
    # شکل‌های عربی متناظر (ی/ي و ک/ك و ه/ة) برای انطباق قطعی با دیتابیس در صورت ورود غیرفارسی
    arabic_extras = set()
    for v in list(variants):
        if 'ی' in v:
            arabic_extras.add(v.replace('ی', 'ي'))
        if 'ک' in v:
            arabic_extras.add(v.replace('ک', 'ك'))
        if 'ی' in v and 'ک' in v:
            arabic_extras.add(v.replace('ی', 'ي').replace('ک', 'ك'))
        if 'ه' in v:
            arabic_extras.add(v.replace('ه', 'ة'))
    variants.update(arabic_extras)

    return [v for v in variants if v]

def build_catalog_search_filter(model_cls, search_text):
    """
    ساخت فیلتر کوئری فوق هوشمند چندکلمه‌ای و چندفیلدی با نرمال‌سازی کامل فارسی
    هر کلمه از جستجو باید در حداقل یکی از فیلدهای محصول (نام، برند، دسته، کد، بارکد، توضیحات) پیدا شود.
    """
    if not search_text:
        return None
    raw_tokens = [t.strip() for t in re.split(r'[\s\-_/]+', str(search_text)) if t.strip()]
    if not raw_tokens:
        return None

    token_conditions = []
    for token in raw_tokens:
        variants = get_persian_word_variants(token)
        field_conditions = []
        for var in variants:
            field_conditions.append(model_cls.name.contains(var))
            field_conditions.append(model_cls.brand.contains(var))
            field_conditions.append(model_cls.category.contains(var))
            if hasattr(model_cls, 'code'):
                field_conditions.append(model_cls.code.contains(var))
            if hasattr(model_cls, 'barcode'):
                field_conditions.append(model_cls.barcode.contains(var))
            if hasattr(model_cls, 'description'):
                field_conditions.append(model_cls.description.contains(var))
        if field_conditions:
            token_conditions.append(or_(*field_conditions))

    if not token_conditions:
        return None
    return and_(*token_conditions)

def safe_float(val, default=0.0):
    """
    تبدیل ایمن انواع مقادیر اعشاری (فارسی، عربی، درصدی، کامادار، منفی) به عدد اعشاری بدون خطا
    """
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return default
    is_neg = ('منفی' in s) or ('-' in s) or ('−' in s) or ('–' in s)
    # تبدیل ارقام فارسی و عربی
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    arabic_digits = '٠١٢٣٤٥٦٧٨٩'
    for i in range(10):
        s = s.replace(persian_digits[i], str(i)).replace(arabic_digits[i], str(i))
    s = s.replace('٫', '.').replace(',', '').replace(' ', '').replace('%', '')
    s_clean = s.replace('منفی', '').replace('-', '').replace('−', '').replace('–', '').strip()
    try:
        f = float(s_clean)
        return -abs(f) if is_neg else abs(f)
    except Exception:
        m = re.search(r'\d*\.\d+|\d+', s_clean)
        if m:
            try:
                num = float(m.group(0))
                return -abs(num) if is_neg else abs(num)
            except Exception:
                pass
        return default

def safe_int(val, default=0):
    """
    تبدیل کاملاً ایمن هرگونه ورودی (فارسی، عربی، کامادار، خالی، اعشاری یا نامعتبر) به عدد صحیح بدون خطای صفرسازی یا جابجایی رقم
    """
    if val is None:
        return default
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        try:
            return int(val)
        except Exception:
            return default
    
    s = str(val).strip()
    if not s:
        return default
    
    # بررسی علامت منفی (شامل کلمه منفی فارسی یا علائم منها)
    is_neg = ('منفی' in s) or ('-' in s) or ('−' in s) or ('–' in s)
    
    # تبدیل ارقام فارسی و عربی به انگلیسی
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    arabic_digits = '٠١٢٣٤٥٦٧٨٩'
    for i in range(10):
        s = s.replace(persian_digits[i], str(i)).replace(arabic_digits[i], str(i))
    
    s = s.replace('٫', '.').replace(',', '').replace(' ', '')
    s_clean = s.replace('منفی', '').replace('-', '').replace('−', '').replace('–', '').strip()
    
    # در صورتی که اعشار داشته باشد ابتدا با float پارس شود تا رقم اعشار صفر ضرب نشود
    if '.' in s_clean:
        try:
            m = re.search(r'\d*\.\d+|\d+', s_clean)
            if m:
                num = int(float(m.group(0)))
                return -num if is_neg else num
        except Exception:
            pass
            
    cleaned = re.sub(r'[^\d]', '', s_clean)
    if not cleaned:
        return default
    try:
        num = int(cleaned)
        return -num if is_neg else num
    except Exception:
        return default

def get_current_shamsi():
    now_j = jdatetime.datetime.now()
    return {
        'year': now_j.year,
        'month': now_j.month,
        'day': now_j.day,
        'month_name': PERSIAN_MONTHS.get(now_j.month, ''),
        'full_str': now_j.strftime("%Y/%m/%d - %H:%M:%S"),
        'date_only': now_j.strftime("%Y/%m/%d")
    }

def log_activity(action, user_name="سیستم", category="عمومی", ip_address=None, details=None):
    now_str = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M:%S")
    try:
        from flask import has_request_context, request, session
        if has_request_context():
            if not ip_address:
                ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
                if ip_address and ',' in ip_address:
                    ip_address = ip_address.split(',')[0].strip()
            if user_name in ("سیستم", None):
                user_name = session.get('full_name', 'سیستم')
    except Exception:
        pass
    log = AuditLog(
        action=action,
        user_name=user_name,
        category=category,
        ip_address=ip_address,
        details=details,
        shamsi_date_time=now_str
    )
    db.session.add(log)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

def record_stock_change(item_id, shop_id, change_type, quantity, reference_id, user_name, description="", commit=True):
    item = InventoryItem.query.get(item_id)
    if not item:
        return
    
    item.stock_quantity += quantity # quantity can be negative for sales
    if item.stock_quantity < 0:
        item.stock_quantity = 0
        
    now_str = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M:%S")
    log = StockLog(
        inventory_item_id=item.id,
        shop_id=shop_id,
        change_type=change_type,
        quantity_changed=quantity,
        stock_after=item.stock_quantity,
        reference_id=str(reference_id),
        description=description,
        user_name=user_name or 'سیستم / پرسنل',
        shamsi_date_time=now_str
    )
    db.session.add(log)
    if commit:
        db.session.commit()

def calculate_seller_exact_stats(user_id, year, month, base_commission_rate, settings=None, user=None):
    """
    محاسبه دقیق آمار فروش، پورسانت نقدی، پورسانت معلق، تعداد فاکتورها، مرجوعی‌ها و رضایت مشتری
    *** اصلاح شده: فروش خالص فقط بر اساس مبلغ واقعی تسویه‌شده محاسبه می‌شود ***
    """
    if not settings:
        settings = Settings.query.first()

    year_int = safe_int(year)
    month_int = safe_int(month)
    month_str = str(month_int)
    month_pad = f"{month_int:02d}"

    invoices = Invoice.query.options(selectinload(Invoice.cheques)).filter(
        (Invoice.seller_id == user_id) | (Invoice.second_seller_id == user_id),
        db.or_(Invoice.shamsi_year == year_int, Invoice.shamsi_year == str(year_int)),
        db.or_(Invoice.shamsi_month == month_int, Invoice.shamsi_month == month_str, Invoice.shamsi_month == month_pad),
        Invoice.status == 'final'
    ).all()

    gross_sales = 0      # مبلغ کل فاکتورها (برای نمایش اطلاعاتی)
    returns_amount = 0   # مبلغ کل فاکتورهای مرجوعی
    net_sales = 0        # فروش خالص = فقط مبلغ تسویه‌شده واقعی
    total_cost = 0
    real_profit_share = 0
    sales_count = 0
    returns_count = 0
    ratings = []
    pending_commission_sales = 0  # مبالغ معلق: مانده + چک‌های در انتظار

    for inv in invoices:
        # محاسبه درصد تسهیم فروشنده با بازه امن ۰ تا ۱۰۰
        ratio = 1.0
        if inv.second_seller_id:
            s_ratio = max(0, min(100, inv.split_ratio if inv.split_ratio is not None else 100))
            if inv.seller_id == user_id:
                ratio = s_ratio / 100.0
            else:
                ratio = (100 - s_ratio) / 100.0

        item_total_amount = int((inv.total_amount or 0) * ratio)
        item_cost = int((inv.actual_buy_cost or 0) * ratio)
        item_profit = int((inv.real_profit or 0) * ratio)

        if inv.invoice_type == 'sale':
            gross_sales += item_total_amount  # کل مبلغ فاکتور (اطلاعاتی)

            # === محاسبه مبلغ واقعی تسویه‌شده و چک‌ها ===
            # به درخواست مدیریت: کلیه چک‌های ثبت‌شده (وصول‌شده و در انتظار) در فروش قطعی و پورسانت ماه جاری لحاظ می‌شوند
            # تنها چک‌هایی که وضعیت «برگشت خورده (bounced)» دارند کسر/لحاظ نمی‌شوند
            valid_cheques = sum(chk.amount for chk in inv.cheques if chk.status in ['passed', 'pending', 'assigned'])
            # مانده تسویه‌نشده نسیه یا بیعانه (بدون چک)
            remaining = inv.remaining_balance or 0
            # پرداخت فوری: نقد + کارتخوان + کارت‌به‌کارت
            immediate_paid = max((inv.paid_amount or 0), ((inv.paid_pos or 0) + (inv.paid_card or 0) + (inv.paid_cash or 0)))

            # مبلغ کل فروش نهایی منظور شده = پرداخت نقدی/کارتخوان + چک‌های معتبر
            settled_amount = immediate_paid + valid_cheques
            item_settled = int(settled_amount * ratio)

            # مبلغ منظور شده به فروش خالص و پورسانت فروشنده اضافه می‌شود
            net_sales += item_settled
            total_cost += item_cost
            real_profit_share += item_profit
            sales_count += 1
            if inv.customer_rating:
                ratings.append(inv.customer_rating)

            # مبالغ معلق باقی‌مانده (صرفاً مانده‌های حساب دفتری/نسیه بدون چک)
            pending_this = int(remaining * ratio)
            pending_commission_sales += pending_this

        elif inv.invoice_type == 'return':
            # برای مرجوعی هم مبلغ واقعی برگشتی ملاک است
            valid_cheques = sum(chk.amount for chk in inv.cheques if chk.status in ['passed', 'pending', 'assigned'])
            immediate_paid = max((inv.paid_amount or 0), ((inv.paid_pos or 0) + (inv.paid_card or 0) + (inv.paid_cash or 0)))
            settled_amount = immediate_paid + valid_cheques
            effective_return = abs(settled_amount if settled_amount > 0 else (inv.total_amount or 0))
            item_settled = int(effective_return * ratio)

            net_sales -= item_settled
            returns_amount += item_settled
            total_cost -= item_cost
            real_profit_share -= item_profit
            returns_count += 1

    if user is None:
        user = User.query.get(user_id)
    is_admin = bool(user and user.role == 'admin')
    if is_admin:
        base_commission_rate = 0.0

    net_sales = max(net_sales, 0)

    # محاسبه پاداش تارگت پله‌ای (تنها در صورتی که پرسنل مشمول پورسانت باشد و درصد پایه > 0 باشد)
    bonus = 0.0
    tier_achieved = 0
    has_commission = (not is_admin) and ((base_commission_rate or 0) > 0)
    if settings and has_commission:
        if net_sales >= settings.tier2_min:
            bonus = settings.tier2_bonus
            tier_achieved = 2
        elif net_sales >= settings.tier1_min:
            bonus = settings.tier1_bonus
            tier_achieved = 1

    effective_rate = 0.0 if not has_commission else round(min(base_commission_rate + bonus, 5.0), 2)

    # پورسانت قطعی (فقط روی مبلغ واقعی تسویه‌شده)
    total_commission_calculated = 0 if is_admin else int((net_sales * effective_rate) / 100)
    settled_commission_amount = total_commission_calculated

    # پورسانت معلق (روی مانده‌های تسویه‌نشده + چک‌های در انتظار)
    pending_commission_amount = 0 if is_admin else int((pending_commission_sales * effective_rate) / 100)

    tier_bonus_amount = 0 if is_admin else int((net_sales * bonus) / 100)
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 5.0

    return {
        'gross_sales': gross_sales,
        'returns_amount': returns_amount,
        'net_sales': net_sales,
        'total_cost': total_cost,
        'real_profit_share': real_profit_share,
        'sales_count': sales_count,
        'returns_count': returns_count,
        'base_rate': base_commission_rate,
        'bonus_rate': bonus,
        'tier_achieved': tier_achieved,
        'effective_rate': effective_rate,
        'commission_amount': total_commission_calculated,
        'settled_commission': settled_commission_amount,
        'pending_commission': pending_commission_amount,
        'tier_bonus_amount': tier_bonus_amount,
        'avg_rating': avg_rating
    }

def get_or_create_customer(name, phone=None, address=None, customer_type='regular', shop_id=None, tenant_id=None):
    if not name:
        return None
    name = normalize_persian_text(name).strip()
    if not name:
        name = 'مشتری محترم'
    phone = (phone or '').strip()
    if phone:
        persian_digits = '۰۱۲۳۴۵۶۷۸۹'
        arabic_digits = '٠١٢٣٤٥٦٧۸۹'
        for i in range(10):
            phone = phone.replace(persian_digits[i], str(i)).replace(arabic_digits[i], str(i))
        phone = re.sub(r'[^\d]', '', phone).strip() or None
    else:
        phone = None

    if not tenant_id:
        try:
            from flask import session
            tenant_id = session.get('tenant_id') or 1
        except Exception:
            tenant_id = 1

    customer = None
    if phone:
        customer = Customer.query.filter_by(tenant_id=tenant_id, phone=phone).first()
        if not customer:
            customer = Customer.query.filter_by(phone=phone).first()
    if not customer:
        customer = Customer.query.filter_by(tenant_id=tenant_id, name=name).first()
        if not customer:
            customer = Customer.query.filter_by(name=name).first()
    if not customer:
        customer = Customer(
            tenant_id=tenant_id,
            name=name,
            phone=phone,
            address=str(address) if (address and not str(address).isdigit()) else None,
            customer_type=customer_type or 'regular',
            total_purchases=0,
            outstanding_balance=0
        )
        try:
            db.session.add(customer)
            db.session.commit()
        except Exception:
            db.session.rollback()
            if phone:
                customer = Customer.query.filter_by(tenant_id=tenant_id, phone=phone).first() or Customer.query.filter_by(phone=phone).first()
            if not customer:
                customer = Customer.query.filter_by(tenant_id=tenant_id, name=name).first() or Customer.query.filter_by(name=name).first()
    else:
        changed = False
        if not getattr(customer, 'tenant_id', None):
            customer.tenant_id = tenant_id
            changed = True
        if phone and not customer.phone:
            # بررسی عدم تکرار شماره در دیتابیس همین تننت
            existing = Customer.query.filter_by(tenant_id=tenant_id, phone=phone).first()
            if not existing:
                customer.phone = phone
                changed = True
        if address and not str(address).isdigit() and not customer.address:
            customer.address = str(address)
            changed = True
        if changed:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
    return customer

def calculate_store_financial_summary(year, month, settings=None):
    """
    محاسبه جامع شاخص‌های مالی، فروش، سود ناخالص، هزینه‌ها و سود خالص کل فروشگاه
    شامل تفکیک پرداخت‌های دریافتی، تنخواه، اجاره شعب، حقوق و پورسانت
    """
    if not settings:
        settings = Settings.query.first()

    year_int = safe_int(year)
    month_int = safe_int(month)
    month_str = str(month_int)
    month_pad = f"{month_int:02d}"

    month_invoices = Invoice.query.options(
        selectinload(Invoice.cheques),
        selectinload(Invoice.items)
    ).filter(
        db.or_(Invoice.shamsi_year == year_int, Invoice.shamsi_year == str(year_int)),
        db.or_(Invoice.shamsi_month == month_int, Invoice.shamsi_month == month_str, Invoice.shamsi_month == month_pad),
        Invoice.status == 'final'
    ).all()

    shop1_total = 0
    shop2_total = 0
    gross_sales = 0
    returns_amount = 0
    total_sales_all = 0
    estimated_gross_profit = 0
    total_actual_cost = 0
    total_discounts = 0

    paid_pos = 0
    paid_card = 0
    paid_cash = 0
    paid_cheque = 0
    remaining_balance = 0

    sales_count = 0
    returns_count = 0

    for inv in month_invoices:
        valid_cheques = sum(chk.amount for chk in inv.cheques if chk.status in ['passed', 'pending', 'assigned'])
        immediate_paid = max((inv.paid_amount or 0), ((inv.paid_pos or 0) + (inv.paid_card or 0) + (inv.paid_cash or 0)))
        settled_amt = immediate_paid + valid_cheques
        profit_amt = inv.real_profit or 0
        cost_amt = inv.actual_buy_cost or 0

        if inv.invoice_type == 'sale':
            gross_sales += (inv.total_amount or 0)
            sales_count += 1
            total_discounts += (inv.discount_amount or 0)
            total_sales_all += settled_amt
            estimated_gross_profit += profit_amt
            total_actual_cost += cost_amt
            paid_pos += (inv.paid_pos or 0)
            paid_card += (inv.paid_card or 0)
            paid_cash += (inv.paid_cash or 0)
            paid_cheque += (inv.paid_cheque or 0)
            remaining_balance += (inv.remaining_balance or 0)
            if inv.shop_id == 2:
                shop2_total += settled_amt
            else:
                shop1_total += settled_amt
        elif inv.invoice_type == 'return':
            effective_return = abs(settled_amt if settled_amt > 0 else (inv.total_amount or 0))
            returns_amount += abs(inv.total_amount or effective_return)
            returns_count += 1
            total_sales_all -= effective_return
            estimated_gross_profit -= profit_amt
            total_actual_cost -= cost_amt
            if inv.shop_id == 2:
                shop2_total -= effective_return
            else:
                shop1_total -= effective_return

    total_sales_all = max(0, total_sales_all)
    net_sales = gross_sales - returns_amount

    # محاسبه پورسانت‌ها
    sellers = User.query.filter(User.role.in_(['seller', 'cashier']), User.is_active == True).all()
    total_commissions = 0
    for s in sellers:
        s_stats = calculate_seller_exact_stats(s.id, year_int, month_int, s.commission_rate, settings, user=s)
        total_commissions += s_stats['settled_commission'] + s_stats.get('tier_bonus_amount', 0)

    all_staff = User.query.filter_by(is_active=True).all()
    total_base_salaries = sum(u.base_salary or 0 for u in all_staff if u.role != 'admin')
    total_payroll = total_base_salaries + total_commissions

    shops = Shop.query.all()
    total_rent = sum(s.rent_amount or 0 for s in shops)

    expenses = Expense.query.filter(
        db.or_(Expense.shamsi_year == year_int, Expense.shamsi_year == str(year_int)),
        db.or_(Expense.shamsi_month == month_int, Expense.shamsi_month == month_str, Expense.shamsi_month == month_pad)
    ).all()
    total_expenses = sum(e.amount for e in expenses)

    petty_deposits = PettyCashDeposit.query.filter(
        db.or_(PettyCashDeposit.shamsi_year == year_int, PettyCashDeposit.shamsi_year == str(year_int)),
        db.or_(PettyCashDeposit.shamsi_month == month_int, PettyCashDeposit.shamsi_month == month_str, PettyCashDeposit.shamsi_month == month_pad)
    ).all()
    total_petty_deposits = sum(p.amount for p in petty_deposits)

    store_net_profit = estimated_gross_profit - (total_payroll + total_rent + total_expenses)
    base_sales = net_sales if net_sales > 0 else total_sales_all
    profit_margin_percent = round((store_net_profit / base_sales * 100), 1) if base_sales > 0 else 0
    gross_margin_percent = round((estimated_gross_profit / base_sales * 100), 1) if base_sales > 0 else 0

    return {
        'year': year_int,
        'month': month_int,
        'gross_sales': gross_sales,
        'returns_amount': returns_amount,
        'net_sales': net_sales,
        'total_sales_all': total_sales_all,
        'sales_count': sales_count,
        'returns_count': returns_count,
        'total_discounts': total_discounts,
        'actual_buy_cost': total_actual_cost,
        'total_actual_cost': total_actual_cost,
        'real_profit': estimated_gross_profit,
        'estimated_gross_profit': estimated_gross_profit,
        'paid_pos': paid_pos,
        'paid_card': paid_card,
        'paid_cash': paid_cash,
        'paid_cheque': paid_cheque,
        'remaining_balance': remaining_balance,
        'shop1_total': shop1_total,
        'shop2_total': shop2_total,
        'total_expenses': total_expenses,
        'total_petty_deposits': total_petty_deposits,
        'total_rent': total_rent,
        'total_commissions': total_commissions,
        'total_base_salaries': total_base_salaries,
        'total_payroll': total_payroll,
        'store_net_profit': store_net_profit,
        'net_store_profit': store_net_profit,
        'profit_margin_percent': profit_margin_percent,
        'gross_margin_percent': gross_margin_percent
    }

# ==================== موتور هوش مصنوعی و تحلیل هوشمند ====================

def parse_smart_invoice_text(raw_text, current_shop_id=1):
    """
    موتور هوش مصنوعی تجزیه و پردازش متن آزاد فاکتور
    مثال ورودی:
    «۲ تا هود داتیس ۵۲۲ و یک گاز اخوان gi135 دادم به آقای علیزاده 09121112233 مبلغ کل ۲۴ میلیون، ۵ میلیون نقد و ۱۹ میلیون چک صیادی»
    """
    if not raw_text or not raw_text.strip():
        return {'success': False, 'message': 'متن ورودی خالی است.'}

    text = raw_text.replace('ي', 'ی').replace('ك', 'ک')
    
    # استخراج شماره تماس
    phone_match = re.search(r'09\d{9}', text)
    customer_phone = phone_match.group(0) if phone_match else ''

    # استخراج نام مشتری
    customer_name = 'مشتری محترم'
    name_match = re.search(r'(به|بنام|آقای|خانم|جناب)\s+([آ-ی\s]{3,25})', text)
    if name_match:
        customer_name = name_match.group(2).strip()

    # تشخیص نحوه پرداخت
    payment_method = 'pos'
    if 'چک' in text:
        payment_method = 'cheque'
    elif 'بیعانه' in text or 'مانده' in text:
        payment_method = 'deposit'
    elif 'کارت به کارت' in text or 'واریز' in text:
        payment_method = 'card_to_card'
    elif 'نقد' in text:
        payment_method = 'cash'

    # جستجو در کالاهای انبار برای تطبیق هوشمند
    all_inventory = InventoryItem.query.filter_by(shop_id=current_shop_id).all()
    detected_items = []
    
    for inv_item in all_inventory:
        item_keywords = inv_item.name.lower().split()
        # اگر نام کالا یا کلمات کلیدی آن در متن بود
        matches = [kw for kw in item_keywords if len(kw) > 2 and kw in text.lower()]
        if len(matches) >= 2 or inv_item.name in text:
            # تخمین تعداد
            qty = 1
            qty_match = re.search(rf'(\d+)\s*(تا|عدد|دستگاه)?\s*{re.escape(inv_item.name[:8])}', text)
            if qty_match:
                qty = int(qty_match.group(1))
            
            detected_items.append({
                'inventory_id': inv_item.id,
                'name': inv_item.name,
                'category': inv_item.category,
                'quantity': qty,
                'buy_price': inv_item.buy_price,
                'sell_price': inv_item.sell_price,
                'total_price': inv_item.sell_price * qty
            })

    # استخراج مبالغ به تومان/میلیون
    total_amount = sum(item['total_price'] for item in detected_items)
    
    # اگر مبلغ صریحاً با واژه میلیون ذکر شده بود
    price_match = re.search(r'(\d+[\.\d]*)\s*(میلیون|ملیون)', text)
    if price_match:
        extracted_price = int(float(price_match.group(1)) * 1_000_000)
        if total_amount == 0 or abs(extracted_price - total_amount) > 1000:
            total_amount = extracted_price

    return {
        'success': True,
        'customer_name': customer_name,
        'customer_phone': customer_phone,
        'payment_method': payment_method,
        'items': detected_items,
        'total_amount': total_amount,
        'raw_text': raw_text
    }

def get_inventory_ai_insights():
    """
    تحلیل هوشمند و پیش‌بینی کسری و اقلام پرفروش انبار
    """
    items = InventoryItem.query.all()
    critical_items = []
    healthy_items = []
    total_inventory_value = 0
    total_inventory_sell_value = 0
    
    for item in items:
        total_inventory_value += item.buy_price * item.stock_quantity
        total_inventory_sell_value += item.sell_price * item.stock_quantity
        
        if item.stock_quantity <= item.min_alert_stock:
            critical_items.append({
                'id': item.id,
                'name': item.name,
                'category': item.category,
                'shop_name': item.shop.name if item.shop else '',
                'stock': item.stock_quantity,
                'min_stock': item.min_alert_stock,
                'suggested_reorder': max(10 - item.stock_quantity, item.min_alert_stock * 3),
                'urgency': 'بحرانی' if item.stock_quantity == 0 else 'هشدار'
            })
        else:
            healthy_items.append(item)

    return {
        'total_items_count': len(items),
        'critical_count': len(critical_items),
        'critical_items': critical_items,
        'total_buy_valuation': total_inventory_value,
        'total_sell_valuation': total_inventory_sell_value,
        'estimated_stock_profit': total_inventory_sell_value - total_inventory_value
    }

def send_invoice_sms(invoice, base_url=None):
    """
    ارسال بلادرنگ پیامک گارانتی، اصالت و لینک مشاهده فاکتور از طریق وب‌سرویس سریع SMS.ir
    """
    import requests
    from models import Settings, db

    if not invoice:
        return False, "فاکتور یافت نشد."

    phone = str(invoice.customer_phone or '').strip()
    if not phone:
        return False, "شماره تماس مشتری برای این فاکتور ثبت نشده است."

    # تبدیل اعداد فارسی/عربی به انگلیسی و حذف کاراکترهای اضافی
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    arabic_digits = '٠١٢٣٤٥٦٧٨٩'
    for i in range(10):
        phone = phone.replace(persian_digits[i], str(i)).replace(arabic_digits[i], str(i))
    phone = re.sub(r'[^\d]', '', phone)

    if not phone.startswith('09') or len(phone) != 11:
        return False, f"شماره همراه مشتری ({phone}) نامعتبر است. شماره همراه باید با 09 شروع شده و ۱۱ رقمی باشد."

    settings = Settings.query.first()
    api_key = (settings.sms_api_key if settings and settings.sms_api_key else 'mDVL1257srjKMnY7X9Yj87Y1ssazFsEncwDtt3kMF9NtAcBa').strip()
    template_id_str = str(settings.sms_template_id if settings and settings.sms_template_id else '355952').strip()
    sms_enabled = settings.sms_enabled if settings and settings.sms_enabled is not None else True

    if not sms_enabled:
        return False, "سامانه پیامکی در تنظیمات سیستم غیرفعال است."

    try:
        template_id = int(template_id_str)
    except Exception:
        template_id = 355952

    domain = (settings.public_domain if settings and settings.public_domain else 'tahmasebistore.ir').strip()
    if not domain.startswith('http://') and not domain.startswith('https://'):
        domain = f"https://{domain}"

    domain = domain.rstrip('/')
    invoice_link = f"{domain}/invoice/view/{invoice.invoice_number}"

    cust_name = (invoice.customer_name or 'مشتری محترم').strip()[:40]
    inv_num = str(invoice.invoice_number or invoice.id).strip()[:40]

    payload = {
        "mobile": phone,
        "templateId": template_id,
        "parameters": [
            {"name": "NAME", "value": cust_name},
            {"name": "INVOICE", "value": inv_num},
            {"name": "CODE", "value": inv_num},
            {"name": "LINK", "value": invoice_link}
        ]
    }

    headers = {
        "X-API-KEY": api_key,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post("https://api.sms.ir/v1/send/verify", json=payload, headers=headers, timeout=12)
        resp_json = {}
        try:
            resp_json = resp.json()
        except Exception:
            pass

        # در SMS.ir وضعیت 1 یا 200 یا کد ۲۰۰/۲۰۱ نشان‌دهنده موفقیت است
        is_success = resp.status_code in [200, 201] and (
            resp_json.get('status') == 1 or 
            resp_json.get('isSuccessful') is True or 
            'data' in resp_json
        )

        if is_success:
            now_str = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M:%S")
            invoice.sms_sent = True
            invoice.sms_sent_at = now_str
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()

            log_activity(
                f"ارسال پیامک گارانتی فاکتور {inv_num} به {phone} (شناسه قالب {template_id})",
                user_name="سامانه هوشمند SMS.ir",
                category="پیامک",
                details=f"لینک فاکتور: {invoice_link}"
            )
            return True, f"پیامک گارانتی و لینک فاکتور با موفقیت به {phone} ارسال شد."
        else:
            err_msg = resp_json.get('message') or resp.text or f"کد وضعیت {resp.status_code}"
            log_activity(
                f"خطا در ارسال پیامک فاکتور {inv_num} به {phone}: {err_msg}",
                user_name="سامانه هوشمند SMS.ir",
                category="پیامک",
                details=str(resp_json)
            )
            return False, f"سامانه پیامکی: {err_msg}"

    except requests.exceptions.Timeout:
        log_activity(f"تایم‌اوت ارتباط با وب‌سرویس پیامک برای فاکتور {inv_num}", "سامانه هوشمند SMS.ir", "پیامک")
        return False, "تایم‌اوت ارتباط با سرور پیامک (لطفاً مجدداً امتحان فرمایید)."
    except Exception as e:
        log_activity(f"خطای سیستمی ارسال پیامک فاکتور {inv_num}: {str(e)}", "سامانه هوشمند SMS.ir", "پیامک")
        return False, f"خطای شبکه در ارسال پیامک: {str(e)}"


DEFAULT_AI_PROXY = 'https://tahmasebi-app.onrender.com/api/ai/proxy'
DEFAULT_CLOUDFLARE_PROXY = 'https://nameless-mountain-929bgemini-proxy.abolfazlzamani356.workers.dev'

def ai_scan_paper_invoice(image_bytes, mime_type='image/jpeg', api_key=None, model_name=None):
    """
    اسکن و تحلیل هوشمند تصویر فاکتور دست‌نویس یا چاپی با استفاده از Google AI Studio (Gemini Vision)
    ویژه استخراج اقلام، قیمت‌ها، پکیج‌های ترکیبی (مانند کابینت با سنگ) و تخفیف‌ها در صنف لوازم ساختمانی و بهداشتی
    """
    if not image_bytes:
        return {
            'success': False,
            'error': 'no_image',
            'message': 'تصویری برای پردازش ارسال نشده است.'
        }

    # بهینه‌سازی و فشرده‌سازی تصویر در سمت سرور در صورت بزرگ بودن
    try:
        if len(image_bytes) > 600 * 1024:
            import io
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes))
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            max_dim = 1600
            if max(img.width, img.height) > max_dim:
                img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            out_buf = io.BytesIO()
            img.save(out_buf, format='JPEG', quality=80, optimize=True)
            image_bytes = out_buf.getvalue()
            mime_type = 'image/jpeg'
    except Exception:
        pass

    prompt_text = """تو یک حسابدار هوشمند و فوق‌العاده دقیق در صنف لوازم بهداشتی و ساختمانی (فروشگاه طهماسبی) هستی.
وظیفه تو خواندن تصویر این برگه فاکتور دست‌نویس یا دفتری و تبدیل دقیق آن به ساختار استاندارد فاکتور است.

قوانین و عرف بازار لوازم بهداشتی و ساختمانی:
۱. اقلام ترکیبی و پکیج‌ها (Bundles):
- اگر در فاکتور نوشته شده «کابین با سنگ»، «روشویی با سنگ»، «کابینت ۶۰ و کاسه» یا موارد مشابه، آن را به عنوان یک قلم واحد (پکیج ترکیبی) با نام کامل و قیمت مجموع ثبت کن و به هیچ وجه تفکیک نکن.
- اگر چند تکه شیرآلات (مثلاً ست ۴ تکه یا شیر توالت و دوش) با یک جمع کل نوشته شده، آن را به عنوان یک ردیف «ست شیرآلات ...» با قیمت تجمیعی ثبت کن.
۲. مبالغ و اعداد:
- تمام اعداد و مبالغ را به تومان (Toman) برگردان (ارقام انگلیسی). اگر فاکتور به ریال نوشته شده (یک صفر بیشتر دارد)، آن را به تومان تبدیل کن.
- تعداد کالا (quantity) حداقل ۱ است.
- قیمت واحد (unit_price) و قیمت کل ردیف (total_price) را با دقت استخراج کن.
۳. تخفیف‌ها و تسویه نهایی:
- هرگونه تخفیف پای فاکتور، خط‌خوردگی یا کسر مبلغ برای مشتری را در فیلد discount_amount ثبت کن.
- مبلغ نهایی قابل پرداخت فاکتور را در grand_total قرار بده.
- اگر نام یا شماره موبایل خریدار در برگه نوشته شده، استخراج کن.
- اگر یادداشت نحوه پرداخت دارد (مثلاً کارتخوان، چک صیادی، نقد)، در payment_note بنویس.

خروجی باید صرفاً یک شیء معتبر JSON با این ساختار باشد:
{
  "customer_name": "نام مشتری یا خالی",
  "customer_phone": "شماره موبایل یا خالی",
  "date": "تاریخ فاکتور یا خالی",
  "items": [
    {
      "name": "نام دقیق کالا یا پکیج ترکیبی",
      "category": "یکی از دسته‌ها: روشویی کابینتی، شیرآلات، سینک، هود، گاز صفحه‌ای، توالت فرنگی، فلاش تانک، علم دوش، عمومی",
      "quantity": 1,
      "unit_price": 4500000,
      "total_price": 4500000,
      "discount": 0,
      "is_bundle": false,
      "description": ""
    }
  ],
  "subtotal_amount": 4500000,
  "discount_amount": 200000,
  "grand_total": 4300000,
  "payment_note": "",
  "raw_notes": ""
}
فقط و فقط یک شیء معتبر JSON خروجی بده، بدون هیچ توضیح یا علامت اضافه."""

    res = call_gemini_unified(
        prompt=prompt_text,
        image_bytes=image_bytes,
        mime_type=mime_type,
        json_mode=True,
        temperature=0.1
    )

    if not res.get('success'):
        return {
            'success': False,
            'error': res.get('error', 'api_failed'),
            'message': res.get('message', 'خطا در ارتباط با وب‌سرویس هوش مصنوعی گوگل')
        }

    data = res.get('data')
    if not data and res.get('clean_text'):
        try:
            data = json.loads(res.get('clean_text'))
        except Exception:
            pass

    if not data or not isinstance(data, dict):
        return {
            'success': False,
            'error': 'invalid_json',
            'message': 'هوش مصنوعی نتوانست اقلام فاکتور را در قالب ساختاریافته استخراج کند. لطفاً از وضوح تصویر اطمینان حاصل فرمایید.'
        }

    # استانداردسازی داده‌ها
    sanitized_items = []
    calc_subtotal = 0
    for it in data.get('items', []):
        q = int(it.get('quantity') or 1)
        if q <= 0:
            q = 1
        up = int(it.get('unit_price') or 0)
        tp = int(it.get('total_price') or (up * q))
        disc = int(it.get('discount') or 0)
        calc_subtotal += (up * q)
        sanitized_items.append({
            'name': str(it.get('name') or 'کالای فاکتور').strip(),
            'category': str(it.get('category') or 'عمومی').strip(),
            'quantity': q,
            'unit_price': up,
            'total_price': tp,
            'discount': disc,
            'is_bundle': bool(it.get('is_bundle', False)),
            'description': str(it.get('description') or '').strip()
        })

    subtot = int(data.get('subtotal_amount') or calc_subtotal)
    disc_tot = int(data.get('discount_amount') or 0)
    gtot = int(data.get('grand_total') or (subtot - disc_tot))

    parsed_response = {
        'customer_name': str(data.get('customer_name') or '').strip(),
        'customer_phone': str(data.get('customer_phone') or '').strip(),
        'date': str(data.get('date') or '').strip(),
        'items': sanitized_items,
        'subtotal_amount': subtot,
        'discount_amount': disc_tot,
        'grand_total': gtot,
        'payment_note': str(data.get('payment_note') or '').strip(),
        'raw_notes': str(data.get('raw_notes') or '').strip()
    }

    try:
        log_activity(
            f"تحلیل موفق فاکتور دفتری توسط هوش مصنوعی ({res.get('model')}) با استخراج {len(sanitized_items)} قلم کالا",
            user_name="موتور هوش مصنوعی Gemini",
            category="هوش مصنوعی",
            details=f"مبلغ کل: {gtot:,} تومان"
        )
    except Exception:
        pass

    return {
        'success': True,
        'data': parsed_response,
        'model_used': res.get('model')
    }

def call_gemini_unified(prompt, image_bytes=None, mime_type='image/jpeg', json_mode=False, system_instruction=None, temperature=0.2):
    """
    موتور ارتباط یکپارچه و هوشمند با Google AI (Gemini 3.8 Flash و مدل‌های روز)
    پشتیبانی خودکار از ریورس پروکسی کلودفلر، کلیدهای جدید AQ و هدر x-goog-api-key
    """
    import os
    import time
    import requests
    import base64
    
    api_key = None
    model_name = 'gemini-3.8-flash'
    is_foreign_server = bool(os.environ.get('RENDER') or os.environ.get('RENDER_INSTANCE_ID'))
    default_target = 'https://generativelanguage.googleapis.com' if is_foreign_server else DEFAULT_AI_PROXY
    base_url = default_target
    
    try:
        st = Settings.query.first()
        if st:
            if st.gemini_api_key:
                api_key = st.gemini_api_key.strip()
            if st.gemini_model:
                model_name = st.gemini_model.strip()
            if st.gemini_base_url and st.gemini_base_url.strip():
                custom_url = st.gemini_base_url.strip()
                if not is_foreign_server:
                    # روی سرورهای ایران (مثل لیارا)، دامنه‌های googleapis و workers.dev مسدود یا تحریم هستند و باید از نود پروکسی Render استفاده شود
                    if not custom_url or 'googleapis.com' in custom_url or 'workers.dev' in custom_url:
                        base_url = DEFAULT_AI_PROXY
                    else:
                        base_url = custom_url
                else:
                    base_url = custom_url
    except Exception:
        pass

    if not api_key:
        api_key = os.environ.get('GEMINI_API_KEY', '').strip()

    if not api_key:
        return {
            'success': False,
            'error': 'no_api_key',
            'message': 'کلید API هوش مصنوعی گوگل ثبت نشده است. لطفاً در پنل تنظیمات مدیر، کلید خود را وارد نمایید.'
        }

    # نقشه‌برداری هوشمند مدل‌ها به مدل‌های رسمی، باثبات و پرسرعت Google API (سریع‌ترین پاسخ‌دهی و نرخ درخواست ۱۵ در دقیقه)
    MODEL_ALIAS_MAP = {
        'gemini-3.8-flash': ['gemini-3.1-flash-lite', 'gemini-3.5-flash-lite', 'gemini-3-flash-preview'],
        'gemini-3.1-flash-lite': ['gemini-3.1-flash-lite', 'gemini-3.5-flash-lite'],
        'gemini-3.5-flash-lite': ['gemini-3.5-flash-lite', 'gemini-3.1-flash-lite'],
        'gemini-3-flash': ['gemini-3.1-flash-lite', 'gemini-3-flash-preview'],
        'gemini-2.5-flash': ['gemini-3.1-flash-lite', 'gemini-3-flash-preview'],
        'gemini-1.5-pro': ['gemini-3.1-flash-lite', 'gemini-3-flash-preview'],
        'gemini-1.5-flash': ['gemini-3.1-flash-lite', 'gemini-3.5-flash-lite']
    }

    candidate_models = []
    for m in MODEL_ALIAS_MAP.get(model_name, [model_name]):
        if m not in candidate_models:
            candidate_models.append(m)

    for m in ['gemini-3.1-flash-lite', 'gemini-3.5-flash-lite']:
        if m not in candidate_models:
            candidate_models.append(m)

    parts = []
    if system_instruction:
        parts.append({"text": f"دستورالعمل سیستمی:\n{system_instruction}\n---\n"})
    parts.append({"text": prompt})

    if image_bytes:
        b64_img = base64.b64encode(image_bytes).decode('utf-8')
        parts.append({
            "inlineData": {
                "mimeType": mime_type or "image/jpeg",
                "data": b64_img
            }
        })

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 1024
        }
    }
    if json_mode:
        payload["generationConfig"]["response_mime_type"] = "application/json"

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }

    last_err = None
    start_time = time.time()
    for cand in candidate_models:
        # تضمین قطعی اینکه کل فرآیند از ۲۰ ثانیه بیشتر نشود تا با لیمیت ۳۰ ثانیه‌ای سرور و خطای ۵۰۲ روبرو نشویم
        elapsed = time.time() - start_time
        if elapsed > 20:
            break

        url = f"{base_url.rstrip('/')}/v1beta/models/{cand}:generateContent?key={api_key}"
        try:
            # زمان مجاز برای مدل اول تا ۲۰ ثانیه است که زمان کاملاً کافی برای تولید گزارش کامل حتی با اینترنت متغیر فراهم می‌کند
            time_left = max(5, int(22 - (time.time() - start_time)))
            cand_timeout = min(20, time_left) if cand == candidate_models[0] else min(7, time_left)
            resp = requests.post(url, json=payload, headers=headers, timeout=cand_timeout)
            if resp.status_code == 200:
                res_json = resp.json()
                cands = res_json.get('candidates', [])
                if cands:
                    out_parts = cands[0].get('content', {}).get('parts', [])
                    if out_parts:
                        raw_text = out_parts[0].get('text', '').strip()
                        clean_text = raw_text
                        if clean_text.startswith('```json'):
                            clean_text = clean_text[7:]
                        elif clean_text.startswith('```'):
                            clean_text = clean_text[3:]
                        if clean_text.endswith('```'):
                            clean_text = clean_text[:-3]
                        clean_text = clean_text.strip()
                        
                        json_data = None
                        if json_mode:
                            try:
                                json_data = json.loads(clean_text)
                            except Exception:
                                pass
                                
                        display_model = 'Gemini 3.8 Flash' if '3.8' in model_name else cand
                        return {
                            'success': True,
                            'text': raw_text,
                            'clean_text': clean_text,
                            'data': json_data,
                            'model': display_model
                        }
            elif resp.status_code == 429:
                last_err = "محدودیت تعداد درخواست در دقیقه گوگل (Rate Limit 429): در حساب رایگان گوگل، حداکثر تعداد درخواست در دقیقه پر شده است. لطفاً ۱ دقیقه صبر فرمایید یا در تنظیمات از مدل سریع Flash Lite استفاده نمایید."
                # برای جلوگیری از مسدودیت بیشتر کلید، بلافاصله متوقف شو
                break
            elif resp.status_code == 503:
                last_err = "سرور گوگل به دلیل ترافیک بالا موقتاً پاسخ نداد (503 Service Unavailable). در حال تلاش با مدل جایگزین..."
                continue
            elif resp.status_code == 403:
                last_err = "خطای ۴۰۳ گوگل: دسترسی نامعتبر یا محدودیت جغرافیایی آی‌پی. لطفاً اتصال Cloudflare Worker یا کلید را بررسی نمایید."
                break
            elif resp.status_code == 400:
                last_err = f"خطای ۴۰۰ گوگل (پارامتر نامعتبر): {resp.text[:120]}"
            else:
                last_err = f"کد خطا {resp.status_code}: {resp.text[:140]}"
        except requests.exceptions.Timeout:
            last_err = "تایم‌اوت ارتباط با سرور گوگل: پاسخ در مهلت مقرر (۲۰ ثانیه) از سرور گوگل دریافت نشد. لطفاً مجدداً ارسال نمایید."
            # اگر مدل اول در ۲۰ ثانیه پاسخ نداد، فرصت کافی برای مدل دوم نمانده تا از خطای ۵۰۲ سرور جلوگیری شود
            break
        except Exception as ex:
            last_err = str(ex)

    return {
        'success': False,
        'error': 'api_failed',
        'message': f'خطا در ارتباط با گوگل: {last_err or "عدم دریافت پاسخ در زمان مناسب"}'
    }

def ai_business_copilot(query_text, user_name="مدیر"):
    """
    دستیار اجرایی و تحلیلگر ارشد کسب‌وکار هوش مصنوعی ویژه مدیران فروشگاه طهماسبی
    تحلیل زنده دیتابیس، فروش روز و ماه، سود ناخالص/خالص، عملکرد پرسنل و هشدارها
    """
    try:
        now_j = jdatetime.datetime.now()
        year = now_j.year
        month = now_j.month
        day = now_j.day
        month_name = PERSIAN_MONTHS.get(month, '')

        try:
            fin = calculate_store_financial_summary(year, month)
        except Exception:
            fin = {}

        today_invoices = Invoice.query.filter_by(shamsi_year=year, shamsi_month=month, shamsi_day=day, status='final').all()
        today_sales = sum(inv.total_amount or 0 for inv in today_invoices if inv.invoice_type == 'sale')
        today_count = len([i for i in today_invoices if i.invoice_type == 'sale'])
        today_settled = sum((inv.paid_pos or 0) + (inv.paid_card or 0) + (inv.paid_cash or 0) for inv in today_invoices if inv.invoice_type == 'sale')

        top_items_data = db.session.query(
            InvoiceItem.item_name,
            db.func.sum(InvoiceItem.quantity).label('qty'),
            db.func.sum(InvoiceItem.total_price).label('revenue')
        ).join(Invoice).filter(
            Invoice.shamsi_year == year,
            Invoice.shamsi_month == month,
            Invoice.status == 'final',
            Invoice.invoice_type == 'sale'
        ).group_by(InvoiceItem.item_name).order_by(db.desc('qty')).limit(5).all()

        top_items_str = ", ".join([f"{item[0]} ({item[1]} عدد - {item[2]:,} تومان)" for item in top_items_data]) or "ثبت نشده"

        pending_cheques = Cheque.query.filter_by(status='pending').all()
        bounced_cheques = Cheque.query.filter_by(status='bounced').all()
        pending_chk_amt = sum(c.amount for c in pending_cheques)
        bounced_chk_amt = sum(c.amount for c in bounced_cheques)

        low_stock_items = InventoryItem.query.filter(InventoryItem.stock_quantity <= InventoryItem.min_alert_stock).limit(6).all()
        low_stock_str = ", ".join([f"{it.name} (موجودی: {it.stock_quantity})" for it in low_stock_items]) or "تمامی اقلام موجودی کافی دارند"

        system_instruction = f"""تو دستیار ارشد هوش مصنوعی، مشاور مالی و مدیر عملیاتی فوق‌العاده باهوش «فروشگاه لوازم بهداشتی و ساختمانی طهماسبی» هستی.
نام کاربری که با او گفتگو می‌کنی: «{user_name}» است.
امروز: {now_j.strftime('%Y/%m/%d')} است.

خلاصه وضعیت زنده دیتابیس فروشگاه:
- فروش ناخالص ماه {month_name}: {fin.get('gross_sales', 0):,} تومان
- مرجوعی ماه: {fin.get('returns_amount', 0):,} تومان
- فروش خالص ماه: {fin.get('net_sales', 0):,} تومان
- سود ناخالص برآورد شده: {fin.get('estimated_gross_profit', 0):,} تومان (حاشیه سود: {fin.get('gross_margin_percent', 0)}%)
- کل بار مالی حقوق و پورسانت پرسنل: {fin.get('total_payroll', 0):,} تومان
- کل هزینه‌های جاری و اجاره: {fin.get('total_expenses', 0) + fin.get('total_rent', 0):,} تومان
- سود خالص قطعی فروشگاه تا این لحظه: {fin.get('store_net_profit', 0):,} تومان
- مانده بدهی نسیه مشتریان در این ماه: {fin.get('remaining_balance', 0):,} تومان
- آمار امروز ({day} {month_name}): {today_count} فاکتور فروش به مبلغ {today_sales:,} تومان (دریافتی نقد/کارتخوان: {today_settled:,} تومان)
- پرفروش‌ترین کالاهای ماه: {top_items_str}
- چک‌های در جریان: {len(pending_cheques)} فقره به مبلغ {pending_chk_amt:,} تومان
- چک‌های برگشتی: {len(bounced_cheques)} فقره به مبلغ {bounced_chk_amt:,} تومان
- هشدارهای کسری انبار: {low_stock_str}

قوانین پاسخگویی:
۱. به سوال کاربر با زبان فارسی روان، محترمانه، پرانرژی و سرشار از بینش مدیریتی و اقتصادی پاسخ بده.
۲. تمام مبالغ پولی را دقیقاً به «تومان» با ارقام تفکیک‌شده سه‌رقمی (کاما) بنویس.
۳. از بولت‌پوینت‌های جذاب و ایموجی‌های مناسب استفاده کن.
۴. در پایان پاسخت، حتماً ۱ یا ۲ نکته یا اقدام فوری پیشنهادی (Actionable Advice) برای رشد فروشگاه یا رفع چالش‌های موجود ارائه کن.
۵. پاسخ را ساختاریافته، بسیار جذاب، مستقیم، بدون حاشیه‌پردازی و حداکثر در ۲۵۰ الی ۳۵۰ کلمه ارائه کن تا خروجی با حداکثر سرعت تولید شود.
"""

        res = call_gemini_unified(query_text, system_instruction=system_instruction, temperature=0.3)
        if res.get('success'):
            return {
                'success': True,
                'reply': res.get('text', ''),
                'model': res.get('model', 'Gemini 3.8 Flash'),
                'today_sales': today_sales,
                'net_profit': fin.get('store_net_profit', 0)
            }
        else:
            return {
                'success': False,
                'error': res.get('error'),
                'message': res.get('message', 'خطا در ارتباط با هوش مصنوعی.')
            }
    except Exception as ex:
        return {
            'success': False,
            'error': 'internal_error',
            'message': f'خطا در پردازش اطلاعات فروشگاه: {str(ex)}'
        }

def ai_suggest_cross_sell(item_names, categories=None):
    """
    پیشنهاد هوشمند اقلام مکمل و تکمیلی سبد خرید (Cross-Selling & Upselling)
    ویژه صنف لوازم بهداشتی و ساختمانی
    """
    if not item_names:
        return {'success': True, 'suggestions': []}

    categories = categories or []
    items_text = ", ".join(item_names)
    cats_text = ", ".join(categories)

    rule_suggestions = []
    combined_str = (items_text + " " + cats_text).lower()

    if any(k in combined_str for k in ['روشویی', 'کابین', 'کابینت', 'سنگ']):
        rule_suggestions.extend([
            {'name': 'شیر روشویی پایه بلند لوکس', 'category': 'شیرآلات', 'estimated_price': 2200000, 'reason': 'مکمل ضروری کاسه روشویی و کابینت'},
            {'name': 'سیفون اتوماتیک روشویی پاپ‌آپ', 'category': 'سایر و اکسسوری', 'estimated_price': 350000, 'reason': 'آب‌بندی استاندارد زیر کاسه'},
            {'name': 'شیلنگ پیسوار حصیری استیل (جفت)', 'category': 'سایر و اکسسوری', 'estimated_price': 180000, 'reason': 'اتصال آب سرد و گرم به شیر روشویی'},
            {'name': 'آینه باکس تاچ ال‌ای‌دی ضد بخار', 'category': 'آینه و آینه بک‌لایت', 'estimated_price': 1650000, 'reason': 'هارمونی کامل با کابینت روشویی'}
        ])

    if any(k in combined_str for k in ['سینک', 'گرانیتی', 'استیل']):
        rule_suggestions.extend([
            {'name': 'شیر ظرفشویی شاوری شلنگدار دو منظوره', 'category': 'شیرآلات', 'estimated_price': 3400000, 'reason': 'شستشوی آسان گوشه‌های لگن سینک'},
            {'name': 'سیفون دو لگنه فانتزی با زیرآب', 'category': 'سایر و اکسسوری', 'estimated_price': 480000, 'reason': 'خروج بهینه آب و جلوگیری از بوی نامطبوع'},
            {'name': 'سبد رول شستشوی میوه و استند کشویی', 'category': 'سایر و اکسسوری', 'estimated_price': 320000, 'reason': 'اکسسوری محبوب روی لگن سینک'}
        ])

    if any(k in combined_str for k in ['هود', 'داتیس', 'اخوان']):
        rule_suggestions.extend([
            {'name': 'لوله خرطومی آلومینیومی نسوز ۱۰ متری', 'category': 'سایر و اکسسوری', 'estimated_price': 250000, 'reason': 'هدایت دود و هوای مکش به خروجی'},
            {'name': 'تبدیل خروجی هود ۱۲ به ۱۵ با بست فلزی', 'category': 'سایر و اکسسوری', 'estimated_price': 90000, 'reason': 'فیت کردن دهانه لوله هود'}
        ])

    if any(k in combined_str for k in ['توالت فرنگی', 'فرنگی', 'کرد', 'مروارید']):
        rule_suggestions.extend([
            {'name': 'بوگیر ژله‌ای توالت فرنگی (موم‌دار)', 'category': 'سایر و اکسسوری', 'estimated_price': 140000, 'reason': 'آب‌بندی ۱۰۰٪ کف و عدم نشت بو'},
            {'name': 'شیر توالت اهرمی برنجی با شلنگ ریزبافت', 'category': 'شیرآلات', 'estimated_price': 1450000, 'reason': 'ست ضروری کنار فرنگی'},
            {'name': 'شیر پیسوار فیلتردار ۱/۲ اینچ', 'category': 'سایر و اکسسوری', 'estimated_price': 120000, 'reason': 'کنترل ورودی آب مخزن فرنگی'}
        ])

    if any(k in combined_str for k in ['دوش', 'شیر حمام', 'علم']):
        rule_suggestions.extend([
            {'name': 'علم دوش دوکاره یونیورست با گوشی تلفنی', 'category': 'علم دوش', 'estimated_price': 1850000, 'reason': 'حمام لوکس همراه با ماساژور'},
            {'name': 'کنجی حمام استیل ضدزنگ ۳ طبقه', 'category': 'سایر و اکسسوری', 'estimated_price': 290000, 'reason': 'نگهداری شوینده‌ها در محوطه دوش'}
        ])

    catalog_matches = []
    try:
        for r in rule_suggestions[:4]:
            p_cat = ProductCatalog.query.filter(
                ProductCatalog.is_active == True,
                or_(
                    ProductCatalog.category == r['category'],
                    ProductCatalog.name.contains(r['category'])
                )
            ).first()
            if p_cat:
                catalog_matches.append({
                    'name': p_cat.name,
                    'category': p_cat.category,
                    'estimated_price': p_cat.sale_price or r['estimated_price'],
                    'reason': r['reason'],
                    'in_catalog': True,
                    'catalog_id': p_cat.id
                })
            else:
                catalog_matches.append({
                    'name': r['name'],
                    'category': r['category'],
                    'estimated_price': r['estimated_price'],
                    'reason': r['reason'],
                    'in_catalog': False,
                    'catalog_id': None
                })
    except Exception:
        catalog_matches = rule_suggestions[:4]

    return {
        'success': True,
        'source': 'ai_catalog_rules',
        'suggestions': catalog_matches
    }

def ai_extract_product_from_box(image_bytes, mime_type='image/jpeg'):
    """
    استخراج آنی مشخصات، برند، مدل، بارکد و قیمت کالا از تصویر جعبه، کارتن یا فاکتور خرید
    """
    prompt = """تصویر این کارتن، جعبه کالا، بارکد یا فاکتور خرید در صنف لوازم بهداشتی و ساختمانی را بادقت بخوان.
مشخصات را صرفاً در قالب یک شیء معتبر JSON استخراج کن:
{
  "name": "نام تجاری دقیق و کامل کالا مثلا: شیر ظرفشویی شاوری شودر مدل بیزانس کروم",
  "brand": "برند کالا مانند: شودر، قهرمان، اخوان، داتیس، راسان، مروارید، لوتوس، چینی کرد، فونیکس",
  "category": "یکی از دسته‌ها: روشویی کابینتی، شیرآلات، سینک، هود، گاز صفحه‌ای، توالت فرنگی، فلاش تانک، علم دوش، فر توکار، سایر و اکسسوری",
  "code": "کد مدل یا کد فنی کالا",
  "barcode": "بارکد عددی در صورت رویت",
  "buy_price": 0,
  "sell_price": 0,
  "stock_quantity": 1,
  "description": "ویژگی‌ها مانند رنگ، جنس، ابعاد و گارانتی"
}
فقط و فقط یک شیء معتبر JSON خروجی بده."""

    res = call_gemini_unified(prompt, image_bytes=image_bytes, mime_type=mime_type, json_mode=True, temperature=0.1)
    if res.get('success') and res.get('data'):
        data = res['data']
        return {
            'success': True,
            'data': {
                'name': str(data.get('name') or 'کالای جدید شناسایی‌شده').strip(),
                'brand': str(data.get('brand') or '').strip(),
                'category': str(data.get('category') or 'عمومی').strip(),
                'code': str(data.get('code') or '').strip(),
                'barcode': str(data.get('barcode') or '').strip(),
                'buy_price': safe_int(data.get('buy_price'), 0),
                'sell_price': safe_int(data.get('sell_price'), 0),
                'stock_quantity': safe_int(data.get('stock_quantity'), 1),
                'description': str(data.get('description') or '').strip()
            },
            'model': res.get('model')
        }
    return {
        'success': False,
        'message': res.get('message', 'امکان استخراج مشخصات از تصویر وجود نداشت.')
    }

def ai_customer_credit_risk(customer_id):
    """
    اعتبارسنجی هوشمند خریدار، تحلیل سوابق چک‌های صیادی و ارزیابی ریسک فروش نسیه
    """
    cust = db.session.get(Customer, customer_id)
    if not cust:
        return {'success': False, 'message': 'مشتری یافت نشد'}

    invoices = Invoice.query.filter_by(customer_id=cust.id).all()
    cheques = Cheque.query.filter(or_(Cheque.customer_phone == cust.phone, Cheque.customer_name == cust.name)).all()

    total_spent = sum(inv.total_amount or 0 for inv in invoices if inv.status == 'final')
    passed_chk = len([c for c in cheques if c.status == 'passed'])
    bounced_chk = len([c for c in cheques if c.status == 'bounced'])
    pending_chk = len([c for c in cheques if c.status == 'pending'])

    score = 100
    if bounced_chk > 0:
        score -= (bounced_chk * 30)
    if cust.outstanding_balance > (cust.credit_limit or 50000000):
        score -= 20
    elif cust.outstanding_balance > 0:
        score -= 10

    if total_spent > 100000000 and bounced_chk == 0:
        score = min(100, score + 10)

    score = max(10, min(100, score))

    if score >= 85:
        tier = 'A+'
        risk_label = 'بسیار کم‌ریسک و مشتری طلایی'
    elif score >= 70:
        tier = 'A'
        risk_label = 'خوش‌حساب و معتبر'
    elif score >= 50:
        tier = 'B'
        risk_label = 'ریسک متوسط (فروش نسیه با احتیاط)'
    else:
        tier = 'C'
        risk_label = 'پرریسک (توصیه: فقط نقدی یا چک معتبر تضمین‌شده)'

    if cust.outstanding_balance > 0:
        sms_draft = f"جناب آقای/سرکار خانم {cust.name} گرامی، با سلام و احترام از حسن انتخاب شما در فروشگاه‌های طهماسبی. مانده حساب دفتری شما مبلغ {cust.outstanding_balance:,} تومان می‌باشد. خواهشمند است جهت هماهنگی تسویه با واحد حسابداری تماس حاصل فرمایید. با سپاس."
    else:
        sms_draft = f"جناب آقای/سرکار خانم {cust.name} عزیز، از اعتماد و خرید شما از فروشگاه‌های ساختمانی طهماسبی صمیمانه سپاسگزاریم. کلیه اقلام فاکتور شما شامل گارانتی و خدمات پس از فروش می‌باشند."

    summary = f"امتیاز {score} از ۱۰۰ ({tier}) - {risk_label} | کل خرید: {total_spent:,} تومان | مانده بدهی: {cust.outstanding_balance:,} تومان | چک پاس شده: {passed_chk} | چک برگشتی: {bounced_chk}"

    cust.ai_credit_score = score
    cust.ai_risk_tier = tier
    cust.ai_risk_summary = summary
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    return {
        'success': True,
        'customer_id': cust.id,
        'customer_name': cust.name,
        'score': score,
        'tier': tier,
        'risk_label': risk_label,
        'total_spent': total_spent,
        'outstanding_balance': cust.outstanding_balance,
        'passed_cheques': passed_chk,
        'bounced_cheques': bounced_chk,
        'pending_cheques': pending_chk,
        'summary': summary,
        'sms_draft': sms_draft
    }

def ai_audit_store_anomalies(limit=15):
    """
    ممیزی و دیده‌بان هوشمند خطاهای مالی، تخفیف‌های غیرمجاز و فروش با زیان
    """
    anomalies = []
    
    loss_items = db.session.query(InvoiceItem, Invoice).join(Invoice).filter(
        Invoice.status == 'final',
        Invoice.invoice_type == 'sale',
        InvoiceItem.unit_buy_price > 0,
        InvoiceItem.unit_sell_price < InvoiceItem.unit_buy_price
    ).order_by(Invoice.id.desc()).limit(limit).all()

    total_loss_amount = 0
    loss_items_count = 0

    for it, inv in loss_items:
        loss_per_unit = (it.unit_buy_price - it.unit_sell_price)
        total_loss = loss_per_unit * it.quantity
        total_loss_amount += total_loss
        loss_items_count += 1
        anomalies.append({
            'severity': 'danger',
            'type': 'loss_sale',
            'title': f'فروش زیر قیمت خرید در فاکتور {inv.invoice_number}',
            'invoice_id': inv.id,
            'invoice_number': inv.invoice_number,
            'customer_name': inv.customer_name,
            'loss_amount': total_loss,
            'loss_per_unit': loss_per_unit,
            'quantity': it.quantity,
            'unit_buy_price': it.unit_buy_price,
            'unit_sell_price': it.unit_sell_price,
            'details': f"کالای «{it.item_name}» به قیمت خرید {it.unit_buy_price:,} با قیمت فروش {it.unit_sell_price:,} تومان فاکتور شده است (زیان کل: {total_loss:,} تومان).",
            'date': inv.shamsi_date_time
        })

    high_disc_invoices = Invoice.query.filter(
        Invoice.status == 'final',
        Invoice.invoice_type == 'sale',
        Invoice.subtotal_amount > 1000000,
        Invoice.discount_amount > (Invoice.subtotal_amount * 0.25)
    ).order_by(Invoice.id.desc()).limit(limit).all()

    total_high_discount_amount = 0
    for inv in high_disc_invoices:
        disc_pct = round((inv.discount_amount / inv.subtotal_amount) * 100, 1) if inv.subtotal_amount else 0
        total_high_discount_amount += (inv.discount_amount or 0)
        anomalies.append({
            'severity': 'warning',
            'type': 'high_discount',
            'title': f'تخفیف غیرعادی ({disc_pct}٪) در فاکتور {inv.invoice_number}',
            'invoice_id': inv.id,
            'invoice_number': inv.invoice_number,
            'customer_name': inv.customer_name,
            'discount_amount': inv.discount_amount or 0,
            'discount_percent': disc_pct,
            'details': f"مبلغ ناخالص: {inv.subtotal_amount:,} تومان | تخفیف اعمال‌شده: {inv.discount_amount:,} تومان.",
            'date': inv.shamsi_date_time
        })

    neg_stock_items = InventoryItem.query.filter(InventoryItem.stock_quantity < 0).limit(5).all()
    for it in neg_stock_items:
        anomalies.append({
            'severity': 'danger',
            'type': 'negative_stock',
            'title': f'موجودی منفی در انبار: {it.name}',
            'invoice_id': None,
            'invoice_number': 'انبار',
            'customer_name': it.shop.name if it.shop else 'مرکزی',
            'details': f"موجودی ثبت‌شده در سیستم: {it.stock_quantity} عدد است. لطفاً اصلاح انبارگردانی انجام شود.",
            'date': 'هم‌اکنون'
        })

    summary = {
        'total_loss_amount': total_loss_amount,
        'loss_items_count': loss_items_count,
        'high_discount_count': len(high_disc_invoices),
        'total_high_discount_amount': total_high_discount_amount,
        'negative_stock_count': len(neg_stock_items),
        'total_anomalies_count': len(anomalies)
    }

    return {
        'anomalies': anomalies,
        'summary': summary
    }



