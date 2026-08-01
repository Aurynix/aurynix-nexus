from pathlib import Path


def safe_filename(filename: str) -> str:
    import re
    name = re.sub(r"[^\w\s\-.]", "", filename).strip()
    return name or "unnamed"


def get_file_extension(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").lower()


def human_readable_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} TB"
