"""Resolve retained view assets relative to their bundle directory."""

from pathlib import Path, PureWindowsPath


def bundle_asset(directory, value):
    if not isinstance(value, str) or not value or Path(value).anchor or PureWindowsPath(value).anchor:
        raise ValueError("relative-view-bundle-path-required")
    root = Path(directory).resolve()
    asset = (root / value).resolve()
    if asset == root or not asset.is_relative_to(root):
        raise ValueError("view-bundle-path-outside-directory")
    return asset


def bundle_reference(directory, path):
    return Path(path).resolve().relative_to(Path(directory).resolve()).as_posix()
