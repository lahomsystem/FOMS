import { getDb } from './db';
import type { EstimateRow, EstimateHistoryRow } from '../types/models';

function nowIso() {
  return new Date().toISOString();
}

function mapRows<T>(rs: any): T[] {
  const out: T[] = [];
  for (let i = 0; i < rs.rows.length; i++) out.push(rs.rows.item(i));
  return out;
}

export async function listEstimates(): Promise<EstimateRow[]> {
  const db = await getDb();
  const [rs] = await db.executeSql('SELECT * FROM estimates ORDER BY created_at DESC');
  return mapRows<EstimateRow>(rs);
}

export async function searchEstimates(customerName: string): Promise<EstimateRow[]> {
  const db = await getDb();
  const q = `%${customerName}%`;
  const [rs] = await db.executeSql('SELECT * FROM estimates WHERE customer_name LIKE ? ORDER BY created_at DESC', [q]);
  return mapRows<EstimateRow>(rs);
}

export async function getEstimate(id: number): Promise<EstimateRow | null> {
  const db = await getDb();
  const [rs] = await db.executeSql('SELECT * FROM estimates WHERE id = ? LIMIT 1', [id]);
  if (rs.rows.length <= 0) return null;
  return rs.rows.item(0) as EstimateRow;
}

export async function saveEstimate(params: {
  id?: number;
  customer_name: string;
  estimate_data: any;
}): Promise<number> {
  const db = await getDb();
  const createdAt = nowIso();
  const updatedAt = nowIso();
  const estimateJson = JSON.stringify(params.estimate_data ?? {});

  if (params.id != null) {
    // history 저장
    const [oldRs] = await db.executeSql('SELECT estimate_data_json FROM estimates WHERE id = ? LIMIT 1', [params.id]);
    if (oldRs.rows.length > 0) {
      const oldJson = oldRs.rows.item(0).estimate_data_json as string;
      await db.executeSql(
        'INSERT INTO estimate_histories(estimate_id, estimate_data_json, created_at) VALUES(?, ?, ?)',
        [params.id, oldJson, updatedAt],
      );
    }

    await db.executeSql(
      'UPDATE estimates SET customer_name = ?, estimate_data_json = ?, updated_at = ? WHERE id = ?',
      [params.customer_name, estimateJson, updatedAt, params.id],
    );
    return params.id;
  }

  const [rs] = await db.executeSql(
    'INSERT INTO estimates(customer_name, estimate_data_json, created_at, updated_at) VALUES(?, ?, ?, ?)',
    [params.customer_name, estimateJson, createdAt, updatedAt],
  );
  // @ts-ignore
  return rs.insertId as number;
}

export async function deleteEstimate(id: number): Promise<void> {
  const db = await getDb();
  // SQLite 외래키 강제 사용 안 하므로 명시 삭제
  await db.transaction(async tx => {
    tx.executeSql('DELETE FROM estimate_histories WHERE estimate_id = ?', [id]);
    tx.executeSql('DELETE FROM estimates WHERE id = ?', [id]);
  });
}

export async function getEstimateHistories(estimateId: number): Promise<EstimateHistoryRow[]> {
  const db = await getDb();
  const [rs] = await db.executeSql(
    'SELECT * FROM estimate_histories WHERE estimate_id = ? ORDER BY created_at DESC',
    [estimateId],
  );
  return mapRows<EstimateHistoryRow>(rs);
}


