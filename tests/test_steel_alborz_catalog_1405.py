# -*- coding: utf-8 -*-
"""
Tests for Steel Alborz (استیل البرز) Catalog List 50 (Fall 1405)
Validating 21% purchase discount calculation and database synchronization.
"""
import pytest
import sqlite3
import os
import sys

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import steel_alborz_catalog_data

def test_steel_alborz_catalog_generator():
    items = steel_alborz_catalog_data.generate_all_steel_alborz_items(21.0)
    assert len(items) == 235, f"Expected 235 items, got {len(items)}"
    
    for item in items:
        sell = item['sell_price']
        buy = item['buy_price']
        assert sell > 0, f"Sell price must be positive for {item['name']}"
        assert buy > 0, f"Buy price must be positive for {item['name']}"
        expected_buy = int(round(sell * 0.79))
        assert buy == expected_buy, f"Buy price {buy} does not match 21% discount of {sell} (expected {expected_buy}) for {item['name']}"
        assert '21.0%' in item['description'] or '21%' in item['description']
        assert item['brand'] == 'استیل البرز (Steel Alborz)'

def test_steel_alborz_database_records():
    db_path = os.path.join(base_dir, 'instance', 'tahmasebi_store_persistent.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("SELECT count(*) FROM product_catalog WHERE brand = 'استیل البرز (Steel Alborz)'")
    count = c.fetchone()[0]
    assert count == 235, f"Expected 235 Steel Alborz products in DB, found {count}"
    
    # Check sample items across all categories
    test_cases = [
        # (name, expected_sell, expected_buy)
        ('سینک پرسی روکار ساحل مدل تک لگن 50*50*0.4', 3020000, int(round(3020000 * 0.79))),
        ('سینک نیمه فانتزی توکار استیل البرز مدل 301/52', 13970000, int(round(13970000 * 0.79))),
        ('سیفون نیمه فانتزی تک لگن استیل البرز', 1020000, int(round(1020000 * 0.79))),
        ('سینک باکسی توکار استیل البرز مدل 959/52', 44670000, int(round(44670000 * 0.79))),
        ('سینک فانتزی روکار استیل البرز مدل 856/60', 29570000, int(round(29570000 * 0.79))),
        ('اجاق گاز صفحه‌ای سرامیکی استیل البرز مدل C5903', 127530000, int(round(127530000 * 0.79))),
        ('اجاق گاز صفحه‌ای استیل البرز مدل S6121 (Chef)', 84010000, int(round(84010000 * 0.79))),
        ('اجاق گاز صفحه‌ای شیشه‌ای استیل البرز مدل G5904/S', 59260000, int(round(59260000 * 0.79))),
        ('اجاق گاز صفحه‌ای استیل البرز مدل S6125', 52920000, int(round(52920000 * 0.79))),
        ('هود مخفی توکار استیل البرز مدل SA518', 35810000, int(round(35810000 * 0.79))),
        ('هود آشپزخانه زیرکابینتی استیل البرز مدل SA119', 32720000, int(round(32720000 * 0.79))),
        ('فر برقی توکار استیل البرز مدل FE82', 121850000, int(round(121850000 * 0.79))),
        ('مایکروویو توکار استیل البرز مدل MS252', 68220000, int(round(68220000 * 0.79))),
        ('شیر ظرفشویی استیل البرز مدل ST411', 28500000, int(round(28500000 * 0.79))),
    ]
    
    for name, expected_sell, expected_buy in test_cases:
        c.execute("SELECT sell_price, buy_price, description FROM product_catalog WHERE name = ? AND brand = 'استیل البرز (Steel Alborz)'", (name,))
        row = c.fetchone()
        assert row is not None, f"Product '{name}' not found in DB!"
        sell, buy, desc = row
        assert sell == expected_sell, f"Sell price mismatch for '{name}': expected {expected_sell}, got {sell}"
        assert buy == expected_buy, f"Buy price mismatch for '{name}': expected {expected_buy}, got {buy}"
        assert '21.0%' in desc or '21%' in desc
    
    conn.close()

def test_app_py_steel_alborz_seeding_config():
    app_path = os.path.join(base_dir, 'app.py')
    with open(app_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert "_seed_catalog('استیل البرز (Steel Alborz)', generate_all_steel_alborz_items, 21.0, 'Steel Alborz', update_existing=True)" in content
