import pytest
from datetime import datetime
from models import Cheque, Customer, Invoice

@pytest.mark.unit
def test_cheques_view_calendar_context(admin_client, clean_db):
    """Verify cheques_view passes accurate Shamsi calendar grid attributes."""
    resp = admin_client.get('/cheques?cal_year=1405&cal_month=8')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Check calendar elements in HTML
    assert 'tabBtnCalendar' in html
    assert 'tabBtnTable' in html
    assert 'tabBtnLedger' in html
    assert 'آبان ۱۴۰۵' in html
    assert 'chequeActionModal' in html

@pytest.mark.unit
def test_cheque_lifecycle_status_update_api(admin_client, clean_db):
    """Verify updating cheque status across pending, passed, assigned, and bounced lifecycles."""
    # Create or reset test cheque
    chk = Cheque.query.filter_by(sayad_number="9876543210987654").first()
    if not chk:
        chk = Cheque(
            sayad_number="9876543210987654",
            bank_name="بانک سامان",
            amount=25000000,
            due_shamsi_date="1405/08/15",
            status="pending",
            customer_name="مشتری تست صیاد",
            customer_phone="09121112233",
            shop_id=1
        )
        clean_db.add(chk)
    else:
        chk.status = "pending"
        chk.passed_shamsi_date = None
        chk.payee_name = None
    clean_db.commit()

    # 1. Mark as Passed
    resp_pass = admin_client.post('/api/cheque/update_status', json={
        "cheque_id": chk.id,
        "status": "passed"
    })
    assert resp_pass.status_code == 200
    assert resp_pass.get_json()["success"] is True
    clean_db.refresh(chk)
    assert chk.status == "passed"
    assert chk.passed_shamsi_date is not None

    # 2. Mark as Assigned to Payee
    resp_assign = admin_client.post('/api/cheque/update_status', json={
        "cheque_id": chk.id,
        "status": "assigned",
        "payee_name": "شرکت اخوان جم"
    })
    assert resp_assign.status_code == 200
    clean_db.refresh(chk)
    assert chk.status == "assigned"
    assert chk.payee_name == "شرکت اخوان جم"

    # 3. Mark as Bounced
    resp_bounce = admin_client.post('/api/cheque/update_status', json={
        "cheque_id": chk.id,
        "status": "bounced"
    })
    assert resp_bounce.status_code == 200
    clean_db.refresh(chk)
    assert chk.status == "bounced"

@pytest.mark.integration
def test_customer_credit_ledger_lookup(admin_client, clean_db):
    """Verify /api/customer/ledger retrieves customer credit dossier, purchase history, debt, and cheques."""
    phone = "09123459999"
    name = "دکتر طباطبایی"

    # Create customer
    cust = Customer.query.filter_by(phone=phone).first()
    if not cust:
        cust = Customer(name=name, phone=phone)
        clean_db.add(cust)
        clean_db.commit()

    # Create invoice for customer if not already present
    inv = Invoice.query.filter_by(invoice_number="INV-TEST-LEDGER-01").first()
    if not inv:
        inv = Invoice(
            invoice_number="INV-TEST-LEDGER-01",
            customer_id=cust.id,
            customer_name=name,
            customer_phone=phone,
            seller_id=1,
            shop_id=1,
            total_amount=50000000,
            paid_pos=30000000,
            remaining_balance=20000000,
            status="final",
            shamsi_year=1405,
            shamsi_month=8,
            shamsi_day=15,
            shamsi_date_time="1405/08/15 12:00:00"
        )
        clean_db.add(inv)

    # Create cheque for customer if not already present
    chk = Cheque.query.filter_by(sayad_number="5555444433332222").first()
    if not chk:
        chk = Cheque(
            sayad_number="5555444433332222",
            bank_name="بانک ملت",
            amount=20000000,
            due_shamsi_date="1405/09/01",
            status="pending",
            customer_name=name,
            customer_phone=phone,
            shop_id=1
        )
        clean_db.add(chk)
    clean_db.commit()

    # Lookup customer by phone
    resp = admin_client.get(f'/api/customer/ledger?query={phone}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["customer"]["name"] == name

    summary = data["summary"]
    assert summary["total_purchased"] >= 50000000
    assert summary["remaining_debt"] >= 20000000

    # Invoices list should include this invoice
    inv_nums = [i["invoice_number"] for i in data["invoices"]]
    assert "INV-TEST-LEDGER-01" in inv_nums

    # Cheques list should include this cheque
    cheque_sayads = [c["sayad_number"] for c in data["cheques"]]
    assert "5555444433332222" in cheque_sayads

@pytest.mark.unit
def test_customer_ledger_persian_digits_lookup(admin_client, clean_db):
    """Verify customer credit ledger lookup works with Persian digits phone number."""
    # Lookup using Persian digits
    resp = admin_client.get('/api/customer/ledger?query=۰۹۱۲۳۴۵۹۹۹۹')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["customer"]["phone"] == "09123459999"

@pytest.mark.unit
def test_customer_ledger_not_found(admin_client, clean_db):
    """Verify customer credit ledger returns 404 for nonexistent customer."""
    resp = admin_client.get('/api/customer/ledger?query=09999999999')
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["success"] is False

@pytest.mark.unit
def test_cheque_status_update_invalid_status_rejected(admin_client, clean_db):
    """Verify updating cheque with invalid status returns 400."""
    chk = Cheque.query.first()
    assert chk is not None

    resp = admin_client.post('/api/cheque/update_status', json={
        "cheque_id": chk.id,
        "status": "some_invalid_status"
    })
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False

@pytest.mark.unit
def test_cheque_status_update_unauthorized_seller(seller_client, clean_db):
    """Verify non-inventory seller cannot change cheque status (returns 403)."""
    chk = Cheque.query.first()
    assert chk is not None

    resp = seller_client.post('/api/cheque/update_status', json={
        "cheque_id": chk.id,
        "status": "passed"
    })
    assert resp.status_code == 403
    assert resp.get_json()["success"] is False

