"""Version local data before startup writes; keep recoverable, local snapshots."""
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile, ZIP_STORED

SCHEMA_VERSION = 1
DATA_NAMES = ("settings.json", "tag_metadata.json", "prompts", "vocabulary", "jobs", "data-version.json")


def write_metadata(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def backup_data(directory, reason, app_version):
    """Include user files, not browser caches, installer downloads or older backups."""
    directory = Path(directory).resolve()
    target = directory / "backups"
    target.mkdir(exist_ok=True)
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    temporary, archive = target / (name + ".partial"), target / (name + ".zip")
    try:
        with ZipFile(temporary, "w", compression=ZIP_STORED, allowZip64=True) as output:
            for name in DATA_NAMES:
                root = directory / name
                if not root.exists():
                    continue
                if root.is_symlink():
                    raise ValueError("数据目录包含外部链接，请先整理后再更新。")
                paths = [root] if root.is_file() else sorted(root.rglob("*"))
                for item in paths:
                    if item.is_symlink() or not item.resolve().is_relative_to(directory):
                        raise ValueError("数据目录包含外部链接，请先整理后再更新。")
                    if item.is_file():
                        output.write(item, item.relative_to(directory).as_posix())
            output.writestr("backup-info.json", json.dumps({"reason": reason,
                "app_version": app_version, "schema_version": SCHEMA_VERSION}, ensure_ascii=False))
        with ZipFile(temporary) as check:
            if check.testzip() is not None:
                raise OSError("Data backup verification failed")
        temporary.replace(archive)
        return archive
    finally:
        temporary.unlink(missing_ok=True)


def prepare_data(directory, app_version):
    """Schema 0 (0.2.x) -> 1 is additive: retain all existing content and settings."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "data-version.json"
    metadata = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(metadata, dict):
        raise ValueError("用户数据版本文件无效，请从备份恢复。")
    version = metadata.get("schema_version", 0)
    if type(version) is not int or version < 0 or version > SCHEMA_VERSION:
        raise ValueError("用户数据由更新版本创建。请升级应用，勿使用旧版修改这些数据。")
    if version == SCHEMA_VERSION and metadata.get("app_version") == app_version:
        return metadata
    existing = any((directory / name).exists() for name in DATA_NAMES)
    backup = backup_data(directory, "before-data-migration", metadata.get("app_version", "0.2.x")) if existing else None
    metadata = {"schema_version": SCHEMA_VERSION, "app_version": app_version,
                "migrated_from": version, "backup": backup.name if backup else None}
    write_metadata(path, metadata)
    return metadata
