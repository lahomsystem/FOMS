"""Operator CLI compatibility; canonical: ``foms.services.admin.backup_service``."""

from foms.services.admin.backup_service import SimpleBackupSystem, main

__all__ = ["SimpleBackupSystem", "main"]

if __name__ == "__main__":
    main()
