"""Run actual Lua 5.1 modules and decode their output with the built C# CLI."""

import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys


def reference_contract_gate(repo, lua, private, cli, destination):
    """Decode real bound Lua output through the strict snapshot consumers."""
    sys.path.insert(0, str(repo))
    from scripts.inspect_typed_resource import inspect

    fixture = json.loads((repo / "contracts/addon/fixtures/reference-v1.json").read_text("utf-8"))
    lua.execute('''rr2ReferenceState = {clock=1, player="player_1", detail={
        coordX=0,coordY=2,coordZ=-3,health=100,healthMax=100,mana=20,manaMax=40,
        power=0,combo=0,planar=0,planarMax=5,combat=false,dead=false,mounted=false,zone="Sanctum"}}
        rr2ReferenceApi = {Time={Frame=function() return rr2ReferenceState.clock end},
        Unit={Lookup=function() return rr2ReferenceState.player end,
        Detail=function() return rr2ReferenceState.detail end}}''')
    producer = private.Reference.New(lua.globals().rr2ReferenceApi)
    producer.Bind(producer, fixture["nonce"])
    before_frame, _ = producer.Update(producer)
    lua.execute('rr2ReferenceState.clock=2; rr2ReferenceState.detail.mana=0; rr2ReferenceState.detail.combat=true')
    after_frame, _ = producer.Update(producer)
    assert before_frame == fixture["beforeFrame"] and after_frame == fixture["afterFrame"]

    paths = []
    for index, frame in enumerate((before_frame, after_frame)):
        wire = frame.encode("ascii")
        chunks = []
        for offset in range(0, len(wire), 4096):
            data = wire[offset:offset + 4096]
            chunks.append(dict(address=f"0x{0x10000 + offset:X}", requestedByteLength=len(data),
                               status="success", bytesRead=len(data), bytesBase64=base64.b64encode(data).decode(),
                               bytesSha256=hashlib.sha256(data).hexdigest().upper(), win32ErrorCode=None, reason=None))
        snapshot = dict(
            schemaVersion=1, evidenceKind="native-memory-snapshot/1",
            source=dict(requestEvidenceKind="native-memory-snapshot-request/1", requestSha256="A" * 64,
                        requestSha256Verification="producer-declared",
                        implementation=dict(toolVersion="test", deploymentKind="assembly-files",
                                            assemblySha256={"test": "B" * 64}, bundleFileName=None, bundleSha256=None)),
            identity=dict(processId=42, processStartUtcTicks=638964000000000000,
                          executablePath=r"C:\RIFT\rift_x64.exe", executableSha256="C" * 64,
                          moduleBaseAddress=65536, moduleSize=4096),
            startedAtUtc=f"2026-11-06T12:00:0{index * 3}Z",
            completedAtUtc=f"2026-11-06T12:00:0{index * 3 + 1}Z", status="complete", reason=None,
            chunks=chunks, limitations=["Synthetic snapshot of actual Lua 5.1 output; no live game acceptance."])
        path = destination / f"reference-{index + 1}.snapshot.json"
        with path.open("x", encoding="utf-8") as stream:
            json.dump(snapshot, stream)
        resource = inspect(path, "mana", session_id=fixture["nonce"])
        assert resource["selected"]["current"] == fixture[("before", "after")[index]]["fields"]["mana"]
        paths.append(path)
    args = ["dotnet", str(cli.resolve()), "inspect-typed-wire", "--before", str(paths[0].resolve()),
            "--after", str(paths[1].resolve()), "--session-id", fixture["nonce"]]
    result = subprocess.run(args, text=True, encoding="utf-8", capture_output=True, check=False)
    if result.returncode:
        raise AssertionError(f"RR2 reference decoder failed: {result.stderr}")
    report = json.loads(result.stdout)
    assert report["status"] == "advanced-in-covered-scope", report
    assert report["selected"]["after"]["sessionId"] == fixture["nonce"]
    assert report["selected"]["after"]["fields"] == fixture["after"]["fields"]
    assert report["selected"]["after"]["xyz"] == dict(x=0, y=2, z=-3)
    with (destination / "reference-comparison.json").open("x", encoding="utf-8") as stream:
        stream.write(result.stdout)
    # A foreign load nonce must never become usable even when sequence advances.
    args[-1] = "f" * 32
    rejected = subprocess.run(args, text=True, encoding="utf-8", capture_output=True, check=False)
    assert rejected.returncode == 0 and json.loads(rejected.stdout)["status"] != "advanced-in-covered-scope"
    print("RR2R1 real Lua 5.1 -> strict .NET snapshot pair + Python Mana extraction passed; foreign nonce rejected.")

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
    if (toc.Identifier != "RiftReader2" or toc.Version != "0.2.0" or toc.Environment != "4.4"
            or toc.Author != "360madden" or startup_files != ["wire.lua", "producer.lua", "reference.lua", "live.lua", "guidance.lua", "main.lua"]):
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

        # Verify the actual Lua wrapper against the independent C# envelope decoder.
        nonce = "0123456789abcdef0123456789abcdef"
        live = private.Live.New()
        bound = live.Bind(live, nonce)
        if bound is not True:
            raise AssertionError("Live binding failed")
        envelope = live.Wrap(live, frame).encode("ascii", errors="strict")
        live_path = args.output_directory / (case["name"] + ".live.wire")
        with live_path.open("xb") as output:
            output.write(envelope)
        live_result = subprocess.run(
            ["dotnet", str(args.cli.resolve()), "decode-live-addon", "--frame", str(live_path.resolve()), "--session-id", nonce],
            text=True, encoding="utf-8", capture_output=True, check=False,
        )
        if live_result.returncode != 0:
            raise AssertionError(f"{case['name']}: live decoder failed: {live_result.stderr}")
        live_report = json.loads(live_result.stdout)
        if (live_report["addon"] != report or live_report["sessionId"] != nonce
                or live_report["bindingStatus"] != "unbound" or live_report["freshnessStatus"] != "unverified"
                or live_report["envelopeSha256"].lower() != hashlib.sha256(envelope).hexdigest()):
            raise AssertionError(f"{case['name']}: live envelope decoding differs or overstated verification")
    # Exercise the real producer -> external CLI -> real Lua receiver, rather
    # than copying a golden slash string into each language's isolated tests.
    for lab, nonce in (("lab1", "0123456789abcdef0123456789abcdef"),
                       ("lab2", "fedcba9876543210fedcba9876543210")):
        state = dict(clock=123.5, beforePlayer="uGuidance123", afterPlayer="uGuidance123",
                     detail=dict(coordX=10, coordY=2, coordZ=20, health=100, healthMax=100, combat=False))
        producer = private.Producer.New(make_api(to_lua(state)))
        frame, observation = producer.Update(producer)
        live = private.Live.New()
        assert live.Bind(live, nonce) is True
        envelope = live.Wrap(live, frame)
        frame_path = args.output_directory / ("guidance-" + lab + ".wire")
        frame_path.write_bytes(envelope.encode("ascii"))
        result = subprocess.run(
            ["dotnet", str(args.cli.resolve()), "guide-addon", "--frame", str(frame_path.resolve()),
             "--lab", lab, "--session-id", nonce, "--result-sequence", "1",
             "--destination-x", "7", "--destination-y", "6", "--destination-z", "24"],
            text=True, encoding="utf-8", capture_output=True, check=False)
        if result.returncode != 0:
            raise AssertionError(f"{lab}: external guidance failed: {result.stderr}")
        report = json.loads(result.stdout)
        receiver = private.Guidance.New()
        accepted, _ = receiver.Bind(receiver, lab, nonce)
        assert accepted is True
        command = report["slashCommand"].removeprefix("/rr2guide ")
        accepted, reason = receiver.Receive(receiver, command, observation, 124)
        if accepted is not True or receiver.Result.distance != 5 or receiver.Result.dy != 4:
            raise AssertionError(f"{lab}: real external command rejected or wrong math: {reason}")
        wrong_lab = "lab2" if lab == "lab1" else "lab1"
        other = private.Guidance.New()
        assert other.Bind(other, wrong_lab, nonce)[0] is True
        assert other.Receive(other, command, observation, 124)[0] is False
        # Expiry is checked against the original source clock, with fresh local
        # observation time. It must remove the accepted calculated result.
        observation.clock.value = 134
        receiver.Status(receiver, observation, 134)
        assert receiver.Result is None
        report["validation"] = dict(kind="synthetic-lua-csharp-lua", receiptSourceAgeSeconds=0.5,
                                    wrongLabRejected=True, expiryCleared=True, gameRuntimeVerified=False)
        with (args.output_directory / ("guidance-" + lab + ".json")).open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
    reference_contract_gate(repo, lua, private, args.cli, args.output_directory)
    print(f"Lua 5.1: {lua_checks} lifecycle/encoder checks; {len(cases)} addon + {len(cases)} live-envelope real Lua -> C# shared cases; 2 synthetic lab-bound Lua -> C# -> Lua guidance round trips passed.")


if __name__ == "__main__":
    main()
