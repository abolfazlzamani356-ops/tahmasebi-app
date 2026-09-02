import re
import json
import jdatetime
from datetime import datetime
from models import db, User, Invoice, InvoiceItem, InventoryItem, StockLog, AuditLog, Settings, SalarySlip, Customer, Cheque

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

def log_activity(action, user_name="سیستم", category="عمومی"):
    now_str = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M:%S")
    log = AuditLog(action=action, user_name=user_name, category=category, shamsi_date_time=now_str)
    db.session.add(log)
    db.session.commit()

def record_stock_change(item_id, shop_id, change_type, quantity, reference_id, user_name, description=""):
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
        user_name=user_name,
        shamsi_date_time=now_str
    )
    db.session.add(log)
    db.session.commit()

def calculate_seller_exact_stats(user_id, year, month, base_commission_rate, settings=None):
    """
    محاسبه دقیق آمار فروش، پورسانت نقدی، پورسانت معلق، تعداد فاکتورها، مرجوعی‌ها و رضایت مشتری
    """
    if not settings:
        settings = Settings.query.first()

    invoices = Invoice.query.filter(
        (Invoice.seller_id == user_id) | (Invoice.second_seller_id == user_id),
        Invoice.shamsi_year == year,
        Invoice.shamsi_month == month,
        Invoice.status == 'final'
    ).all()

    gross_sales = 0
    net_sales = 0
    total_cost = 0
    real_profit_share = 0
    sales_count = 0
    returns_count = 0
    ratings = []
    
    pending_commission_sales = 0 # فروش‌هایی که چک پاس‌نشده یا مانده بیعانه دارند

    for inv in invoices:
        # محاسبه درصد تسهیم فروشنده
        ratio = 1.0
        if inv.second_seller_id:
            if inv.seller_id == user_id:
                ratio = (inv.split_ratio if inv.split_ratio is not None else 100) / 100.0
            else:
                ratio = (100 - (inv.split_ratio if inv.split_ratio is not None else 100)) / 100.0

        item_amount = int(inv.total_amount * ratio)
        item_cost = int((inv.actual_buy_cost or 0) * ratio)
        item_profit = int((inv.real_profit or 0) * ratio)

        if inv.invoice_type == 'sale':
            gross_sales += item_amount
            net_sales += item_amount
            total_cost += item_cost
            real_profit_share += item_profit
            sales_count += 1
            if inv.customer_rating:
                ratings.append(inv.customer_rating)
                
            # بررسی اینکه آیا فاکتور دارای مانده پرداخت‌نشده یا چک پاس‌نشده است
            has_bounced_cheque = False
            for chk in inv.cheques:
                if chk.status == 'bounced':
                    has_bounced_cheque = True
                elif chk.status == 'pending':
                    pending_commission_sales += int(chk.amount * ratio)

            if inv.payment_method == 'deposit' and inv.total_amount > (inv.paid_amount or 0):
                remaining = (inv.total_amount - (inv.paid_amount or 0))
                pending_commission_sales += int(remaining * ratio)

        elif inv.invoice_type == 'return':
            net_sales -= item_amount
            total_cost -= item_cost
            real_profit_share -= item_profit
            returns_count += 1

    net_sales = max(net_sales, 0)
    
    # محاسبه پاداش تارگت پله‌ای
    bonus = 0.0
    tier_achieved = 0
    if settings:
        if net_sales >= settings.tier2_min:
            bonus = settings.tier2_bonus
            tier_achieved = 2
        elif net_sales >= settings.tier1_min:
            bonus = settings.tier1_bonus
            tier_achieved = 1

    effective_rate = round(min(base_commission_rate + bonus, 5.0), 2)
    
    # پورسانت کل
    total_commission_calculated = int((net_sales * effective_rate) / 100)
    
    # پورسانت معلق (ناشی از چک‌های در انتظار یا مانده بیعانه)
    pending_commission_amount = int((pending_commission_sales * effective_rate) / 100)
    # پورسانت قطعی و وصول شده
    settled_commission_amount = max(total_commission_calculated - pending_commission_amount, 0)
    
    tier_bonus_amount = int((net_sales * bonus) / 100)
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 5.0

    return {
        'gross_sales': gross_sales,
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

def get_or_create_customer(name, phone=None, address=None):
    if not name:
        return None
    name = name.strip()
    customer = None
    if phone:
        phone = phone.strip()
        customer = Customer.query.filter_by(phone=phone).first()
    if not customer:
        customer = Customer.query.filter_by(name=name).first()
    if not customer:
        customer = Customer(
            name=name,
            phone=phone,
            address=address,
            customer_type='regular',
            total_purchases=0,
            outstanding_balance=0
        )
        db.session.add(customer)
        db.session.commit()
    elif phone and not customer.phone:
        customer.phone = phone
        db.session.commit()
    return customer

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
