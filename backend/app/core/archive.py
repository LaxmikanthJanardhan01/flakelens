import os
import stat
import zipfile
from pathlib import Path
from typing import Union, List, Tuple
from backend.app.config import settings


class ArchiveSecurityException(Exception):
    """Raised when an uploaded archive violates security boundaries (Zip-Slip, Zip Bomb, Symlink)."""
    pass


class ArchiveValidationException(Exception):
    """Raised when an uploaded archive is corrupted, invalid, or empty."""
    pass


def validate_and_extract_zip(
    zip_source: Union[str, Path, zipfile.ZipFile],
    target_dir: Union[str, Path],
) -> Tuple[Path, int]:
    """
    Validates and safely extracts a ZIP archive into the target directory.

    Security validations enforced:
    1. Rejects absolute paths (e.g. /etc/passwd or C:\\evil.py).
    2. Rejects Zip-Slip directory traversal paths (e.g. ../../evil.py).
    3. Rejects symlinks and hardlinks (S_IFLNK).
    4. Rejects archives with excessive file count (> MAX_ARCHIVE_FILES).
    5. Rejects archives with excessive total uncompressed size (> MAX_ARCHIVE_UNCOMPRESSED_SIZE).
    6. Rejects suspicious compression ratios (> MAX_ARCHIVE_COMPRESSION_RATIO) to prevent Zip Bombs.

    Returns:
        Tuple[Path, int]: (canonical target directory path, number of extracted files)
    """
    resolved_target = Path(target_dir).resolve()
    os.makedirs(resolved_target, exist_ok=True)

    try:
        if isinstance(zip_source, zipfile.ZipFile):
            zip_ref = zip_source
            close_zip = False
        else:
            zip_ref = zipfile.ZipFile(zip_source, "r")
            close_zip = True
    except zipfile.BadZipFile as e:
        raise ArchiveValidationException(f"Invalid or corrupted ZIP file: {str(e)}")
    except Exception as e:
        raise ArchiveValidationException(f"Unable to read archive: {str(e)}")

    try:
        members = zip_ref.infolist()
        if not members:
            raise ArchiveValidationException("Archive is empty.")

        # 1. Enforce Maximum File Count
        if len(members) > settings.MAX_ARCHIVE_FILES:
            raise ArchiveSecurityException(
                f"Archive file count limit exceeded: {len(members)} files "
                f"(maximum allowed: {settings.MAX_ARCHIVE_FILES})."
            )

        # 2. Cumulative Uncompressed Size & Per-Member Inspection
        total_uncompressed_bytes = 0
        canonical_target_str = str(resolved_target)

        for member in members:
            # 2.1 File size & cumulative limits
            total_uncompressed_bytes += member.file_size
            if total_uncompressed_bytes > settings.MAX_ARCHIVE_UNCOMPRESSED_SIZE:
                raise ArchiveSecurityException(
                    f"Archive uncompressed size limit exceeded: {total_uncompressed_bytes} bytes "
                    f"(maximum allowed: {settings.MAX_ARCHIVE_UNCOMPRESSED_SIZE} bytes)."
                )

            # 2.2 Zip Bomb Compression Ratio Check (files larger than 1KB)
            if member.file_size > 1024 and member.compress_size > 0:
                ratio = member.file_size / member.compress_size
                if ratio > settings.MAX_ARCHIVE_COMPRESSION_RATIO:
                    raise ArchiveSecurityException(
                        f"Zip bomb detected: compression ratio for '{member.filename}' "
                        f"is {ratio:.1f}:1 (limit: {settings.MAX_ARCHIVE_COMPRESSION_RATIO}:1)."
                    )

            # 2.3 Reject Absolute Paths
            clean_name = member.filename
            if clean_name.startswith(("/", "\\")) or (len(clean_name) > 1 and clean_name[1] == ":"):
                raise ArchiveSecurityException(
                    f"Absolute paths inside archive forbidden: '{clean_name}'"
                )

            # 2.4 Reject Symlinks and special UNIX links
            unix_mode = member.external_attr >> 16
            if unix_mode and stat.S_ISLNK(unix_mode):
                raise ArchiveSecurityException(
                    f"Symlinks inside archive forbidden: '{clean_name}'"
                )

            # 2.5 Zip-Slip Path Traversal Protection
            target_entry_path = (resolved_target / clean_name).resolve()
            try:
                common = os.path.commonpath([canonical_target_str, str(target_entry_path)])
                if common != canonical_target_str:
                    raise ArchiveSecurityException(
                        f"Zip-Slip path traversal attempt detected: '{clean_name}'"
                    )
            except ValueError:
                # Occurs on Windows if paths resolve across different drive letters
                raise ArchiveSecurityException(
                    f"Cross-drive path traversal attempt detected: '{clean_name}'"
                )

        # 3. Safe Extraction
        extracted_count = 0
        for member in members:
            target_entry_path = (resolved_target / member.filename).resolve()
            if member.is_dir():
                os.makedirs(target_entry_path, exist_ok=True)
            else:
                os.makedirs(target_entry_path.parent, exist_ok=True)
                with zip_ref.open(member) as source, open(target_entry_path, "wb") as dest:
                    dest.write(source.read())
                extracted_count += 1

        return resolved_target, extracted_count

    finally:
        if close_zip:
            zip_ref.close()

