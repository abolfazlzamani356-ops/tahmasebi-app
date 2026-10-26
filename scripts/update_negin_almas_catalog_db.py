# -*- coding: utf-8 -*-
"""
Database update script for Negin Almas (نگین الماس) Catalog (List 1405.07.15)
With 15% purchase discount.
"""
import sys, os, sqlite3, shutil
from datetime import datetime

base_dir = r'I:\محاسبه درصد های بچه ها'
sys.path.insert(0, base_dir)
import negin_almas_catalog_data

db_path = os.path.join(base_dir, 'instance', 'tahmasebi_store_persistent.db')
backup_path = os.path.join(base_dir, 'instance', f'tahmasebi_store_persistent_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')

print(f"Creating DB backup at: {backup_path}")
shutil.copy2(db_path, backup_path)

conn = sqlite3.connect(db_path)
c = conn.cursor()

# Generate new items with 15% discount
new_items = negin_almas_catalog_data.generate_all_negin_almas_items(15.0)
print(f"Generated {len(new_items)} items from negin_almas_catalog_data.")

updated_count = 0
inserted_count = 0
unchanged_count = 0
now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

for item in new_items:
    name = item['name']
    brand = item['brand']
    category = item['category']
    sell_price = item['sell_price']
    buy_price = item['buy_price']
    desc = item['description']
    
    c.execute("""
        SELECT id, sell_price, buy_price 
        FROM product_catalog 
        WHERE name = ? AND (brand = ? OR brand LIKE '%نگین الماس%' OR brand LIKE '%Negin Almas%')
    """, (name, brand))
    row = c.fetchone()
    if row:
        prod_id, old_sell, old_buy = row
        if old_sell != sell_price or old_buy != buy_price:
            c.execute("""
                UPDATE product_catalog
                SET brand = ?, sell_price = ?, buy_price = ?, category = ?, description = ?
                WHERE id = ?
            """, (brand, sell_price, buy_price, category, desc, prod_id))
            updated_count += 1
        else:
            unchanged_count += 1
    else:
        c.execute("""
            INSERT INTO product_catalog (name, category, brand, buy_price, sell_price, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, category, brand, buy_price, sell_price, desc, now_str))
        inserted_count += 1

conn.commit()

# Final check
c.execute("SELECT COUNT(id) FROM product_catalog WHERE brand = 'نگین الماس (Negin Almas)'")
negin_total = c.fetchone()[0]

print(f"\nUpdate completed successfully:")
print(f" - Updated existing items: {updated_count}")
print(f" - Inserted new items: {inserted_count}")
print(f" - Unchanged items: {unchanged_count}")
print(f" - Total 'نگین الماس (Negin Almas)' products in DB: {negin_total}")

# Verify sample items across categories
categories = ['سینک', 'گاز صفحه‌ای']
print("\nSample updated Negin Almas items per category:")
for cat in categories:
    c.execute("""
        SELECT name, sell_price, buy_price, description 
        FROM product_catalog 
        WHERE brand = 'نگین الماس (Negin Almas)' AND category = ?
        ORDER BY id ASC LIMIT 3
    """, (cat,))
    for row in c.fetchall():
        print(f"[{cat}] {row[0]}: مصرف‌کننده={row[1]:,} | خرید={row[2]:,}")

conn.close()
