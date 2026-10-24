# -*- coding: utf-8 -*-
"""
Tests for Milan Bronze (میلان برنز) Catalog (List 05 - 1405.07.05)
Validating 18% purchase discount calculation and database synchronization.
"""
import pytest
import sqlite3
import os
import sys

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import milan_catalog_data

def test_milan_catalog_generator():
    items = milan_catalog_data.generate_all_milan_items(18.0)
    assert len(items) == 144, f"Expected 144 items, got {len(items)}"
    
    valid_categories = {'سینک', 'هود', 'گاز صفحه‌ای', 'فر توکار'}
    
    for item in items:
        sell = item['sell_price']
        buy = item['buy_price']
        assert sell > 0, f"Sell price must be positive for {item['name']}"
        assert buy > 0, f"Buy price must be positive for {item['name']}"
        expected_buy = int(round(sell * 0.82))
        assert buy == expected_buy, f"Buy price {buy} does not match 18% discount of {sell} (expected {expected_buy}) for {item['name']}"
        assert '18.0%' in item['description'] or '18%' in item['description']
        assert item['brand'] == 'میلان (Milan)'
        assert item['category'] in valid_categories, f"Invalid category {item['category']} for {item['name']}"

def test_milan_database_records():
    db_path = os.path.join(base_dir, 'instance', 'tahmasebi_store_persistent.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(id) FROM product_catalog WHERE brand = 'میلان (Milan)'")
    count = c.fetchone()[0]
    assert count == 144, f"Expected 144 Milan products in DB, found {count}"
    
    test_cases = [
        # (name, expected_sell, expected_buy)
        ('سینک دست‌ساز میلان مدل 4043 سایز 50*43', 16150000, int(round(16150000 * 0.82))),
        ('سینک دست‌ساز میلان مدل 40105-S03 سایز 105*52', 46150000, int(round(46150000 * 0.82))),
        ('سینک فانتزی توکار میلان مدل 9010 سایز 120*52', 27750000, int(round(27750000 * 0.82))),
        ('سینک فانتزی روکار میلان مدل 9011 سایز 120*60', 29850000, int(round(29850000 * 0.82))),
        ('سینک نیمه فانتزی توکار میلان مدل 1010 سایز 120*50', 16750000, int(round(16750000 * 0.82))),
        ('سینک تک لگن فانتزی میلان مدل 3010 سایز 45*40', 8650000, int(round(8650000 * 0.82))),
        ('هود مخفی توکار میلان مدل آراد 3000 (استیل 3 دور)', 12990000, int(round(12990000 * 0.82))),
        ('هود مورب دیواری میلان مدل آرمان موشن', 23990000, int(round(23990000 * 0.82))),
        ('گاز صفحه‌ای میلان مدل G5NEW پنج شعله', 32990000, int(round(32990000 * 0.82))),
        ('گاز صفحه‌ای میلان مدل G83T پنج شعله', 41090000, int(round(41090000 * 0.82))),
        ('گاز صفحه‌ای استیل میلان مدل S1 پنج شعله', 34690000, int(round(34690000 * 0.82))),
        ('گاز صفحه‌ای استیل میلان مدل S21Duol پنج شعله', 37990000, int(round(37990000 * 0.82))),
        ('فر توکار برقی میلان مدل BO100', 46190000, int(round(46190000 * 0.82))),
        ('فر توکار برقی میلان مدل BO601', 68090000, int(round(68090000 * 0.82))),
    ]
    
    for name, expected_sell, expected_buy in test_cases:
        c.execute("SELECT sell_price, buy_price, description FROM product_catalog WHERE name = ? AND brand = 'میلان (Milan)'", (name,))
        row = c.fetchone()
        assert row is not None, f"Product '{name}' not found in DB!"
        sell, buy, desc = row
        assert sell == expected_sell, f"Sell price mismatch for '{name}': expected {expected_sell}, got {sell}"
        assert buy == expected_buy, f"Buy price mismatch for '{name}': expected {expected_buy}, got {buy}"
        assert '18.0%' in desc or '18%' in desc
    
    conn.close()

def test_app_py_milan_seeding_config():
    app_path = os.path.join(base_dir, 'app.py')
    with open(app_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert "_seed_catalog('میلان (Milan)', generate_all_milan_items, 18.0, 'Milan', update_existing=True)" in content
