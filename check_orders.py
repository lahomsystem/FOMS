STAGING_URL = 'postgresql://postgres:jDkSuQDkQZkGZCFmPMOnFoDaXNJebidd@maglev.proxy.rlwy.net:24958/railway'
import psycopg2
conn_stg = psycopg2.connect(STAGING_URL)
cur_stg = conn_stg.cursor()
cur_stg.execute("SELECT id, customer_name, status, deleted_at FROM orders WHERE id IN (2217, 2218, 2209, 2213, 2212, 2208, 2211, 2214, 2215)")
print('Staging 9 orders:')
for row in cur_stg.fetchall():
    print(row)


STAGING_URL = 'postgresql://postgres:jDkSuQDkQZkGZCFmPMOnFoDaXNJebidd@maglev.proxy.rlwy.net:24958/railway'

conn_stg = psycopg2.connect(STAGING_URL)
cur_stg = conn_stg.cursor()
cur_stg.execute("SELECT id, customer_name, status, is_erp_beta, structured_data->'workflow'->>'stage' FROM orders WHERE is_erp_beta = True AND status != 'DELETED'")
print('Staging erp beta orders:')
for row in cur_stg.fetchall():
    if row[2] in ('AS', 'AS_RECEIVED', 'AS_COMPLETED') or row[4] in ('AS', 'AS처리'):
        print(row)
