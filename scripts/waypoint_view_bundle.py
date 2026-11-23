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


def saved_scene_asset(directory, manifest, value):
    """Resolve a presentation asset, including an older Windows bundle after a copy."""
    if manifest.get("bundleVersion") == 1:
        return bundle_asset(directory, value)
    origin = manifest.get("directory")
    if not isinstance(origin, str) or not PureWindowsPath(origin).is_absolute():
        return Path(directory) / value
    recorded_root = PureWindowsPath(origin)
    recorded_asset = PureWindowsPath(value)
    if not recorded_asset.anchor:
        return bundle_asset(directory, recorded_asset.as_posix())
    if recorded_asset.is_relative_to(recorded_root):
        return bundle_asset(directory, recorded_asset.relative_to(recorded_root).as_posix())
    if PureWindowsPath(directory) == recorded_root:
        return Path(directory) / value
    return None
