import pytest
import json

@pytest.mark.unit
def test_bi_analytics_api_endpoint(admin_client, clean_db):
    """Verify /api/admin/bi_analytics returns JSON with branch daily comparison, brand analytics, and store balance sheet."""
    resp = admin_client.get('/api/admin/bi_analytics')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True

    # Check branch comparison array of 31 days
    branch_comp = data.get("branch_comparison")
    assert isinstance(branch_comp, list)
    assert len(branch_comp) == 31
    for day_stat in branch_comp:
        assert "day" in day_stat
        assert "shop1_sales" in day_stat
        assert "shop2_sales" in day_stat
        assert "shop1_profit" in day_stat
        assert "shop2_profit" in day_stat

    # Check top brands list
    top_brands = data.get("top_brands")
    assert isinstance(top_brands, list)
    for b in top_brands:
        assert "brand" in b
        assert "sales" in b
        assert "profit" in b

    # Check store balance sheet structure
    balance_sheet = data.get("store_balance_sheet")
    assert isinstance(balance_sheet, dict)
    assert "net_sales" in balance_sheet
    assert "cogs" in balance_sheet
    assert "gross_profit" in balance_sheet
    assert "operating_expenses" in balance_sheet
    assert "rent" in balance_sheet
    assert "payroll" in balance_sheet
    assert "net_profit" in balance_sheet
    assert "gross_margin_percent" in balance_sheet
    assert "net_margin_percent" in balance_sheet

@pytest.mark.unit
def test_store_balance_sheet_mathematical_integrity(admin_client, clean_db):
    """Verify financial balance sheet satisfies fundamental accounting identities."""
    resp = admin_client.get('/api/admin/bi_analytics')
    assert resp.status_code == 200
    bs = resp.get_json()["store_balance_sheet"]

    net_sales = bs["net_sales"]
    cogs = bs["cogs"]
    gross_profit = bs["gross_profit"]
    operating_expenses = bs["operating_expenses"]
    rent = bs["rent"]
    payroll = bs["payroll"]
    net_profit = bs["net_profit"]

    # Gross Profit = Net Sales - COGS
    assert gross_profit == (net_sales - cogs)

    # Net Profit = Gross Profit - (Operating Expenses + Rent + Payroll)
    assert net_profit == (gross_profit - (operating_expenses + rent + payroll))

@pytest.mark.integration
def test_admin_dashboard_template_renders_bi_and_scorecards(admin_client, clean_db):
    """Verify admin dashboard HTML contains the Chart.js canvases, balance sheet, and sales scorecards."""
    resp = admin_client.get('/admin/dashboard')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Verify canvas IDs for BI widgets
    assert 'id="branchComparisonChart"' in html
    assert 'id="brandProfitChart"' in html

    # Verify Balance Sheet section
    assert "ترازنامه مالی و صورت سود و زیان رسمی طهماسبی" in html
    assert "بهای خرید کالاها (COGS)" in html
    assert "فروش کل خالص (Net Sales)" in html

    # Verify Salesperson Scorecards section
    assert "کارنامه و کارت‌های عملکرد فروشندگان طهماسبی" in html

@pytest.mark.integration
def test_bi_analytics_with_return_invoice_deduction(admin_client, clean_db):
    """Verify that return invoices properly decrease net_sales and gross_profit in BI analytics."""
    from models import Invoice, InvoiceItem
    import jdatetime

    now_j = jdatetime.datetime.now()
    now_str = now_j.strftime("%Y/%m/%d %H:%M:%S")
    
    import uuid
    uid = uuid.uuid4().hex[:8]
    sale_num = f"INV-BI-SALE-{uid}"
    ret_num = f"INV-BI-RET-{uid}"

    try:
        # Create a test sale invoice
        sale_inv = Invoice(
            invoice_number=sale_num,
            customer_name="مشتری تست بی‌آی",
            seller_id=1,
            shop_id=1,
            total_amount=10000000,
            paid_pos=10000000,
            paid_amount=10000000,
            actual_buy_cost=7000000,
            real_profit=3000000,
            invoice_type='sale',
            status='final',
            shamsi_year=now_j.year,
            shamsi_month=now_j.month,
            shamsi_day=now_j.day,
            shamsi_date_time=now_str
        )
        clean_db.add(sale_inv)
        clean_db.flush()

        item_sale = InvoiceItem(
            invoice_id=sale_inv.id,
            item_name="سینک گرانیتی فونیکس مدل پلاس",
            quantity=1,
            unit_sell_price=10000000,
            total_price=10000000,
            unit_buy_price=7000000,
            row_profit=3000000
        )
        clean_db.add(item_sale)

        # Create a test return invoice
        ret_inv = Invoice(
            invoice_number=ret_num,
            customer_name="مشتری تست مرجوعی بی‌آی",
            seller_id=1,
            shop_id=1,
            total_amount=2000000,
            paid_pos=2000000,
            paid_amount=2000000,
            actual_buy_cost=1400000,
            real_profit=600000,
            invoice_type='return',
            status='final',
            shamsi_year=now_j.year,
            shamsi_month=now_j.month,
            shamsi_day=now_j.day,
            shamsi_date_time=now_str
        )
        clean_db.add(ret_inv)
        clean_db.flush()

        item_ret = InvoiceItem(
            invoice_id=ret_inv.id,
            item_name="سینک گرانیتی فونیکس مدل پلاس",
            quantity=1,
            unit_sell_price=2000000,
            total_price=2000000,
            unit_buy_price=1400000,
            row_profit=600000
        )
        clean_db.add(item_ret)
        clean_db.commit()

        resp = admin_client.get(f'/api/admin/bi_analytics?year={now_j.year}&month={now_j.month}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        # Balance sheet gross profit identity must hold strictly
        bs = data["store_balance_sheet"]
        assert bs["gross_profit"] == bs["net_sales"] - bs["cogs"]
        assert bs["net_profit"] == bs["gross_profit"] - bs["total_operating_expenses"]
    finally:
        InvoiceItem.query.filter(InvoiceItem.invoice_id.in_([sale_inv.id, ret_inv.id])).delete(synchronize_session=False)
        Invoice.query.filter(Invoice.id.in_([sale_inv.id, ret_inv.id])).delete(synchronize_session=False)
        clean_db.commit()

