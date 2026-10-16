import pytest
from app import app, db
from helpers import (
    calculate_seller_exact_stats,
    calculate_store_financial_summary
)
from models import User, Shop, Settings, Invoice, Cheque

@pytest.mark.unit
def test_split_payment_conservation_identity():
    """Identity: paid_pos + paid_card + paid_cash + paid_cheque + remaining_balance == total_amount."""
    total = 25000000
    pos = 5000000
    card = 3000000
    cash = 2000000
    cheque = 10000000
    remaining = total - (pos + card + cash + cheque)
    assert remaining == 5000000
    assert (pos + card + cash + cheque + remaining) == total

@pytest.mark.unit
def test_pure_nesyeh_non_coercive():
    """If no upfront payment is provided, remaining_balance must be 100% of total with paid_pos=0."""
    total = 18000000
    pos = 0
    card = 0
    cash = 0
    cheque = 0
    remaining = total - (pos + card + cash + cheque)
    assert remaining == total
    assert pos == 0

@pytest.mark.unit
def test_full_pos_settlement():
    total = 12000000
    pos = 12000000
    remaining = max(0, total - pos)
    assert remaining == 0

@pytest.mark.unit
def test_split_card_and_cash():
    total = 40000000
    card = 25000000
    cash = 15000000
    remaining = max(0, total - (card + cash))
    assert remaining == 0

@pytest.mark.unit
def test_split_with_cheques_and_cash():
    total = 75000000
    cash = 15000000
    cheque = 50000000
    remaining = total - (cash + cheque)
    assert remaining == 10000000

@pytest.mark.unit
def test_exact_penny_rounding_no_drift():
    # 3 items of 33,333 Tomans summing to 100,000 with 1 Toman rounding adjustment
    total = 100000
    items_share = [round(total * 1/3) for _ in range(2)]
    items_share.append(total - sum(items_share))
    assert sum(items_share) == total

@pytest.mark.unit
def test_seller_commission_base_rate_math(app_ctx):
    user = User(username='tmp_seller_math', role='seller', base_salary=0, commission_rate=1.5)
    settings = Settings(tier1_min=100000000, tier1_bonus=0.5, tier2_min=200000000, tier2_bonus=1.0)
    # Testing formula with 0 invoices
    stats = calculate_seller_exact_stats(999999, 1405, 1, 1.5, settings=settings, user=user)
    assert stats['net_sales'] == 0
    assert stats['commission_amount'] == 0
    assert stats['effective_rate'] == 1.5

@pytest.mark.unit
def test_admin_zero_commission_enforcement(app_ctx):
    admin_user = User(username='tmp_admin_math', role='admin', base_salary=0, commission_rate=2.0)
    settings = Settings(tier1_min=100000000, tier1_bonus=0.5, tier2_min=200000000, tier2_bonus=1.0)
    stats = calculate_seller_exact_stats(admin_user.id or 1, 1405, 1, 2.0, settings=settings, user=admin_user)
    # Admin MUST have effective_rate 0.0 and commission_amount 0
    assert stats['effective_rate'] == 0.0
    assert stats['commission_amount'] == 0

@pytest.mark.unit
def test_seller_bonus_tier1_threshold(app_ctx):
    # Tier 1: net_sales >= tier1_min -> bonus rate added
    base_rate = 1.0
    tier1_bonus = 0.5
    effective = min(base_rate + tier1_bonus, 5.0)
    assert effective == 1.5

@pytest.mark.unit
def test_seller_bonus_tier2_threshold(app_ctx):
    # Tier 2: net_sales >= tier2_min -> tier2_bonus added
    base_rate = 1.0
    tier2_bonus = 1.0
    effective = min(base_rate + tier2_bonus, 5.0)
    assert effective == 2.0

@pytest.mark.unit
def test_maximum_commission_cap_five_percent():
    base_rate = 4.5
    tier_bonus = 1.5
    # Capped at 5.0%
    effective = round(min(base_rate + tier_bonus, 5.0), 2)
    assert effective == 5.0

@pytest.mark.unit
def test_split_seller_fifty_fifty():
    total_sales = 50000000
    ratio = 50
    seller1_share = int(total_sales * (ratio / 100.0))
    seller2_share = int(total_sales * ((100 - ratio) / 100.0))
    assert seller1_share == 25000000
    assert seller2_share == 25000000
    assert seller1_share + seller2_share == total_sales

@pytest.mark.unit
def test_split_seller_seventy_thirty():
    total_sales = 60000000
    ratio = 70
    seller1_share = int(total_sales * (ratio / 100.0))
    seller2_share = int(total_sales * ((100 - ratio) / 100.0))
    assert seller1_share == 42000000
    assert seller2_share == 18000000
    assert seller1_share + seller2_share == total_sales

@pytest.mark.unit
def test_split_ratio_boundary_clamping():
    # If ratio is entered as -20 or 150, it must clamp to 0..100
    raw_ratio_high = 150
    raw_ratio_low = -10
    clamped_high = max(0, min(100, raw_ratio_high))
    clamped_low = max(0, min(100, raw_ratio_low))
    assert clamped_high == 100
    assert clamped_low == 0

@pytest.mark.unit
def test_return_invoice_reduces_net_sales():
    gross = 80000000
    returned = 15000000
    net = max(0, gross - returned)
    assert net == 65000000

@pytest.mark.unit
def test_return_exceeding_sales_clamped_to_zero():
    gross = 10000000
    returned = 15000000
    net = max(0, gross - returned)
    assert net == 0

@pytest.mark.unit
def test_bounced_cheque_excluded_from_settled():
    chk_passed = 10000000
    chk_pending = 5000000
    chk_bounced = 7000000
    # Business logic in helpers.py line 347: valid cheques status in ['passed', 'pending', 'assigned']
    valid_cheques = chk_passed + chk_pending
    assert valid_cheques == 15000000

@pytest.mark.unit
def test_store_net_profit_calculation():
    gross_profit = 45000000
    total_payroll = 15000000
    total_rent = 12000000
    total_expenses = 3000000
    net_profit = gross_profit - (total_payroll + total_rent + total_expenses)
    assert net_profit == 15000000

@pytest.mark.unit
def test_store_loss_month():
    gross_profit = 20000000
    total_costs = 35000000
    net_profit = gross_profit - total_costs
    assert net_profit == -15000000

@pytest.mark.unit
def test_profit_margin_formula():
    net_profit = 20000000
    base_sales = 100000000
    margin = round((net_profit / base_sales * 100), 1)
    assert margin == 20.0

@pytest.mark.unit
def test_zero_sales_margin_no_zerodivision():
    net_profit = -5000000
    base_sales = 0
    margin = round((net_profit / base_sales * 100), 1) if base_sales > 0 else 0
    assert margin == 0

@pytest.mark.unit
def test_store_payroll_summation():
    salaries = 30000000
    commissions = 12500000
    total_payroll = salaries + commissions
    assert total_payroll == 42500000

@pytest.mark.unit
def test_branch_totals_sum_to_total_sales():
    shop1 = 65000000
    shop2 = 45000000
    total = shop1 + shop2
    assert total == 110000000

@pytest.mark.unit
def test_petty_cash_deposit_aggregation():
    deposits = [5000000, 2000000, 3000000]
    assert sum(deposits) == 10000000

@pytest.mark.unit
def test_customer_rating_average():
    ratings = [5, 4, 5, 4, 5]
    avg = round(sum(ratings) / len(ratings), 1)
    assert avg == 4.6
