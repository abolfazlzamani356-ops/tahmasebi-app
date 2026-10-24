import sys, os, sqlite3, shutil
from datetime import datetime

base_dir = r'i:\محاسبه درصد های بچه ها'
sys.path.insert(0, base_dir)
import kasra_catalog_data

db_path = os.path.join(base_dir, 'instance', 'tahmasebi_store_persistent.db')
backup_path = os.path.join(base_dir, 'instance', f'tahmasebi_store_persistent_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')

print(f"Creating DB backup at: {backup_path}")
shutil.copy2(db_path, backup_path)

conn = sqlite3.connect(db_path)
c = conn.cursor()

# Generate new items with 20% discount
new_items = kasra_catalog_data.generate_all_kasra_items(20.0)
print(f"Generated {len(new_items)} items from kasra_catalog_data.")

updated_count = 0
inserted_count = 0
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
        c.execute("""
            INSERT INTO product_catalog (name, category, brand, buy_price, sell_price, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, category, brand, buy_price, sell_price, desc, now_str))
        inserted_count += 1

conn.commit()

# Final check
c.execute("SELECT count(*) FROM product_catalog WHERE brand = 'کسرا (Kasra)'")
kasra_total = c.fetchone()[0]
c.execute("SELECT count(*) FROM product_catalog WHERE brand = 'ایزی‌پایپ (Easy Pipe)'")
easypipe_total = c.fetchone()[0]

print(f"Update completed successfully:")
print(f" - Updated existing items: {updated_count}")
print(f" - Inserted new items: {inserted_count}")
print(f" - Total 'کسرا (Kasra)' products in DB: {kasra_total}")
print(f" - Total 'ایزی‌پایپ (Easy Pipe)' products in DB: {easypipe_total}")

# Verify 5 random sample items
c.execute("""
    SELECT name, sell_price, buy_price, description 
    FROM product_catalog 
    WHERE brand = 'کسرا (Kasra)' 
    ORDER BY id ASC LIMIT 5
""")
print("\nSample updated Kasra items:")
for r in c.fetchall():
    print(r)

conn.close()
