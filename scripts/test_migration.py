import subprocess
import sys
import time

def run_command(cmd):
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(result.stdout)
    if result.stderr:
        print(f"STDERR: {result.stderr}", file=sys.stderr)
    return result.returncode == 0

def main():
    print("Testing DB Migration...")
    
    if not run_command("alembic upgrade head"):
        print("Failed to upgrade to head")
        sys.exit(1)
        
    print("Upgrade successful, checking downgrade...")
    
    if not run_command("alembic downgrade -1"):
        print("Failed to downgrade")
        sys.exit(1)
        
    print("Downgrade successful, re-upgrading...")
    
    if not run_command("alembic upgrade head"):
        print("Failed to re-upgrade")
        sys.exit(1)
        
    print("All migration tests passed.")

if __name__ == "__main__":
    main()