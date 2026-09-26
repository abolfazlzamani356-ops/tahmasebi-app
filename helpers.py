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

            # === محاسبه مبلغ واقعی تسویه‌شده ===
            # چک‌های وصول‌شده
            passed_cheque = sum(chk.amount for chk in inv.cheques if chk.status == 'passed')
            # چک‌های در انتظار (معلق)
            pending_cheque = sum(chk.amount for chk in inv.cheques if chk.status == 'pending')
            # مانده تسویه‌نشده
            remaining = inv.remaining_balance or 0
            # پرداخت فوری: نقد + کارتخوان + کارت‌به‌کارت
            immediate_paid = max((inv.paid_amount or 0), ((inv.paid_pos or 0) + (inv.paid_card or 0) + (inv.paid_cash or 0)))

            # مبلغ تسویه‌شده = پرداخت فوری + چک‌های وصول‌شده
            settled_amount = immediate_paid + passed_cheque
            item_settled = int(settled_amount * ratio)

            # فقط مبلغ تسویه‌شده به فروش خالص اضافه می‌شود
            net_sales += item_settled
            total_cost += item_cost
            real_profit_share += item_profit
            sales_count += 1
            if inv.customer_rating:
                ratings.append(inv.customer_rating)

            # مبالغ معلق: مانده‌ی تسویه‌نشده + چک‌های در انتظار
            pending_this = int((pending_cheque + remaining) * ratio)
            pending_commission_sales += pending_this

        elif inv.invoice_type == 'return':
            # برای مرجوعی هم مبلغ واقعی برگشتی ملاک است، در صورت عدم ثبت پرداخت، کل مبلغ فاکتور ملاک کسر است
            passed_cheque = sum(chk.amount for chk in inv.cheques if chk.status == 'passed')
            immediate_paid = max((inv.paid_amount or 0), ((inv.paid_pos or 0) + (inv.paid_card or 0) + (inv.paid_cash or 0)))
            settled_amount = immediate_paid + passed_cheque
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

def get_or_create_customer(name, phone=None, address=None, customer_type='regular', shop_id=None):
    if not name:
        return None
    name = normalize_persian_text(name).strip()
    if not name:
        name = 'مشتری محترم'
    phone = (phone or '').strip()
    if phone:
        persian_digits = '۰۱۲۳۴۵۶۷۸۹'
        arabic_digits = '٠١٢٣٤٥٦٧٨٩'
        for i in range(10):
            phone = phone.replace(persian_digits[i], str(i)).replace(arabic_digits[i], str(i))
        phone = re.sub(r'[^\d]', '', phone) or None

    customer = None
    if phone:
        customer = Customer.query.filter_by(phone=phone).first()
    if not customer:
        customer = Customer.query.filter_by(name=name).first()
    if not customer:
        customer = Customer(
            name=name,
            phone=phone,
            address=str(address) if (address and not str(address).isdigit()) else None,
            customer_type=customer_type or 'regular',
            total_purchases=0,
            outstanding_balance=0
        )
        db.session.add(customer)
        db.session.commit()
    else:
        changed = False
        if phone and not customer.phone:
            customer.phone = phone
            changed = True
        if address and not str(address).isdigit() and not customer.address:
            customer.address = str(address)
            changed = True
        if changed:
            db.session.commit()
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
        passed_chk = sum(chk.amount for chk in inv.cheques if chk.status == 'passed')
        immediate_paid = max((inv.paid_amount or 0), ((inv.paid_pos or 0) + (inv.paid_card or 0) + (inv.paid_cash or 0)))
        settled_amt = immediate_paid + passed_chk
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



