using System.Text.Json;
using System.Text.Json.Serialization;

namespace RiftReader2.Infrastructure;

public static class JsonFormat
{
    public static JsonSerializerOptions Options { get; } = Create();

    private static JsonSerializerOptions Create()
    {
        var options = new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
            RespectRequiredConstructorParameters = true,
            RespectNullableAnnotations = true,
            AllowDuplicateProperties = false,
            WriteIndented = true,
            MaxDepth = 16
        };
        options.MakeReadOnly(populateMissingResolver: true);
        return options;
    }
}
