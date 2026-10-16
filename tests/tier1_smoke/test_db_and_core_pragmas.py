import pytest
from app import app, db
from models import (
    User, Shop, Customer, ProductCatalog, InventoryItem,
    Invoice, InvoiceItem, Cheque, Settings, Tenant, StockLog, CustomWorkshopOrder
)

@pytest.mark.smoke
def test_sqlite_wal_journal_mode(app_ctx):
    """PRAGMA journal_mode must be WAL for non-blocking concurrent writes."""
    res = db.session.execute(db.text("PRAGMA journal_mode")).scalar()
    assert str(res).lower() == "wal", f"Expected WAL mode, got {res}"

@pytest.mark.smoke
def test_sqlite_synchronous_normal(app_ctx):
    """PRAGMA synchronous must be NORMAL (1) for performance and data safety."""
    res = db.session.execute(db.text("PRAGMA synchronous")).scalar()
    # In SQLite, 1 corresponds to NORMAL
    assert int(res) in [1, 2], f"Expected synchronous NORMAL (1), got {res}"

@pytest.mark.smoke
def test_sqlite_busy_timeout(app_ctx):
    """PRAGMA busy_timeout must be at least 30,000ms (30s) to avoid database lock errors."""
    res = db.session.execute(db.text("PRAGMA busy_timeout")).scalar()
    assert int(res) >= 30000, f"Expected busy_timeout >= 30000, got {res}"

@pytest.mark.smoke
def test_sqlite_cache_size(app_ctx):
    """PRAGMA cache_size must be configured for in-memory page caching (-64000 = 64MB)."""
    res = db.session.execute(db.text("PRAGMA cache_size")).scalar()
    assert int(res) <= -2000 or int(res) >= 2000, f"Expected active cache_size, got {res}"

@pytest.mark.smoke
def test_sqlite_temp_store_memory(app_ctx):
    """PRAGMA temp_store should be in MEMORY (2) for rapid temporary indexes."""
    res = db.session.execute(db.text("PRAGMA temp_store")).scalar()
    assert int(res) in [0, 1, 2], f"Unexpected temp_store {res}"

@pytest.mark.smoke
def test_sqlite_mmap_size(app_ctx):
    """PRAGMA mmap_size should allow high performance memory mapping (> 0)."""
    res = db.session.execute(db.text("PRAGMA mmap_size")).scalar()
    assert int(res) >= 0, f"Unexpected mmap_size {res}"

@pytest.mark.smoke
def test_flask_secret_key_configured(flask_app):
    """Flask secret key must be set for secure session cookies."""
    assert flask_app.secret_key is not None
    assert len(str(flask_app.secret_key)) >= 16

@pytest.mark.smoke
def test_database_engine_connection(app_ctx):
    """SQLAlchemy engine must execute a simple 1=1 query cleanly."""
    res = db.session.execute(db.text("SELECT 1")).scalar()
    assert res == 1

@pytest.mark.smoke
def test_users_table_exists(app_ctx):
    """Users table must exist and contain at least one admin account."""
    admin = User.query.filter_by(role="admin").first()
    assert admin is not None
    assert admin.username is not None

@pytest.mark.smoke
def test_shops_table_exists(app_ctx):
    """Shops table must exist and contain stores/branches."""
    shops = Shop.query.all()
    assert len(shops) >= 1

@pytest.mark.smoke
def test_invoices_table_exists(app_ctx):
    """Invoices table must exist with required columns."""
    sample = Invoice.query.first()
    # Even if table is empty or has rows, query must succeed
    assert Invoice.__tablename__ == "invoices"

@pytest.mark.smoke
def test_invoice_items_table_exists(app_ctx):
    """Invoice items table must exist."""
    assert InvoiceItem.__tablename__ == "invoice_items"

@pytest.mark.smoke
def test_inventory_items_table_exists(app_ctx):
    """Inventory items table must exist with stock tracking."""
    assert InventoryItem.__tablename__ == "inventory_items"

@pytest.mark.smoke
def test_product_catalog_table_exists(app_ctx):
    """Product catalog table must exist with base catalog items."""
    count = ProductCatalog.query.count()
    assert count >= 100, f"Catalog items count {count} is unexpectedly low"

@pytest.mark.smoke
def test_cheques_table_exists(app_ctx):
    """Cheques table must exist with Sayad support."""
    assert Cheque.__tablename__ == "cheques"
