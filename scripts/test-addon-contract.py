"""Run actual Lua 5.1 modules and decode their output with the built C# CLI."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess

import lupa
from lupa.lua51 import LuaRuntime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()
    if lupa.__version__ != "2.8":
        raise RuntimeError("Install the pinned requirements-lua-tests.txt (lupa 2.8).")

    repo = Path(__file__).resolve().parent.parent
    lua = LuaRuntime(unpack_returned_tuples=True)
    if lua.eval("_VERSION") != "Lua 5.1":
        raise RuntimeError("The contract gate requires actual Lua 5.1.")
    private = lua.table()
    info = lua.table(identifier="RiftReader2")
    package = repo / "addon/RiftReader2"
    read_toc = lua.eval("""function(source)
        local chunk = assert(loadstring(source))
        local metadata = {}
        setfenv(chunk, metadata)
        chunk()
        return metadata
    end""")
    toc = read_toc((package / "RiftAddon.toc").read_text(encoding="utf-8"))
    startup_files = list(toc.RunOnStartup.values())
    if (toc.Identifier != "RiftReader2" or toc.Version != "0.1.0" or toc.Environment != "4.4"
            or toc.Author != "360madden" or startup_files != ["wire.lua", "producer.lua", "main.lua"]):
        raise AssertionError("Addon metadata or startup module order differs from the supported package.")
    for module in startup_files[:-1]:
        lua.execute((repo / "addon/RiftReader2" / module).read_text(encoding="utf-8"), info, private)
    run_tests = lua.execute((repo / "tests/lua/test_addon.lua").read_text(encoding="utf-8"))
    main_source = (package / "main.lua").read_text(encoding="utf-8")
    lua_checks = run_tests(private, main_source)
    if type(lua_checks) is not int or lua_checks < 1:
        raise AssertionError("Lua lifecycle tests did not report completed assertions.")

    def to_lua(value):
        if isinstance(value, dict):
            if "special" in value:
                return {"nan": math.nan, "positiveInfinity": math.inf,
                        "negativeInfinity": -math.inf}[value["special"]]
            return lua.table_from({key: to_lua(item) for key, item in value.items()})
        if isinstance(value, list):
            return lua.table_from([to_lua(item) for item in value])
        return value

    make_api = lua.eval("""function(state)
        local lookups = 0
        return {
            Time = { Frame = function() return state.clock end },
            Unit = {
                Lookup = function()
                    lookups = lookups + 1
                    if lookups == 1 then return state.beforePlayer end
                    return state.afterPlayer
                end,
                Detail = function() return state.detail end
            }
        }
    end""")
    # Lua assertions cover main.lua with synthetic events; load it in this runtime
    # too, to ensure every file named by the package is executable in Lua 5.1.
    lua.execute(main_source, info, private)
    cases = json.loads((repo / "contracts/addon/fixtures/cases.json").read_text(encoding="utf-8"))
    args.output_directory.mkdir(parents=True, exist_ok=True)
    for case in cases:
        producer = private.Producer.New(make_api(to_lua(case)))
        if isinstance(producer, tuple):
            producer = producer[0]
        result = producer.Update(producer)
        frame = result[0] if isinstance(result, tuple) else result
        if not isinstance(frame, str):
            raise AssertionError(f"{case['name']}: producer failed: {producer.LastError}")
        wire = frame.encode("ascii", errors="strict")
        frame_path = args.output_directory / (case["name"] + ".wire")
        with frame_path.open("xb") as output:
            output.write(wire)
        decoded = subprocess.run(
            ["dotnet", str(args.cli.resolve()), "decode-addon", "--frame", str(frame_path.resolve())],
            text=True, encoding="utf-8", capture_output=True, check=False,
        )
        if decoded.returncode != 0:
            raise AssertionError(f"{case['name']}: decoder exit {decoded.returncode}: {decoded.stderr}")
        report = json.loads(decoded.stdout)
        if report["observation"] != case["expected"]:
            raise AssertionError(f"{case['name']}: Lua to C# observation differs from shared expectation: {report['observation']}")
        if (report["schemaVersion"] != 1 or report["evidenceKind"] != "addon-api-reference"
                or report["bindingStatus"] != "unbound" or report["freshnessStatus"] != "unverified"):
            raise AssertionError(f"{case['name']}: decoder overstated source verification")
        if report["frameSha256"].lower() != hashlib.sha256(wire).hexdigest():
            raise AssertionError(f"{case['name']}: wire provenance hash differs")
        with (args.output_directory / (case["name"] + ".json")).open("x", encoding="utf-8", newline="\n") as output:
            output.write(decoded.stdout)
    print(f"Lua 5.1: {lua_checks} lifecycle/encoder checks; {len(cases)} real Lua -> C# shared cases passed.")


if __name__ == "__main__":
    main()
