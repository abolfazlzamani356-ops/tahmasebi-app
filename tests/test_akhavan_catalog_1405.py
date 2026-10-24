# -*- coding: utf-8 -*-
"""
Tests for Akhavan (اخوان) Catalog 1405 Update
Validating 21% purchase discount calculation and database synchronization.
"""
import pytest
import sqlite3
import os
import sys

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import akhavan_catalog_data

def test_akhavan_catalog_generator():
    items = akhavan_catalog_data.generate_all_akhavan_items(21.0)
    assert len(items) == 473, f"Expected 473 items, got {len(items)}"
    
    for item in items:
        sell = item['sell_price']
        buy = item['buy_price']
        assert sell > 0, f"Sell price must be positive for {item['name']}"
        assert buy > 0, f"Buy price must be positive for {item['name']}"
        expected_buy = int(round(sell * 0.79))
        assert buy == expected_buy, f"Buy price {buy} does not match 21% discount of {sell} (expected {expected_buy}) for {item['name']}"
        assert '21.0%' in item['description'] or '21%' in item['description']
        assert item['brand'] == 'اخوان (Akhavan)'

def test_akhavan_database_records():
    db_path = os.path.join(base_dir, 'instance', 'tahmasebi_store_persistent.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Check sample items across all categories
    test_cases = [
        # (name, expected_sell, expected_buy)
        ('سینک اخوان کد 4', 20487100, int(round(20487100 * 0.79))),
        ('سینک اخوان کد 88', 22265100, int(round(22265100 * 0.79))),
        ('سینک باکسی اخوان کد 303', 35638800, int(round(35638800 * 0.79))),
        ('سینک باکسی اخوان کد NEW-321', 24100000, int(round(24100000 * 0.79))),
        ('سینک باکسی اخوان کد NEW-323', 28700000, int(round(28700000 * 0.79))),
        ('سینک باکسی اخوان کد 333 (R0)', 60664100, int(round(60664100 * 0.79))),
        ('سینک زیر کابینتی اخوان کد 400', 18895300, int(round(18895300 * 0.79))),
        ('سینک صنعتی یک لگن اخوان مدل W35', 6651800, int(round(6651800 * 0.79))),
        ('اجاق گاز مبله فردار اخوان مدل M2-EDTS', 98925500, int(round(98925500 * 0.79))),
        ('اجاق گاز مبله فردار اخوان مدل M15-EDTR', 133317100, int(round(133317100 * 0.79))),
        ('اجاق گاز صفحه‌ای اخوان مدل GI4', 31444700, int(round(31444700 * 0.79))),
        ('اجاق گاز صفحه‌ای اخوان مدل GI-150', 44801900, int(round(44801900 * 0.79))),
        ('اجاق گاز صفحه‌ای اخوان مدل GI-150S', 44801900, int(round(44801900 * 0.79))),
        ('اجاق گاز صفحه‌ای اخوان مدل G1', 27352800, int(round(27352800 * 0.79))),
        ('اجاق گاز صفحه‌ای اخوان مدل V8-SHT', 72393700, int(round(72393700 * 0.79))),
        ('اجاق گاز صفحه‌ای اخوان مدل GE3', 95092100, int(round(95092100 * 0.79))),
        ('هود اخوان مدل H4', 28486900, int(round(28486900 * 0.79))),
        ('هود موتور فلزی اخوان مدل H51-MF', 32035800, int(round(32035800 * 0.79))),
        ('هود اخوان مدل H200', 23524600, int(round(23524600 * 0.79))),
        ('فر توکار اخوان مدل F3', 54800600, int(round(54800600 * 0.79))),
        ('فر توکار اخوان مدل F20', 76818600, int(round(76818600 * 0.79))),
        ('فر ریل‌دار پرو اخوان مدل F41-Pro', 110841200, int(round(110841200 * 0.79))),
        ('شیر ظرفشویی اخوان مدل T51', 28476800, int(round(28476800 * 0.79))),
        ('شیر ظرفشویی اخوان مدل T52', 23152500, int(round(23152500 * 0.79))),
    ]
    
    for name, expected_sell, expected_buy in test_cases:
        c.execute("SELECT sell_price, buy_price, description FROM product_catalog WHERE name = ? AND brand = 'اخوان (Akhavan)'", (name,))
        row = c.fetchone()
        assert row is not None, f"Product '{name}' not found in DB!"
        sell, buy, desc = row
        assert sell == expected_sell, f"Sell price mismatch for '{name}': expected {expected_sell}, got {sell}"
        assert buy == expected_buy, f"Buy price mismatch for '{name}': expected {expected_buy}, got {buy}"
        assert '21.0%' in desc or '21%' in desc
    
    conn.close()

def test_app_py_akhavan_seeding_config():
    app_path = os.path.join(base_dir, 'app.py')
    with open(app_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert "_seed_catalog('اخوان (Akhavan)', generate_all_akhavan_items, 21.0, 'Akhavan', update_existing=True)" in content
