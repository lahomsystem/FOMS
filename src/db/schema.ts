export const DB_NAME = 'MobileCalculator.db';
export const DB_LOCATION = 'default' as const; // 내부 저장소 (언인스톨 시 자동 삭제)

export const SCHEMA_VERSION = 1;
export const SEED_VERSION = 1; // seed 데이터 포맷 변경 시 증가

export const SQL = {
  meta: {
    create: `
      CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
      );
    `,
    get: `SELECT value FROM meta WHERE key = ? LIMIT 1;`,
    set: `INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value;`,
  },

  products: {
    create: `
      CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        pricing_type TEXT NOT NULL,
        price_30cm INTEGER,
        price_1cm INTEGER,
        price_1m INTEGER
      );
    `,
  },

  additional_option_categories: {
    create: `
      CREATE TABLE IF NOT EXISTS additional_option_categories (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL
      );
    `,
  },
  additional_options: {
    create: `
      CREATE TABLE IF NOT EXISTS additional_options (
        id INTEGER PRIMARY KEY,
        category_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        price INTEGER NOT NULL
      );
    `,
    idxCategory: `CREATE INDEX IF NOT EXISTS idx_additional_options_category_id ON additional_options(category_id);`,
  },

  notes_categories: {
    create: `
      CREATE TABLE IF NOT EXISTS notes_categories (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL
      );
    `,
  },
  notes_options: {
    create: `
      CREATE TABLE IF NOT EXISTS notes_options (
        id INTEGER PRIMARY KEY,
        category_id INTEGER NOT NULL,
        name TEXT NOT NULL
      );
    `,
    idxCategory: `CREATE INDEX IF NOT EXISTS idx_notes_options_category_id ON notes_options(category_id);`,
  },

  estimates: {
    create: `
      CREATE TABLE IF NOT EXISTS estimates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_name TEXT NOT NULL,
        estimate_data_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
    `,
    idxCustomer: `CREATE INDEX IF NOT EXISTS idx_estimates_customer_name ON estimates(customer_name);`,
    idxCreated: `CREATE INDEX IF NOT EXISTS idx_estimates_created_at ON estimates(created_at);`,
  },
  estimate_histories: {
    create: `
      CREATE TABLE IF NOT EXISTS estimate_histories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estimate_id INTEGER NOT NULL,
        estimate_data_json TEXT NOT NULL,
        created_at TEXT NOT NULL
      );
    `,
    idxEstimate: `CREATE INDEX IF NOT EXISTS idx_histories_estimate_id ON estimate_histories(estimate_id);`,
  },
} as const;


