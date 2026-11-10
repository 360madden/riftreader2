using System.Globalization;
using System.Text.Json;
using RiftReader2.Application;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Cli;

/// <summary>Offline A-turn calibration from retained native samples and a key-release receipt.</summary>
internal static class TurnProbeCliCommand
{
    private sealed record Sample(
        TurnSkeletonFacing Facing, DateTimeOffset Started, DateTimeOffset Completed,
        string GameSha256, ulong ModuleBase, long ModuleSize, ulong ComponentAddress);

    internal static async Task<int> RunAsync(
        IReadOnlyDictionary<string, string> options, TextWriter output, CancellationToken cancellationToken)
    {
        if (!options.TryGetValue("--before", out var beforePath)
            || !options.TryGetValue("--after", out var afterPath)
            || !options.TryGetValue("--receipt", out var receiptPath)
            || !options.TryGetValue("--matrix", out var matrix)
            || !options.TryGetValue("--uncontaminated", out var uncontaminatedText))
            throw new ArgumentException("--before, --after, --receipt, --matrix and --uncontaminated are required.");
        if (matrix is not ("primary" or "secondary"))
            throw new ArgumentException("--matrix must be primary or secondary.");
        if (uncontaminatedText is not ("true" or "false"))
            throw new ArgumentException("--uncontaminated must be true or false.");
        using var beforeJson = await LoadAsync(beforePath, cancellationToken);
        using var afterJson = await LoadAsync(afterPath, cancellationToken);
        using var receiptJson = await LoadAsync(receiptPath, cancellationToken);
        Sample before, after;
        ControlAction action;
        ControlExecutionResult execution;
        double observedHold;
        DateTimeOffset actionStart, actionEnd;
        try
        {
            before = ReadSample(beforeJson.RootElement, matrix);
            after = ReadSample(afterJson.RootElement, matrix);
            (action, execution, observedHold, actionStart, actionEnd) = ReadAction(receiptJson.RootElement);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or
            FormatException or OverflowException)
        {
            throw new InvalidDataException("Malformed turn sample or action receipt.", ex);
        }

        if (before.GameSha256 != after.GameSha256 || before.ModuleBase != after.ModuleBase
            || before.ModuleSize != after.ModuleSize || before.ComponentAddress != after.ComponentAddress)
            throw new InvalidDataException("Build, module or candidate-component identity changed.");
        if (before.Started > before.Completed || after.Started > after.Completed
            || before.Completed >= actionStart || actionStart > actionEnd
            || actionEnd >= after.Started)
            throw new InvalidDataException("Before/action/after capture windows must be ordered without overlap.");

        var analysis = TurnSkeletonPlanner.AnalyzeAProbe(
            before.Facing, after.Facing, action, execution, observedHold,
            uncontaminatedText == "true");
        var report = new
        {
            schemaVersion = 1,
            contractVersion = "rr2-offline-a-turn-candidate-calibration/1",
            status = analysis.Status,
            gameSha256 = before.GameSha256,
            processId = before.Facing.GameProcessId,
            processStartUtcTicks = before.Facing.GameStartUtcTicks.ToString(CultureInfo.InvariantCulture),
            unitKey = before.Facing.UnitKey,
            candidateComponentAddress = before.ComponentAddress.ToString(CultureInfo.InvariantCulture),
            matrix,
            beforeCandidateDegrees = before.Facing.CandidateDegrees,
            afterCandidateDegrees = after.Facing.CandidateDegrees,
            analysis.SignedCandidateDeltaDegrees,
            requestedHoldMilliseconds = action.HoldMilliseconds,
            observedKeyHoldMilliseconds = observedHold,
            inputWindowUncontaminatedOperatorDeclared = uncontaminatedText == "true",
            inputDeliverySucceeded = execution.DeliverySucceeded,
            inputReleaseSucceeded = execution.ReleaseSucceeded,
            analysis.Calibration,
            analysis.Qualification,
            actorHeadingQualified = false
        };
        if (options.TryGetValue("--output", out var destination))
            await JsonReportWriter.WriteNewAsync(destination, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(report, JsonFormat.Options));
        return 0;
    }

    private static async Task<JsonDocument> LoadAsync(string path, CancellationToken token)
    {
        var file = new FileInfo(path);
        if (file.Length is < 1 or > 256_000)
            throw new InvalidDataException("Turn evidence file is empty or exceeds 256 KB.");
        var raw = await File.ReadAllBytesAsync(path, token);
        if (raw.Length is < 1 or > 256_000)
            throw new InvalidDataException("Turn evidence file size changed.");
        return JsonDocument.Parse(raw);
    }

    private static Sample ReadSample(JsonElement root, string matrix)
    {
        if (root.GetProperty("qualification").GetString() !=
            "matrix-descriptor-candidate-only; body-facing/axis/sign/passive-freshness/restart-unverified")
            throw new InvalidDataException("Expected a current native orientation candidate report.");
        var id = root.GetProperty("identity");
        var sha = id.GetProperty("executableSha256").GetString() ?? "";
        if (sha.Length != 64 || sha.Any(c => !Uri.IsHexDigit(c)))
            throw new InvalidDataException("Invalid game build identity.");
        var pid = id.GetProperty("processId").GetInt32();
        var ticks = id.GetProperty("processStartUtcTicks").GetInt64();
        var unit = root.GetProperty("unitKey").GetString() ?? "";
        var component = root.GetProperty("componentAddress").GetUInt64();
        if (!ulong.TryParse(unit, NumberStyles.None, CultureInfo.InvariantCulture, out var unitId)
            || unitId == 0 || component == 0)
            throw new InvalidDataException("Missing native player/component owner.");
        var entry = root.GetProperty(matrix);
        if (entry.GetProperty("status").GetString() != "structural-y-planar-matrix-candidate"
            || entry.GetProperty("sourceOffset").GetInt32() != (matrix == "primary" ? 0x60 : 0x94))
            throw new InvalidDataException("Requested orientation matrix is not a structural candidate.");
        var angle = VerifiedMatrixAngle(entry);
        var started = root.GetProperty("startedAtUtc").GetDateTimeOffset();
        var completed = root.GetProperty("completedAtUtc").GetDateTimeOffset();
        var facing = new TurnSkeletonFacing("native-owned-" + matrix, pid, ticks,
            unit, angle, completed, false);
        return new(facing, started, completed, sha.ToUpperInvariant(),
            id.GetProperty("moduleBaseAddress").GetUInt64(),
            id.GetProperty("moduleSize").GetInt64(), component);
    }

    private static double VerifiedMatrixAngle(JsonElement matrix)
    {
        var bits = matrix.GetProperty("rawBits").EnumerateArray()
            .Select(item => item.GetUInt32()).ToArray();
        var rows = matrix.GetProperty("rowMajorF32").EnumerateArray()
            .Select(item => item.GetDouble()).ToArray();
        if (bits.Length != 9 || rows.Length != 9)
            throw new InvalidDataException("Orientation matrix must contain nine raw and decoded cells.");
        for (var index = 0; index < 9; index++)
        {
            if (!double.IsFinite(rows[index])
                || BitConverter.SingleToUInt32Bits((float)rows[index]) != bits[index])
                throw new InvalidDataException("Matrix raw bits disagree with decoded float cells.");
        }
        var angle = matrix.GetProperty("planarAngleDegreesCandidate").GetDouble();
        var computed = Math.Atan2(
            BitConverter.UInt32BitsToSingle(bits[6]),
            BitConverter.UInt32BitsToSingle(bits[0])) * 180 / Math.PI;
        if (!double.IsFinite(angle) || !double.IsFinite(computed)
            || angle is < -180 or > 180 || Math.Abs(angle - computed) > 0.001)
            throw new InvalidDataException("Stored candidate angle disagrees with raw matrix.");
        return angle;
    }

    private static (ControlAction, ControlExecutionResult, double, DateTimeOffset, DateTimeOffset)
        ReadAction(JsonElement root)
    {
        var action = root.GetProperty("action");
        var keys = action.GetProperty("keys").EnumerateArray().Select(x => x.GetString() ?? "").ToArray();
        var hold = action.GetProperty("holdMilliseconds").GetInt32();
        var result = root.GetProperty("result");
        bool Flag(string field) => result.GetProperty(field).GetBoolean();
        var execution = new ControlExecutionResult(
            Flag("deliverySucceeded"), Flag("releaseSucceeded"), Flag("cancelled"),
            Flag("targetLost"), Flag("stateUncertain"),
            result.TryGetProperty("requiresCallerDisarm", out var mustDisarm) && mustDisarm.GetBoolean(),
            TimeSpan.Zero, false, null);
        if (root.GetProperty("recoveryRequired").GetBoolean())
            execution = execution with { RequiresCallerDisarm = true };
        var events = root.GetProperty("inputEvents").EnumerateArray().ToArray();
        var downs = events.Where(x => x.GetProperty("kind").GetString() == "keyDownInserted").ToArray();
        var ups = events.Where(x => x.GetProperty("kind").GetString() == "keyUpInserted").ToArray();
        if (downs.Length != 1 || ups.Length != 1 ||
            downs[0].GetProperty("value").GetString() != "a" ||
            ups[0].GetProperty("value").GetString() != "a")
            throw new InvalidDataException("Exactly one A down/up timing pair is required.");
        var down = downs[0].GetProperty("elapsedMilliseconds").GetDouble();
        var up = ups[0].GetProperty("elapsedMilliseconds").GetDouble();
        if (!double.IsFinite(down) || !double.IsFinite(up) || down < 0 || up <= down)
            throw new InvalidDataException("Invalid key down/up event timing.");
        return (new ControlAction(keys, hold), execution, up - down,
            root.GetProperty("startedAtUtc").GetDateTimeOffset(),
            root.GetProperty("completedAtUtc").GetDateTimeOffset());
    }
}
