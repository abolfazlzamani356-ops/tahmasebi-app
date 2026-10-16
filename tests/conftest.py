import os
import sys
import socket
import threading
import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import app, db
from models import User, Shop, Customer, ProductCatalog, InventoryItem, Invoice, InvoiceItem, Cheque, Settings, Tenant

def pytest_configure(config):
    config.addinivalue_line("markers", "smoke: Tier 1 smoke and sanity tests")
    config.addinivalue_line("markers", "unit: Tier 2 unit and boundary tests")
    config.addinivalue_line("markers", "integration: Tier 3 integration and cross-feature tests")
    config.addinivalue_line("markers", "e2e: Tier 4 end-to-end browser touch and performance tests")

@pytest.fixture(scope="session")
def flask_app():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    return app

@pytest.fixture(scope="function")
def app_ctx(flask_app):
    ctx = flask_app.app_context()
    ctx.push()
    yield ctx
    ctx.pop()

@pytest.fixture(scope="function")
def client(flask_app, app_ctx):
    return flask_app.test_client()

@pytest.fixture(scope="function")
def admin_client(flask_app, app_ctx):
    c = flask_app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = 1
        sess["full_name"] = "محمد طهماسبی (مدیریت کل)"
        sess["role"] = "admin"
        sess["shop_id"] = 1
        sess["tenant_id"] = 1
        sess["is_super_admin"] = True
    return c

@pytest.fixture(scope="function")
def seller_client(flask_app, app_ctx):
    c = flask_app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = 6
        sess["full_name"] = "ابوالفضل زمانی"
        sess["role"] = "seller"
        sess["shop_id"] = 1
        sess["tenant_id"] = 1
        sess["can_manage_inventory"] = False
    return c

@pytest.fixture(scope="function")
def cashier_client(flask_app, app_ctx):
    c = flask_app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = 8
        sess["full_name"] = "صندوقدار آزمایشی"
        sess["role"] = "cashier"
        sess["shop_id"] = 2
        sess["tenant_id"] = 1
        sess["can_manage_inventory"] = False
    return c

@pytest.fixture(scope="function")
def warehouse_client(flask_app, app_ctx):
    c = flask_app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = 7
        sess["full_name"] = "مدیر انبار"
        sess["role"] = "seller"
        sess["shop_id"] = 1
        sess["tenant_id"] = 1
        sess["can_manage_inventory"] = True
    return c

@pytest.fixture(scope="function")
def clean_db(app_ctx):
    """Ensure database session is clean before and after tests."""
    yield db.session
    try:
        db.session.rollback()
    except Exception:
        pass

def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port

@pytest.fixture(scope="session")
def live_server_url(flask_app):
    """Run a live background Werkzeug server for Playwright browser testing."""
    from werkzeug.serving import make_server
    port = get_free_port()
    server = make_server("127.0.0.1", port, flask_app, threaded=True)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    url = f"http://127.0.0.1:{port}"
    yield url
    server.shutdown()
    server_thread.join(timeout=3)

@pytest.fixture(scope="session")
def playwright_instance():
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    yield pw
    pw.stop()

@pytest.fixture(scope="session")
def browser(playwright_instance):
    """Launch Microsoft Edge on Windows via Playwright channel='msedge'."""
    try:
        b = playwright_instance.chromium.launch(channel="msedge", headless=True)
        yield b
        b.close()
    except Exception:
        # Fallback to standard chromium if available
        try:
            b = playwright_instance.chromium.launch(headless=True)
            yield b
            b.close()
        except Exception as e:
            pytest.skip(f"Browser could not be launched: {e}")
