import SQLite, { type SQLiteDatabase } from 'react-native-sqlite-storage';
import { DB_LOCATION, DB_NAME, SQL, SCHEMA_VERSION, SEED_VERSION } from './schema';

SQLite.DEBUG(false);
SQLite.enablePromise(true);

let dbInstance: SQLiteDatabase | null = null;

async function openDb(): Promise<SQLiteDatabase> {
  if (dbInstance) return dbInstance;
  dbInstance = await SQLite.openDatabase({
    name: DB_NAME,
    location: DB_LOCATION,
  });
  return dbInstance;
}

async function exec(db: SQLiteDatabase, statement: string, params: any[] = []) {
  return db.executeSql(statement, params);
}

export async function initDb(): Promise<void> {
  const db = await openDb();

  // 기본 테이블 생성
  await exec(db, SQL.meta.create);
  await exec(db, SQL.products.create);
  await exec(db, SQL.additional_option_categories.create);
  await exec(db, SQL.additional_options.create);
  await exec(db, SQL.additional_options.idxCategory);
  await exec(db, SQL.notes_categories.create);
  await exec(db, SQL.notes_options.create);
  await exec(db, SQL.notes_options.idxCategory);
  await exec(db, SQL.estimates.create);
  await exec(db, SQL.estimates.idxCustomer);
  await exec(db, SQL.estimates.idxCreated);
  await exec(db, SQL.estimate_histories.create);
  await exec(db, SQL.estimate_histories.idxEstimate);

  // 메타 설정
  await setMeta('schema_version', String(SCHEMA_VERSION));
  await setMeta('seed_version', String(SEED_VERSION));
}

export async function getMeta(key: string): Promise<string | null> {
  const db = await openDb();
  const [rs] = await exec(db, SQL.meta.get, [key]);
  if (rs.rows.length <= 0) return null;
  return rs.rows.item(0).value as string;
}

export async function setMeta(key: string, value: string): Promise<void> {
  const db = await openDb();
  await exec(db, SQL.meta.set, [key, value]);
}

export async function getDb(): Promise<SQLiteDatabase> {
  return openDb();
}


