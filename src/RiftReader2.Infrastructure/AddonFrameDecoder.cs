using System.Text.Json;
using RiftReader2.Domain;

namespace RiftReader2.Infrastructure;

public static class AddonFrameDecoder
{
    public const int MaxFrameBytes = 4096;

    private const long MaxSafeInteger = 9_007_199_254_740_991;
    private static readonly byte[] Prefix = "RR2A1|"u8.ToArray();
    private static readonly byte[] Suffix = "|ENDRR2A1"u8.ToArray();

    public static AddonObservation Decode(ReadOnlySpan<byte> frame)
    {
        if (frame.Length == 0 || frame.Length > MaxFrameBytes)
            throw Invalid("Addon frame must contain 1 to 4096 bytes.");
        if (ContainsNonAscii(frame))
            throw Invalid("Addon frame must contain ASCII bytes only.");
        if (frame.Length < Prefix.Length + Suffix.Length ||
            !frame.StartsWith(Prefix) ||
            !frame.EndsWith(Suffix))
            throw Invalid("Addon frame markers are invalid.");

        var payload = frame[Prefix.Length..^Suffix.Length];
        try
        {
            using var document = JsonDocument.Parse(
                payload.ToArray(),
                new JsonDocumentOptions
                {
                    AllowTrailingCommas = false,
                    CommentHandling = JsonCommentHandling.Disallow,
                    MaxDepth = 8
                });
            return DecodeRoot(document.RootElement);
        }
        catch (InvalidDataException)
        {
            throw;
        }
        catch (Exception exception) when (exception is JsonException or FormatException or OverflowException)
        {
            throw Invalid("Addon frame JSON is malformed or contains an invalid value.", exception);
        }
    }

    private static AddonObservation DecodeRoot(JsonElement root)
    {
        RequireExactProperties(
            root,
            "observation",
            "schemaVersion",
            "addonVersion",
            "sequence",
            "epoch",
            "clock",
            "player",
            "fields");

        var schemaVersion = ReadInteger(root, "schemaVersion", 1, 1);
        var addonVersion = ReadString(root, "addonVersion");
        if (addonVersion != "0.1.0")
            throw Invalid("Unsupported addonVersion; expected 0.1.0.");
        var sequence = ReadInteger(root, "sequence", 1, MaxSafeInteger);
        var epoch = ReadInteger(root, "epoch", 1, MaxSafeInteger);
        var clock = ReadNumberField(root.GetProperty("clock"), "clock", nonnegative: true);
        var player = ReadStringField(root.GetProperty("player"), "player");
        var fieldsElement = root.GetProperty("fields");
        RequireExactProperties(
            fieldsElement,
            "fields",
            "coordX",
            "coordY",
            "coordZ",
            "health",
            "healthMax",
            "combat");
        var fields = new AddonObservationFields(
            ReadNumberField(fieldsElement.GetProperty("coordX"), "fields.coordX"),
            ReadNumberField(fieldsElement.GetProperty("coordY"), "fields.coordY"),
            ReadNumberField(fieldsElement.GetProperty("coordZ"), "fields.coordZ"),
            ReadNumberField(fieldsElement.GetProperty("health"), "fields.health"),
            ReadNumberField(fieldsElement.GetProperty("healthMax"), "fields.healthMax"),
            ReadBooleanField(fieldsElement.GetProperty("combat"), "fields.combat"));

        if (clock.Status != AddonFieldStatus.Ok)
        {
            if (player.Status != AddonFieldStatus.Unavailable || !AllUnavailable(fields))
                throw Invalid("An unsuccessful clock requires unavailable player and fields.");
        }
        else if (player.Status != AddonFieldStatus.Ok && !AllUnavailable(fields))
        {
            throw Invalid("An unsuccessful player requires unavailable fields.");
        }

        return new(
            checked((int)schemaVersion),
            addonVersion,
            sequence,
            epoch,
            clock,
            player,
            fields);
    }

    private static AddonNumberField ReadNumberField(JsonElement element, string name, bool nonnegative = false)
    {
        var (status, value) = ReadField(element, name);
        if (status != AddonFieldStatus.Ok)
            return new(status, null);
        if (value.ValueKind != JsonValueKind.Number || !value.TryGetDouble(out var number) || !double.IsFinite(number))
            throw Invalid($"{name}.value must be a finite number.");
        if (nonnegative && number < 0)
            throw Invalid($"{name}.value must be nonnegative.");
        return new(status, number);
    }

    private static AddonStringField ReadStringField(JsonElement element, string name)
    {
        var (status, value) = ReadField(element, name);
        if (status != AddonFieldStatus.Ok)
            return new(status, null);
        if (value.ValueKind != JsonValueKind.String)
            throw Invalid($"{name}.value must be a string.");
        var text = value.GetString()!;
        if (text.Length is < 1 or > 128 || text.Any(character => character is < (char)0x20 or > (char)0x7e))
            throw Invalid($"{name}.value must contain 1 to 128 printable ASCII characters.");
        return new(status, text);
    }

    private static AddonBooleanField ReadBooleanField(JsonElement element, string name)
    {
        var (status, value) = ReadField(element, name);
        if (status != AddonFieldStatus.Ok)
            return new(status, null);
        if (value.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
            throw Invalid($"{name}.value must be a boolean.");
        return new(status, value.GetBoolean());
    }

    private static (AddonFieldStatus Status, JsonElement Value) ReadField(JsonElement element, string name)
    {
        if (element.ValueKind != JsonValueKind.Object)
            throw Invalid($"{name} must be an object.");

        var properties = element.EnumerateObject().ToArray();
        var names = new HashSet<string>(StringComparer.Ordinal);
        foreach (var property in properties)
        {
            if (!names.Add(property.Name))
                throw Invalid($"{name} contains duplicate property '{property.Name}'.");
            if (property.Name is not ("status" or "value"))
                throw Invalid($"{name} contains unknown property '{property.Name}'.");
        }
        if (!names.Contains("status"))
            throw Invalid($"{name} is missing status.");

        var statusElement = element.GetProperty("status");
        if (statusElement.ValueKind != JsonValueKind.String)
            throw Invalid($"{name}.status must be a string.");
        var status = statusElement.GetString() switch
        {
            "ok" => AddonFieldStatus.Ok,
            "unavailable" => AddonFieldStatus.Unavailable,
            "invalid" => AddonFieldStatus.Invalid,
            _ => throw Invalid($"{name}.status is unsupported.")
        };
        var hasValue = names.Contains("value");
        if ((status == AddonFieldStatus.Ok) != hasValue)
            throw Invalid($"{name} has a status/value mismatch.");
        return (status, hasValue ? element.GetProperty("value") : default);
    }

    private static void RequireExactProperties(JsonElement element, string name, params string[] expected)
    {
        if (element.ValueKind != JsonValueKind.Object)
            throw Invalid($"{name} must be an object.");
        var expectedNames = new HashSet<string>(expected, StringComparer.Ordinal);
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var property in element.EnumerateObject())
        {
            if (!seen.Add(property.Name))
                throw Invalid($"{name} contains duplicate property '{property.Name}'.");
            if (!expectedNames.Contains(property.Name))
                throw Invalid($"{name} contains unknown property '{property.Name}'.");
        }
        var missing = expectedNames.FirstOrDefault(property => !seen.Contains(property));
        if (missing is not null)
            throw Invalid($"{name} is missing property '{missing}'.");
    }

    private static long ReadInteger(JsonElement root, string property, long minimum, long maximum)
    {
        var element = root.GetProperty(property);
        if (element.ValueKind != JsonValueKind.Number || !element.TryGetInt64(out var value) || value < minimum || value > maximum)
            throw Invalid($"{property} must be an integer from {minimum} through {maximum}.");
        return value;
    }

    private static string ReadString(JsonElement root, string property)
    {
        var element = root.GetProperty(property);
        if (element.ValueKind != JsonValueKind.String)
            throw Invalid($"{property} must be a string.");
        return element.GetString()!;
    }

    private static bool AllUnavailable(AddonObservationFields fields) =>
        fields.CoordX.Status == AddonFieldStatus.Unavailable &&
        fields.CoordY.Status == AddonFieldStatus.Unavailable &&
        fields.CoordZ.Status == AddonFieldStatus.Unavailable &&
        fields.Health.Status == AddonFieldStatus.Unavailable &&
        fields.HealthMax.Status == AddonFieldStatus.Unavailable &&
        fields.Combat.Status == AddonFieldStatus.Unavailable;

    private static bool ContainsNonAscii(ReadOnlySpan<byte> value)
    {
        foreach (var character in value)
        {
            if (character > 0x7f)
                return true;
        }
        return false;
    }

    private static InvalidDataException Invalid(string message, Exception? inner = null) =>
        new(message, inner);
}
