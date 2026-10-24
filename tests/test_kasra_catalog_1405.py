import pytest
import sqlite3
import os
import sys

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import kasra_catalog_data

def test_kasra_catalog_generator():
    items = kasra_catalog_data.generate_all_kasra_items(20.0)
    assert len(items) >= 700
    
    kasra_items = [i for i in items if i['brand'] == 'کسرا (Kasra)']
    assert len(kasra_items) >= 700
    
    for item in kasra_items:
        sell = item['sell_price']
        buy = item['buy_price']
        assert sell > 0, f"Sell price must be positive for {item['name']}"
        assert buy > 0, f"Buy price must be positive for {item['name']}"
        expected_buy = int(round(sell * 0.80))
        assert buy == expected_buy, f"Buy price {buy} does not match 20% discount of {sell} (expected {expected_buy}) for {item['name']}"
        assert '20%' in item['description']

def test_kasra_database_records():
    db_path = os.path.join(base_dir, 'instance', 'tahmasebi_store_persistent.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("SELECT count(*) FROM product_catalog WHERE brand = 'کسرا (Kasra)'")
    count = c.fetchone()[0]
    assert count >= 700, f"Expected at least 700 Kasra products in DB, found {count}"
    
    # Check Karoon Chrome
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'شیر توالت (آفتابه) کسرا مدل کارون کروم'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 8100000
    assert buy == 6480000
    
    # Check Robbin Chrome
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'ست کامل ۴ تکه شیرآلات کسرا مدل رابین کروم'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 44130000
    assert buy == int(round(44130000 * 0.80))
    
    # Check Built-in Mechanism Tip 5
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'مکانیزم حمام توکار کسرا تیپ ۵'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 17500000
    assert buy == int(round(17500000 * 0.80))
    
    # Check Flush tank Val-hang
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'استراکچر و مکانیزم فلاش تانک توکار کسرا مدل وال هنگ'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 26600000
    assert buy == int(round(26600000 * 0.80))
    
    conn.close()
