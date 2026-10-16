"""
Test suite for Milestone 1: Dual-Mode Foundation & Catalog Virtualization
Author: Worker M1
"""
import pytest
from bs4 import BeautifulSoup
from app import app, User


def test_dual_mode_switcher_in_base_and_seller_dashboard(seller_client):
    """Verify POS v2 switcher button in base.html and seller_dashboard.html."""
    res = seller_client.get('/seller_dashboard')
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # 1. Base navbar switcher button
    assert 'ورود به صندوق لمسی POS v2' in html
    assert 'setTahmasebiUiMode(\'pos_v2\')' in html
    assert '/pos' in html

    # 2. Function definitions in base.html
    assert 'function setTahmasebiUiMode(mode)' in html
    assert 'function getTahmasebiUiMode()' in html

    # 3. Seller dashboard header action button
    soup = BeautifulSoup(html, 'html.parser')
    pos_links = [a for a in soup.find_all('a', href=True) if a['href'] in ['/pos', '/demo/pos']]
    assert len(pos_links) >= 2  # At least navbar and seller_dashboard header/banner


def test_pos_v2_role_aware_return_seller(seller_client):
    """Verify role-aware return button in POS v2 routes seller to /seller_dashboard."""
    res = seller_client.get('/pos')
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Seller must return to /seller_dashboard
    assert 'href="/seller_dashboard"' in html
    assert 'setTahmasebiUiMode(\'classic_erp\')' in html
    assert 'بازگشت به داشبورد کلاسیک ERP' in html


def test_pos_v2_role_aware_return_admin(admin_client):
    """Verify role-aware return button in POS v2 routes admin to /admin_dashboard."""
    res = admin_client.get('/pos')
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Admin must return to /admin_dashboard
    assert 'href="/admin_dashboard"' in html
    assert 'setTahmasebiUiMode(\'classic_erp\')' in html
    assert 'بازگشت به داشبورد کلاسیک ERP' in html


def test_pos_v2_catalog_virtualization_and_search_tokens(seller_client):
    """Verify POS v2 contains virtual scrolling, SWR IndexedDB cache, and Persian tokenizer."""
    res = seller_client.get('/pos')
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # SWR & IndexedDB cache
    assert 'TahmasebiPosDB' in html
    assert 'catalog_cache' in html
    assert '/api/inventory/catalog-stock' in html
    assert '__TAHMASEBI_CATALOG_CACHE__' in html

    # Persian normalization
    assert 'normalizePersianText' in html
    assert '_normSearch' in html
    assert '_normSearchCompact' in html

    # Virtual scrolling container & 60fps RAF binding
    assert 'gridScrollContainer' in html
    assert 'onGridScroll' in html
    assert 'virtualTotalHeight' in html
    assert 'virtualOffsetY' in html
    assert 'visibleCards' in html

    # Touch Ergonomics (min-h-[48px], viewport-fit=cover)
    assert 'viewport-fit=cover' in html
    assert 'min-h-[48px]' in html


def test_catalog_stock_api_payload(seller_client):
    """Verify /api/inventory/catalog-stock returns catalog items with expected structure."""
    res = seller_client.get('/api/inventory/catalog-stock')
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list)
    assert len(data) >= 4000  # 4,091 catalog items in database
    
    first_item = data[0]
    for field in ['id', 'name', 'category', 'brand', 'code', 'sell_price', 'stock_1', 'stock_2']:
        assert field in first_item, f"Field {field} missing from catalog-stock API item"
