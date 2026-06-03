"""File-system browser API — lets the UI pick a script path via a server-side walk.

GET /api/browse?path=<dir>   → lists directory contents
GET /api/browse/drives       → lists available drive letters (Windows) or / (Unix)

Security: only lists paths; never reads file contents. Restricted to the local machine.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

router = APIRouter()


def _safe_path(raw: str) -> Path:
    """Resolve and return a Path. Raises 400 on empty input."""
    if not raw:
        raise HTTPException(status_code=400, detail="path is required")
    return Path(raw).resolve()


@router.get("/drives")
def list_drives():
    """Return available filesystem roots (drive letters on Windows, / on Unix)."""
    if sys.platform == "win32":
        import string
        drives = []
        for letter in string.ascii_uppercase:
            p = Path(f"{letter}:\\")
            if p.exists():
                drives.append({"name": f"{letter}:", "path": str(p)})
        return JSONResponse({"drives": drives})
    else:
        return JSONResponse({"drives": [{"name": "/", "path": "/"}]})


@router.get("")
def browse(path: str = Query(default="")):
    """
    List the contents of *path*.

    Returns:
        current  — the resolved path string
        parent   — parent directory (None if at a root)
        dirs     — sorted list of sub-directory names + full paths
        files    — sorted list of script-like files (name + full path + ext)
    """
    # Default: user's home on Unix, C:\ on Windows
    if not path:
        path = str(Path.home()) if sys.platform != "win32" else "C:\\"

    target = _safe_path(path)

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {target}")
    if not target.is_dir():
        # If a file was passed, use its parent
        target = target.parent

    try:
        entries = list(target.iterdir())
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {target}")

    # Directories
    dirs = sorted(
        [{"name": e.name, "path": str(e)} for e in entries if e.is_dir() and not e.name.startswith(".")],
        key=lambda d: d["name"].lower(),
    )

    # Script/executable files — filter to relevant extensions
    SCRIPT_EXTS = {".py", ".ps1", ".bat", ".cmd", ".exe", ".go", ".sh"}
    files = sorted(
        [
            {"name": e.name, "path": str(e), "ext": e.suffix.lower()}
            for e in entries
            if e.is_file() and e.suffix.lower() in SCRIPT_EXTS
        ],
        key=lambda f: f["name"].lower(),
    )

    parent = str(target.parent) if target.parent != target else None

    return JSONResponse({
        "current": str(target),
        "parent": parent,
        "dirs": dirs,
        "files": files,
    })
