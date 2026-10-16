import pytest
import json
from models import ProductCatalog, InventoryItem, Shop, StockTransfer, StockLog

@pytest.mark.unit
def test_catalog_quick_price_inline_edit(admin_client, clean_db):
    """Verify inline editing of buy and sell prices via POST /api/catalog/quick_price with warehouse sync."""
    # Ensure a catalog item exists
    item = ProductCatalog.query.filter_by(name="تست شیر ظرفشویی اهرمی").first()
    if not item:
        item = ProductCatalog(
            name="تست شیر ظرفشویی اهرمی",
            category="شیرآلات",
            brand="آس",
            code="TAP-TEST-001",
            buy_price=1000000,
            sell_price=1500000
        )
        clean_db.add(item)
        clean_db.commit()

    # Update sell price inline
    resp = admin_client.post('/api/catalog/quick_price', json={
        "item_id": item.id,
        "sell_price": 1750000
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["sell_price"] == 1750000

    clean_db.refresh(item)
    assert item.sell_price == 1750000

    # Update buy price inline
    resp2 = admin_client.post('/api/catalog/quick_price', json={
        "item_id": item.id,
        "buy_price": 1100000
    })
    assert resp2.status_code == 200
    clean_db.refresh(item)
    assert item.buy_price == 1100000

    # Verify inventory in warehouse also has synchronized prices
    inv = InventoryItem.query.filter_by(name=item.name, shop_id=1).first()
    if inv:
        assert inv.buy_price == 1100000
        assert inv.sell_price == 1750000

@pytest.mark.unit
def test_catalog_quick_price_permission_denied(seller_client, clean_db):
    """Verify non-inventory staff cannot alter catalog prices."""
    item = ProductCatalog.query.first()
    assert item is not None

    resp = seller_client.post('/api/catalog/quick_price', json={
        "item_id": item.id,
        "sell_price": 9999999
    })
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["success"] is False

@pytest.mark.unit
def test_catalog_stock_api_includes_workshop_shop3(admin_client, clean_db):
    """Verify /api/inventory/catalog-stock returns stock and min thresholds for Branch 1, Branch 2, and Workshop (Shop 3)."""
    resp = admin_client.get('/api/inventory/catalog-stock')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    if len(data) > 0:
        first = data[0]
        assert "stock_1" in first
        assert "stock_2" in first
        assert "stock_3" in first
        assert "min_1" in first
        assert "min_2" in first
        assert "min_3" in first

@pytest.mark.integration
def test_inter_branch_and_workshop_transfer_auto_approve(admin_client, clean_db):
    """Verify inter-branch and workshop transfer with auto_approve flag updates both inventories atomically."""
    item_name = "کالای آزمایشی انتقال انبار"
    
    # Setup stock in Shop 1
    inv1 = InventoryItem.query.filter_by(name=item_name, shop_id=1).first()
    if not inv1:
        inv1 = InventoryItem(name=item_name, shop_id=1, stock_quantity=20, category="عمومی", buy_price=100000, sell_price=150000)
        clean_db.add(inv1)
    else:
        inv1.stock_quantity = 20
        
    inv3 = InventoryItem.query.filter_by(name=item_name, shop_id=3).first()
    if not inv3:
        inv3 = InventoryItem(name=item_name, shop_id=3, stock_quantity=5, category="عمومی", buy_price=100000, sell_price=150000)
        clean_db.add(inv3)
    else:
        inv3.stock_quantity = 5
        
    clean_db.commit()

    # Request auto-approved transfer of 7 units from Shop 1 to Shop 3 (Workshop)
    resp = admin_client.post('/transfer/request', data={
        "from_shop_id": 1,
        "to_shop_id": 3,
        "item_name": item_name,
        "quantity": 7,
        "auto_approve": "1"
    }, follow_redirects=True)
    assert resp.status_code == 200

    clean_db.refresh(inv1)
    clean_db.refresh(inv3)
    assert inv1.stock_quantity == 13
    assert inv3.stock_quantity == 12

    # Verify StockTransfer record has accepted status
    transfer = StockTransfer.query.filter_by(item_name=item_name, from_shop_id=1, to_shop_id=3).order_by(StockTransfer.id.desc()).first()
    assert transfer is not None
    assert transfer.status == "accepted"
    assert transfer.quantity == 7

@pytest.mark.integration
def test_batch_price_update_async_json(admin_client, clean_db):
    """Verify non-blocking bulk percentage price update returns JSON for AJAX frontend with animated progress."""
    # Create test catalog items
    b_name = "برند تست بچ"
    item1 = ProductCatalog(name="کالای بچ ۱", brand=b_name, category="شیرآلات", buy_price=100000, sell_price=200000)
    item2 = ProductCatalog(name="کالای بچ ۲", brand=b_name, category="شیرآلات", buy_price=100000, sell_price=200000)
    clean_db.add_all([item1, item2])
    clean_db.commit()

    # Apply 30% discount on buy price from consumer price
    resp = admin_client.post('/admin/catalog/batch_price_update', json={
        "target_brand": b_name,
        "target_category": "all",
        "update_type": "buy_discount",
        "discount_percent": 30.0,
        "sync_inventory": True
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["updated_count"] >= 2

    clean_db.refresh(item1)
    clean_db.refresh(item2)
    # 200,000 * (1 - 0.30) = 140,000
    assert item1.buy_price == 140000
    assert item2.buy_price == 140000

@pytest.mark.unit
def test_catalog_quick_price_persian_digits_and_negative_clamping(admin_client, clean_db):
    """Verify quick price parses Persian digits with commas and clamps negative prices to 0."""
    item = ProductCatalog.query.first()
    assert item is not None

    # Test Persian digits and commas
    resp = admin_client.post('/api/catalog/quick_price', json={
        "item_id": item.id,
        "sell_price": "۲,۵۰۰,۰۰۰"
    })
    assert resp.status_code == 200
    assert resp.get_json()["sell_price"] == 2500000

    # Test negative clamping
    resp2 = admin_client.post('/api/catalog/quick_price', json={
        "item_id": item.id,
        "buy_price": -99999
    })
    assert resp2.status_code == 200
    assert resp2.get_json()["buy_price"] == 0

@pytest.mark.unit
def test_inter_branch_transfer_same_shop_rejected(admin_client, clean_db):
    """Verify requesting transfer with same origin and destination returns 400."""
    resp = admin_client.post('/transfer/request', json={
        "from_shop_id": 1,
        "to_shop_id": 1,
        "item_name": "کالای تست انتقال همسان",
        "quantity": 5
    })
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False
    assert "یکسان" in resp.get_json()["message"]

@pytest.mark.unit
def test_batch_price_update_empty_criteria_rejected(admin_client, clean_db):
    """Verify batch price update without any brand or category criteria returns 400."""
    resp = admin_client.post('/admin/catalog/batch_price_update', json={
        "target_brand": "all",
        "target_category": "all",
        "update_type": "buy_discount",
        "discount_percent": 15.0
    })
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False

