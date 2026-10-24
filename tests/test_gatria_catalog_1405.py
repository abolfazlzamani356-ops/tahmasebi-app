# -*- coding: utf-8 -*-
"""
Tests for Gatria (چینی بهداشتی گاتریا) Catalog 1405-07-18
Validating 15% purchase discount calculation and database synchronization.
"""
import pytest
import sqlite3
import os
import sys

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import gatria_catalog_data

def test_gatria_catalog_generator():
    items = gatria_catalog_data.generate_all_gatria_items(15.0)
    assert len(items) == 881, f"Expected 881 items, got {len(items)}"
    
    for item in items:
        sell = item['sell_price']
        buy = item['buy_price']
        assert sell > 0, f"Sell price must be positive for {item['name']}"
        assert buy > 0, f"Buy price must be positive for {item['name']}"
        expected_buy = int(round(sell * 0.85))
        assert buy == expected_buy, f"Buy price {buy} does not match 15% discount of {sell} (expected {expected_buy}) for {item['name']}"
        assert '15.0%' in item['description'] or '15%' in item['description']
        assert item['brand'] == 'گاتریا (Gatria)'

def test_gatria_database_records():
    db_path = os.path.join(base_dir, 'instance', 'tahmasebi_store_persistent.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("SELECT count(*) FROM product_catalog WHERE brand = 'گاتریا (Gatria)'")
    count = c.fetchone()[0]
    assert count == 881, f"Expected 881 Gatria products in DB, found {count}"
    
    # Check Satron One piece Grade 1 White
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'توالت فرنگی ساترون یک تکه گاتریا - سفید (درجه ۱)'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 21657000
    assert buy == int(round(21657000 * 0.85))
    
    # Check Wall Hung Leo with bidet Grade 1 White
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'توالت فرنگی والهنگ لئو گاتریا مجهز به جای بیده - سفید (درجه ۱)'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 19814000
    assert buy == int(round(19814000 * 0.85))
    
    # Check Sink York 75 Grade 1 White
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'سینک سرامیکی یورک 75 گاتریا - سفید (درجه ۱)'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 3290000
    assert buy == int(round(3290000 * 0.85))
    
    # Check Concealed Cistern 6001
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'فلاش تانک توکار پروفیلی 6001 گاتریا'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 20165000
    assert buy == int(round(20165000 * 0.85))
    
    # Check Double Button 7001/8001
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'کلید استراکچر 7001 و 8001 سفید گاتریا'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 2070000
    assert buy == int(round(2070000 * 0.85))
    
    # Check Bidet pack 80000627
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'پک شیر بغل فرنگی سرد گاتریا (کد 80000627)'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 2665000
    assert buy == int(round(2665000 * 0.85))
    
    # Check PP Seat cover
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'درب آرام‌بند P.P فرنگی گاتریا'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 2500000
    assert buy == int(round(2500000 * 0.85))

    conn.close()
