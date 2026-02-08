-- Railway DEV Database Migration: Add users.team column
-- 
-- Execute this SQL in Railway Dashboard:
-- 1. Go to Railway Dashboard (https://railway.app)
-- 2. Select your DEV environment
-- 3. Click on PostgreSQL database
-- 4. Go to "Query" tab
-- 5. Paste and execute this SQL

-- Step 1: Check if column exists
SELECT column_name 
FROM information_schema.columns 
WHERE table_name='users' AND column_name='team';

-- Step 2: Add team column if not exists
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS team VARCHAR(50);

-- Step 3: Verify the change
SELECT column_name, data_type, is_nullable
FROM information_schema.columns 
WHERE table_name='users' 
ORDER BY ordinal_position;

-- Step 4: (Optional) Set default value for existing users
-- UPDATE users SET team = 'SALES' WHERE team IS NULL;
