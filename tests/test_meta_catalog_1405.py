# -*- coding: utf-8 -*-
"""
Tests for Meta Kitchens (مِـتا) Catalog (13 Mehr 1405)
Validating 25% purchase discount calculation and database synchronization.
"""
import pytest
import sqlite3
import os
import sys

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import meta_catalog_data

def test_meta_catalog_generator():
    items = meta_catalog_data.generate_all_meta_items(25.0)
    assert len(items) == 72, f"Expected 72 items, got {len(items)}"
    
    valid_categories = {'سینک', 'هود', 'گاز صفحه‌ای'}
    
    for item in items:
        sell = item['sell_price']
        buy = item['buy_price']
        assert sell > 0, f"Sell price must be positive for {item['name']}"
        assert buy > 0, f"Buy price must be positive for {item['name']}"
        expected_buy = int(round(sell * 0.75))
        assert buy == expected_buy, f"Buy price {buy} does not match 25% discount of {sell} (expected {expected_buy}) for {item['name']}"
        assert '25.0%' in item['description'] or '25%' in item['description']
        assert item['brand'] == 'متا (Meta)'
        assert item['category'] in valid_categories, f"Invalid category {item['category']} for {item['name']}"

def test_meta_database_records():
    db_path = os.path.join(base_dir, 'instance', 'tahmasebi_store_persistent.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(id) FROM product_catalog WHERE brand = 'متا (Meta)'")
    count = c.fetchone()[0]
    assert count == 72, f"Expected 72 Meta products in DB, found {count}"
    
    test_cases = [
        # (name, expected_sell, expected_buy)
        # Sinks - Page 3
        ('سینک استیل متا مدل ML802UR-B زیرسطحی', 67850000, int(round(67850000 * 0.75))),
        ('سینک استیل متا مدل ML1202RS-L/R-G لیوان‌شوردار', 77050000, int(round(77050000 * 0.75))),
        # Sinks - Page 4
        ('سینک استیل متا مدل ML104SP-G شیر آبشاری و لیوان‌شور', 59869800, int(round(59869800 * 0.75))),
        ('سینک استیل متا مدل M104SP-G شیر آبشاری و لیوان‌شور', 69232500, int(round(69232500 * 0.75))),
        ('سینک استیل متا مدل M104 ساده', 51256000, int(round(51256000 * 0.75))),
        # Sinks - Page 5
        ('سینک استیل متا مدل M90RS-G گوشه R10 لیوان‌شور', 60720000, int(round(60720000 * 0.75))),
        ('سینک استیل متا مدل ML104 ساده', 48296600, int(round(48296600 * 0.75))),
        # Sinks - Page 6
        ('سینک استیل متا مدل M902S-G دو پله لیوان‌شور', 59131500, int(round(59131500 * 0.75))),
        ('سینک استیل متا مدل M90S-G پله‌دار لیوان‌شور', 54425200, int(round(54425200 * 0.75))),
        # Sinks - Page 7
        ('سینک استیل متا مدل ML90S پله‌دار', 46639000, int(round(46639000 * 0.75))),
        ('سینک استیل متا مدل ML90R گوشه R10', 56577500, int(round(56577500 * 0.75))),
        # Sinks - Page 8
        ('سینک استیل متا مدل M77 ساده', 42498100, int(round(42498100 * 0.75))),
        ('سینک استیل متا مدل M77RS-G گوشه R10 لیوان‌شور', 56328000, int(round(56328000 * 0.75))),
        # Sinks - Page 9
        ('سینک استیل متا مدل ML77RD آبچکان‌دار گوشه R10', 46556000, int(round(46556000 * 0.75))),
        # Sinks - Page 10
        ('سینک استیل متا مدل MD50 دست‌ساز', 30921700, int(round(30921700 * 0.75))),
        ('سینک استیل متا مدل M65S-G پله‌دار لیوان‌شور', 40876200, int(round(40876200 * 0.75))),
        # Cooktops - Page 12
        ('گاز صفحه‌ای شیشه‌ای سفید متا مدل MG503W', 52054600, int(round(52054600 * 0.75))),
        ('گاز صفحه‌ای شیشه‌ای مشکی متا مدل MG504B', 45367800, int(round(45367800 * 0.75))),
        ('گاز صفحه‌ای استیل متا مدل MS501S', 49230500, int(round(49230500 * 0.75))),
        ('گاز صفحه‌ای شیشه‌ای مشکی متا مدل MG503B', 45367800, int(round(45367800 * 0.75))),
        # Hoods - Page 12
        ('هود مخفی متا مدل MH03B موتور BLDC', 40825900, int(round(40825900 * 0.75))),
        ('هود مخفی متا مدل MH02W سفید', 40250000, int(round(40250000 * 0.75))),
        ('هود مخفی متا مدل MH02B مشکی', 34544900, int(round(34544900 * 0.75))),
        ('هود مخفی متا مدل MH01B مشکی knock', 42538800, int(round(42538800 * 0.75))),
    ]
    
    for name, expected_sell, expected_buy in test_cases:
        c.execute("SELECT sell_price, buy_price, description FROM product_catalog WHERE name = ? AND brand = 'متا (Meta)'", (name,))
        row = c.fetchone()
        assert row is not None, f"Product '{name}' not found in DB!"
        sell, buy, desc = row
        assert sell == expected_sell, f"Sell price mismatch for '{name}': expected {expected_sell}, got {sell}"
        assert buy == expected_buy, f"Buy price mismatch for '{name}': expected {expected_buy}, got {buy}"
        assert '25.0%' in desc or '25%' in desc
    
    conn.close()

def test_app_py_meta_seeding_config():
    app_path = os.path.join(base_dir, 'app.py')
    with open(app_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert "_seed_catalog('متا (Meta)', generate_all_meta_items, 25.0, 'Meta', update_existing=True)" in content
