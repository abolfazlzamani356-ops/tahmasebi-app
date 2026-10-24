# -*- coding: utf-8 -*-
"""
Tests for Ilia Steel (ایلیا استیل) Catalog (13 Mehr 1405)
Validating 18% purchase discount calculation and database synchronization.
"""
import pytest
import sqlite3
import os
import sys

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import ilia_steel_catalog_data

def test_ilia_steel_catalog_generator():
    items = ilia_steel_catalog_data.generate_all_ilia_steel_items(18.0)
    assert len(items) == 219, f"Expected 219 items, got {len(items)}"
    
    valid_categories = {'سینک', 'هود', 'گاز صفحه‌ای', 'فر توکار'}
    
    for item in items:
        sell = item['sell_price']
        buy = item['buy_price']
        assert sell > 0, f"Sell price must be positive for {item['name']}"
        assert buy > 0, f"Buy price must be positive for {item['name']}"
        expected_buy = int(round(sell * 0.82))
        assert buy == expected_buy, f"Buy price {buy} does not match 18% discount of {sell} (expected {expected_buy}) for {item['name']}"
        assert '18.0%' in item['description'] or '18%' in item['description']
        assert item['brand'] == 'ایلیا استیل (Ilia Steel)'
        assert item['category'] in valid_categories, f"Invalid category {item['category']} for {item['name']}"

def test_ilia_steel_database_records():
    db_path = os.path.join(base_dir, 'instance', 'tahmasebi_store_persistent.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(id) FROM product_catalog WHERE brand = 'ایلیا استیل (Ilia Steel)'")
    count = c.fetchone()[0]
    assert count >= 219, f"Expected at least 219 Ilia Steel products in DB, found {count}"
    
    test_cases = [
        # (name, expected_sell, expected_buy)
        # Sinks
        ('سینک فانتزی توکار ایلیا استیل مدل 2012', 26261000, int(round(26261000 * 0.82))),
        ('سینک فانتزی روکار ایلیا استیل مدل 1013', 31138000, int(round(31138000 * 0.82))),
        ('سینک نیمه فانتزی توکار ایلیا استیل مدل 4013', 16883000, int(round(16883000 * 0.82))),
        ('سینک نیمه فانتزی روکار ایلیا استیل مدل 3021', 15707000, int(round(15707000 * 0.82))),
        ('سینک کلاسیک ایلیا استیل مدل 111', 7294000, int(round(7294000 * 0.82))),
        ('سینک شیشه‌ای توکار ایلیا استیل مدل 8011', 33655000, int(round(33655000 * 0.82))),
        ('سینک باکس دست‌ساز ایلیا استیل مدل 6001', 11811000, int(round(11811000 * 0.82))),
        ('سینک باکس دست‌ساز ایلیا استیل مدل 6044', 77860000, int(round(77860000 * 0.82))),
        # Cooktops
        ('گاز صفحه‌ای شیشه‌ای ایلیا استیل مدل G 201', 22763000, int(round(22763000 * 0.82))),
        ('گاز صفحه‌ای شیشه‌ای ایلیا استیل مدل G 527 RF', 52113000, int(round(52113000 * 0.82))),
        ('گاز صفحه‌ای استیل ایلیا استیل مدل S 201', 23629000, int(round(23629000 * 0.82))),
        ('گاز صفحه‌ای استیل ایلیا استیل مدل S 512WD', 58980000, int(round(58980000 * 0.82))),
        ('گاز صفحه‌ای ایتالیایی ایلیا استیل مدل IS 5910', 65844000, int(round(65844000 * 0.82))),
        ('گاز صفحه‌ای ایتالیایی ایلیا استیل مدل IG5919BE', 75543000, int(round(75543000 * 0.82))),
        # Hoods
        ('هود ایلیا استیل مدل سارینا سفید', 35524000, int(round(35524000 * 0.82))),
        ('هود ایلیا استیل مدل هیوا WIFI', 40569000, int(round(40569000 * 0.82))),
        ('هود ایلیا استیل مدل تارا', 50922000, int(round(50922000 * 0.82))),
        # Ovens
        ('فر توکار ایلیا استیل مدل IO 110', 85300000, int(round(85300000 * 0.82))),
        ('فر توکار ایلیا استیل مدل IO 114 (بخارپز)', 129158000, int(round(129158000 * 0.82))),
        ('فر توکار ایلیا استیل مدل IO 119schott', 128363000, int(round(128363000 * 0.82))),
        ('فر توکار ایلیا استیل مدل IO 501', 104133000, int(round(104133000 * 0.82))),
    ]
    
    for name, expected_sell, expected_buy in test_cases:
        c.execute("SELECT sell_price, buy_price, description FROM product_catalog WHERE name = ? AND brand = 'ایلیا استیل (Ilia Steel)'", (name,))
        row = c.fetchone()
        assert row is not None, f"Product '{name}' not found in DB!"
        sell, buy, desc = row
        assert sell == expected_sell, f"Sell price mismatch for '{name}': expected {expected_sell}, got {sell}"
        assert buy == expected_buy, f"Buy price mismatch for '{name}': expected {expected_buy}, got {buy}"
        assert '18.0%' in desc or '18%' in desc
    
    conn.close()

def test_app_py_ilia_steel_seeding_config():
    app_path = os.path.join(base_dir, 'app.py')
    with open(app_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert "_seed_catalog('ایلیا استیل (Ilia Steel)', generate_all_ilia_steel_items, 18.0, 'Ilia Steel', update_existing=True)" in content
