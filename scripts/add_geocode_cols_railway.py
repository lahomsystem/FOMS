"""Add geocode columns to Railway orders table if missing. Safe to re-run."""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def main():
    from sqlalchemy import create_engine, text
    url = os.environ.get('DATABASE_URL', '')
    if not url or 'railway' not in url.lower():
        print('Set DATABASE_URL to Railway public DB URL')
        sys.exit(1)
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    engine = create_engine(url)
    cols = [
        ('lat', 'ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION'),
        ('lng', 'ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION'),
        ('geocode_status', 'ADD COLUMN IF NOT EXISTS geocode_status VARCHAR(50)'),
        ('geocoded_at', 'ADD COLUMN IF NOT EXISTS geocoded_at TIMESTAMP'),
        ('address_hash', 'ADD COLUMN IF NOT EXISTS address_hash VARCHAR(64)'),
    ]
    with engine.connect() as conn:
        for name, clause in cols:
            try:
                conn.execute(text(f'ALTER TABLE orders {clause}'))
                conn.commit()
                print(f'OK: {name}')
            except Exception as e:
                print(f'Skip {name}: {e}')
                conn.rollback()
    print('Done.')

if __name__ == '__main__':
    main()
