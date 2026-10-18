"""Read-only directory browsing for the repository picker.

The browser cannot reveal absolute server paths, so the picker navigates the
server's filesystem through here. Browsing is confined to ``settings.fs_root``
(the home directory by default).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..schemas.filesystem import FsEntry, FsListing

router = APIRouter(prefix="/api/fs", tags=["filesystem"])


def _root() -> Path:
    return settings.fs_root.expanduser().resolve()


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


@router.get("/list", response_model=FsListing)
def list_directories(path: str | None = None, hidden: bool = False) -> FsListing:
    """List sub-directories of ``path`` (default: the configured root)."""
    root = _root()
    target = Path(path).expanduser().resolve() if path else root

    if not _within(target, root):
        raise HTTPException(status_code=403, detail=f"Outside the browsable root ({root})")
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"{target} does not exist")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"{target} is not a directory")

    entries: list[FsEntry] = []
    try:
        children = sorted(target.iterdir(), key=lambda p: p.name.lower())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=f"Cannot read {target}") from exc

    for child in children:
        try:
            if not child.is_dir() or child.is_symlink() and not child.resolve().is_dir():
                continue
        except OSError:
            continue
        if not hidden and child.name.startswith("."):
            continue
        entries.append(FsEntry(name=child.name, path=str(child), is_git=(child / ".git").exists()))

    parent = str(target.parent) if target != root else None
    return FsListing(
        root=str(root),
        path=str(target),
        parent=parent,
        is_git=(target / ".git").exists(),
        entries=entries,
    )
