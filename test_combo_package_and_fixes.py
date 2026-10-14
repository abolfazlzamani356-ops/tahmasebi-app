import pytest
from app import app, db, InventoryItem, ProductCatalog, Invoice, InvoiceItem, User, Shop

def test_combo_package_invoice_clean_names_and_stock_deduction():
    with app.app_context():
        # Setup test data
        shop = Shop.query.first()
        if not shop:
            shop = Shop(name="شعبه آزمایشی", commission_rate=1.0)
            db.session.add(shop)
            db.session.commit()

        # Create 2 inventory items
        item1 = InventoryItem(
            name="آینه باکس روشویی تست کمبو ۱",
            category="روشویی کابینتی",
            stock_quantity=10,
            buy_price=3000000,
            sell_price=4940000,
            shop_id=shop.id
        )
        item2 = InventoryItem(
            name="روشویی فول ست تست کمبو ۲",
            category="روشویی کابینتی",
            stock_quantity=5,
            buy_price=7000000,
            sell_price=11386000,
            shop_id=shop.id
        )
        db.session.add_all([item1, item2])
        db.session.commit()

        seller = User.query.filter_by(role='seller').first()
        if not seller:
            seller = User(username='test_seller_combo', full_name='فروشنده تست کمبو', role='seller', shop_id=shop.id)
            seller.set_password('123456')
            db.session.add(seller)
            db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = seller.id
            sess['role'] = 'seller'
            sess['shop_id'] = shop.id
            sess['tenant_id'] = 1

        # Submit invoice simulating the combo package (agreed total 4,940,000 Tomans)
        # item 1: 1,494,769 Toman
        # item 2: 3,445,231 Toman
        # Total = 4,940,000 Toman
        payload = {
            'customer_name': 'مشتری پکیج ترکیبی',
            'customer_phone': '09120000000',
            'item_inventory_id[]': [str(item1.id), str(item2.id)],
            'item_custom_name[]': [item1.name, item2.name],
            'item_category[]': ['روشویی کابینتی', 'روشویی کابینتی'],
            'item_quantity[]': ['1', '1'],
            'item_original_price[]': ['4,940,000', '11,386,000'],
            'item_discount_percent[]': ['70', '70'],
            'item_price[]': ['1,494,769', '3,445,231'],
            'item_buy_price[]': ['3,000,000', '7,000,000'],
            'total_amount': '4,940,000',
            'paid_pos': '4,940,000',
            'paid_card': '',
            'paid_cash': '',
            'remaining_balance': '0',
            'customer_rating': '5',
            'split_ratio': '100'
        }

        resp = client.post('/invoice/add', data=payload, follow_redirects=True)
        assert resp.status_code == 200

        # Verify stock was deducted for both items
        db.session.refresh(item1)
        db.session.refresh(item2)
        assert item1.stock_quantity == 9, "Item 1 stock should have been decremented by 1"
        assert item2.stock_quantity == 4, "Item 2 stock should have been decremented by 1"

        # Verify invoice items exist with clean names
        inv = Invoice.query.filter_by(customer_name='مشتری پکیج ترکیبی').order_by(Invoice.id.desc()).first()
        assert inv is not None
        assert inv.total_amount == 4940000
        assert len(inv.items) == 2
        
        # Verify names are clean and NOT corrupted with '(پکیج ترکیبی)'
        assert inv.items[0].item_name == "آینه باکس روشویی تست کمبو ۱"
        assert inv.items[1].item_name == "روشویی فول ست تست کمبو ۲"
        assert "(پکیج ترکیبی)" not in inv.items[0].item_name
        assert "(همراه پکیج)" not in inv.items[1].item_name

        # Clean up
        db.session.delete(inv)
        db.session.delete(item1)
        db.session.delete(item2)
        db.session.commit()
