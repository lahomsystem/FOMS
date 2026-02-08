"""
Railway DEV Database Migration: Add users.team column

This script connects to Railway DEV PostgreSQL and adds the missing 'team' column.
Run with: railway run python railway_add_team_column.py
"""

import os
import psycopg2
from psycopg2 import sql

def add_team_column():
    # Get DATABASE_URL from Railway environment
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        print("ERROR: DATABASE_URL not found in environment variables")
        print("Please run with: railway run python railway_add_team_column.py")
        return False
    
    print(f"Connecting to database...")
    
    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        # Check if column already exists
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
        
        # Verify
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name='users' 
            ORDER BY ordinal_position;
        """)
        
        print("\nCurrent users table schema:")
        for row in cursor.fetchall():
            print(f"  - {row[0]}: {row[1]}")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    success = add_team_column()
    exit(0 if success else 1)
