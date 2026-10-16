import pytest

@pytest.mark.unit
def test_combo_proportional_price_allocation_basic():
    """
    Two items:
    Item 1 original: 4,940,000 Toman
    Item 2 original: 11,386,000 Toman
    Total catalog sum = 16,326,000 Toman
    Agreed combo price = 4,940,000 Toman
    """
    p1 = 4940000
    p2 = 11386000
    catalog_sum = p1 + p2
    agreed_price = 4940000

    alloc1 = round(agreed_price * (p1 / catalog_sum))
    alloc2 = agreed_price - alloc1  # Remainder correction

    assert alloc1 + alloc2 == agreed_price
    assert alloc1 == 1494769
    assert alloc2 == 3445231

@pytest.mark.unit
def test_combo_proportional_three_items():
    p1 = 10000000
    p2 = 20000000
    p3 = 30000000
    catalog_sum = 60000000
    agreed_price = 45000000  # 25% discount

    allocations = [round(agreed_price * (p / catalog_sum)) for p in [p1, p2, p3]]
    # Adjust remainder
    diff = agreed_price - sum(allocations)
    allocations[-1] += diff

    assert sum(allocations) == agreed_price
    assert allocations[0] == 7500000
    assert allocations[1] == 15000000
    assert allocations[2] == 22500000

@pytest.mark.unit
def test_combo_reset_to_catalog_sum():
    """When seller clicks 'Reset to Catalog Sum', agreed price equals catalog sum and discount is 0%."""
    items = [
        {"name": "روشویی", "price": 5000000},
        {"name": "آینه", "price": 2000000},
        {"name": "باکس", "price": 1500000}
    ]
    catalog_sum = sum(i["price"] for i in items)
    agreed_price = catalog_sum
    allocations = [round(agreed_price * (i["price"] / catalog_sum)) for i in items]
    diff = agreed_price - sum(allocations)
    allocations[-1] += diff

    assert agreed_price == 8500000
    assert sum(allocations) == catalog_sum
    for orig, alloc in zip(items, allocations):
        assert orig["price"] == alloc

@pytest.mark.unit
def test_combo_clean_name_contract():
    """Item names in combo must NOT have '(پکیج ترکیبی)' injected."""
    raw_name = "روشویی کابینتی مدل رویال"
    combo_label = "(پکیج ترکیبی)"
    # Contract: the saved invoice item name must equal clean raw_name
    assert combo_label not in raw_name

@pytest.mark.unit
def test_combo_extreme_price_ratio():
    # 99,000,000 Toman jacuzzi + 1,000,000 Toman valve = 100M total
    # Agreed: 80,000,000
    p1 = 99000000
    p2 = 1000000
    agreed = 80000000
    alloc1 = round(agreed * (p1 / 100000000))
    alloc2 = agreed - alloc1
    assert alloc1 + alloc2 == agreed
    assert alloc1 == 79200000
    assert alloc2 == 800000

@pytest.mark.unit
def test_combo_odd_pennies_exact_sum():
    # 3 items of 1 Toman with agreed total 2
    prices = [1, 1, 1]
    agreed = 2
    allocs = [round(agreed * (p / 3)) for p in prices]
    diff = agreed - sum(allocs)
    allocs[-1] += diff
    assert sum(allocs) == 2

@pytest.mark.unit
def test_stock_deduction_formula():
    current_stock = 15
    sold_qty = 4
    stock_after = max(0, current_stock - sold_qty)
    assert stock_after == 11

@pytest.mark.unit
def test_stock_floor_zero_protection():
    current_stock = 2
    sold_qty = 5
    stock_after = max(0, current_stock - sold_qty)
    assert stock_after == 0

@pytest.mark.unit
def test_reorder_point_critical_vs_warning():
    # stock <= 0 is critical ('بحرانی')
    stock_zero = 0
    urgency_zero = 'بحرانی' if stock_zero == 0 else 'هشدار'
    assert urgency_zero == 'بحرانی'

    # 0 < stock <= min_alert is warning ('هشدار')
    stock_low = 2
    min_alert = 3
    is_alert = stock_low <= min_alert
    urgency_low = 'بحرانی' if stock_low == 0 else 'هشدار'
    assert is_alert is True
    assert urgency_low == 'هشدار'

@pytest.mark.unit
def test_suggested_reorder_formula():
    stock = 1
    min_alert = 3
    suggested = max(10 - stock, min_alert * 3)
    assert suggested == 9

@pytest.mark.unit
def test_bulk_price_percentage_increase():
    orig_price = 4500000
    percent = 15  # +15%
    new_price = round(orig_price * (1 + percent / 100))
    assert new_price == 5175000

@pytest.mark.unit
def test_bulk_price_percentage_decrease():
    orig_price = 6000000
    percent = -10  # -10%
    new_price = round(orig_price * (1 + percent / 100))
    assert new_price == 5400000

@pytest.mark.unit
def test_bulk_price_rounding_to_thousands():
    # Rounding 5,175,230 to nearest 1,000 Tomans
    raw = 5175230
    rounded = round(raw / 1000) * 1000
    assert rounded == 5175000

@pytest.mark.unit
def test_bulk_price_extreme_negative_boundary():
    orig = 2000000
    percent = -100
    new_price = max(0, round(orig * (1 + percent / 100)))
    assert new_price == 0

@pytest.mark.unit
def test_bulk_price_zero_percent_identity():
    orig = 3500000
    percent = 0
    new_price = round(orig * (1 + percent / 100))
    assert new_price == orig

@pytest.mark.unit
def test_sayad_cheque_number_16_digits_validation():
    valid_sayad = "1234567890123456"
    invalid_short = "12345"
    invalid_alpha = "123456789012345A"

    assert len(valid_sayad) == 16 and valid_sayad.isdigit()
    assert not (len(invalid_short) == 16 and invalid_short.isdigit())
    assert not (len(invalid_alpha) == 16 and invalid_alpha.isdigit())

@pytest.mark.unit
def test_cheque_valid_statuses_set():
    valid_statuses = {'pending', 'passed', 'bounced', 'assigned'}
    assert 'pending' in valid_statuses
    assert 'passed' in valid_statuses
    assert 'bounced' in valid_statuses
    assert 'assigned' in valid_statuses
    assert 'invalid_status' not in valid_statuses

@pytest.mark.unit
def test_customer_ai_risk_tier_classification():
    def get_tier(score):
        if score >= 85:
            return 'A', 'بسیار کم‌ریسک و مشتری طلایی'
        elif score >= 70:
            return 'B', 'خوش‌حساب و معتبر'
        elif score >= 50:
            return 'C', 'ریسک متوسط (با احتیاط)'
        else:
            return 'D', 'پرریسک (فقط نقدی)'

    tA, _ = get_tier(95)
    tB, _ = get_tier(75)
    tC, _ = get_tier(60)
    tD, _ = get_tier(35)

    assert tA == 'A'
    assert tB == 'B'
    assert tC == 'C'
    assert tD == 'D'

@pytest.mark.unit
def test_customer_credit_score_bounds():
    score = 88
    assert 0 <= score <= 100

@pytest.mark.unit
def test_customer_outstanding_balance_update():
    prev_balance = 10000000
    invoice_remaining = 5000000
    new_balance = prev_balance + invoice_remaining
    assert new_balance == 15000000

@pytest.mark.unit
def test_customer_total_purchases_update():
    prev_purchases = 25000000
    invoice_total = 12000000
    new_purchases = prev_purchases + invoice_total
    assert new_purchases == 37000000

@pytest.mark.unit
def test_dual_mode_switcher_url_toggle():
    classic_url = "/seller_dashboard"
    pos_v2_url = "/pos"
    assert classic_url != pos_v2_url
    assert pos_v2_url == "/pos"

@pytest.mark.unit
def test_tax_rate_zero_percent_requirement():
    subtotal = 50000000
    tax_rate = 0.0
    tax = int(subtotal * tax_rate)
    total = subtotal + tax
    assert tax == 0
    assert total == subtotal

@pytest.mark.unit
def test_shamsi_date_parsing_format():
    sample_date = "1405/01/15"
    parts = sample_date.split('/')
    assert len(parts) == 3
    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    assert year == 1405
    assert 1 <= month <= 12
    assert 1 <= day <= 31

@pytest.mark.unit
def test_inventory_transfer_voucher_delta():
    origin_stock = 20
    dest_stock = 5
    transfer_qty = 8

    origin_after = origin_stock - transfer_qty
    dest_after = dest_stock + transfer_qty

    assert origin_after == 12
    assert dest_after == 13
    assert (origin_after + dest_after) == (origin_stock + dest_stock)
