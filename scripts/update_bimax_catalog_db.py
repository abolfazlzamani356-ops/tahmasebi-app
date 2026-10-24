# -*- coding: utf-8 -*-
"""
Database update script for Bimax Catalog (Version 63 - 1405/07/15)
With 19% purchase discount.
"""
import sys, os, sqlite3, shutil
from datetime import datetime

base_dir = r'I:\محاسبه درصد های بچه ها'
sys.path.insert(0, base_dir)
import bimax_catalog_data

db_path = os.path.join(base_dir, 'instance', 'tahmasebi_store_persistent.db')
backup_path = os.path.join(base_dir, 'instance', f'tahmasebi_store_persistent_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')

print(f"Creating DB backup at: {backup_path}")
shutil.copy2(db_path, backup_path)

conn = sqlite3.connect(db_path)
c = conn.cursor()

# Generate new items with 19% discount
new_items = bimax_catalog_data.generate_all_bimax_items(19.0)
print(f"Generated {len(new_items)} items from bimax_catalog_data.")

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
    
    c.execute("SELECT id, sell_price, buy_price FROM product_catalog WHERE name = ? AND brand = ?", (name, brand))
    row = c.fetchone()
    if row:
        prod_id, old_sell, old_buy = row
        if old_sell != sell_price or old_buy != buy_price:
            c.execute("""
                UPDATE product_catalog
                SET sell_price = ?, buy_price = ?, category = ?, description = ?
                WHERE id = ?
            """, (sell_price, buy_price, category, desc, prod_id))
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
c.execute("SELECT count(*) FROM product_catalog WHERE brand = 'بیمکث (Bimax)'")
bimax_total = c.fetchone()[0]

print(f"\nUpdate completed successfully:")
print(f" - Updated existing items: {updated_count}")
print(f" - Inserted new items: {inserted_count}")
print(f" - Unchanged items: {unchanged_count}")
print(f" - Total 'بیمکث (Bimax)' products in DB: {bimax_total}")

# Verify sample items
c.execute("""
    SELECT name, category, sell_price, buy_price, description 
    FROM product_catalog 
    WHERE brand = 'بیمکث (Bimax)' 
    ORDER BY id ASC LIMIT 5
""")
print("\nSample updated Bimax items (First 5):")
for r in c.fetchall():
    print(r)

# Verify sample new E-series items
c.execute("""
    SELECT name, category, sell_price, buy_price, description 
    FROM product_catalog 
    WHERE brand = 'بیمکث (Bimax)' AND name LIKE '%سری E%' OR (brand = 'بیمکث (Bimax)' AND name LIKE '%E10%')
    LIMIT 5
""")
print("\nSample new E-series items:")
for r in c.fetchall():
    print(r)

conn.close()
