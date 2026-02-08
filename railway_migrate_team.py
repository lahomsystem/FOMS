"""
Direct connection to Railway DEV PostgreSQL to add users.team column

This script will prompt for DATABASE_URL if not in environment.
"""

import psycopg2
import sys

def get_database_url():
    """Get DATABASE_URL from user input"""
    print("=" * 60)
    print("Railway DEV Database Migration: Add users.team column")
    print("=" * 60)
    print()
    print("Please provide the DATABASE_URL from Railway dashboard:")
    print("1. Go to Railway Dashboard")
    print("2. Select DEV environment -> PostgreSQL")
    print("3. Go to 'Connect' tab")
    print("4. Copy 'Postgres Connection URL'")
    print()
    
    database_url = input("Paste DATABASE_URL here: ").strip()
    
    if not database_url:
        print("ERROR: DATABASE_URL is required!")
        return None
    
    return database_url

def add_team_column(database_url):
    """Add team column to users table"""
    print("\nConnecting to database...")
    
    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        print("✓ Connected successfully!")
        
        # Check if column already exists
        print("\nChecking if 'team' column exists...")
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users' AND column_name='team';
        """)
        
        if cursor.fetchone():
            print("✓ Column 'users.team' already exists!")
        else:
            print("Adding 'team' column to users table...")
            
            # Add team column
            cursor.execute("""
                ALTER TABLE users 
                ADD COLUMN team VARCHAR(50);
            """)
            
            conn.commit()
            print("✓ Successfully added 'team' column to users table!")
        
        # Verify schema
        print("\nVerifying users table schema:")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name='users' 
            ORDER BY ordinal_position;
        """)
        
        print("\nCurrent users table columns:")
        print("-" * 60)
        for row in cursor.fetchall():
            nullable = "NULL" if row[2] == "YES" else "NOT NULL"
            print(f"  {row[0]:20} {row[1]:15} {nullable}")
        print("-" * 60)
        
        cursor.close()
        conn.close()
        
        print("\n✓ Migration completed successfully!")
        print("\nYou can now restart your Railway service.")
        
        return True
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    database_url = get_database_url()
    
    if database_url:
        success = add_team_column(database_url)
        sys.exit(0 if success else 1)
    else:
        sys.exit(1)
