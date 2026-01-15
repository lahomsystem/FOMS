import type { SQLiteDatabase } from 'react-native-sqlite-storage';
import { getDb } from './db';
import type { Product, AdditionalOption, AdditionalOptionCategory, NotesCategory, NotesOption } from '../types/models';

function mapRows<T>(rs: any): T[] {
  const out: T[] = [];
  for (let i = 0; i < rs.rows.length; i++) out.push(rs.rows.item(i));
  return out;
}

export async function listProducts(): Promise<Product[]> {
  const db = await getDb();
  const [rs] = await db.executeSql('SELECT * FROM products ORDER BY name ASC');
  return mapRows<Product>(rs);
}

export async function upsertProduct(p: Product): Promise<void> {
  const db = await getDb();
  await db.executeSql(
    `INSERT OR REPLACE INTO products(id, name, pricing_type, price_30cm, price_1cm, price_1m)
     VALUES(?, ?, ?, ?, ?, ?)`,
    [
      p.id,
      p.name,
      p.pricing_type,
      p.price_30cm ?? null,
      p.price_1cm ?? null,
      p.price_1m ?? null,
    ],
  );
}

export async function deleteProduct(id: number): Promise<void> {
  const db = await getDb();
  await db.executeSql('DELETE FROM products WHERE id = ?', [id]);
}

export async function listAdditionalOptionCategories(): Promise<AdditionalOptionCategory[]> {
  const db = await getDb();
  const [rs] = await db.executeSql('SELECT * FROM additional_option_categories ORDER BY name ASC');
  return mapRows<AdditionalOptionCategory>(rs);
}

export async function listAdditionalOptionsByCategory(categoryId: number): Promise<AdditionalOption[]> {
  const db = await getDb();
  const [rs] = await db.executeSql(
    'SELECT * FROM additional_options WHERE category_id = ? ORDER BY name ASC',
    [categoryId],
  );
  return mapRows<AdditionalOption>(rs);
}

export async function upsertAdditionalOptionCategory(cat: AdditionalOptionCategory): Promise<void> {
  const db = await getDb();
  await db.executeSql('INSERT OR REPLACE INTO additional_option_categories(id, name) VALUES(?, ?)', [
    cat.id,
    cat.name,
  ]);
}

export async function deleteAdditionalOptionCategory(id: number): Promise<void> {
  const db = await getDb();
  await db.transaction(async tx => {
    tx.executeSql('DELETE FROM additional_options WHERE category_id = ?', [id]);
    tx.executeSql('DELETE FROM additional_option_categories WHERE id = ?', [id]);
  });
}

export async function upsertAdditionalOption(opt: AdditionalOption): Promise<void> {
  const db = await getDb();
  await db.executeSql(
    'INSERT OR REPLACE INTO additional_options(id, category_id, name, price) VALUES(?, ?, ?, ?)',
    [opt.id, opt.category_id, opt.name, opt.price],
  );
}

export async function deleteAdditionalOption(id: number): Promise<void> {
  const db = await getDb();
  await db.executeSql('DELETE FROM additional_options WHERE id = ?', [id]);
}

export async function listNotesCategories(): Promise<NotesCategory[]> {
  const db = await getDb();
  const [rs] = await db.executeSql('SELECT * FROM notes_categories ORDER BY name ASC');
  return mapRows<NotesCategory>(rs);
}

export async function listNotesOptionsByCategory(categoryId: number): Promise<NotesOption[]> {
  const db = await getDb();
  const [rs] = await db.executeSql('SELECT * FROM notes_options WHERE category_id = ? ORDER BY name ASC', [
    categoryId,
  ]);
  return mapRows<NotesOption>(rs);
}

export async function upsertNotesCategory(cat: NotesCategory): Promise<void> {
  const db = await getDb();
  await db.executeSql('INSERT OR REPLACE INTO notes_categories(id, name) VALUES(?, ?)', [cat.id, cat.name]);
}

export async function deleteNotesCategory(id: number): Promise<void> {
  const db = await getDb();
  await db.transaction(async tx => {
    tx.executeSql('DELETE FROM notes_options WHERE category_id = ?', [id]);
    tx.executeSql('DELETE FROM notes_categories WHERE id = ?', [id]);
  });
}

export async function upsertNotesOption(opt: NotesOption): Promise<void> {
  const db = await getDb();
  await db.executeSql('INSERT OR REPLACE INTO notes_options(id, category_id, name) VALUES(?, ?, ?)', [
    opt.id,
    opt.category_id,
    opt.name,
  ]);
}

export async function deleteNotesOption(id: number): Promise<void> {
  const db = await getDb();
  await db.executeSql('DELETE FROM notes_options WHERE id = ?', [id]);
}

export async function getNextId(table: string): Promise<number> {
  const db = await getDb();
  const [rs] = await db.executeSql(`SELECT COALESCE(MAX(id), 0) AS max_id FROM ${table}`);
  const maxId = rs.rows.item(0).max_id as number;
  return Number(maxId) + 1;
}

export async function withTransaction<T>(fn: (txDb: SQLiteDatabase) => Promise<T>): Promise<T> {
  const db = await getDb();
  let result!: T;
  await db.transaction(async tx => {
    // SQLiteStorage의 tx는 SQLiteDatabase와 타입이 다르지만 executeSql 호환
    // 여기서는 간단히 db를 넘김 (필요 시 tx 래퍼 확장)
    result = await fn(db);
  });
  return result;
}


