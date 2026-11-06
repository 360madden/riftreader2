using System.ComponentModel;
using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using RiftReader2.Infrastructure;
using Forms = System.Windows.Forms;

namespace RiftReader2.Live;

/// <summary>A local read-only presentation of the existing position sampler.</summary>
internal static class PositionPanelCommand
{
    internal static int Run(string[] args)
    {
        try
        {
            var options = NativeCommandRunner.ParseOptions(args, "--profile", "--output-directory");
            var profilePath = options.GetValueOrDefault("--profile") ??
                Path.Combine(AppContext.BaseDirectory, "position-candidate-profile.json");
            var outputDirectory = options.GetValueOrDefault("--output-directory") ??
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "RiftReader2", "Position", DateTimeOffset.UtcNow.ToString("yyyyMMddTHHmmssZ", CultureInfo.InvariantCulture) + "-" + Guid.NewGuid().ToString("N")[..8]);
            var profile = NativePositionProfileLoader.LoadAsync(profilePath).GetAwaiter().GetResult();
            var directory = Path.GetFullPath(outputDirectory);
            if (Directory.Exists(directory) || File.Exists(directory))
                throw new IOException("The panel evidence directory already exists; use a new session directory.");
            Directory.CreateDirectory(directory);
            JsonReportWriter.WriteNewAsync(Path.Combine(directory, "panel-session.json"), new
            {
                SchemaVersion = 1,
                ContractVersion = "native-position-panel-session/1",
                StartedAtUtc = DateTimeOffset.UtcNow.ToString("O"),
                Qualification = "candidate-only",
                profile.SourceSha256,
                profile.Profile,
                MaximumMonitoringSeconds = 600,
                PollDelayMilliseconds = 1000,
                FreshnessTimeoutMilliseconds = 3000,
                NoGameInput = true,
                PatchRecovery = "deferred; exact-build guard retained"
            }).GetAwaiter().GetResult();
            Exception? failure = null;
            var thread = new Thread(() =>
            {
                try
                {
                    Forms.Application.SetHighDpiMode(Forms.HighDpiMode.SystemAware);
                    Forms.Application.EnableVisualStyles();
                    Forms.Application.SetCompatibleTextRenderingDefault(false);
                    using var form = new PositionPanelForm(profile, directory);
                    Forms.Application.Run(form);
                }
                catch (Exception exception)
                {
                    failure = exception;
                }
            });
            thread.SetApartmentState(ApartmentState.STA);
            thread.Start();
            thread.Join();
            if (failure is not null)
                throw new IOException("The position window could not complete its session.", failure);
            return 0;
        }
        catch (Exception exception) when (exception is ArgumentException or IOException or
            UnauthorizedAccessException or InvalidDataException or JsonException or Win32Exception)
        {
            Console.Error.WriteLine($"Position panel: {exception.Message}");
            return 2;
        }
    }
}

internal sealed class PositionPanelForm : Forms.Form
{
    private readonly Forms.Button startButton = new() { Text = "Start", Name = "Start", Width = 130, Height = 42 };
    private readonly Forms.Button readButton = new() { Text = "Read", Name = "Read", Width = 130, Height = 42 };
    private readonly Forms.Button stopButton = new() { Text = "Stop", Name = "Stop", Width = 130, Height = 42 };
    private readonly Forms.Label statusLabel = new() { Text = "Stopped", Name = "Status", AutoSize = true };
    private readonly Forms.Label xyzLabel = new() { Text = "X  —\nY  —\nZ  —", Name = "Coordinates", AutoSize = true };
    private readonly Forms.Label identityLabel = new() { Text = "No current game reading", Name = "Identity", AutoSize = true };
    private readonly Forms.Label freshnessLabel = new() { Text = "", Name = "Freshness", AutoSize = true };
    private readonly Forms.Label reasonLabel = new() { Text = "Enter the world in RIFT, then choose Start or Read.", Name = "Reason", AutoSize = false, Height = 62, Width = 580 };
    private readonly Forms.Timer timer = new() { Interval = 150 };
    private readonly PositionPanelController controller;
    private readonly StreamWriter journal;
    private readonly object journalGate = new();
    private readonly string directory;
    private readonly TimeProvider timeProvider = TimeProvider.System;
    private long lastReadTimestamp;
    private int attempt;
    private volatile bool closing;

    internal PositionPanelForm(LoadedNativePositionProfile profile, string directory)
    {
        this.directory = directory;
        journal = new StreamWriter(new FileStream(Path.Combine(directory, "panel-events.jsonl"),
            FileMode.CreateNew, FileAccess.Write, FileShare.Read))
        { AutoFlush = true };
        controller = new PositionPanelController(async token =>
        {
            var number = Interlocked.Increment(ref attempt);
            var report = await Task.Run(() => PositionSampleCommand.ReadAsync(profile, 1, 0, token), token);
            token.ThrowIfCancellationRequested();
            var path = Path.Combine(directory, $"read-{number:D5}.json");
            await JsonReportWriter.WriteNewAsync(path, report, token);
            Record("report", new { Path = Path.GetFileName(path), Sha256 = Convert.ToHexString(SHA256.HashData(await File.ReadAllBytesAsync(path, token))), report.Samples.Identity });
            return report;
        });
        Text = "RiftReader2 · Player position";
        Name = "RiftReader2PositionPanel";
        ClientSize = new Size(640, 590);
        MinimumSize = new Size(656, 629);
        StartPosition = Forms.FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 11);
        BackColor = Color.FromArgb(246, 249, 251);
        var layout = new Forms.FlowLayoutPanel
        {
            Dock = Forms.DockStyle.Fill,
            FlowDirection = Forms.FlowDirection.TopDown,
            WrapContents = false,
            Padding = new Forms.Padding(24),
            AutoScroll = true
        };
        layout.Controls.Add(new Forms.Label { Text = "Player position", Font = new Font(Font.FontFamily, 21, FontStyle.Bold), AutoSize = true });
        layout.Controls.Add(statusLabel);
        var buttons = new Forms.FlowLayoutPanel { Width = 580, Height = 58 };
        buttons.Controls.AddRange([startButton, readButton, stopButton]);
        layout.Controls.Add(buttons);
        xyzLabel.Font = new Font("Consolas", 23, FontStyle.Bold);
        xyzLabel.Margin = new Forms.Padding(3, 8, 3, 18);
        layout.Controls.Add(xyzLabel);
        layout.Controls.Add(identityLabel);
        layout.Controls.Add(freshnessLabel);
        layout.Controls.Add(reasonLabel);
        layout.Controls.Add(new Forms.Label
        {
            Text = "Start monitors for up to 10 minutes. Read takes one fresh sample.\nStop clears the values and cancels the current read.\nNative XYZ candidate · Read-only · Patch recovery deferred",
            AutoSize = true,
            ForeColor = Color.DimGray,
            Margin = new Forms.Padding(3, 12, 3, 3)
        });
        Controls.Add(layout);
        controller.Changed += OnChanged;
        startButton.Click += (_, _) => { Record("start", null); controller.Start(); };
        readButton.Click += async (_, _) => { Record("read", null); await ReadAsync(); };
        stopButton.Click += (_, _) => { Record("stop", null); controller.Stop(); };
        timer.Tick += async (_, _) =>
        {
            controller.RefreshFreshness();
            if (controller.State.IsMonitoring && !controller.State.IsReading &&
                (lastReadTimestamp == 0 || timeProvider.GetElapsedTime(lastReadTimestamp) >= TimeSpan.FromSeconds(1)))
                await ReadAsync();
        };
        Shown += (_, _) => { Record("opened", new { Environment.ProcessId, Directory = directory }); timer.Start(); Render(controller.State); };
        FormClosing += (_, _) =>
        {
            timer.Stop();
            controller.Stop();
            Record("closed", null);
            closing = true;
        };
    }

    private async Task ReadAsync()
    {
        lastReadTimestamp = timeProvider.GetTimestamp();
        await controller.ReadAsync();
    }

    private void OnChanged(PositionPanelState state)
    {
        if (closing || IsDisposed)
            return;
        Record("state", state);
        if (InvokeRequired)
        {
            try
            {
                BeginInvoke(() => { if (!closing) Render(controller.State); });
            }
            catch (InvalidOperationException) when (closing || IsDisposed)
            {
                // Closing a window may race the completion of its canceled read.
            }
            return;
        }
        Render(controller.State);
    }

    private void Render(PositionPanelState state)
    {
        startButton.Enabled = !state.IsMonitoring;
        readButton.Enabled = !state.IsReading;
        stopButton.Enabled = state.IsMonitoring || state.IsReading || state.Observation is not null;
        var absent = state.Reason?.Contains("found 0.", StringComparison.Ordinal) == true;
        var initializing = state.Reason == "position-values-not-ready";
        var unsupportedBuild = state.Reason?.Contains("SHA-256", StringComparison.Ordinal) == true ||
            state.Reason == "profile-process-build-mismatch";
        statusLabel.Text = absent ? "Waiting for RIFT" : initializing ? "Waiting for position" : state.Status switch
        {
            "live" => state.IsMonitoring ? "Monitoring · Fresh reading" : "Fresh reading",
            "waiting" => "Waiting for RIFT",
            "reading" => "Reading…",
            "stale" => "Reading expired",
            "unavailable" => "Position unavailable",
            "expired" => "Monitoring finished",
            _ => "Stopped"
        };
        var observation = state.Status == "live" ? state.Observation : null;
        xyzLabel.Text = observation is null ? "X  —\nY  —\nZ  —" :
            string.Create(CultureInfo.InvariantCulture, $"X  {observation.X:F5}\nY  {observation.Y:F5}\nZ  {observation.Z:F5}");
        identityLabel.Text = observation is null || state.Identity is null ? "No current game reading" :
            $"Game session {state.Identity.ProcessId}";
        freshnessLabel.Text = observation is null ? "" : $"Updated {DateTimeOffset.Parse(observation.CompletedAtUtc, CultureInfo.InvariantCulture):HH:mm:ss 'UTC'} · fresh for up to 3 seconds";
        reasonLabel.Text = absent ? "RIFT is closed. Launch it and enter the world to read your position." :
            initializing ? state.IsMonitoring
                ? "Position values are still initializing. Monitoring will retry automatically."
                : "Position values are still initializing. Enter the world, then choose Read or Start." :
            unsupportedBuild ? "This game build does not match the saved profile. Patch recovery is deferred." :
            state.Status == "unavailable" ? "The current position could not be read. Details were saved in this session's evidence." :
            state.Status == "stale" ? "The last reading has expired. Choose Read or Start to get a fresh position." :
            state.Status == "expired" ? "The 10-minute monitoring session has finished. Choose Start to continue." :
            state.IsMonitoring
            ? "Each read finds the current game process and resolves its position afresh."
            : "Enter the world in RIFT, then choose Start or Read.";
    }

    private void Record(string kind, object? value)
    {
        lock (journalGate)
        {
            if (!closing)
                journal.WriteLine(JsonSerializer.Serialize(new { AtUtc = DateTimeOffset.UtcNow.ToString("O"), Kind = kind, Value = value }, new JsonSerializerOptions(JsonFormat.Options) { WriteIndented = false }));
        }
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            closing = true;
            timer.Dispose();
            controller.Dispose();
            lock (journalGate)
                journal.Dispose();
        }
        base.Dispose(disposing);
    }
}
