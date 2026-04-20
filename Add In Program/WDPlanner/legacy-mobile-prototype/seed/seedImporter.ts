import { getDb, getMeta, setMeta } from '../db/db';

type SeedProductsFile = { products?: any[] };
type SeedCategoriesFile = { categories?: any[] };

export async function importSeedIfNeeded(): Promise<void> {
  const imported = await getMeta('seed_imported');
  if (imported === 'true') return;

  const db = await getDb();
  await db.transaction(async tx => {
    // 1) products
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const productsJson = require('../../assets/seed/products.json') as SeedProductsFile;
    const products = productsJson.products || [];
    for (const p of products) {
      if (!p || p.id == null) continue;
      tx.executeSql(
        `INSERT OR REPLACE INTO products(id, name, pricing_type, price_30cm, price_1cm, price_1m)
         VALUES(?, ?, ?, ?, ?, ?)`,
        [
          Number(p.id),
          String(p.name || ''),
          String(p.pricing_type || ''),
          p.price_30cm != null ? Number(p.price_30cm) : null,
          p.price_1cm != null ? Number(p.price_1cm) : null,
          p.price_1m != null ? Number(p.price_1m) : null,
        ],
      );
    }

    // 2) additional options
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const addJson = require('../../assets/seed/additional_options.json') as SeedCategoriesFile;
    const addCats = addJson.categories || [];
    for (const c of addCats) {
      if (!c) continue;
      const catId = Number(c.id);
      tx.executeSql(`INSERT OR REPLACE INTO additional_option_categories(id, name) VALUES(?, ?)`, [
        catId,
        String(c.name || ''),
      ]);
      const opts = Array.isArray(c.options) ? c.options : [];
      for (const o of opts) {
        if (!o) continue;
        tx.executeSql(
          `INSERT OR REPLACE INTO additional_options(id, category_id, name, price)
           VALUES(?, ?, ?, ?)`,
          [Number(o.id), catId, String(o.name || ''), Number(o.price || 0)],
        );
      }
    }

    // 3) notes categories
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const notesJson = require('../../assets/seed/notes_categories.json') as SeedCategoriesFile;
    const notesCats = notesJson.categories || [];
    for (const c of notesCats) {
      if (!c) continue;
      const catId = Number(c.id);
      tx.executeSql(`INSERT OR REPLACE INTO notes_categories(id, name) VALUES(?, ?)`, [
        catId,
        String(c.name || ''),
      ]);
      const opts = Array.isArray(c.options) ? c.options : [];
      for (const o of opts) {
        if (!o) continue;
        tx.executeSql(`INSERT OR REPLACE INTO notes_options(id, category_id, name) VALUES(?, ?, ?)`, [
          Number(o.id),
          catId,
          String(o.name || ''),
        ]);
      }
    }
  });

  await setMeta('seed_imported', 'true');
}


