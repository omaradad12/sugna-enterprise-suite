"""
Temporary storage for audit screening uploads. Files are never stored permanently.
Call delete_session_files() when finishing screening, closing a case, or in cleanup job.
"""
import os
import uuid
from pathlib import Path

from django.conf import settings


def get_screening_temp_root() -> Path:
    """Return the root directory for temporary screening files (separate from permanent storage)."""
    root = Path(settings.SCREENING_UPLOAD_TEMP_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_session_dir(session_id: int) -> Path:
    """Return the directory for a screening session's files."""
    return get_screening_temp_root() / str(session_id)


def save_upload_to_temp(session_id: int, uploaded_file, original_name: str = None) -> str:
    """
    Save an uploaded file to temporary screening storage. Returns the relative path
    (session_id/filename) to store in ScreeningUploadFile.temp_file_path.
    """
    root = get_screening_temp_root()
    session_dir = root / str(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    name = original_name or getattr(uploaded_file, "name", None) or "upload"
    # Sanitize and ensure unique
    safe = "".join(c for c in os.path.basename(name) if c.isalnum() or c in "._- ").strip() or "file"
    if not safe:
        safe = "file"
    base, ext = os.path.splitext(safe)
    unique_name = f"{base}_{uuid.uuid4().hex[:8]}{ext}"
    rel_path = f"{session_id}/{unique_name}"
    full_path = root / rel_path
    with open(full_path, "wb") as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)
    return rel_path


def get_full_path(relative_path: str) -> Path:
    """Resolve relative path under screening temp root to full path."""
    return get_screening_temp_root() / relative_path


def delete_session_files(session_id: int) -> int:
    """
    Delete all temporary files for a session from disk. Returns number of files removed.
    Call this when finishing screening, when case is closed, or in cleanup job.
    """
    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return 0
    count = 0
    for p in session_dir.iterdir():
        if p.is_file():
            try:
                p.unlink()
                count += 1
            except OSError:
                pass
    try:
        session_dir.rmdir()
    except OSError:
        pass
    return count


def delete_file_by_rel_path(relative_path: str) -> bool:
    """Delete a single file by its relative path. Returns True if deleted."""
    full = get_full_path(relative_path)
    if full.is_file():
        try:
            full.unlink()
            return True
        except OSError:
            pass
    return False


def get_session_total_size_mb(session_id: int) -> float:
    """Return total size in MB of files in session directory (for limit checks)."""
    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return 0.0
    total = 0
    for p in session_dir.iterdir():
        if p.is_file():
            total += p.stat().st_size
    return total / (1024 * 1024)
