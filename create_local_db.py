from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

@compiles(JSONB, 'sqlite')
def compile_jsonb(type_, compiler, **kw):
    return "TEXT"

from models import Base, User, Order
# Import other models if needed to ensure they are registered

SQLITE_DB_PATH = "migration_ready.db"

def init_db():
    print(f"Creating fresh database: {SQLITE_DB_PATH}")
    engine = create_engine(f'sqlite:///{SQLITE_DB_PATH}')
    print(f"Registered tables: {Base.metadata.tables.keys()}")
    Base.metadata.create_all(engine)
    print("Database initialized successfully.")

if __name__ == '__main__':
    init_db()
