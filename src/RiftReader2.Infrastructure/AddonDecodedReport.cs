using System.Security.Cryptography;
using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

public sealed record AddonDecodedReport(
    int SchemaVersion,
    string EvidenceKind,
    string BindingStatus,
    string FreshnessStatus,
    string FrameSha256,
    IReadOnlyDictionary<string, object?> Observation)
{
    public static AddonDecodedReport FromFrame(ReadOnlySpan<byte> frame)
    {
        var observation = AddonFrameDecoder.Decode(frame);
        var frameSha256 = Convert.ToHexString(SHA256.HashData(frame));
        return Create(observation, frameSha256);
    }

    private static AddonDecodedReport Create(AddonObservation observation, string frameSha256) =>
        new(
            1,
            "addon-api-reference",
            "unbound",
            "unverified",
            frameSha256,
            ToWireObservation(observation));

    private static IReadOnlyDictionary<string, object?> ToWireObservation(AddonObservation observation) =>
        new Dictionary<string, object?>
        {
            ["schemaVersion"] = observation.SchemaVersion,
            ["addonVersion"] = observation.AddonVersion,
            ["sequence"] = observation.Sequence,
            ["epoch"] = observation.Epoch,
            ["clock"] = ToWireField(observation.Clock.Status, observation.Clock.Value),
            ["player"] = ToWireField(observation.Player.Status, observation.Player.Value),
            ["fields"] = new Dictionary<string, object?>
            {
                ["coordX"] = ToWireField(observation.Fields.CoordX.Status, observation.Fields.CoordX.Value),
                ["coordY"] = ToWireField(observation.Fields.CoordY.Status, observation.Fields.CoordY.Value),
                ["coordZ"] = ToWireField(observation.Fields.CoordZ.Status, observation.Fields.CoordZ.Value),
                ["health"] = ToWireField(observation.Fields.Health.Status, observation.Fields.Health.Value),
                ["healthMax"] = ToWireField(observation.Fields.HealthMax.Status, observation.Fields.HealthMax.Value),
                ["combat"] = ToWireField(observation.Fields.Combat.Status, observation.Fields.Combat.Value)
            }
        };

    private static IReadOnlyDictionary<string, object?> ToWireField(AddonFieldStatus status, object? value)
    {
        var field = new Dictionary<string, object?>
        {
            ["status"] = status switch
            {
                AddonFieldStatus.Ok => "ok",
                AddonFieldStatus.Unavailable => "unavailable",
                AddonFieldStatus.Invalid => "invalid",
                _ => throw new ArgumentOutOfRangeException(nameof(status))
            }
        };
        if (status == AddonFieldStatus.Ok)
            field["value"] = value;
        return field;
    }
}
