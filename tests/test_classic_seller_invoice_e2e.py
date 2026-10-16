import pytest
import re
from bs4 import BeautifulSoup
from app import app, db, Invoice, User, ProductCatalog, InventoryItem, StockLog

def test_classic_seller_form_submission_in_browser(live_server_url, browser):
    serializer = app.session_interface.get_signing_serializer(app)
    # seller user_id=6
    cookie_val = serializer.dumps({'user_id': 6, 'role': 'seller', 'shop_id': 1, 'tenant_id': 1})
    
    context = browser.new_context()
    context.add_cookies([{'name': 'session', 'value': cookie_val, 'domain': '127.0.0.1', 'path': '/'}])
    
    page = context.new_page()
    page_errors = []
    page.on("pageerror", lambda err: page_errors.append(str(err)))
    page.on("console", lambda msg: print(f"CONSOLE [{msg.type}]: {msg.text}"))
    
    page.goto(f"{live_server_url}/seller_dashboard", wait_until="networkidle")
    print("Page title:", page.title())

    # Check form exists
    form = page.locator("#mainInvoiceForm")
    assert form.count() == 1

    # Fill customer name
    page.fill("#custNameInput", "تست خریدار مرورگر")
    # Fill item price
    page.fill(".item-price", "2,500,000")
    # Trigger price change
    page.evaluate("() => { const inp = document.querySelector('.item-price'); inp.dispatchEvent(new Event('input', {bubbles: true})); inp.dispatchEvent(new Event('change', {bubbles: true})); }")
    page.wait_for_timeout(300)

    # Check total amount
    tot = page.input_value("#totalAmountInput")
    print("Total amount input value:", tot)
    assert tot != ""

    # Click submit
    submit_btn = page.locator("#mainInvoiceForm button[type='submit']")
    print("Submit button text before click:", submit_btn.inner_text())
    
    # Listen to response or navigation
    with page.expect_navigation(timeout=10000) as nav_info:
        submit_btn.click()
    
    print("Navigated to:", page.url)
    print("Page errors:", page_errors)
    context.close()


def test_modal_nesting_structural_integrity():
    """بررسی ساختار DOM برای اطمینان از عدم تداخل و تودرتو نبودن مودال آپدیت درصدی در کاتالوگ و انبار"""
    template_files = ['templates/inventory.html', 'templates/catalog.html', 'inventory.html', 'catalog.html']
    for tf in template_files:
        with open(tf, 'r', encoding='utf-8') as f:
            content = f.read()
        cleaned = re.sub(r'\{%.*?%\}', '', content)
        cleaned = re.sub(r'\{\{.*?\}\}', '', cleaned)
        soup = BeautifulSoup(cleaned, 'html.parser')
        
        batch_modal = soup.find(id='batchPriceModal')
        assert batch_modal is not None, f"batchPriceModal must exist in {tf}"
        
        # Check parent hierarchy
        parents = []
        curr = batch_modal.parent
        while curr and curr.name:
            if curr.get('id'):
                parents.append(curr.get('id'))
            curr = curr.parent
            
        assert 'faucetWizardModal' not in parents, f"batchPriceModal is erroneously nested in faucetWizardModal in {tf}!"
        assert 'stocktakingModal' not in parents, f"batchPriceModal is erroneously nested in stocktakingModal in {tf}!"


def test_batch_price_modal_opens_directly_in_browser(live_server_url, browser):
    """بررسی باز شدن فوری و مستقیم مودال آپدیت درصدی بدون نیاز به کلیک روی آیتم دیگر"""
    serializer = app.session_interface.get_signing_serializer(app)
    # admin user_id=1
    cookie_val = serializer.dumps({'user_id': 1, 'role': 'admin', 'shop_id': 1, 'tenant_id': 1})
    
    context = browser.new_context()
    context.add_cookies([{'name': 'session', 'value': cookie_val, 'domain': '127.0.0.1', 'path': '/'}])
    
    page = context.new_page()
    page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
    page.on("console", lambda msg: print(f"CONSOLE [{msg.type}]: {msg.text}"))
    
    page.goto(f"{live_server_url}/admin/catalog", wait_until="networkidle")
    page.wait_for_selector("#batchPriceModal", state="attached")
    page.evaluate("() => window.openBatchPriceModal()")
    
    batch_modal = page.locator("#batchPriceModal")
    batch_modal.wait_for(state="visible", timeout=5000)
    assert batch_modal.is_visible(), "batchPriceModal should be visible immediately upon calling openBatchPriceModal()"
    style_display = page.evaluate("() => window.getComputedStyle(document.getElementById('batchPriceModal')).display")
    rect = page.evaluate("() => { const r = document.getElementById('batchPriceModal').getBoundingClientRect(); return {width: r.width, height: r.height}; }")
    assert style_display == "flex", f"Expected display: flex, got {style_display}"
    assert rect['width'] > 0 and rect['height'] > 0, f"Expected non-zero dimensions, got {rect}"
    
    # Close it
    page.evaluate("() => window.closeBatchPriceModal()")
    batch_modal.wait_for(state="hidden", timeout=5000)
    assert not batch_modal.is_visible()

    # Also test in /inventory
    page.goto(f"{live_server_url}/inventory", wait_until="networkidle")
    page.wait_for_selector("#batchPriceModal", state="attached")
    page.evaluate("() => window.openBatchPriceModal()")
    inv_modal = page.locator("#batchPriceModal")
    inv_modal.wait_for(state="visible", timeout=5000)
    assert inv_modal.is_visible(), "batchPriceModal should be visible in /inventory"
    inv_display = page.evaluate("() => window.getComputedStyle(document.getElementById('batchPriceModal')).display")
    inv_rect = page.evaluate("() => { const r = document.getElementById('batchPriceModal').getBoundingClientRect(); return {width: r.width, height: r.height}; }")
    assert inv_display == "flex"
    assert inv_rect['width'] > 0 and inv_rect['height'] > 0
    page.evaluate("() => window.closeBatchPriceModal()")
    inv_modal.wait_for(state="hidden", timeout=5000)
    assert not inv_modal.is_visible()

    context.close()


def test_classic_seller_invoice_catalog_item_stock_deduction():
    """بررسی اتصال اقلام کاتالوگ در فاکتور فروشنده کلاسیک و کسر اتمیک موجودی انبار"""
    with app.app_context():
        seller = User.query.filter_by(role='seller').first() or User.query.first()
        seller_id = seller.id
        seller_username = seller.username
        seller_role = seller.role
        seller_full_name = seller.full_name
        shop_id = seller.shop_id or 1
        
        # Find or create a catalog item
        cat_item = ProductCatalog.query.first()
        assert cat_item is not None, "ProductCatalog should have at least one product"
        cat_item_id = cat_item.id
        cat_item_name = cat_item.name
        cat_item_category = cat_item.category
        cat_item_sell_price = cat_item.sell_price
        cat_item_buy_price = cat_item.buy_price or 0
        
        # Check or create inventory item for this branch
        inv_item = InventoryItem.query.filter_by(name=cat_item_name, shop_id=shop_id).first()
        if not inv_item:
            inv_item = InventoryItem(
                name=cat_item_name,
                category=cat_item_category,
                brand=cat_item.brand,
                sell_price=cat_item_sell_price,
                buy_price=cat_item_buy_price,
                stock_quantity=10,
                shop_id=shop_id
            )
            db.session.add(inv_item)
        else:
            inv_item.stock_quantity = 10
        db.session.commit()
        initial_stock = 10
            
        test_inv_num = "TEST-CLASSIC-CAT-DEDUCT-99"
        # Clean any prior invoice
        prior = Invoice.query.filter_by(invoice_number=test_inv_num).first()
        if prior:
            db.session.delete(prior)
            db.session.commit()
            
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = seller_id
            sess['username'] = seller_username
            sess['role'] = seller_role
            sess['shop_id'] = shop_id
            sess['full_name'] = seller_full_name
            
        post_data = {
            'doc_status': 'final',
            'invoice_number': test_inv_num,
            'customer_name': 'خریدار تست کاتالوگ',
            'customer_phone': '09129998877',
            'item_inventory_id[]': [''],
            'item_catalog_id[]': [str(cat_item_id)],
            'item_custom_name[]': [cat_item_name],
            'item_category[]': [cat_item_category],
            'item_quantity[]': ['2'],
            'item_price[]': [str(cat_item_sell_price)],
            'item_original_price[]': [str(cat_item_sell_price)],
            'item_discount_percent[]': [''],
            'item_buy_price[]': [str(cat_item_buy_price)],
            'total_amount': str(cat_item_sell_price * 2),
            'paid_pos': str(cat_item_sell_price * 2),
            'remaining_balance': '0'
        }
        resp = client.post('/invoice/add', data=post_data, follow_redirects=False)
        assert resp.status_code == 302
        
    with app.app_context():
        created_inv = Invoice.query.filter_by(invoice_number=test_inv_num).first()
        assert created_inv is not None, "Invoice must be created in database"
        assert len(created_inv.items) == 1
        
        # Verify inventory stock deduction
        refreshed_inv_item = InventoryItem.query.filter_by(name=cat_item_name, shop_id=shop_id).first()
        assert refreshed_inv_item.stock_quantity == initial_stock - 2, f"Stock should be deducted by 2 (from {initial_stock} to {initial_stock-2}), got {refreshed_inv_item.stock_quantity}"
        
        # Verify StockLog
        log_entry = StockLog.query.filter_by(reference_id=test_inv_num, inventory_item_id=refreshed_inv_item.id).first()
        assert log_entry is not None, "StockLog entry should be recorded for the invoice deduction"
        assert log_entry.quantity_changed == -2
        
        # Cleanup
        db.session.delete(created_inv)
        if log_entry:
            db.session.delete(log_entry)
        refreshed_inv_item.stock_quantity = initial_stock
        db.session.commit()


def test_batch_price_ajax_submission_returns_json_and_no_302():
    """تست اعتبارسنجی ارسال ایجکس فرم آپدیت درصدی با هدر X-Requested-With و اطمینان از پاسخ JSON به جای 302"""
    unique_brand = "برند موقت تست ایجکس ۹۹"
    with app.app_context():
        # Create isolated test catalog item
        test_item = ProductCatalog(
            name="کالای تست ایجکس ۹۹",
            brand=unique_brand,
            category="عمومی",
            buy_price=500000,
            sell_price=1000000
        )
        db.session.add(test_item)
        db.session.commit()
        item_id = test_item.id

    try:
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = 1
                sess['role'] = 'admin'

            form_data = {
                'target_brand': unique_brand,
                'target_category': 'all',
                'update_type': 'buy_discount',
                'discount_percent': '25.0',
                'sync_inventory': '1'
            }
            # AJAX submission from browser FormData
            resp = client.post(
                '/admin/catalog/batch_price_update',
                data=form_data,
                headers={'X-Requested-With': 'XMLHttpRequest'},
                follow_redirects=False
            )
            assert resp.status_code == 200, f"Expected 200 JSON, got {resp.status_code} (Location: {resp.headers.get('Location')})"
            assert 'application/json' in resp.content_type
            data = resp.get_json()
            assert data is not None
            assert data.get('success') is True
            assert data.get('updated_count', 0) >= 1

            with app.app_context():
                reloaded = db.session.get(ProductCatalog, item_id)
                # 1,000,000 * (1 - 0.25) = 750,000
                assert reloaded.buy_price == 750000
    finally:
        with app.app_context():
            to_del = db.session.get(ProductCatalog, item_id)
            if to_del:
                db.session.delete(to_del)
                db.session.commit()


def test_batch_price_ajax_criteria_validation_returns_400_json():
    """تست بازگشت خطای ۴۰۰ به صورت JSON در درخواست‌های ایجکس زمانی که نه برند و نه دسته انتخاب نشده است"""
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['role'] = 'admin'

        form_data = {
            'target_brand': 'all',
            'target_category': 'all',
            'update_type': 'buy_discount',
            'discount_percent': '20.0'
        }
        resp = client.post(
            '/admin/catalog/batch_price_update',
            data=form_data,
            headers={'X-Requested-With': 'XMLHttpRequest'},
            follow_redirects=False
        )
        assert resp.status_code == 400
        assert 'application/json' in resp.content_type
        data = resp.get_json()
        assert data is not None
        assert data.get('success') is False
        assert 'حداقل یک برند' in data.get('message', '')


def test_batch_price_modal_elements_and_progress_in_both_catalog_and_inventory():
    """بررسی وجود فرم هماهنگ، آیدی‌ها و نوار پیشرفت زنده در تمام ۴ فایل قالب کاتالوگ و انبار"""
    template_files = ['templates/inventory.html', 'templates/catalog.html', 'inventory.html', 'catalog.html']
    for tf in template_files:
        with open(tf, 'r', encoding='utf-8') as f:
            content = f.read()
        soup = BeautifulSoup(content, 'html.parser')
        batch_modal = soup.find(id='batchPriceModal')
        assert batch_modal is not None, f"batchPriceModal must exist in {tf}"
        form = batch_modal.find('form', id='batchPriceForm')
        assert form is not None, f"batchPriceForm must exist in {tf}"
        assert 'handleBatchPriceSubmit' in (form.get('onsubmit') or ''), f"form in {tf} must trigger handleBatchPriceSubmit"
        progress = batch_modal.find(id='batchProgressContainer')
        assert progress is not None, f"batchProgressContainer must exist in {tf}"
        submit_btn = batch_modal.find(id='batchSubmitBtn')
        assert submit_btn is not None, f"batchSubmitBtn must exist in {tf}"


def test_classic_seller_invoice_multi_payment_and_custom_items():
    """تست ثبت فاکتور از پنل فروشنده کلاسیک با پرداخت ترکیبی (پوز + نقد) و اقلام سفارشی"""
    with app.app_context():
        seller = User.query.filter_by(role='seller').first() or User.query.first()
        seller_id = seller.id
        shop_id = seller.shop_id or 1
        test_inv_num = "TEST-SELLER-MULTI-PAY-88"

        prior = Invoice.query.filter_by(invoice_number=test_inv_num).first()
        if prior:
            db.session.delete(prior)
            db.session.commit()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = seller_id
            sess['role'] = 'seller'
            sess['shop_id'] = shop_id

        post_data = {
            'doc_status': 'final',
            'invoice_number': test_inv_num,
            'customer_name': 'خریدار پرداخت چندگانه',
            'customer_phone': '09351234567',
            'item_inventory_id[]': [''],
            'item_catalog_id[]': [''],
            'item_custom_name[]': ['کالای دست‌ساز سفارشی کارگاه'],
            'item_category[]': ['روشویی'],
            'item_quantity[]': ['2'],
            'item_price[]': ['1,500,000'],
            'item_original_price[]': ['1,500,000'],
            'item_discount_percent[]': [''],
            'item_buy_price[]': ['900,000'],
            'total_amount': '3,000,000',
            'paid_pos': '2,000,000',
            'paid_cash': '1,000,000',
            'remaining_balance': '0'
        }
        resp = client.post('/invoice/add', data=post_data, follow_redirects=False)
        assert resp.status_code == 302

    with app.app_context():
        inv = Invoice.query.filter_by(invoice_number=test_inv_num).first()
        assert inv is not None
        assert inv.total_amount == 3000000
        assert inv.paid_pos == 2000000
        assert inv.paid_cash == 1000000
        assert inv.remaining_balance == 0
        assert inv.is_settled is True
        assert inv.has_custom_items is True
        assert len(inv.items) == 1
        assert inv.items[0].is_custom is True
        assert inv.items[0].unit_buy_price == 900000

        # Cleanup
        db.session.delete(inv)
        db.session.commit()

