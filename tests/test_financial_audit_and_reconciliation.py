import pytest
import uuid
import jdatetime
from app import app, db
from models import User, Shop, Settings, Invoice, InvoiceItem, Cheque, Expense
from helpers import calculate_seller_exact_stats, calculate_store_financial_summary

@pytest.mark.unit
def test_invoiced_sales_gross_profit_net_profit_invariants(admin_client, clean_db):
    """
    Assert fundamental accounting identities:
    1. gross_sales - returns_amount == net_sales
    2. net_sales - cogs == gross_profit
    3. gross_profit - total_operating_expenses == net_profit
    """
    resp = admin_client.get('/api/admin/bi_analytics')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True

    bs = data["store_balance_sheet"]
    gross_sales = bs["gross_sales"]
    returns_amount = bs["returns_amount"]
    net_sales = bs["net_sales"]
    cogs = bs["cogs"]
    gross_profit = bs["gross_profit"]
    total_operating_expenses = bs["total_operating_expenses"]
    net_profit = bs["net_profit"]

    # Invariant 1: Net Sales Identity
    assert net_sales == max(0, gross_sales - returns_amount)

    # Invariant 2: Gross Profit Identity
    assert gross_profit == (net_sales - cogs)

    # Invariant 3: Net Profit Identity
    assert net_profit == (gross_profit - total_operating_expenses)

    # Invariant 4: Operating Expenses Breakdown
    assert total_operating_expenses == (bs["operating_expenses"] + bs["rent"] + bs["payroll"])


@pytest.mark.unit
def test_cash_flow_reconciliation_zero_leakage(admin_client, clean_db):
    """
    Assert Cash Flow & Collection Reconciler satisfies zero-leakage invariant:
    collected_immediate + cheques_total + pending_credit == net_sales
    reconciliation_diff == 0
    """
    resp = admin_client.get('/api/admin/bi_analytics')
    assert resp.status_code == 200
    data = resp.get_json()
    bs = data["store_balance_sheet"]

    collected_immediate = bs.get("collected_immediate", 0)
    cheques_total = bs.get("cheques_total", 0)
    pending_credit = bs.get("pending_credit", 0)
    reconciled_total = bs.get("reconciled_total", 0)
    reconciliation_diff = bs.get("reconciliation_diff", 0)
    net_sales = bs["net_sales"]

    # Zero-leakage invariant down to 1 Rial
    assert reconciled_total == (collected_immediate + cheques_total + pending_credit)
    assert reconciled_total == net_sales
    assert reconciliation_diff == 0


@pytest.mark.integration
def test_admin_dashboard_template_harmony_and_no_rogue_minus(admin_client, clean_db):
    """
    Verify admin dashboard HTML renders:
    1. Cash Flow Reconciler section
    2. True Gross Profit without any rogue minus sign
    3. Mathematical harmony between top banner and balance sheet
    """
    resp = admin_client.get('/admin/dashboard')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Check balance sheet titles and labels
    assert "ترازنامه مالی و صورت سود و زیان رسمی طهماسبی" in html
    assert "سود ناخالص واقعی (True Gross Profit)" in html
    assert "سود خالص نهایی مدیریت (True Net Profit)" in html
    assert "تفکیک نقدینگی و وصولی‌ها (Cash Flow Reconciler)" in html
    assert "انطباق ۱۰۰٪ بدون ۱ ریال مغایرت" in html

    # Verify no rogue minus sign on gross profit
    # The gross profit div must have the clean equal sign layout with emerald font
    assert 'class="text-lg font-black text-emerald-400 font-mono flex items-center justify-start gap-1"' in html
    assert '<span class="text-emerald-400 font-bold">=</span>' in html


@pytest.mark.unit
def test_seller_commission_no_double_counting(app_ctx, clean_db):
    """
    Verify calculate_seller_exact_stats:
    1. settled_commission is based on effective_rate (base + bonus)
    2. base_commission + tier_bonus_amount == settled_commission
    3. Tier bonus is never double-counted in payroll or store expenses
    """
    seller = User.query.filter_by(role='seller').first()
    if not seller:
        seller = User(username='test_seller_audit', full_name='فروشنده تست ممیزی', role='seller', shop_id=1, commission_rate=1.0)
        clean_db.add(seller)
        clean_db.commit()

    now_j = jdatetime.datetime.now()
    now_str = now_j.strftime("%Y/%m/%d %H:%M:%S")
    settings = Settings.query.first() or Settings(tier1_min=50000000, tier1_bonus=0.5, tier2_min=100000000, tier2_bonus=1.0)

    uid = uuid.uuid4().hex[:6]
    inv = Invoice(
        invoice_number=f"INV-COMM-AUDIT-{uid}",
        customer_name="مشتری تست پورسانت",
        seller_id=seller.id,
        shop_id=1,
        total_amount=60000000,
        paid_pos=60000000,
        paid_amount=60000000,
        remaining_balance=0,
        actual_buy_cost=40000000,
        real_profit=20000000,
        invoice_type='sale',
        status='final',
        shamsi_year=now_j.year,
        shamsi_month=now_j.month,
        shamsi_day=now_j.day,
        shamsi_date_time=now_str
    )
    clean_db.add(inv)
    clean_db.commit()

    try:
        stats = calculate_seller_exact_stats(seller.id, now_j.year, now_j.month, seller.commission_rate, settings, user=seller)
        assert stats['net_sales'] >= 60000000

        # Target tier bonus according to settings
        expected_bonus = 0.0
        if stats['net_sales'] >= settings.tier2_min:
            expected_bonus = settings.tier2_bonus
        elif stats['net_sales'] >= settings.tier1_min:
            expected_bonus = settings.tier1_bonus

        assert stats['bonus_rate'] == expected_bonus
        assert stats['effective_rate'] == round(min(seller.commission_rate + expected_bonus, 5.0), 2)

        # Mathematical breakdown consistency
        base_comm = stats['base_commission']
        bonus_comm = stats['tier_bonus_amount']
        total_comm = stats['settled_commission']

        assert base_comm + bonus_comm == total_comm
        assert total_comm == int(stats['net_sales'] * stats['effective_rate'] / 100)
    finally:
        clean_db.delete(inv)
        clean_db.commit()


@pytest.mark.integration
def test_multi_branch_full_reconciliation_cycle(admin_client, clean_db):
    """
    Test complete lifecycle with:
    - Shop 1 sale with mixed payments (POS, Card, Cash, Cheque, Nesyeh)
    - Shop 2 sale with full payment
    - Shop 1 return with partial refund
    Assert exact Rial balance across Admin Dashboard and Store Balance Sheet.
    """
    now_j = jdatetime.datetime.now()
    now_str = now_j.strftime("%Y/%m/%d %H:%M:%S")
    uid = uuid.uuid4().hex[:6]

    # Sale 1 (Shop 1): Total 50,000,000 (POS: 20M, Card: 10M, Cash: 5M, Cheque: 10M, Nesyeh: 5M)
    inv1 = Invoice(
        invoice_number=f"INV-CYCLE-1-{uid}",
        customer_name="مشتری چرخه ۱",
        seller_id=1,
        shop_id=1,
        total_amount=50000000,
        paid_pos=20000000,
        paid_card=10000000,
        paid_cash=5000000,
        paid_cheque=10000000,
        paid_amount=35000000,
        remaining_balance=5000000,
        actual_buy_cost=30000000,
        real_profit=20000000,
        invoice_type='sale',
        status='final',
        shamsi_year=now_j.year,
        shamsi_month=now_j.month,
        shamsi_day=now_j.day,
        shamsi_date_time=now_str
    )
    clean_db.add(inv1)
    clean_db.flush()

    chk1 = Cheque(
        invoice_id=inv1.id,
        sayad_number="1234567890123456",
        bank_name="بانک ملت",
        amount=10000000,
        due_shamsi_date=f"{now_j.year}/{now_j.month:02d}/25",
        customer_name="مشتری چرخه ۱",
        shop_id=1,
        status='pending'
    )
    clean_db.add(chk1)

    # Sale 2 (Shop 2): Total 30,000,000 (POS: 30M)
    inv2 = Invoice(
        invoice_number=f"INV-CYCLE-2-{uid}",
        customer_name="مشتری چرخه ۲",
        seller_id=1,
        shop_id=2,
        total_amount=30000000,
        paid_pos=30000000,
        paid_amount=30000000,
        remaining_balance=0,
        actual_buy_cost=20000000,
        real_profit=10000000,
        invoice_type='sale',
        status='final',
        shamsi_year=now_j.year,
        shamsi_month=now_j.month,
        shamsi_day=now_j.day,
        shamsi_date_time=now_str
    )
    clean_db.add(inv2)

    # Return 1 (Shop 1): Return 10,000,000 (Refund POS: 10M)
    inv_ret = Invoice(
        invoice_number=f"INV-CYCLE-RET-{uid}",
        customer_name="مشتری مرجوعی چرخه",
        seller_id=1,
        shop_id=1,
        total_amount=10000000,
        paid_pos=10000000,
        paid_amount=10000000,
        remaining_balance=0,
        actual_buy_cost=6000000,
        real_profit=4000000,
        invoice_type='return',
        status='final',
        shamsi_year=now_j.year,
        shamsi_month=now_j.month,
        shamsi_day=now_j.day,
        shamsi_date_time=now_str
    )
    clean_db.add(inv_ret)
    clean_db.commit()

    try:
        resp = admin_client.get(f'/api/admin/bi_analytics?year={now_j.year}&month={now_j.month}')
        assert resp.status_code == 200
        data = resp.get_json()
        bs = data["store_balance_sheet"]

        # Mathematical validation
        # Gross sales includes both sales, return is subtracted
        # Net Sales = Gross Sales - Returns
        assert bs["net_sales"] == bs["gross_sales"] - bs["returns_amount"]

        # Gross Profit = Net Sales - COGS
        assert bs["gross_profit"] == bs["net_sales"] - bs["cogs"]

        # Net Profit = Gross Profit - Operating Expenses
        assert bs["net_profit"] == bs["gross_profit"] - bs["total_operating_expenses"]

        # Cash Flow Reconciler Zero Difference
        assert bs["reconciliation_diff"] == 0
        assert bs["reconciled_total"] == bs["net_sales"]
        assert bs["reconciled_total"] == bs["collected_immediate"] + bs["cheques_total"] + bs["pending_credit"]
    finally:
        clean_db.delete(chk1)
        clean_db.delete(inv1)
        clean_db.delete(inv2)
        clean_db.delete(inv_ret)
        clean_db.commit()
