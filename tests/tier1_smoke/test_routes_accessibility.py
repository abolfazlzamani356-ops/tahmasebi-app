import pytest

@pytest.mark.smoke
def test_anonymous_index_redirects_to_login(client):
    resp = client.get('/', follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')

@pytest.mark.smoke
def test_login_page_renders_ok(client):
    resp = client.get('/login')
    assert resp.status_code == 200
    assert "ورود به سامانه" in resp.get_data(as_text=True)

@pytest.mark.smoke
def test_anonymous_pos_redirects_to_login(client):
    resp = client.get('/pos', follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')

@pytest.mark.smoke
def test_anonymous_demo_pos_redirects_to_login(client):
    resp = client.get('/demo/pos', follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')

@pytest.mark.smoke
def test_anonymous_seller_dashboard_redirects_to_login(client):
    resp = client.get('/seller_dashboard', follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')

@pytest.mark.smoke
def test_anonymous_admin_dashboard_redirects_to_login(client):
    resp = client.get('/admin_dashboard', follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')

@pytest.mark.smoke
def test_anonymous_inventory_redirects_to_login(client):
    resp = client.get('/inventory', follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')

@pytest.mark.smoke
def test_anonymous_catalog_redirects_to_login(client):
    resp = client.get('/admin/catalog', follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')

@pytest.mark.smoke
def test_anonymous_cheques_redirects_to_login(client):
    resp = client.get('/admin/cheques', follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')

@pytest.mark.smoke
def test_anonymous_payroll_redirects_to_login(client):
    resp = client.get('/admin/payroll', follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')

@pytest.mark.smoke
def test_anonymous_customers_redirects_to_login(client):
    resp = client.get('/admin/customers', follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')

@pytest.mark.smoke
def test_anonymous_customer_lookup_api_unauthorized(client):
    resp = client.get('/api/customer/lookup?phone=09121112233')
    assert resp.status_code in [401, 302]

@pytest.mark.smoke
def test_anonymous_barcode_lookup_api_unauthorized(client):
    resp = client.get('/api/barcode/lookup?code=626000000101')
    assert resp.status_code in [401, 302]

@pytest.mark.smoke
def test_seller_index_redirects_to_seller_dashboard(seller_client):
    resp = seller_client.get('/', follow_redirects=False)
    assert resp.status_code == 302
    assert '/seller_dashboard' in resp.headers.get('Location', '')

@pytest.mark.smoke
def test_seller_dashboard_accessible(seller_client):
    resp = seller_client.get('/seller_dashboard')
    assert resp.status_code == 200

@pytest.mark.smoke
def test_seller_pos_v2_accessible(seller_client):
    resp = seller_client.get('/pos')
    assert resp.status_code == 200
    content = resp.get_data(as_text=True)
    assert "صندوق فروش" in content or "posApp" in content

@pytest.mark.smoke
def test_seller_cannot_access_admin_dashboard(seller_client):
    resp = seller_client.get('/admin_dashboard', follow_redirects=False)
    # Must redirect seller away from admin dashboard
    assert resp.status_code in [302, 403]

@pytest.mark.smoke
def test_admin_index_redirects_to_admin_dashboard(admin_client):
    resp = admin_client.get('/', follow_redirects=False)
    assert resp.status_code == 302
    assert '/admin_dashboard' in resp.headers.get('Location', '')

@pytest.mark.smoke
def test_admin_dashboard_accessible(admin_client):
    resp = admin_client.get('/admin_dashboard')
    assert resp.status_code == 200

@pytest.mark.smoke
def test_admin_inventory_accessible(admin_client):
    resp = admin_client.get('/inventory')
    assert resp.status_code == 200

@pytest.mark.smoke
def test_admin_catalog_accessible(admin_client):
    resp = admin_client.get('/admin/catalog')
    assert resp.status_code == 200

@pytest.mark.smoke
def test_admin_cheques_accessible(admin_client):
    resp = admin_client.get('/admin/cheques')
    assert resp.status_code == 200

@pytest.mark.smoke
def test_admin_payroll_accessible(admin_client):
    resp = admin_client.get('/admin/payroll')
    assert resp.status_code == 200

@pytest.mark.smoke
def test_admin_customers_accessible(admin_client):
    resp = admin_client.get('/admin/customers')
    assert resp.status_code == 200

@pytest.mark.smoke
def test_authenticated_catalog_stock_api_accessible(seller_client):
    resp = seller_client.get('/api/inventory/catalog-stock')
    assert resp.status_code == 200
    assert resp.is_json
