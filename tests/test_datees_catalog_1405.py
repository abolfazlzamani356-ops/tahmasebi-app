# -*- coding: utf-8 -*-
"""
Tests for Datees (داتیس) Catalog (version: D0251)
Validating 18% purchase discount calculation and database synchronization.
"""
import pytest
import sqlite3
import os
import sys

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import datees_catalog_data

def test_datees_catalog_generator():
    items = datees_catalog_data.generate_all_datees_items(18.0)
    assert len(items) == 193, f"Expected 193 items, got {len(items)}"
    
    valid_categories = {'گاز صفحه‌ای', 'هود', 'سینک', 'فر توکار', 'مایکروویو'}
    
    for item in items:
        sell = item['sell_price']
        buy = item['buy_price']
        assert sell > 0, f"Sell price must be positive for {item['name']}"
        assert buy > 0, f"Buy price must be positive for {item['name']}"
        expected_buy = int(round(sell * 0.82))
        assert buy == expected_buy, f"Buy price {buy} does not match 18% discount of {sell} (expected {expected_buy}) for {item['name']}"
        assert '18.0%' in item['description'] or '18%' in item['description']
        assert item['brand'] == 'داتیس (Datees)'
        assert item['category'] in valid_categories, f"Invalid category {item['category']} for {item['name']}"

def test_datees_database_records():
    db_path = os.path.join(base_dir, 'instance', 'tahmasebi_store_persistent.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(id) FROM product_catalog WHERE brand = 'داتیس (Datees)'")
    count = c.fetchone()[0]
    assert count >= 193, f"Expected at least 193 Datees products in DB, found {count}"
    
    test_cases = [
        # (name, expected_sell, expected_buy)
        ('اجاق گاز صفحه‌ای شیشه‌ای داتیس مدل DG 598 (قطعات ساباف ایتالیا)', 68259000, int(round(68259000 * 0.82))),
        ('اجاق گاز صفحه‌ای شیشه‌ای داتیس مدل DG 593 (ایرانی)', 48005000, int(round(48005000 * 0.82))),
        ('اجاق گاز صفحه‌ای شیشه‌ای داتیس مدل DG 402 (۴ شعله)', 36604000, int(round(36604000 * 0.82))),
        ('اجاق گاز صفحه‌ای استیل داتیس مدل DS 590 (قطعات ساباف)', 74368000, int(round(74368000 * 0.82))),
        ('اجاق برقی المنتی شیشه‌ای داتیس مدل DGE 250 (۲ شعله)', 55666000, int(round(55666000 * 0.82))),
        ('هود مخفی داتیس مدل فرمان صوتی', 47238000, int(round(47238000 * 0.82))),
        ('هود آسانسوری داتیس مدل ELEVA سایز 70', 51872000, int(round(51872000 * 0.82))),
        ('هود مورب داتیس مدل کلاسیک الترا', 48855000, int(round(48855000 * 0.82))),
        ('سینک استیل توکار داتیس مدل 214', 40750000, int(round(40750000 * 0.82))),
        ('سینک زیرکورینی استیل داتیس مدل 703 (سایز 52*74)', 48872000, int(round(48872000 * 0.82))),
        ('فر برقی توکار داتیس مدل 744', 151329000, int(round(151329000 * 0.82))),
        ('فر برقی توکار داتیس مدل 685', 62390000, int(round(62390000 * 0.82))),
        ('فر برق و گاز توکار داتیس مدل 672', 93919000, int(round(93919000 * 0.82))),
        ('مایکروویو توکار داتیس مدل 944 الترا', 151274000, int(round(151274000 * 0.82))),
        ('کشو گرمکن توکار داتیس مدل 960', 52762000, int(round(52762000 * 0.82))),
    ]
    
    for name, expected_sell, expected_buy in test_cases:
        c.execute("SELECT sell_price, buy_price, description FROM product_catalog WHERE name = ? AND brand = 'داتیس (Datees)'", (name,))
        row = c.fetchone()
        assert row is not None, f"Product '{name}' not found in DB!"
        sell, buy, desc = row
        assert sell == expected_sell, f"Sell price mismatch for '{name}': expected {expected_sell}, got {sell}"
        assert buy == expected_buy, f"Buy price mismatch for '{name}': expected {expected_buy}, got {buy}"
        assert '18.0%' in desc or '18%' in desc
    
    conn.close()

def test_app_py_datees_seeding_config():
    app_path = os.path.join(base_dir, 'app.py')
    with open(app_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert "_seed_catalog('داتیس (Datees)', generate_all_datees_items, 18.0, 'Datees', update_existing=True)" in content
