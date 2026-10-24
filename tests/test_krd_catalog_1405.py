# -*- coding: utf-8 -*-
"""
Tests for KRD Cabin Catalog (Series Modern - 1405-07-12)
Validating 30% purchase discount calculation and database synchronization.
"""
import pytest
import sqlite3
import os
import sys

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import krd_catalog_data

def test_krd_catalog_generator():
    items = krd_catalog_data.generate_all_krd_items(30.0)
    assert len(items) == 125, f"Expected 125 items, got {len(items)}"
    
    for item in items:
        sell = item['sell_price']
        buy = item['buy_price']
        assert sell > 0, f"Sell price must be positive for {item['name']}"
        assert buy > 0, f"Buy price must be positive for {item['name']}"
        expected_buy = int(round(sell * 0.70))
        assert buy == expected_buy, f"Buy price {buy} does not match 30% discount of {sell} (expected {expected_buy}) for {item['name']}"
        assert '30.0%' in item['description'] or '30%' in item['description']
        assert item['brand'] == 'KRD'

def test_krd_database_records():
    db_path = os.path.join(base_dir, 'instance', 'tahmasebi_store_persistent.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("SELECT count(*) FROM product_catalog WHERE brand = 'KRD'")
    count = c.fetchone()[0]
    assert count == 125, f"Expected 125 KRD products in DB, found {count}"
    
    test_cases = [
        # (name, expected_sell, expected_buy)
        ('روشویی فول ست KRD مدل هلیا 60 (کابین + آینه باکس)', 13435000, int(round(13435000 * 0.70))),
        ('کابین تک روشویی KRD مدل هلیا 60', 7606000, int(round(7606000 * 0.70))),
        ('آینه باکس روشویی KRD مدل هلیا 60', 5829000, int(round(5829000 * 0.70))),
        ('باکس تک روشویی KRD مدل هلیا 60', 3605000, int(round(3605000 * 0.70))),
        ('آینه تک روشویی KRD مدل هلیا 60', 2224000, int(round(2224000 * 0.70))),
        ('روشویی فول ست KRD مدل مارتین 60 (کابین + آینه باکس)', 13830000, int(round(13830000 * 0.70))),
        ('روشویی فول ست KRD مدل دلارام (کابین + آینه باکس)', 14384000, int(round(14384000 * 0.70))),
        ('روشویی فول ست KRD مدل لیون (کابین + آینه باکس)', 16974000, int(round(16974000 * 0.70))),
        ('روشویی فول ست KRD مدل ارکیده (کابین + آینه باکس)', 26290000, int(round(26290000 * 0.70))),
        ('کابین تک روشویی KRD مدل ارکیده', 17582000, int(round(17582000 * 0.70))),
        ('روشویی فول ست KRD مدل بهار (کابین + آینه باکس)', 14614000, int(round(14614000 * 0.70))),
    ]
    
    for name, expected_sell, expected_buy in test_cases:
        c.execute("SELECT sell_price, buy_price, description FROM product_catalog WHERE name = ? AND brand = 'KRD'", (name,))
        row = c.fetchone()
        assert row is not None, f"Product '{name}' not found in DB!"
        sell, buy, desc = row
        assert sell == expected_sell, f"Sell price mismatch for '{name}': expected {expected_sell}, got {sell}"
        assert buy == expected_buy, f"Buy price mismatch for '{name}': expected {expected_buy}, got {buy}"
        assert '30.0%' in desc or '30%' in desc
    
    conn.close()

def test_app_py_krd_seeding_config():
    app_path = os.path.join(base_dir, 'app.py')
    with open(app_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert "_seed_catalog('KRD', generate_all_krd_items, 30.0, 'KRD', update_existing=True)" in content
