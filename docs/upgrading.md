# Upgrading ScriptManager

Use `upgrade.ps1` to upgrade any existing installation — it handles git pull, pip upgrade, database migrations, and service restart in one command.

---

## Quick Reference

```powershell
# Development install
.\upgrade.ps1

# Production install (default dirs)
.\upgrade.ps1 -Production

# Production install (custom dirs)
.\upgrade.ps1 -Production `
    -InstallDir "D:\Apps\ScriptManager" `
    -DataDir    "D:\ScriptManagerData"
```

---

## What the Upgrade Script Does

1. **`git pull`** — pulls latest source from the repo (skippable)
2. **Stops the Windows service** — prevents file-lock issues during upgrade
3. **`pip install --upgrade`** — installs the new package version in-place
4. **Database migrations** — runs `alembic upgrade head` to apply any schema changes; falls back to `create_all` if no migration files exist yet
5. **Restarts the Windows service** — and verifies it comes back healthy
6. **Reports** installed version and UI URL

---

## Flags

| Flag | Description |
|------|-------------|
| `-Production` | Use production layout (`-InstallDir` / `-DataDir`) |
| `-InstallDir` | Venv location (default: `C:\Program Files\ScriptManager`) |
| `-DataDir` | Data/config location (default: `C:\ProgramData\ScriptManager`) |
| `-ServiceName` | Windows service name (default: `ScriptManager`) |
| `-SkipGitPull` | Don't run `git pull` (e.g. if you manage source separately) |
| `-SkipServiceRestart` | Upgrade the package only — don't restart the service |
| `-SkipMigrations` | Skip Alembic migration step |

---

## Examples

### Upgrade dev install (most common)
```powershell
.\upgrade.ps1
```

### Upgrade production install
```powershell
# Run from the cloned source directory (needed for pip install)
.\upgrade.ps1 -Production
```

### Upgrade but restart the service yourself later
Useful during business hours — upgrade now, bounce the service at a maintenance window:
```powershell
.\upgrade.ps1 -SkipServiceRestart
# ... later, as Administrator:
Restart-Service ScriptManager
```

### Pull was already done, just reinstall + migrate
```powershell
.\upgrade.ps1 -SkipGitPull
```

### Manual upgrade (without the script)

If you prefer to do it step by step:

**Dev install:**
```powershell
cd <repo-dir>
git pull
.\.venv\Scripts\python.exe -m pip install -e . --upgrade
.\.venv\Scripts\python.exe -m alembic upgrade head
# As Administrator:
Restart-Service ScriptManager
```

**Production install:**
```powershell
cd <repo-dir>
git pull
& "C:\Program Files\ScriptManager\.venv\Scripts\python.exe" `
    -m pip install . --upgrade
& "C:\Program Files\ScriptManager\.venv\Scripts\python.exe" `
    -m alembic upgrade head
# As Administrator:
Restart-Service ScriptManager
```

---

## Database Migrations

ScriptManager uses [Alembic](https://alembic.sqlalchemy.org/) for schema migrations.

- `upgrade.ps1` runs `alembic upgrade head` automatically
- If you need to check what migrations are pending:
  ```powershell
  .\.venv\Scripts\python.exe -m alembic history
  .\.venv\Scripts\python.exe -m alembic current
  ```
- To roll back one version:
  ```powershell
  .\.venv\Scripts\python.exe -m alembic downgrade -1
  ```

> **Note:** The current version uses `create_all` (adds missing tables/columns on startup). Alembic is in place for future schema changes that require data migration.

---

## Verifying the Upgrade

```powershell
# Check installed version
.\.venv\Scripts\python.exe -c "import importlib.metadata; print(importlib.metadata.version('scriptmgr'))"

# Check service status
Get-Service ScriptManager

# Check the UI is responding
Invoke-WebRequest -Uri "http://localhost:8765/" -UseBasicParsing | Select-Object StatusCode
```

---

## Rollback

ScriptManager doesn't have a built-in rollback, but since the source is git-managed:

```powershell
# 1. Stop the service
Stop-Service ScriptManager

# 2. Revert the source
git checkout <previous-tag-or-commit>

# 3. Reinstall the old version
.\.venv\Scripts\python.exe -m pip install -e . --upgrade

# 4. Roll back the database (if migrations were applied)
.\.venv\Scripts\python.exe -m alembic downgrade -1

# 5. Restart
Start-Service ScriptManager
```
