# -*- coding: utf-8 -*-
"""
Tests for Bimax (بیمکث) Catalog Version 63 (1405/07/15)
Validating 19% purchase discount calculation and database synchronization.
"""
import pytest
import sqlite3
import os
import sys

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import bimax_catalog_data

def test_bimax_catalog_generator():
    items = bimax_catalog_data.generate_all_bimax_items(19.0)
    assert len(items) == 163, f"Expected 163 items, got {len(items)}"
    
    for item in items:
        sell = item['sell_price']
        buy = item['buy_price']
        assert sell > 0, f"Sell price must be positive for {item['name']}"
        assert buy > 0, f"Buy price must be positive for {item['name']}"
        expected_buy = int(round(sell * 0.81))
        assert buy == expected_buy, f"Buy price {buy} does not match 19% discount of {sell} (expected {expected_buy}) for {item['name']}"
        assert '19.0%' in item['description'] or '19%' in item['description']
        assert item['brand'] == 'بیمکث (Bimax)'

def test_bimax_database_records():
    db_path = os.path.join(base_dir, 'instance', 'tahmasebi_store_persistent.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("SELECT count(*) FROM product_catalog WHERE brand = 'بیمکث (Bimax)'")
    count = c.fetchone()[0]
    assert count == 163, f"Expected 163 Bimax products in DB, found {count}"
    
    # Check Hood 1101
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'هود بیمکث مدل 1101 مشکی سایز 80-90'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 32000000
    assert buy == int(round(32000000 * 0.81))
    
    # Check Hood 1601-V2 (آسانسوری)
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'هود آسانسوری بیمکث مدل 1601-V2 مشکی سایز 90'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 110000000
    assert buy == int(round(110000000 * 0.81))

    # Check Hood E100-V3
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'هود مخفی توکار بیمکث مدل E100-V3 مشکی سایز 70'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 13500000
    assert buy == int(round(13500000 * 0.81))

    # Check Gas 2204 مشکی
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'اجاق گاز صفحه‌ای بیمکث مدل 2204 مشکی (G5 Defendi Flame Select)'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 57500000
    assert buy == int(round(57500000 * 0.81))

    # Check Gas 2204 Anti glare سفید
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'اجاق گاز صفحه‌ای بیمکث مدل *2204 سفید Anti glare (AG-G5 Defendi)'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 78500000
    assert buy == int(round(78500000 * 0.81))

    # Check Gas E201 (G5)
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'اجاق گاز صفحه‌ای مشکی بیمکث مدل E201 (G5)'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 27500000
    assert buy == int(round(27500000 * 0.81))

    # Check Oven 3106 CHEF X
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'فر توکار بیمکث مدل 3106 CHEF X'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 129000000
    assert buy == int(round(129000000 * 0.81))

    # Check Oven E300-V2
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'فر توکار بیمکث مدل E300-V2 مشکی'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 38500000
    assert buy == int(round(38500000 * 0.81))

    # Check Microwave MT001
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'مایکروویو توکار بیمکث مدل MT001 مکانیکی'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 35000000
    assert buy == int(round(35000000 * 0.81))

    # Check Sink 723
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'سینک دست‌ساز بیمکث مدل 723 سایز 120*50 (فلش مونت R11)'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 65000000
    assert buy == int(round(65000000 * 0.81))

    # Check Sink 4110*
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'سینک دست‌ساز پله‌ای بیمکث مدل *4110 سایز 115*52 (فلش مونت R11)'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 69000000
    assert buy == int(round(69000000 * 0.81))

    # Check Sink E400
    c.execute("SELECT sell_price, buy_price FROM product_catalog WHERE name = 'سینک فانتزی توکار بیمکث مدل E400 سایز 90*50'")
    row = c.fetchone()
    assert row is not None
    sell, buy = row
    assert sell == 26500000
    assert buy == int(round(26500000 * 0.81))

    conn.close()
