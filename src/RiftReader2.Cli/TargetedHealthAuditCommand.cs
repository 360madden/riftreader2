using System.Buffers.Binary;
using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Domain;
using RiftReader2.Infrastructure;

namespace RiftReader2.Cli;

/// <summary>
/// Audits a retained native snapshot against one bounded host-generated health
/// request and its independently pinned live typed reference. No process access.
/// </summary>
internal static class TargetedHealthAuditCommand
{
    private const int MaxRequestBytes = 64 * 1024;
    private const int MaxManifestBytes = 256 * 1024;
    private const int MaxReceiptBytes = 2 * 1024 * 1024;
    private const int MaxCandidateGroups = 16;
    private const int WindowLength = 80;
    private const int MaxObservationGapSeconds = 15;
    private static readonly string[] AllowedTags =
        ["currentHealth", "maximumHealth", "rawPower", "visualLevelHint"];

    public static async Task<int> RunAsync(
        IReadOnlyDictionary<string, string> options,
        TextWriter output,
        CancellationToken cancellationToken)
    {
        foreach (var name in new[] { "--request", "--manifest", "--receipt", "--snapshot" })
            if (!options.ContainsKey(name))
                throw new ArgumentException($"{name} is required.");

        using var request = await ReadJsonAsync(options["--request"], MaxRequestBytes, cancellationToken);
        using var manifest = await ReadJsonAsync(options["--manifest"], MaxManifestBytes, cancellationToken);
        using var receipt = await ReadJsonAsync(options["--receipt"], MaxReceiptBytes, cancellationToken);

        var requestRoot = request.RootElement;
        var manifestRoot = manifest.RootElement;
        var receiptRoot = receipt.RootElement;
        RequireKind(requestRoot, "native-memory-snapshot-request/1");
        RequireKind(manifestRoot, "native-health-targeted-snapshot-plan/1");
        if (Text(manifestRoot, "qualification") != "candidate-only")
            throw new InvalidDataException("The manifest must preserve candidate-only status.");

        var requestTarget = Child(requestRoot, "target");
        var manifestTarget = Child(manifestRoot, "target");
        var requestedPid = PositiveInt(requestTarget, "processId");
        var requestedStart = PositiveInt64(requestTarget, "processStartUtcTicks");
        var requestedBuild = Hash(requestTarget, "executableSha256");
        MatchTarget(manifestTarget, requestedPid, requestedStart, requestedBuild, "manifest");
        if (PositiveInt(requestRoot, "maxDurationMilliseconds") > 5000)
            throw new InvalidDataException("Targeted request exceeds its five-second budget.");

        var requestedRanges = Array(requestRoot, "ranges");
        var selections = Array(manifestRoot, "selections");
        if (requestedRanges.GetArrayLength() is < 1 or > MaxCandidateGroups ||
            selections.GetArrayLength() != requestedRanges.GetArrayLength() ||
            PositiveInt(manifestRoot, "selectedCount") != requestedRanges.GetArrayLength() ||
            PositiveInt(manifestRoot, "totalRequestedBytes") != requestedRanges.GetArrayLength() * WindowLength)
            throw new InvalidDataException("Manifest count does not match bounded request coverage.");
        Hash(manifestRoot, "selectedPatternSha256");
        var sources = Child(manifestRoot, "source");
        Hash(sources, "healthReportSha256");
        Hash(sources, "crossEpochReviewSha256");
        var receiptSha = Hash(sources, "liveReceiptSha256");
        var actualReceiptSha = Convert.ToHexString(SHA256.HashData(await ReadBytesAsync(
            options["--receipt"], MaxReceiptBytes, cancellationToken)));
        if (receiptSha != actualReceiptSha)
            throw new InvalidDataException("Pinned Lua receiver receipt SHA-256 differs.");
        var requestSha = Convert.ToHexString(SHA256.HashData(await ReadBytesAsync(
            options["--request"], MaxRequestBytes, cancellationToken)));
        var manifestSha = Convert.ToHexString(SHA256.HashData(await ReadBytesAsync(
            options["--manifest"], MaxManifestBytes, cancellationToken)));

        var typedManifest = Child(manifestRoot, "typed");
        var sourceValues = Child(typedManifest, "sourceHealthValues");
        var typedValues = Child(typedManifest, "currentValues");
        var expected = new Dictionary<string, int>(StringComparer.Ordinal)
        {
            ["currentHealth"] = NonnegativeInt(typedValues, "health"),
            ["maximumHealth"] = NonnegativeInt(typedValues, "healthMax"),
            ["rawPower"] = NonnegativeInt(typedValues, "power")
        };
        _ = NonnegativeInt(sourceValues, "health");
        _ = NonnegativeInt(sourceValues, "healthMax");
        _ = NonnegativeInt(sourceValues, "power");
        var manifestUnit = Text(typedManifest, "unitId");
        var observer = Text(typedManifest, "observer");
        var generation = NonnegativeInt(typedManifest, "generation");
        var sequence = PositiveInt(typedManifest, "selectedSequence");

        var observation = Child(receiptRoot, "observation");
        var observedTarget = Child(observation, "target");
        if (PositiveInt(observation, "riftProcessCount") != 1)
            throw new InvalidDataException("Pinned receipt does not identify exactly one RIFT process.");
        MatchReceiptTarget(observedTarget, requestedPid, requestedStart, requestedBuild);
        if (Text(observation, "instanceId") != observer)
            throw new InvalidDataException("Pinned receipt observer identity differs.");
        if (Text(Child(observation, "readback"), "status") != "fresh")
            throw new InvalidDataException("Pinned receipt readback is not fresh.");
        var typed = Child(Child(observation, "readback"), "typedApi");
        if (Text(typed, "status") != "fresh" ||
            !Boolean(typed, "sequenceAdvanced") || !Boolean(typed, "frameTimeAdvanced") ||
            NonnegativeInt(typed, "generation") != generation ||
            PositiveInt(typed, "selectedSequence") != sequence)
            throw new InvalidDataException("Pinned typed Lua freshness or generation/sequence differs.");
        var player = Child(Child(typed, "snapshot"), "player");
        if (Text(player, "unitId") != manifestUnit)
            throw new InvalidDataException("Pinned player identity differs.");
        var fields = Child(player, "fields");
        foreach (var (tag, field) in new[] {
                     ("currentHealth", "health"), ("maximumHealth", "healthMax"), ("rawPower", "power") })
        {
            var entry = Child(fields, field);
            if (Text(entry, "status") != "ok" || NonnegativeInt(entry, "value") != expected[tag])
                throw new InvalidDataException($"Pinned typed Lua {field} does not match the manifest.");
        }
        var receiptTime = Timestamp(Text(receiptRoot, "receivedAtUtc"), "receipt time");

        var loaded = await NativeMemorySnapshotFile.LoadAsync(options["--snapshot"], cancellationToken);
        var capture = loaded.File;
        if (capture.Status == "identity-invalidated")
            throw new InvalidDataException("Snapshot process identity was invalidated.");
        if (capture.Identity.ProcessId != requestedPid ||
            capture.Identity.ProcessStartUtcTicks != requestedStart ||
            capture.Identity.ExecutableSha256 != requestedBuild)
            throw new InvalidDataException("Snapshot PID/start/build differs from the request.");
        if (capture.Source.RequestEvidenceKind != "native-memory-snapshot-request/1" ||
            capture.Source.RequestSha256 != requestSha)
            throw new InvalidDataException("Snapshot source request SHA-256 differs from the retained exact request.");
        var started = Timestamp(capture.StartedAtUtc, "snapshot start");
        var completed = Timestamp(capture.CompletedAtUtc, "snapshot completed");
        var referenceAge = (started - receiptTime).TotalSeconds;
        var referenceNear = referenceAge is >= 0 and <= MaxObservationGapSeconds;
        var sourceHealthEqualsMax = NonnegativeInt(sourceValues, "health") ==
                                    NonnegativeInt(sourceValues, "healthMax");
        var currentHealthEqualsMax = expected["currentHealth"] == expected["maximumHealth"];

        if (capture.Chunks.Count > requestedRanges.GetArrayLength())
            throw new InvalidDataException("Snapshot has more chunks than the exact targeted request.");
        var results = new List<object>(requestedRanges.GetArrayLength());
        var readable = 0;
        var matchesAny = 0;
        var historicallyIdentical = 0;
        var previousEnd = 0UL;
        for (var i = 0; i < requestedRanges.GetArrayLength(); i++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var range = requestedRanges[i];
            var selection = selections[i];
            if (Text(range, "addressKind") != "absolute-session-address" ||
                PositiveInt(range, "byteLength") != WindowLength ||
                PositiveInt(selection, "byteLength") != WindowLength)
                throw new InvalidDataException($"Range {i} violates the narrow 80-byte snapshot plan.");
            var address = Address(range, "address");
            if (address < previousEnd || address > ulong.MaxValue - WindowLength)
                throw new InvalidDataException($"Range {i} overlaps or overflows.");
            previousEnd = address + WindowLength;
            if (Address(selection, "rangeSessionAddress") != address ||
                Address(selection, "firstHealthHitSessionAddress") != address + 16)
                throw new InvalidDataException($"Manifest range {i} address differs from the request.");
            var historicalHash = Hash(selection, "sourceWindowSha256");
            var markerData = Array(selection, "markerPositions");
            if (markerData.GetArrayLength() is < 1 or > 16)
                throw new InvalidDataException($"Manifest marker count invalid at range {i}.");

            var sites = new List<(int Offset, string[] Tags)>();
            var offsetsSeen = new HashSet<int>();
            foreach (var site in markerData.EnumerateArray())
            {
                var offset = NonnegativeInt(site, "byteOffset");
                if (offset > WindowLength - 4 || offset % 4 != 0 || !offsetsSeen.Add(offset))
                    throw new InvalidDataException($"Invalid or repeated marker byte offset at range {i}.");
                var tags = Array(site, "tags").EnumerateArray()
                    .Select(item => item.ValueKind == JsonValueKind.String ? item.GetString()! : "")
                    .ToArray();
                if (tags.Length is < 1 or > 4 || tags.Distinct(StringComparer.Ordinal).Count() != tags.Length ||
                    tags.Any(tag => !AllowedTags.Contains(tag, StringComparer.Ordinal)))
                    throw new InvalidDataException($"Range {i} contains invalid typed marker tags.");
                sites.Add((offset, tags));
            }
            var chunk = i < capture.Chunks.Count ? capture.Chunks[i] : null;
            if (chunk is not null &&
                (chunk.Address != $"0x{address:X}" || chunk.RequestedByteLength != WindowLength))
                throw new InvalidDataException($"Snapshot chunk {i} is not the requested range.");
            if (chunk is null || chunk.Status != "success")
            {
                results.Add(new
                {
                    rangeAddress = $"0x{address:X}",
                    status = chunk?.Status ?? "not-captured",
                    sourceWindowSha256 = historicalHash,
                    historicalBytesIdentical = (bool?)null,
                    allSitesMatchAnyCurrentValue = (bool?)null,
                    sites = System.Array.Empty<object>()
                });
                continue;
            }
            var bytes = Convert.FromBase64String(chunk.BytesBase64!);
            if (bytes.Length != WindowLength)
                throw new InvalidDataException($"Range {i} did not return all requested bytes.");
            readable++;
            var identical = Convert.ToHexString(SHA256.HashData(bytes)) == historicalHash;
            if (identical) historicallyIdentical++;
            var siteResults = sites.Select(site =>
            {
                var value = BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(site.Offset, 4));
                var comparisons = site.Tags.Select(tag => new
                {
                    tag,
                    expected = tag == "visualLevelHint" ? (int?)null : expected[tag],
                    matches = tag == "visualLevelHint" ? (bool?)null : value == expected[tag]
                }).ToArray();
                return new { byteOffset = site.Offset, nativeInt32 = value, comparisons };
            }).ToArray();
            var scoredSites = siteResults.Where(x => x.comparisons.Any(y => y.expected.HasValue)).ToArray();
            var candidateMatch = scoredSites.Length > 0 && scoredSites.All(x => x.comparisons.Any(y => y.matches == true));
            if (candidateMatch) matchesAny++;
            results.Add(new
            {
                rangeAddress = $"0x{address:X}",
                status = "success",
                sourceWindowSha256 = historicalHash,
                historicalBytesIdentical = (bool?)identical,
                allSitesMatchAnyCurrentValue = referenceNear ? (bool?)candidateMatch : null,
                sites = (object)siteResults
            });
        }

        var report = new
        {
            schemaVersion = 1,
            evidenceKind = "targeted-health-snapshot-audit/1",
            qualification = "candidate-only",
            source = new
            {
                requestSha256 = requestSha,
                manifestSha256 = manifestSha,
                receiptSha256 = receiptSha,
                snapshotSha256 = loaded.FileSha256,
                capture.Source.Implementation
            },
            identity = capture.Identity,
            capture = new
            {
                capture.Status,
                capture.Reason,
                capture.StartedAtUtc,
                capture.CompletedAtUtc,
                referenceAgeSeconds = referenceAge,
                typedReferenceNearCapture = referenceNear,
                captureChunkCount = capture.Chunks.Count
            },
            typed = new
            {
                observer,
                generation,
                sequence,
                unitId = manifestUnit,
                currentHealth = expected["currentHealth"],
                healthMax = expected["maximumHealth"],
                rawPower = expected["rawPower"],
                historicalHealthEqualsMax = sourceHealthEqualsMax,
                currentHealthEqualsMax
            },
            summary = new
            {
                requestedCandidateGroups = requestedRanges.GetArrayLength(),
                successfulGroups = readable,
                unavailableOrUncapturedGroups = requestedRanges.GetArrayLength() - readable,
                historicalBytesIdenticalGroups = historicallyIdentical,
                currentTypedAnyMatches = referenceNear ? (int?)matchesAny : null,
                currentVsMaxHealthDisambiguated = false
            },
            results,
            coverageWarnings = loaded.CoverageWarnings,
            limitations = new[] {
                "Health/power marker matches are candidate observations, not authoritative gameplay fields.",
                "The visual level hint has no independent typed Lua reference and is never scored as a match.",
                "A snapshot and Lua readback are sequential and cannot establish atomic state.",
                "A reference older than 15 seconds is not used for current-value matching.",
                "Historical byte differences may be unrelated to the tracked health or resource.",
                "Absolute addresses are valid only for the exact PID/start/build in this report.",
                "Health and healthMax require independent changed-state evidence before semantic qualification."
            }
        };
        cancellationToken.ThrowIfCancellationRequested();
        if (options.TryGetValue("--output", out var destination))
            await JsonReportWriter.WriteNewAsync(destination, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(report, JsonFormat.Options));
        return 0;
    }

    public static async Task<int> CompareAsync(
        IReadOnlyDictionary<string, string> options, TextWriter output, CancellationToken cancellationToken)
    {
        if (!options.TryGetValue("--before", out var beforePath) ||
            !options.TryGetValue("--after", out var afterPath))
            throw new ArgumentException("--before and --after are required.");

        var beforeBytes = await ReadBytesAsync(beforePath, 1024 * 1024, cancellationToken);
        var afterBytes = await ReadBytesAsync(afterPath, 1024 * 1024, cancellationToken);
        using var beforeDocument = JsonDocument.Parse(beforeBytes, new JsonDocumentOptions { MaxDepth = 36 });
        using var afterDocument = JsonDocument.Parse(afterBytes, new JsonDocumentOptions { MaxDepth = 36 });
        var a = beforeDocument.RootElement;
        var b = afterDocument.RootElement;
        CheckDistinctKeys(a);
        CheckDistinctKeys(b);
        RequireKind(a, "targeted-health-snapshot-audit/1");
        RequireKind(b, "targeted-health-snapshot-audit/1");
        if (Text(a, "qualification") != "candidate-only" ||
            Text(b, "qualification") != "candidate-only")
            throw new InvalidDataException("Audit source is not candidate-only.");

        var aa = Child(a, "source");
        var bb = Child(b, "source");
        var beforeSnapshotHash = Hash(aa, "snapshotSha256");
        var afterSnapshotHash = Hash(bb, "snapshotSha256");
        if (beforeSnapshotHash == afterSnapshotHash)
            throw new InvalidDataException("Two independent native snapshots are required.");
        if (Hash(aa, "requestSha256") != Hash(bb, "requestSha256"))
            throw new InvalidDataException("The native snapshot requests differ.");
        Hash(aa, "manifestSha256");
        Hash(bb, "manifestSha256");
        Hash(aa, "receiptSha256");
        Hash(bb, "receiptSha256");
        var ai = Child(a, "identity");
        var bi = Child(b, "identity");
        var pid = PositiveInt(ai, "processId");
        var start = PositiveInt64(ai, "processStartUtcTicks");
        var build = Hash(ai, "executableSha256");
        MatchTarget(bi, pid, start, build, "after snapshot");

        var ac = Child(a, "capture");
        var bc = Child(b, "capture");
        if (!Boolean(ac, "typedReferenceNearCapture") ||
            !Boolean(bc, "typedReferenceNearCapture"))
            throw new InvalidDataException("Both audits require current, near-capture Lua references.");
        if (Text(ac, "status") != "complete" || Text(bc, "status") != "complete")
            throw new InvalidDataException("Both audits must have complete native acquisitions.");
        if (Timestamp(Text(ac, "completedAtUtc"), "before completed") >
            Timestamp(Text(bc, "startedAtUtc"), "after started"))
            throw new InvalidDataException("Snapshot acquisition intervals overlap or run in reverse.");

        var at = Child(a, "typed");
        var bt = Child(b, "typed");
        if (Text(at, "observer") != Text(bt, "observer") ||
            Text(at, "unitId") != Text(bt, "unitId") ||
            NonnegativeInt(at, "generation") != NonnegativeInt(bt, "generation") ||
            PositiveInt(bt, "sequence") <= PositiveInt(at, "sequence"))
            throw new InvalidDataException("Typed reference observer, player, generation or sequence changed.");

        var names = new[] { "currentHealth", "healthMax", "rawPower" };
        var beforeTyped = names.ToDictionary(name => name, name => NonnegativeInt(at, name));
        var afterTyped = names.ToDictionary(name => name, name => NonnegativeInt(bt, name));
        var typedChanged = names.Any(name => beforeTyped[name] != afterTyped[name]);

        var ar = Array(a, "results");
        var br = Array(b, "results");
        if (ar.GetArrayLength() is < 1 or > MaxCandidateGroups ||
            br.GetArrayLength() != ar.GetArrayLength())
            throw new InvalidDataException("Audit candidate group counts differ.");
        var groups = new List<object>(ar.GetArrayLength());
        var trackingGroups = 0;
        var unreadableGroups = 0;
        var unexplainedSites = 0;
        for (var groupIndex = 0; groupIndex < ar.GetArrayLength(); groupIndex++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var first = ar[groupIndex];
            var second = br[groupIndex];
            var address = Address(first, "rangeAddress");
            if (Address(second, "rangeAddress") != address ||
                Hash(first, "sourceWindowSha256") != Hash(second, "sourceWindowSha256"))
                throw new InvalidDataException("Audits do not cover the same original candidate region.");
            if (Text(first, "status") != "success" || Text(second, "status") != "success")
                throw new InvalidDataException("An audit claiming a complete snapshot cannot contain unavailable candidate ranges.");
            var firstSites = Array(first, "sites").EnumerateArray().ToArray();
            var secondSites = Array(second, "sites").EnumerateArray().ToArray();
            if (firstSites.Length == 0 || firstSites.Length > 16 || secondSites.Length != firstSites.Length)
                throw new InvalidDataException("Audits have incompatible marker site coverage.");

            var siteReports = new List<object>(firstSites.Length);
            var trackedCount = 0;
            var siteOffsets = new HashSet<int>();
            foreach (var (aSite, bSite) in firstSites.Zip(secondSites))
            {
                var offset = NonnegativeInt(aSite, "byteOffset");
                if (offset > WindowLength - 4 || offset % 4 != 0 ||
                    !siteOffsets.Add(offset) || NonnegativeInt(bSite, "byteOffset") != offset)
                    throw new InvalidDataException("Audit site offsets are inconsistent.");
                var aNative = SignedInt(aSite, "nativeInt32");
                var bNative = SignedInt(bSite, "nativeInt32");
                var beforeTags = CheckSiteComparisons(aSite, beforeTyped, aNative);
                var afterTags = CheckSiteComparisons(bSite, afterTyped, bNative);
                if (!beforeTags.SequenceEqual(afterTags, StringComparer.Ordinal))
                    throw new InvalidDataException("Audit site marker tags changed between samples.");

                var tracked = new List<string>();
                foreach (var tag in beforeTags)
                {
                    if (tag == "visualLevelHint")
                        continue;
                    var key = tag switch
                    {
                        "currentHealth" => "currentHealth",
                        "maximumHealth" => "healthMax",
                        _ => "rawPower"
                    };
                    if (beforeTyped[key] != afterTyped[key] &&
                        aNative == beforeTyped[key] && bNative == afterTyped[key])
                        tracked.Add(tag);
                }
                trackedCount += tracked.Count > 0 ? 1 : 0;
                var status = tracked.Count > 1 ? "tracks-multiple-typed-changes" :
                             tracked.Count == 1 ? "tracks-one-typed-change" :
                             aNative == bNative ? "unchanged-or-cache" : "unexplained-change";
                if (status == "unexplained-change")
                    unexplainedSites++;
                siteReports.Add(new
                {
                    byteOffset = offset,
                    beforeInt32 = aNative,
                    afterInt32 = bNative,
                    markerTags = beforeTags,
                    status,
                    trackedTypedValues = tracked
                });
            }
            if (trackedCount > 0)
                trackingGroups++;
            groups.Add(new
            {
                rangeAddress = $"0x{address:X}",
                status = "compared",
                trackedMarkerSites = trackedCount,
                sites = (object)siteReports
            });
        }
        var report = new
        {
            schemaVersion = 1,
            evidenceKind = "targeted-health-change-comparison/1",
            qualification = "candidate-only",
            source = new
            {
                beforeAuditSha256 = Convert.ToHexString(SHA256.HashData(beforeBytes)),
                afterAuditSha256 = Convert.ToHexString(SHA256.HashData(afterBytes)),
                beforeSnapshotSha256 = beforeSnapshotHash,
                afterSnapshotSha256 = afterSnapshotHash,
                requestSha256 = Hash(aa, "requestSha256")
            },
            processIdentity = new
            {
                processId = pid,
                processStartUtcTicks = start,
                executableSha256 = build
            },
            observer = Text(at, "observer"),
            generation = NonnegativeInt(at, "generation"),
            unitId = Text(at, "unitId"),
            typed = new
            {
                before = beforeTyped,
                after = afterTyped,
                changed = typedChanged,
                deltas = names.ToDictionary(name => name, name => afterTyped[name] - beforeTyped[name])
            },
            summary = new
            {
                candidateGroups = groups.Count,
                comparedGroups = groups.Count - unreadableGroups,
                unavailableGroups = unreadableGroups,
                groupsWithMatchingTypedChange = trackingGroups,
                unexplainedMarkerChanges = unexplainedSites,
                currentHealthFieldQualified = false,
                resourceFieldQualified = false
            },
            groups,
            limitations = new[] {
                "Compares two supplied audit reports; their original native snapshot bytes are not reloaded here.",
                "Matching a typed value change across replicated structures cannot identify the authoritative gameplay field.",
                "An unchanged marker can be a cache, constant or unrelated field; it is not automatically negative evidence.",
                "Audits must be generated for the same exact process epoch, candidate ranges and advancing Lua observer.",
                "Cross-restart and game-update qualification require separate independently verified locators."
            }
        };
        cancellationToken.ThrowIfCancellationRequested();
        if (options.TryGetValue("--output", out var destination))
            await JsonReportWriter.WriteNewAsync(destination, report, cancellationToken);
        await output.WriteLineAsync(JsonSerializer.Serialize(report, JsonFormat.Options));
        return 0;
    }

    private static string[] CheckSiteComparisons(
        JsonElement site, IReadOnlyDictionary<string, int> typed, int native)
    {
        var items = Array(site, "comparisons");
        if (items.GetArrayLength() is < 1 or > 4)
            throw new InvalidDataException("Invalid typed marker comparisons.");
        var tags = new List<string>();
        foreach (var item in items.EnumerateArray())
        {
            var tag = Text(item, "tag");
            if (!AllowedTags.Contains(tag, StringComparer.Ordinal) || tags.Contains(tag, StringComparer.Ordinal))
                throw new InvalidDataException("Invalid or duplicate marker tag.");
            var expected = RequiredProperty(item, "expected");
            var matches = RequiredProperty(item, "matches");
            if (tag == "visualLevelHint")
            {
                if (expected.ValueKind != JsonValueKind.Null || matches.ValueKind != JsonValueKind.Null)
                    throw new InvalidDataException("Visual level is not a typed match.");
            }
            else
            {
                var key = tag switch
                {
                    "maximumHealth" => "healthMax",
                    "currentHealth" => "currentHealth",
                    _ => "rawPower"
                };
                if (expected.ValueKind != JsonValueKind.Number ||
                    !expected.TryGetInt32(out var value) || value != typed[key] ||
                    matches.ValueKind is not (JsonValueKind.True or JsonValueKind.False) ||
                    matches.GetBoolean() != (native == typed[key]))
                    throw new InvalidDataException("A typed site comparison does not match its audit reference.");
            }
            tags.Add(tag);
        }
        return [.. tags];
    }

    private static JsonElement RequiredProperty(JsonElement parent, string name)
    {
        if (parent.ValueKind != JsonValueKind.Object ||
            !parent.TryGetProperty(name, out var property))
            throw new InvalidDataException($"Missing typed comparison property: {name}.");
        return property;
    }

    private static int SignedInt(JsonElement parent, string name)
    {
        if (parent.ValueKind != JsonValueKind.Object || !parent.TryGetProperty(name, out var item) ||
            item.ValueKind != JsonValueKind.Number || !item.TryGetInt32(out var value))
            throw new InvalidDataException($"Missing signed integer: {name}.");
        return value;
    }

    private static async Task<JsonDocument> ReadJsonAsync(
        string path, int maxLength, CancellationToken cancellationToken)
    {
        var bytes = await ReadBytesAsync(path, maxLength, cancellationToken);
        var document = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 36 });
        try
        {
            CheckDistinctKeys(document.RootElement);
            return document;
        }
        catch
        {
            document.Dispose();
            throw;
        }
    }

    private static async Task<byte[]> ReadBytesAsync(
        string path, int maxLength, CancellationToken cancellationToken)
    {
        await using var stream = new FileStream(Path.GetFullPath(path), FileMode.Open, FileAccess.Read, FileShare.Read);
        if (stream.Length > maxLength)
            throw new InvalidDataException($"Input exceeds {maxLength} bytes: {Path.GetFileName(path)}.");
        using var buffer = new MemoryStream((int)stream.Length);
        var block = new byte[8192];
        int read;
        while ((read = await stream.ReadAsync(block.AsMemory(0,
                   (int)Math.Min(block.Length, maxLength + 1 - buffer.Length)), cancellationToken)) > 0)
        {
            buffer.Write(block, 0, read);
            if (buffer.Length > maxLength)
                throw new InvalidDataException($"Input exceeds {maxLength} bytes: {Path.GetFileName(path)}.");
        }
        return buffer.ToArray();
    }

    private static void CheckDistinctKeys(JsonElement root)
    {
        if (root.ValueKind == JsonValueKind.Object)
        {
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in root.EnumerateObject())
            {
                if (!seen.Add(property.Name))
                    throw new InvalidDataException($"Duplicate JSON property: {property.Name}.");
                CheckDistinctKeys(property.Value);
            }
        }
        else if (root.ValueKind == JsonValueKind.Array)
            foreach (var child in root.EnumerateArray())
                CheckDistinctKeys(child);
    }

    private static JsonElement Child(JsonElement parent, string name)
    {
        if (parent.ValueKind != JsonValueKind.Object || !parent.TryGetProperty(name, out var result) ||
            result.ValueKind != JsonValueKind.Object)
            throw new InvalidDataException($"Missing object: {name}.");
        return result;
    }

    private static JsonElement Array(JsonElement parent, string name)
    {
        if (parent.ValueKind != JsonValueKind.Object || !parent.TryGetProperty(name, out var result) ||
            result.ValueKind != JsonValueKind.Array)
            throw new InvalidDataException($"Missing array: {name}.");
        return result;
    }

    private static string Text(JsonElement parent, string name)
    {
        if (parent.ValueKind != JsonValueKind.Object || !parent.TryGetProperty(name, out var item) ||
            item.ValueKind != JsonValueKind.String || string.IsNullOrWhiteSpace(item.GetString()))
            throw new InvalidDataException($"Missing text property: {name}.");
        return item.GetString()!;
    }

    private static int PositiveInt(JsonElement parent, string name)
    {
        var n = NonnegativeInt(parent, name);
        if (n == 0) throw new InvalidDataException($"{name} must be positive.");
        return n;
    }

    private static int NonnegativeInt(JsonElement parent, string name)
    {
        if (parent.ValueKind != JsonValueKind.Object || !parent.TryGetProperty(name, out var item) ||
            item.ValueKind != JsonValueKind.Number || !item.TryGetInt32(out var n) || n < 0)
            throw new InvalidDataException($"{name} must be a nonnegative integer.");
        return n;
    }

    private static long PositiveInt64(JsonElement parent, string name)
    {
        if (parent.ValueKind != JsonValueKind.Object || !parent.TryGetProperty(name, out var item) ||
            item.ValueKind != JsonValueKind.Number || !item.TryGetInt64(out var n) || n <= 0)
            throw new InvalidDataException($"{name} must be a positive 64-bit integer.");
        return n;
    }

    private static bool Boolean(JsonElement parent, string name)
    {
        if (parent.ValueKind != JsonValueKind.Object || !parent.TryGetProperty(name, out var item) ||
            item.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
            throw new InvalidDataException($"{name} must be a boolean.");
        return item.GetBoolean();
    }

    private static string Hash(JsonElement parent, string name)
    {
        var value = Text(parent, name);
        if (value.Length != 64 || value.Any(c => c is not (>= '0' and <= '9') and not (>= 'A' and <= 'F')))
            throw new InvalidDataException($"{name} must be an uppercase SHA-256.");
        return value;
    }

    private static ulong Address(JsonElement parent, string name)
    {
        var value = Text(parent, name);
        if (value.Length < 3 || value.Length > 18 || !value.StartsWith("0x", StringComparison.Ordinal) ||
            !ulong.TryParse(value.AsSpan(2), NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture, out var n) ||
            $"0x{n:X}" != value)
            throw new InvalidDataException($"{name} must be a canonical 64-bit address.");
        return n;
    }

    private static void RequireKind(JsonElement root, string kind)
    {
        if (NonnegativeInt(root, "schemaVersion") != 1 || Text(root, "evidenceKind") != kind)
            throw new InvalidDataException($"Expected {kind} schema version 1.");
    }

    private static void MatchTarget(JsonElement element, int pid, long ticks, string build, string label)
    {
        if (PositiveInt(element, "processId") != pid ||
            PositiveInt64(element, "processStartUtcTicks") != ticks ||
            Hash(element, "executableSha256") != build)
            throw new InvalidDataException($"{label} PID/start/build differs from the exact snapshot request.");
    }

    private static void MatchReceiptTarget(JsonElement target, int pid, long ticks, string build)
    {
        var receiptStart = Timestamp(Text(target, "processStartUtc"), "receipt process start");
        if (PositiveInt(target, "processId") != pid ||
            receiptStart.UtcTicks != ticks ||
            Hash(target, "executableSha256") != build)
            throw new InvalidDataException("Pinned receipt PID/start/build differs from the request.");
    }

    private static DateTimeOffset Timestamp(string value, string property)
    {
        if (!value.EndsWith('Z') && !value.EndsWith("+00:00", StringComparison.Ordinal))
            throw new InvalidDataException($"{property} must specify UTC.");
        if (!DateTimeOffset.TryParse(value, CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out var timestamp))
            throw new InvalidDataException($"{property} is invalid.");
        return timestamp;
    }
}
