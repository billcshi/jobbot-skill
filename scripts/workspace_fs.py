"""Workspace-scoped writes with no-follow directories and atomic private files."""
from __future__ import annotations

import os
import shutil
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path

_ROOTS: set[Path] = set()
OBJECTS_DIRECTORY = "objects"
# Shared catalog of managed workspace directories; none is an intake source.
MANAGED_DIRECTORIES = frozenset({
    'evidence', 'jobs', 'runs', 'scoring', 'reviews', 'companies', 'discovery',
    'research', 'notes', 'history', 'command-logs', '.git', OBJECTS_DIRECTORY,
})


def register(root: Path) -> Path:
    _ROOTS.add(root)
    return root


def guard(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    roots = [root for root in _ROOTS if path.is_relative_to(root)]
    if not roots:
        raise PermissionError(f"Output is not in a registered user workspace: {path}")
    root = max(roots, key=lambda value: len(value.parts))
    cursor = root
    if cursor.is_symlink():
        raise PermissionError(f"Workspace path must not be a symlink: {cursor}")
    for component in path.relative_to(root).parts:
        cursor = cursor / component
        if cursor.is_symlink():
            raise PermissionError(f"Workspace output must not follow a symlink: {cursor}")
        if cursor.is_file() and cursor.stat().st_nlink > 1:
            raise PermissionError(f"Workspace output must not modify a multiply linked file: {cursor}")
    return path


@contextmanager
def _directory(path: Path, create: bool = True):
    path = guard(path)
    root = max((r for r in _ROOTS if path.is_relative_to(r)), key=lambda value: len(value.parts))
    if create and not root.exists():
        root.mkdir(parents=True, mode=0o700)
    if os.open not in os.supports_dir_fd:
        if create:
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
        guard(path)
        yield None
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(root, flags)
    try:
        for part in path.relative_to(root).parts:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def mkdir(path: Path, *, parents: bool = True, exist_ok: bool = True) -> None:
    path = guard(path)
    if not exist_ok and path.exists():
        raise FileExistsError(path)
    with _directory(path):
        pass


def write_bytes(path: Path, data: bytes) -> None:
    path = guard(path)
    with _directory(path.parent) as parent_fd:
        temporary = f".jobbot-{uuid.uuid4().hex}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        if parent_fd is None:
            temp_path = path.parent / temporary
            fd = os.open(temp_path, flags, 0o600)
        else:
            fd = os.open(temporary, flags, 0o600, dir_fd=parent_fd)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            guard(path)
            if parent_fd is None:
                os.replace(temp_path, path)
            else:
                os.replace(temporary, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        finally:
            try:
                if parent_fd is None:
                    temp_path.unlink()
                else:
                    os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass


def write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    write_bytes(path, text.encode(encoding))


def copy_file(source: Path, destination: Path) -> None:
    write_bytes(destination, source.read_bytes())


def append_text(path: Path, text: str) -> None:
    path = guard(path)
    with _directory(path.parent) as parent_fd:
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path.name if parent_fd is not None else path, flags, 0o600,
                     **({"dir_fd": parent_fd} if parent_fd is not None else {}))
        if os.fstat(fd).st_nlink != 1:
            os.close(fd)
            raise PermissionError("Append output must have exactly one filesystem link")
        with os.fdopen(fd, "a", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()


def check_tree(path: Path) -> None:
    path = guard(path)
    if not path.exists():
        return
    for directory, folders, files in os.walk(path, followlinks=False):
        for name in folders + files:
            guard(Path(directory) / name)


def copy_tree(source: Path, destination: Path) -> None:
    check_tree(source)
    mkdir(destination, exist_ok=False)
    for item in source.iterdir():
        if item.is_dir():
            copy_tree(item, destination / item.name)
        else:
            copy_file(item, destination / item.name)


def remove_tree(path: Path) -> None:
    check_tree(path)
    shutil.rmtree(guard(path))


def readonly(path: Path) -> None:
    path = guard(path)
    with _directory(path.parent, create=False) as parent_fd:
        if parent_fd is None:
            path.chmod(stat.S_IRUSR)
        else:
            fd = os.open(path.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
            try:
                os.fchmod(fd, stat.S_IRUSR)
            finally:
                os.close(fd)
