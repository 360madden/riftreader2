"""Optional, read-only VMware host-window preview via local FlaUI-MCP-Core.

This is NOT a reviewed RR2 game capture, a source pin, or movement authority.
It never focuses a window, sends input, or acquires a game-controller lease.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import socket
import struct
import subprocess
import threading
import time
import uuid

LAB_TITLES = {
    "lab1": "RIFT-Lab-1 - VMware Workstation",
    "lab2": "RIFT-Lab-2 - VMware Workstation",
}
DEFAULT_FLAUI_ROOT = Path(r"C:\work\FlaUI-MCP-Core")
WINDOW_LINE = re.compile(r'^\s*-\s+(w\d+):\s+"([^"]+)"\s+\(([^)]+)\)\s*$', re.M)


class PreviewError(ValueError):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _content(result: dict) -> str:
    return "\n".join(x.get("text", "") for x in result.get("content", []))


def select_window(list_result: dict, lab: str) -> str:
    expected = LAB_TITLES[lab]
    matches = [
        handle for handle, title, process in WINDOW_LINE.findall(_content(list_result))
        if title == expected and process.casefold() == "vmware"
    ]
    if len(matches) != 1:
        raise PreviewError("vmware-window-not-unique-or-missing")
    return matches[0]


def _png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        head = f.read(24)
    if (len(head) != 24 or head[:8] != b"\x89PNG\r\n\x1a\n"
            or head[12:16] != b"IHDR"):
        raise PreviewError("native-capture-not-png")
    width, height = struct.unpack(">II", head[16:24])
    if not 0 < width <= 8192 or not 0 < height <= 8192:
        raise PreviewError("native-capture-invalid-dimensions")
    return width, height


def _metadata(result: dict) -> dict:
    for part in result.get("content", []):
        try:
            obj = json.loads(part.get("text", ""))
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict) and "method" in obj:
            return obj
    raise PreviewError("native-capture-metadata-missing")


class _McpClient:
    def __init__(self, flaui_root: Path):
        self.root = flaui_root
        self.process = None
        self.responses = queue.Queue()
        self.request_id = 0

    def __enter__(self):
        exe = self.root / "local/dotnet/dotnet.exe"
        server = self.root / "src/FlaUI.Mcp/bin/Release/net8.0-windows/FlaUI.Mcp.dll"
        if not exe.is_file() or not server.is_file():
            raise PreviewError("flaui-build-or-runtime-missing")
        env = os.environ.copy()
        env.update({
            "FLAUI_MCP_ALLOWED_APPS": "vmware",
            "FLAUI_MCP_KEEP_AWAKE_SECONDS": "0",
            "DOTNET_ROOT": str(self.root / "local/dotnet"),
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
        })
        self.process = subprocess.Popen(
            [str(exe), str(server)], cwd=str(self.root), env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()
        try:
            self._request("initialize", {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "rr2-readonly-vmware-preview", "version": "1"},
            })
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def _read(self):
        for line in self.process.stdout:
            try:
                self.responses.put(json.loads(line))
            except ValueError:
                pass

    def _request(self, method: str, params: dict, timeout: float = 25) -> dict:
        self.request_id += 1
        ident = self.request_id
        message = {"jsonrpc": "2.0", "id": ident, "method": method, "params": params}
        self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                result = self.responses.get(timeout=min(.25, max(.01, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if result.get("id") != ident or result.get("error"):
                raise PreviewError("flaui-protocol-error")
            if result.get("result", {}).get("isError"):
                raise PreviewError("flaui-observation-refused")
            return result.get("result", {})
        raise PreviewError("flaui-observation-timeout")

    def tool(self, name: str, args: dict | None = None) -> dict:
        return self._request("tools/call", {"name": name, "arguments": args or {}})

    def __exit__(self, *_):
        if self.process is None:
            return
        try:
            self.process.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)
        self.process.stdout.close()


def capture_with_client(client, lab: str, output_png: Path) -> dict:
    handle = select_window(client.tool("windows_list_windows"), lab)
    started = _utc()
    start = time.perf_counter()
    response = client.tool("windows_screenshot", {
        "handle": handle, "background": True, "strictNative": True,
        "savePath": str(output_png.resolve()), "includeImage": False,
        "includeMetadata": True, "parkPointer": False,
    })
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    finished = _utc()
    meta = _metadata(response)
    if meta.get("method") != "native-window" or meta.get("screenFallback") is not False:
        raise PreviewError("native-capture-not-proven")
    if not output_png.is_file() or output_png.stat().st_size < 32:
        raise PreviewError("native-capture-file-missing")
    width, height = _png_dimensions(output_png)
    if (meta.get("width"), meta.get("height")) != (width, height):
        raise PreviewError("native-capture-size-mismatch")
    with output_png.open("rb") as f:
        sha = hashlib.file_digest(f, "sha256").hexdigest().upper()
    return {
        "schemaVersion": 1,
        "status": "captured-nonauthoritative",
        "lab": lab,
        "windowTitle": LAB_TITLES[lab],
        "source": "vmware-host-native-window",
        "image": str(output_png.resolve()),
        "imageSha256": sha,
        "imageWidth": width,
        "imageHeight": height,
        "captureStartedUtc": started,
        "captureFinishedUtc": finished,
        "captureDurationMs": duration_ms,
        "nonAuthoritative": True,
        "gameProcessIdentityVerified": False,
        "movementEligible": False,
        "requestedFocusChange": False,
        "gameInputSent": False,
    }


def capture(lab: str, expected_host: str, output: Path, flaui_root: Path = DEFAULT_FLAUI_ROOT) -> dict:
    if lab not in LAB_TITLES:
        raise PreviewError("unknown-lab")
    if expected_host.casefold() != "amd-desktop" or socket.gethostname().casefold() != "amd-desktop":
        raise PreviewError("wrong-machine")
    root = Path(flaui_root)
    if not (root / "local/dotnet/dotnet.exe").is_file():
        raise PreviewError("flaui-runtime-missing")
    if not (root / "src/FlaUI.Mcp/bin/Release/net8.0-windows/FlaUI.Mcp.dll").is_file():
        raise PreviewError("flaui-server-missing")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    with _McpClient(root) as client:
        result = capture_with_client(client, lab, output / "image.png")
    result["endToEndDurationMs"] = round((time.perf_counter() - started) * 1000, 2)
    (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", choices=sorted(LAB_TITLES), required=True)
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--flaui-root", type=Path, default=DEFAULT_FLAUI_ROOT)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    output = args.output or Path(__file__).resolve().parents[1] / "artifacts" / (
        "flaui-preview-" + args.lab + "-" + uuid.uuid4().hex)
    try:
        print(json.dumps(capture(args.lab, args.expected_host, output, args.flaui_root)))
        return 0
    except (PreviewError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
