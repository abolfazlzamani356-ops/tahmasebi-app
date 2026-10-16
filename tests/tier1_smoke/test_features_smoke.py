import pytest
from app import app, db
from helpers import (
    calculate_seller_exact_stats,
    calculate_store_financial_summary,
    get_inventory_ai_insights,
    normalize_persian_text,
    get_persian_word_variants,
    safe_int,
    safe_float
)
from models import ProductCatalog, InventoryItem, Shop, User, Customer, Cheque

# Feature 1: Dual-Mode Switcher Smoke Tests
@pytest.mark.smoke
def test_f01_smoke_pos_view_contains_dashboard_link(seller_client):
    resp = seller_client.get('/pos')
    html = resp.get_data(as_text=True)
    assert '/seller_dashboard' in html

@pytest.mark.smoke
def test_f01_smoke_demo_pos_route_available(seller_client):
    resp = seller_client.get('/demo/pos')
    assert resp.status_code == 200

@pytest.mark.smoke
def test_f01_smoke_base_layout_loads(seller_client):
    resp = seller_client.get('/seller_dashboard')
    assert resp.status_code == 200

# Feature 2: High-Speed Catalog Virtualization Smoke Tests
@pytest.mark.smoke
def test_f02_smoke_catalog_stock_api_payload_structure(seller_client):
    resp = seller_client.get('/api/inventory/catalog-stock')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    if len(data) > 0:
        item = data[0]
        assert "id" in item
        assert "name" in item
        assert "sell_price" in item
        assert "stock_1" in item
        assert "stock_2" in item

@pytest.mark.smoke
def test_f02_smoke_catalog_count_substantial(app_ctx):
    count = ProductCatalog.query.count()
    assert count >= 100

@pytest.mark.smoke
def test_f02_smoke_persian_word_variants_functionality():
    vars = get_persian_word_variants("سینک")
    assert len(vars) >= 1
    assert any("سینک" in v for v in vars)

# Feature 3: Touch POS v2 Interface & Numpad Smoke Tests
@pytest.mark.smoke
def test_f03_smoke_pos_contains_vue_runtime(seller_client):
    resp = seller_client.get('/pos')
    html = resp.get_data(as_text=True)
    assert "vue.global.prod.js" in html

@pytest.mark.smoke
def test_f03_smoke_pos_contains_tailwind_runtime(seller_client):
    resp = seller_client.get('/pos')
    html = resp.get_data(as_text=True)
    assert "tailwind.js" in html

@pytest.mark.smoke
def test_f03_smoke_pos_contains_numpad_buttons(seller_client):
    resp = seller_client.get('/pos')
    html = resp.get_data(as_text=True)
    assert "handleNumpad" in html

# Feature 4: Proportional Combo Package Builder Smoke Tests
@pytest.mark.smoke
def test_f04_smoke_pos_contains_combo_modal(seller_client):
    resp = seller_client.get('/pos')
    html = resp.get_data(as_text=True)
    assert "showComboModal" in html
    assert "سازنده پکیج ترکیبی" in html

@pytest.mark.smoke
def test_f04_smoke_pos_combo_catalog_sum_feature(seller_client):
    resp = seller_client.get('/pos')
    html = resp.get_data(as_text=True)
    assert "comboCatalogSum" in html
    assert "comboAgreedPrice" in html

# Feature 5: Real DB Invoicing & Stock Deduction Smoke Tests
@pytest.mark.smoke
def test_f05_smoke_invoice_add_route_exists(seller_client):
    # Empty POST should handle cleanly without 404 or 500 unhandled
    resp = seller_client.post('/invoice/add', data={}, follow_redirects=True)
    assert resp.status_code == 200

@pytest.mark.smoke
def test_f05_smoke_inventory_model_fields(app_ctx):
    item = InventoryItem.query.first()
    if item:
        assert hasattr(item, "stock_quantity")
        assert hasattr(item, "buy_price")
        assert hasattr(item, "sell_price")

# Feature 6: Print Preview & Sensory Feedback Smoke Tests
@pytest.mark.smoke
def test_f06_smoke_pos_contains_sensory_feedback_hooks(seller_client):
    resp = seller_client.get('/pos')
    html = resp.get_data(as_text=True)
    assert "playTone" in html
    assert "vibrate" in html

@pytest.mark.smoke
def test_f06_smoke_print_templates_renderable(app_ctx):
    # Verify templates exist on filesystem
    from jinja2 import TemplateNotFound
    from flask import render_template
    try:
        html1 = render_template('print_pos.html', invoice=None, settings=None)
        assert html1 is not None
    except Exception as e:
        assert not isinstance(e, TemplateNotFound)

# Feature 7: Smart Inventory Inline Editing Smoke Tests
@pytest.mark.smoke
def test_f07_smoke_inventory_view_renders(admin_client):
    resp = admin_client.get('/inventory')
    assert resp.status_code == 200

@pytest.mark.smoke
def test_f07_smoke_inventory_quick_update_api_accessible(admin_client):
    # Testing quick stock API
    resp = admin_client.post('/api/inventory/quick_stock', json={})
    assert resp.status_code in [200, 400, 302]

# Feature 8: Stock Shortage Alerts & Transfers Smoke Tests
@pytest.mark.smoke
def test_f08_smoke_inventory_ai_insights_helper(app_ctx):
    insights = get_inventory_ai_insights()
    assert isinstance(insights, dict)
    assert "total_items_count" in insights
    assert "critical_count" in insights
    assert "critical_items" in insights

@pytest.mark.smoke
def test_f08_smoke_stock_transfer_model_exists(app_ctx):
    from models import StockTransfer
    assert StockTransfer.__tablename__ == "stock_transfers"

# Feature 9: Non-Blocking Bulk Price Update Smoke Tests
@pytest.mark.smoke
def test_f09_smoke_catalog_admin_view(admin_client):
    resp = admin_client.get('/admin/catalog')
    assert resp.status_code == 200

# Feature 10: Admin BI Interactive Charts Smoke Tests
@pytest.mark.smoke
def test_f10_smoke_admin_dashboard_charts_rendered(admin_client):
    resp = admin_client.get('/admin_dashboard')
    html = resp.get_data(as_text=True)
    assert "chart" in html.lower() or "canvas" in html.lower() or "dashboard" in html.lower()

# Feature 11: Brand Profitability & Commissions Smoke Tests
@pytest.mark.smoke
def test_f11_smoke_seller_commission_helper(app_ctx):
    seller = User.query.filter_by(role="seller").first()
    if seller:
        stats = calculate_seller_exact_stats(seller.id, 1405, 1, 1.0)
        assert isinstance(stats, dict)
        assert "net_sales" in stats
        assert "settled_commission" in stats

# Feature 12: Store Financial Balance Sheet Smoke Tests
@pytest.mark.smoke
def test_f12_smoke_store_financial_summary_helper(app_ctx):
    summary = calculate_store_financial_summary(1405, 1)
    assert isinstance(summary, dict)
    assert "gross_sales" in summary
    assert "store_net_profit" in summary
    assert "total_payroll" in summary

# Feature 13: Cheques Hub Jalali Monthly Calendar Smoke Tests
@pytest.mark.smoke
def test_f13_smoke_cheques_hub_view(admin_client):
    resp = admin_client.get('/admin/cheques')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "چک" in html

@pytest.mark.smoke
def test_f13_smoke_cheque_model_statuses(app_ctx):
    cheque = Cheque.query.first()
    if cheque:
        assert cheque.status in ['pending', 'passed', 'bounced', 'assigned']

# Feature 14: Customer Credit Ledger Inquiry Smoke Tests
@pytest.mark.smoke
def test_f14_smoke_customer_lookup_api_with_phone(seller_client):
    resp = seller_client.get('/api/customer/lookup?phone=09120000000')
    assert resp.status_code == 200
    data = resp.get_json()
    assert "found" in data

@pytest.mark.smoke
def test_f14_smoke_customers_list_view(admin_client):
    resp = admin_client.get('/admin/customers')
    assert resp.status_code == 200

# Additional Tier 1 Feature Coverage
@pytest.mark.smoke
def test_f01_smoke_navbar_links_for_admin(admin_client):
    resp = admin_client.get('/admin_dashboard')
    html = resp.get_data(as_text=True)
    assert 'انبارداری' in html
    assert 'چک' in html

@pytest.mark.smoke
def test_f02_smoke_catalog_has_multiple_categories(app_ctx):
    categories = db.session.query(ProductCatalog.category).distinct().all()
    cat_names = [c[0] for c in categories if c[0]]
    assert len(cat_names) >= 4

@pytest.mark.smoke
def test_f03_smoke_pos_search_input_present(seller_client):
    resp = seller_client.get('/pos')
    html = resp.get_data(as_text=True)
    assert 'searchQuery' in html

@pytest.mark.smoke
def test_f04_smoke_combo_confirm_button_present(seller_client):
    resp = seller_client.get('/pos')
    html = resp.get_data(as_text=True)
    assert 'confirmAddCombo' in html

@pytest.mark.smoke
def test_f05_smoke_shop_and_user_financial_fields(app_ctx):
    shop = Shop.query.first()
    assert hasattr(shop, 'rent_amount')
    seller = User.query.filter_by(role="seller").first()
    if seller:
        assert hasattr(seller, 'commission_rate')
        assert hasattr(seller, 'base_salary')

@pytest.mark.smoke
def test_f09_smoke_catalog_brands_present(app_ctx):
    brands = db.session.query(ProductCatalog.brand).distinct().all()
    brand_names = [b[0] for b in brands if b[0]]
    assert len(brand_names) >= 3

@pytest.mark.smoke
def test_f10_smoke_admin_dashboard_summary_cards(admin_client):
    resp = admin_client.get('/admin_dashboard')
    html = resp.get_data(as_text=True)
    assert 'فروش' in html or 'سود' in html

@pytest.mark.smoke
def test_f13_smoke_cheque_status_filter_options(admin_client):
    resp = admin_client.get('/admin/cheques?status=pending')
    assert resp.status_code == 200
