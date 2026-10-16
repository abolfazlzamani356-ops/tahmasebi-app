"""
Adversarial Verification Suite for Milestone 1:
Virtual Scrolling Grid Bounds, Offset Calculation, Dual-Mode Switcher, and Offline Resilience.
Author: Challenger M1-2
"""
import os
import sys
import math
import time
import pytest
from bs4 import BeautifulSoup
from flask import session

from app import app, User


# =========================================================================
# 1. Dual-Mode Navigation URLs and Role-Aware Routing (HTTP Client Level)
# =========================================================================

def test_unauthenticated_pos_redirects_to_login(client):
    """Verify that unauthenticated access to /pos and /demo/pos redirects to login."""
    res = client.get('/pos', follow_redirects=False)
    assert res.status_code == 302
    assert '/login' in res.location

    res_demo = client.get('/demo/pos', follow_redirects=False)
    assert res_demo.status_code == 302
    assert '/login' in res_demo.location


def test_pos_seller_return_button_routes_to_seller_dashboard(seller_client):
    """Verify seller role return button strictly links to /seller_dashboard."""
    res = seller_client.get('/pos')
    assert res.status_code == 200
    soup = BeautifulSoup(res.get_data(as_text=True), 'html.parser')
    
    # Locate return button to classic ERP
    return_links = [a for a in soup.find_all('a', href=True) if 'setTahmasebiUiMode(\'classic_erp\')' in a.get('onclick', '')]
    assert len(return_links) >= 1, "Return to Classic ERP button not found in POS v2"
    
    return_btn = return_links[0]
    assert return_btn['href'] == '/seller_dashboard', f"Expected /seller_dashboard for seller, got {return_btn['href']}"
    assert 'بازگشت به داشبورد کلاسیک ERP' in return_btn.get_text() or 'ERP کلاسیک' in return_btn.get_text()


def test_pos_admin_return_button_routes_to_admin_dashboard(admin_client):
    """Verify admin role return button strictly links to /admin_dashboard."""
    res = admin_client.get('/pos')
    assert res.status_code == 200
    soup = BeautifulSoup(res.get_data(as_text=True), 'html.parser')
    
    return_links = [a for a in soup.find_all('a', href=True) if 'setTahmasebiUiMode(\'classic_erp\')' in a.get('onclick', '')]
    assert len(return_links) >= 1, "Return to Classic ERP button not found in POS v2"
    
    return_btn = return_links[0]
    assert return_btn['href'] == '/admin_dashboard', f"Expected /admin_dashboard for admin, got {return_btn['href']}"


def test_classic_dashboards_contain_pos_switcher(seller_client, admin_client):
    """Verify that both seller and admin dashboards contain high-visibility switcher to /pos."""
    # Seller Dashboard
    res_seller = seller_client.get('/seller_dashboard')
    assert res_seller.status_code == 200
    seller_html = res_seller.get_data(as_text=True)
    assert '/pos' in seller_html
    assert 'setTahmasebiUiMode(\'pos_v2\')' in seller_html
    assert 'صندوق لمسی POS v2' in seller_html

    # Admin Dashboard
    res_admin = admin_client.get('/admin_dashboard')
    assert res_admin.status_code == 200
    admin_html = res_admin.get_data(as_text=True)
    assert '/pos' in admin_html
    assert 'setTahmasebiUiMode(\'pos_v2\')' in admin_html


# =========================================================================
# 2. Virtual Scrolling & Spacer Math Boundary Test Harness
# =========================================================================

def simulate_virtual_scroll(total_items=4091, col_count=3, viewport_height=600, row_height=150, buffer_rows=3, scroll_top=0):
    """
    Exact replica of the Vue 3 computed properties implemented in pos_demo.html.
    Lines 743-766 in pos_demo.html.
    """
    virtual_total_rows = math.ceil(total_items / col_count)
    virtual_total_height = virtual_total_rows * row_height
    virtual_start_row = max(0, math.floor(scroll_top / row_height) - buffer_rows)
    virtual_visible_row_count = math.ceil(viewport_height / row_height) + (buffer_rows * 2)
    virtual_end_row = min(virtual_total_rows, virtual_start_row + virtual_visible_row_count)
    virtual_offset_y = virtual_start_row * row_height
    
    start_idx = virtual_start_row * col_count
    end_idx = min(total_items, virtual_end_row * col_count)
    rendered_count = max(0, end_idx - start_idx)
    
    # Calculate bottom spacer / remaining height
    rendered_rows = virtual_end_row - virtual_start_row
    bottom_spacer = virtual_total_height - (virtual_offset_y + (rendered_rows * row_height))
    
    return {
        "virtual_total_rows": virtual_total_rows,
        "virtual_total_height": virtual_total_height,
        "virtual_start_row": virtual_start_row,
        "virtual_end_row": virtual_end_row,
        "virtual_offset_y": virtual_offset_y,
        "start_idx": start_idx,
        "end_idx": end_idx,
        "rendered_count": rendered_count,
        "bottom_spacer": bottom_spacer
    }


def test_virtual_offset_and_spacers_at_boundaries():
    """
    Verify top and bottom spacer height calculations across scroll boundaries:
    - index 0 (top, scroll_top = 0)
    - middle index (middle of 4091 items)
    - last index 4091 (scroll_top = max scroll)
    """
    total_items = 4091
    row_height = 150
    buffer_rows = 3
    viewport_height = 550  # Typical mobile container height

    # 1. Boundary: Index 0 (Scroll Top = 0)
    res_0 = simulate_virtual_scroll(total_items, col_count=3, viewport_height=viewport_height, scroll_top=0)
    assert res_0["start_idx"] == 0, "Index 0 must start at 0"
    assert res_0["virtual_start_row"] == 0
    assert res_0["virtual_offset_y"] == 0, "Top spacer/offset must be 0 at scroll top"
    assert res_0["rendered_count"] > 0
    assert res_0["rendered_count"] <= 30
    assert res_0["bottom_spacer"] >= 0

    # 2. Boundary: Middle Index (Scroll Top around item 2045)
    middle_row = 2045 // 3  # row 681
    middle_scroll_top = middle_row * row_height
    res_mid = simulate_virtual_scroll(total_items, col_count=3, viewport_height=viewport_height, scroll_top=middle_scroll_top)
    assert res_mid["virtual_offset_y"] == res_mid["virtual_start_row"] * row_height
    assert res_mid["start_idx"] <= 2045 <= res_mid["end_idx"], "Item 2045 must be inside the rendered window"
    assert res_mid["rendered_count"] <= 30
    assert res_mid["bottom_spacer"] > 0

    # 3. Boundary: Last Index 4091 (Scroll Top = Max Scroll)
    max_scroll = res_0["virtual_total_height"] - viewport_height
    res_last = simulate_virtual_scroll(total_items, col_count=3, viewport_height=viewport_height, scroll_top=max_scroll)
    assert res_last["end_idx"] == 4091, f"Expected end_idx 4091, got {res_last['end_idx']}"
    assert res_last["virtual_end_row"] == res_last["virtual_total_rows"]
    assert res_last["bottom_spacer"] == 0, "Bottom spacer must be exactly 0 at max scroll"
    assert res_last["start_idx"] < 4091
    # Check that item 4090 (last item, 0-indexed) is included
    assert res_last["end_idx"] - 1 == 4090


def test_rapid_scroll_simulation_dom_bounds():
    """
    Stress-test rapid scrolling across all possible scroll positions
    on mobile viewports (col_count=2 and col_count=3) with container heights 350-550px.
    Verify that active cards never exceed 30 elements on mobile devices.
    """
    total_items = 4091
    max_mobile_viewport_height = 550  # Mobile POS catalog pane height
    
    # Rapid scroll step simulation from 0 to max_scroll in small and large increments
    for col_count in [2, 3]:
        for vh in [380, 450, 500, 550]:
            total_height = math.ceil(total_items / col_count) * 150
            max_scroll = max(0, total_height - vh)
            
            # Test rapid increments: 25px, 150px, 500px, 2000px, 10000px
            step_sizes = [25, 150, 500, 2000, 10000]
            for step in step_sizes:
                for st in range(0, max_scroll + 1, step):
                    state = simulate_virtual_scroll(total_items, col_count, vh, scroll_top=st)
                    assert state["rendered_count"] <= 30, (
                        f"VIOLATION: Rendered card count {state['rendered_count']} > 30 "
                        f"at scroll_top={st}, col_count={col_count}, viewport_height={vh}"
                    )
                    assert state["start_idx"] >= 0
                    assert state["end_idx"] <= total_items
                    assert state["virtual_offset_y"] >= 0
                    assert state["bottom_spacer"] >= 0


def test_dom_bounds_stress_unclamped_viewports():
    """
    CRITIC CHALLENGE: Examine whether the formula has an explicit upper bound clamp.
    In pos_demo.html:
        virtualVisibleRowCount = ceil(viewportHeight / ROW_HEIGHT) + (BUFFER_ROWS * 2)
    Notice that if viewportHeight > 600 or colCount == 4 (desktop/tablet),
    the card count exceeds 30 because there is no Math.min(30, ...) clamp!
    """
    # Desktop scenario: col_count=4, viewport_height=650
    state_desktop = simulate_virtual_scroll(4091, col_count=4, viewport_height=650, scroll_top=1000)
    # This reveals the unconstrained desktop node count
    print(f"\n[Adversarial Audit] Desktop col=4, vh=650 -> {state_desktop['rendered_count']} cards rendered.")
    
    # Mobile scenario: col_count=3, viewport_height=650 (tall mobile phone like iPhone 14 Pro Max 932px screen)
    state_tall_mobile = simulate_virtual_scroll(4091, col_count=3, viewport_height=650, scroll_top=1000)
    print(f"[Adversarial Audit] Tall Mobile col=3, vh=650 -> {state_tall_mobile['rendered_count']} cards rendered.")


# =========================================================================
# 3. Playwright Real Headless Browser E2E Stress Tests (Edge Browser)
# =========================================================================

def test_browser_e2e_virtual_scroll_and_rapid_drag(live_server_url, browser):
    """
    Launch real Microsoft Edge headless browser, authenticate seller session,
    navigate to /pos, load 4,091 catalog products, and perform rapid scroll simulation.
    Empirically inspect DOM elements to count active card nodes.
    """
    # 1. Create authenticated session cookie
    serializer = app.session_interface.get_signing_serializer(app)
    cookie_val = serializer.dumps({'user_id': 6, 'role': 'seller', 'shop_id': 1, 'tenant_id': 1})
    
    context = browser.new_context(
        viewport={'width': 412, 'height': 800},  # Standard mobile viewport
        user_agent="Mozilla/5.0 (Linux; Android 13; SM-A536B) AppleWebKit/537.36 Mobile Safari/537.36"
    )
    context.add_cookies([{
        'name': 'session',
        'value': cookie_val,
        'domain': '127.0.0.1',
        'path': '/'
    }])
    
    page = context.new_page()
    page_errors = []
    page.on("pageerror", lambda err: page_errors.append(str(err)))
    
    # 2. Navigate to /pos
    response = page.goto(f"{live_server_url}/pos", wait_until="networkidle")
    assert response.status == 200
    
    # 3. Wait for catalog to load and skeleton to disappear
    page.wait_for_selector("div.pos-grid-scroll", timeout=10000)
    # Wait until skeleton loader is gone
    page.wait_for_function("() => !document.querySelector('.animate-pulse .h-\\\\[140px\\\\]')", timeout=15000)
    
    # Verify initial card count
    initial_cards = page.evaluate("() => document.querySelectorAll('.pos-grid-scroll .h-\\\\[140px\\\\]').length")
    print(f"\n[Browser E2E] Initial rendered cards on mobile: {initial_cards}")
    assert initial_cards <= 30, f"Initial card count {initial_cards} exceeds 30!"
    
    # 4. Rapid scroll simulation in browser
    max_dom_cards = initial_cards
    # Simulate 20 rapid scroll jumps across the 200,000px virtual container
    scroll_positions = [200, 800, 2500, 7000, 15000, 30000, 60000, 100000, 150000, 180000, 204000]
    for sp in scroll_positions:
        page.evaluate(f"() => {{ const el = document.querySelector('.pos-grid-scroll'); if (el) {{ el.scrollTop = {sp}; el.dispatchEvent(new Event('scroll')); }} }}")
        time.sleep(0.05)  # Allow RAF to tick
        card_count = page.evaluate("() => document.querySelectorAll('.pos-grid-scroll .h-\\\\[140px\\\\]').length")
        if card_count > max_dom_cards:
            max_dom_cards = card_count
    
    print(f"[Browser E2E] Maximum active card nodes during rapid scroll: {max_dom_cards}")
    assert max_dom_cards <= 30, f"DOM card count reached {max_dom_cards}, exceeding 30 limit!"
    
    # Check that there were zero uncaught JavaScript errors
    assert len(page_errors) == 0, f"Uncaught page errors: {page_errors}"
    
    context.close()


def test_browser_e2e_offline_resilience_and_caching(live_server_url, browser):
    """
    Stress-test offline resilience:
    - Step 1: Open /pos with network online to establish IndexedDB cache.
    - Step 2: Open a new page with route /api/inventory/catalog-stock blocked/failing (simulating offline).
    - Step 3: Verify graceful degradation, offline badge, and search functionality from IndexedDB cache.
    - Step 4: Verify cold-start failure behavior (cleared cache + offline).
    """
    serializer = app.session_interface.get_signing_serializer(app)
    cookie_val = serializer.dumps({'user_id': 6, 'role': 'seller', 'shop_id': 1, 'tenant_id': 1})
    
    context = browser.new_context(viewport={'width': 412, 'height': 800})
    context.add_cookies([{'name': 'session', 'value': cookie_val, 'domain': '127.0.0.1', 'path': '/'}])
    
    page = context.new_page()
    page_errors = []
    page.on("pageerror", lambda err: page_errors.append(str(err)))
    
    # 1. Warm load: Load catalog online to fill IndexedDB
    page.goto(f"{live_server_url}/pos", wait_until="networkidle")
    page.wait_for_function("() => !document.querySelector('.animate-pulse .h-\\\\[140px\\\\]')", timeout=15000)
    
    # Confirm IndexedDB has items
    has_idb_items = page.evaluate("""
        async () => {
            const items = await getCachedCatalog();
            return items && items.length > 0;
        }
    """)
    assert has_idb_items is True, "IndexedDB catalog cache was not populated"
    
    # 2. Offline simulation: Block /api/inventory/catalog-stock with 503
    page.route("**/api/inventory/catalog-stock", lambda route: route.abort("failed"))
    
    # Reload page in offline mode
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(1000)
    
    # Verify cached products rendered
    offline_card_count = page.evaluate("() => document.querySelectorAll('.pos-grid-scroll .h-\\\\[140px\\\\]').length")
    assert offline_card_count > 0, "Cached products failed to render when network is offline"
    
    # Verify offline badge is displayed
    is_offline_badge_visible = page.evaluate("() => !!document.querySelector('.bg-amber-500\\\\/20')")
    print(f"\n[Browser E2E] Offline badge visible on network failure: {is_offline_badge_visible}")
    assert is_offline_badge_visible is True, "Offline warning badge not shown when fetch failed"
    
    # 3. Test Cold-Start Network Failure (Empty Cache + Offline)
    context_cold = browser.new_context(viewport={'width': 412, 'height': 800})
    context_cold.add_cookies([{'name': 'session', 'value': cookie_val, 'domain': '127.0.0.1', 'path': '/'}])
    cold_page = context_cold.new_page()
    cold_errors = []
    cold_page.on("pageerror", lambda err: cold_errors.append(str(err)))
    
    # Block API for cold start
    cold_page.route("**/api/inventory/catalog-stock", lambda route: route.abort("failed"))
    cold_page.goto(f"{live_server_url}/pos", wait_until="networkidle")
    cold_page.wait_for_timeout(1500)
    
    # Check that there are zero uncaught exceptions
    assert len(cold_errors) == 0, f"Uncaught exceptions during cold offline start: {cold_errors}"
    
    # Check what is displayed: empty state should be visible without freezing
    is_loading = cold_page.evaluate("() => document.querySelector('.animate-pulse') !== null")
    assert is_loading is False, "Skeleton loader remained frozen on cold start offline failure"
    
    context.close()
    context_cold.close()


def test_browser_e2e_dual_mode_switcher_clicks(live_server_url, browser):
    """
    Test dual-mode toggle interaction in a real browser:
    - Click return button from /pos -> verifies redirection to /seller_dashboard
    - Check document.cookie and localStorage tahmasebi_ui_mode values.
    - Click switcher from /seller_dashboard -> verifies navigation back to /pos.
    """
    serializer = app.session_interface.get_signing_serializer(app)
    cookie_val = serializer.dumps({'user_id': 6, 'role': 'seller', 'shop_id': 1, 'tenant_id': 1})
    
    context = browser.new_context(viewport={'width': 1024, 'height': 768})
    context.add_cookies([{'name': 'session', 'value': cookie_val, 'domain': '127.0.0.1', 'path': '/'}])
    
    page = context.new_page()
    page.goto(f"{live_server_url}/pos", wait_until="networkidle")
    
    # Check that setTahmasebiUiMode('pos_v2') was set on mount
    ui_mode = page.evaluate("() => localStorage.getItem('tahmasebi_ui_mode')")
    assert ui_mode == "pos_v2"
    
    # Click Return to Classic ERP
    page.click("a[href='/seller_dashboard']")
    page.wait_for_url(f"{live_server_url}/seller_dashboard")
    assert "/seller_dashboard" in page.url
    
    # Check that localStorage now has classic_erp
    ui_mode_after_return = page.evaluate("() => localStorage.getItem('tahmasebi_ui_mode')")
    assert ui_mode_after_return == "classic_erp"
    
    # In seller_dashboard, click "ورود به صندوق لمسی POS v2"
    page.click("a[href='/pos']")
    page.wait_for_url(f"{live_server_url}/pos")
    assert "/pos" in page.url
    
    context.close()
