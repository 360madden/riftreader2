using System.Net;
using System.Text;
using System.Text.Json;
using RiftReader2.Infrastructure;

namespace RiftReader2.Live;

public sealed class LiveDeliveryClient : IDisposable
{
    private readonly LiveDeliveryConfiguration? configuration;
    private readonly HttpClient client;
    private LiveDeliveryReport state;

    public LiveDeliveryClient(LiveDeliveryConfiguration? configuration)
    {
        this.configuration = configuration;
        client = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false, UseProxy = false })
        {
            Timeout = TimeSpan.FromSeconds(2)
        };
        state = configuration is null
            ? new(false, "disabled", null, null, null)
            : new(true, "ready", SafeEndpoint(configuration.GetValidatedEndpoint()), null, null);
    }

    public LiveDeliveryReport State => state;

    public async Task DeliverAsync(LiveReaderSnapshot snapshot, CancellationToken cancellationToken)
    {
        if (configuration is null)
            return;
        try
        {
            var payload = JsonSerializer.Serialize(snapshot, JsonFormat.Options);
            if (Encoding.UTF8.GetByteCount(payload) > 128 * 1024)
                throw new InvalidDataException("Live observation exceeds 128 KiB.");
            using var request = new HttpRequestMessage(HttpMethod.Post, configuration.GetValidatedEndpoint())
            {
                Content = new StringContent(payload, Encoding.UTF8, "application/json")
            };
            request.Headers.Add("X-RiftReader-Token", configuration.Token);
            using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
            response.EnsureSuccessStatusCode();
            state = state with
            {
                Status = $"delivered-http-{(int)response.StatusCode}",
                LastSuccessUtc = DateTimeOffset.UtcNow.ToString("O"),
                Error = null
            };
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            state = state with { Status = "delivery-timeout", Error = "Delivery exceeded two seconds." };
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            state = state with { Status = "delivery-failed", Error = exception.Message };
        }
    }

    public void Dispose() => client.Dispose();

    private static string SafeEndpoint(Uri endpoint) => endpoint.GetLeftPart(UriPartial.Path);
}
