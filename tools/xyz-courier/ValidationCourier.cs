using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static class ValidationCourierProgram
{
    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            CourierConfig config = CourierConfig.Load(AppDomain.CurrentDomain.BaseDirectory);
            if (args.Length == 1 && string.Equals(args[0], "--preflight", StringComparison.Ordinal))
            {
                config.VerifySourcePayloads();
                Console.WriteLine("{\"status\":\"preflight-passed-no-install-performed\",\"runId\":\"" +
                    config.RunId + "\",\"gameSha256\":\"" + config.GameSha +
                    "\",\"installationPerformed\":false,\"readerExecuted\":false,\"networkUsed\":false}");
                return 0;
            }
            if (args.Length != 0)
                throw new InvalidOperationException("Only --preflight or no arguments are supported.");
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new ValidationCourierForm(config));
            return 0;
        }
        catch (Exception exception)
        {
            Console.WriteLine("{\"status\":\"rejected\"}");
            Console.Error.WriteLine("Courier rejected: " + exception.GetType().Name + ": " + exception.Message);
            return 1;
        }
    }
}

internal sealed class ValidationCourierForm : Form
{
    private const string ClaimUrl = "http://192.168.56.1:8765/rr2-native-pointer-zip-claim-oct24-01";
    private const string UploadUrl = "http://192.168.56.1:8765/rr2-native-pointer-oct24-01-report.zip";
    private const int CommandTimeoutMilliseconds = 20000;
    private const long MaximumZipBytes = 16L * 1024L * 1024L;
    private const int MaximumFiles = 2048;

    private readonly Button installButton = NewButton("Install");
    private readonly Button beforeButton = NewButton("Capture before");
    private readonly Button panelButton = NewButton("Open panel");
    private readonly Button absentButton = NewButton("Capture absent");
    private readonly Button afterButton = NewButton("Capture after");
    private readonly Button packageButton = NewButton("Package");
    private readonly Button declareButton = NewButton("Declare");
    private readonly Button uploadButton = NewButton("Upload");
    private readonly TextBox statusBox = new TextBox();
    private readonly object logGate = new object();
    private readonly JavaScriptSerializer serializer = new JavaScriptSerializer();
    private readonly CourierConfig config;

    private CourierStage stage = CourierStage.New;
    private bool busy;
    private GameIdentity oldIdentity;
    private GameIdentity afterIdentity;
    private Process panelProcess;
    private long panelProcessStartUtcTicks;
    private string zipSha;
    private long zipBytes;

    private string ReaderSha { get { return config.ReaderSha; } }
    private long ReaderBytes { get { return config.ReaderBytes; } }
    private string ProfileSha { get { return config.ProfileSha; } }
    private long ProfileBytes { get { return config.ProfileBytes; } }
    private string GameSha { get { return config.GameSha; } }
    private string InstallRoot { get { return config.InstallRoot; } }

    private string SourceDirectory { get { return AppDomain.CurrentDomain.BaseDirectory; } }
    private string SourceReader { get { return Path.Combine(SourceDirectory, "RiftReader2.Live.exe"); } }
    private string SourceProfile { get { return Path.Combine(SourceDirectory, "position-candidate-profile.json"); } }
    private string InstalledReader { get { return Path.Combine(InstallRoot, "RiftReader2.Live.exe"); } }
    private string InstalledProfile { get { return Path.Combine(InstallRoot, "position-candidate-profile.json"); } }
    private string ResultsRoot { get { return Path.Combine(InstallRoot, "results"); } }
    private string PanelRoot { get { return Path.Combine(ResultsRoot, "panel-01"); } }
    private string ZipPath { get { return Path.Combine(InstallRoot, "xyz-interface-restart-evidence.zip"); } }
    private string ActionLog { get { return Path.Combine(ResultsRoot, "courier-actions.jsonl"); } }

    internal ValidationCourierForm(CourierConfig config)
    {
        if (config == null)
            throw new ArgumentNullException("config");
        this.config = config;
        Text = "RiftReader2 restart validation courier";
        ClientSize = new Size(940, 660);
        MinimumSize = new Size(820, 560);
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 10F);

        FlowLayoutPanel buttons = new FlowLayoutPanel();
        buttons.Dock = DockStyle.Top;
        buttons.Height = 125;
        buttons.Padding = new Padding(8);
        buttons.AutoScroll = true;
        buttons.WrapContents = true;
        buttons.Controls.AddRange(new Control[] {
            installButton, beforeButton, panelButton, absentButton,
            afterButton, packageButton, declareButton, uploadButton
        });

        statusBox.Dock = DockStyle.Fill;
        statusBox.Multiline = true;
        statusBox.ReadOnly = true;
        statusBox.ScrollBars = ScrollBars.Both;
        statusBox.WordWrap = false;
        statusBox.Font = new Font("Consolas", 12F);
        statusBox.BackColor = Color.White;

        Controls.Add(statusBox);
        Controls.Add(buttons);

        installButton.Click += delegate { RunActionAsync("install", Install); };
        beforeButton.Click += delegate { RunActionAsync("capture-before", CaptureBefore); };
        panelButton.Click += delegate { RunActionAsync("open-panel", OpenPanel); };
        absentButton.Click += delegate { RunActionAsync("capture-absent", CaptureAbsent); };
        afterButton.Click += delegate { RunActionAsync("capture-after", CaptureAfter); };
        packageButton.Click += delegate { RunActionAsync("package", Package); };
        declareButton.Click += delegate { RunActionAsync("declare", Declare); };
        uploadButton.Click += delegate { RunActionAsync("upload", Upload); };

        AppendStatus("Validation-only GUI. It never controls RIFT or reads personal files.");
        AppendStatus("Source: " + SourceDirectory);
        AppendStatus("Install destination must be new: " + InstallRoot);
        RefreshButtons();
    }

    private static Button NewButton(string text)
    {
        return new Button { Text = text, Width = 140, Height = 40, Margin = new Padding(5) };
    }

    private async void RunActionAsync(string action, Action work)
    {
        if (busy)
            return;
        busy = true;
        RefreshButtons();
        AppendStatus("");
        AppendStatus(DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture) + "  " + action + " started");
        Exception failure = null;
        try
        {
            await Task.Run(work);
        }
        catch (Exception exception)
        {
            failure = exception;
        }
        if (failure == null)
        {
            AppendStatus(action + " completed.");
            TryLogAction(action, true, 0, null);
        }
        else
        {
            AppendStatus("BLOCKED " + failure.GetType().Name + ": " + failure.Message);
            TryLogAction(action, false, null, failure.GetType().Name + ": " + failure.Message);
        }
        busy = false;
        RefreshButtons();
    }

    private void RefreshButtons()
    {
        installButton.Enabled = !busy && stage == CourierStage.New;
        beforeButton.Enabled = !busy && stage == CourierStage.Installed;
        panelButton.Enabled = !busy && stage == CourierStage.BeforeCaptured;
        absentButton.Enabled = !busy && stage == CourierStage.PanelOpened;
        afterButton.Enabled = !busy && stage == CourierStage.AbsentCaptured;
        packageButton.Enabled = !busy && stage == CourierStage.AfterCaptured;
        declareButton.Enabled = !busy && stage == CourierStage.Packaged;
        uploadButton.Enabled = !busy && stage == CourierStage.Declared;
    }

    private void AppendStatus(string value)
    {
        if (InvokeRequired)
        {
            Invoke(new Action<string>(AppendStatus), value);
            return;
        }
        statusBox.AppendText(value + Environment.NewLine);
    }

    private void Install()
    {
        config.VerifySourcePayloads();
        config.VerifyInstallRootConfinement();
        if (Directory.Exists(InstallRoot) || File.Exists(InstallRoot))
            throw new IOException("Install destination already exists; no overwrite is permitted.");

        Directory.CreateDirectory(InstallRoot);
        Directory.CreateDirectory(ResultsRoot);
        config.VerifyInstallRootConfinement();
        CopyNew(SourceReader, InstalledReader);
        CopyNew(SourceProfile, InstalledProfile);
        VerifyInstalledPins();

        WriteNewJson(Path.Combine(ResultsRoot, "installation.json"), new Dictionary<string, object> {
            { "schemaVersion", 1 },
            { "purpose", "xyz-interface-restart-validation-install" },
            { "installedAtUtc", UtcNow() },
            { "source", "pinned Courier bundle beside ValidationCourier.exe" },
            { "destination", InstallRoot },
            { "readerSha256", ReaderSha },
            { "readerByteLength", ReaderBytes },
            { "profileSha256", ProfileSha },
            { "profileByteLength", ProfileBytes },
            { "courierSha256", CourierSha() },
            { "courierCopied", false },
            { "noGameInput", true }
        });
        WriteNewJson(Path.Combine(ResultsRoot, "courier-config-receipt.json"),
            new Dictionary<string, object> {
                { "schemaVersion", 1 },
                { "purpose", "xyz-interface-courier-run-configuration" },
                { "runId", config.RunId },
                { "configSha256", config.ConfigSha },
                { "destination", InstallRoot },
                { "readerSha256", ReaderSha },
                { "profileSha256", ProfileSha },
                { "gameSha256", GameSha },
                { "patchRecovery", "deferred" },
                { "noGameInput", true }
            });
        stage = CourierStage.Installed;
        AppendStatus("Installed exact reader/profile. Courier remains in the pinned source bundle.");
    }

    private void CaptureBefore()
    {
        RequireStage(CourierStage.Installed);
        VerifyInstalledPins();
        oldIdentity = GetExactlyOneGame();
        WriteIdentity("before-identity.json", "before-full-game-exit", oldIdentity);
        AppendIdentity("BEFORE", oldIdentity);

        CommandResult samples = RunReader(
            "before-samples",
            "sample-position --profile " + Quote(InstalledProfile) +
            " --samples 3 --interval-ms 500 --output " + Quote(Result("before-samples.json")));
        Require(samples.ExitCode == 0 && File.Exists(Result("before-samples.json")),
            "Before sampler did not publish a complete report.");
        RequireSampleIdentity(Result("before-samples.json"), oldIdentity);

        string request = Result("before-pointer.request.json");
        WritePointerRequest(request, oldIdentity);
        CommandResult pointer = RunReader(
            "before-pointer",
            "follow-pointer --request " + Quote(request) +
            " --output " + Quote(Result("before-pointer.json")));
        Require(pointer.ExitCode == 0 && File.Exists(Result("before-pointer.json")),
            "Before raw pointer capture did not complete.");
        stage = CourierStage.BeforeCaptured;
    }

    private void OpenPanel()
    {
        RequireStage(CourierStage.BeforeCaptured);
        VerifyInstalledPins();
        if (Directory.Exists(PanelRoot) || File.Exists(PanelRoot))
            throw new IOException("Fixed panel evidence directory already exists.");
        if (panelProcess != null && !panelProcess.HasExited)
            throw new InvalidOperationException("The validation panel is already running.");

        ProcessStartInfo start = new ProcessStartInfo();
        start.FileName = InstalledReader;
        start.Arguments = "position-panel --profile " + Quote(InstalledProfile) +
            " --output-directory " + Quote(PanelRoot);
        start.WorkingDirectory = InstallRoot;
        start.UseShellExecute = false;
        start.CreateNoWindow = true;
        panelProcess = Process.Start(start);
        if (panelProcess == null)
            throw new InvalidOperationException("The panel process was not created.");
        panelProcessStartUtcTicks = panelProcess.StartTime.ToUniversalTime().Ticks;
        RequirePanelRunning();
        stage = CourierStage.PanelOpened;
        AppendStatus("Panel PID " + panelProcess.Id.ToString(CultureInfo.InvariantCulture) +
            " launched directly. Use its Start / Read / Stop buttons.");
    }

    private void CaptureAbsent()
    {
        RequireStage(CourierStage.PanelOpened);
        VerifyInstalledPins();
        RequirePanelRunning();
        Require(oldIdentity != null, "The old process identity is unavailable.");
        Process[] games = Process.GetProcessesByName("rift_x64");
        try
        {
            Require(games.Length == 0, "Capture absent requires zero rift_x64 processes.");
        }
        finally
        {
            DisposeAll(games);
        }
        Require(!ExactProcessStillAlive(oldIdentity), "The exact old game process is still alive.");

        string absentReport = Result("absent-samples.json");
        CommandResult samples = RunReader(
            "absent-samples",
            "sample-position --profile " + Quote(InstalledProfile) +
            " --samples 1 --interval-ms 0 --output " + Quote(absentReport));
        RequirePanelRunning();
        Require(samples.ExitCode == 2 && !File.Exists(absentReport),
            "Absent-game sampler must exit 2 without publishing a report.");
        WriteNewJson(Result("absence-proof.json"), new Dictionary<string, object> {
            { "schemaVersion", 1 },
            { "purpose", "full-game-exit-absence-proof" },
            { "observedAtUtc", UtcNow() },
            { "riftProcessCount", 0 },
            { "oldTarget", oldIdentity.ToDictionary() },
            { "oldExactProcessAlive", false },
            { "samplerExitCode", samples.ExitCode },
            { "samplerReportExists", false },
            { "readerSha256", ReaderSha },
            { "profileSha256", ProfileSha }
        });
        stage = CourierStage.AbsentCaptured;
        AppendStatus("ABSENT: zero game processes; old PID/start rejected; no sample report.");
    }

    private void CaptureAfter()
    {
        RequireStage(CourierStage.AbsentCaptured);
        VerifyInstalledPins();
        RequirePanelRunning();
        Require(oldIdentity != null, "The old process identity is unavailable.");
        afterIdentity = GetExactlyOneGame();
        Require(afterIdentity.ProcessId != oldIdentity.ProcessId ||
                afterIdentity.ProcessStartUtcTicks != oldIdentity.ProcessStartUtcTicks,
            "After capture did not acquire a new process epoch.");
        WriteIdentity("after-identity.json", "after-normal-game-relaunch", afterIdentity);
        AppendIdentity("AFTER", afterIdentity);

        CommandResult samples = RunReader(
            "after-samples",
            "sample-position --profile " + Quote(InstalledProfile) +
            " --samples 3 --interval-ms 500 --output " + Quote(Result("after-samples.json")));
        RequirePanelRunning();
        Require(samples.ExitCode == 0 && File.Exists(Result("after-samples.json")),
            "After sampler did not publish a complete report.");
        RequireSampleIdentity(Result("after-samples.json"), afterIdentity);

        string request = Result("after-pointer.request.json");
        WritePointerRequest(request, afterIdentity);
        CommandResult pointer = RunReader(
            "after-pointer",
            "follow-pointer --request " + Quote(request) +
            " --output " + Quote(Result("after-pointer.json")));
        RequirePanelRunning();
        Require(pointer.ExitCode == 0 && File.Exists(Result("after-pointer.json")),
            "After raw pointer capture did not complete.");

        string staleRequest = Result("old-epoch-pointer.request.json");
        string staleReport = Result("old-epoch-pointer.json");
        WritePointerRequest(staleRequest, oldIdentity);
        CommandResult stale = RunReader(
            "old-epoch-pointer",
            "follow-pointer --request " + Quote(staleRequest) +
            " --output " + Quote(staleReport));
        RequirePanelRunning();
        Require(stale.ExitCode == 2 && !File.Exists(staleReport),
            "Old-epoch pointer request must exit 2 without publishing a report.");
        WriteNewJson(Result("old-epoch-proof.json"), new Dictionary<string, object> {
            { "schemaVersion", 1 },
            { "purpose", "old-game-epoch-rejection" },
            { "observedAtUtc", UtcNow() },
            { "oldTarget", oldIdentity.ToDictionary() },
            { "newTarget", afterIdentity.ToDictionary() },
            { "exitCode", stale.ExitCode },
            { "reportExists", false }
        });
        stage = CourierStage.AfterCaptured;
    }

    private void Package()
    {
        RequireStage(CourierStage.AfterCaptured);
        VerifyInstalledPins();
        Require(afterIdentity != null, "The after identity is unavailable.");
        Require(panelProcess != null, "The panel was not launched by this courier.");
        Require(panelProcess.HasExited, "Close the panel normally after Stop before packaging.");
        Require(panelProcessStartUtcTicks > 0,
            "The exact launched panel process identity was not retained.");
        Require(panelProcess.ExitCode == 0, "The panel did not exit cleanly.");
        Require(!File.Exists(ZipPath) && !File.Exists(ZipPath + ".incomplete"),
            "Evidence ZIP or incomplete package already exists; no overwrite is permitted.");

        List<FileRecord> originals = EnumerateEvidenceFiles(false);
        WriteNewJson(Result("package-manifest.json"), new Dictionary<string, object> {
            { "schemaVersion", 1 },
            { "purpose", "xyz-interface-full-game-restart-gui-evidence" },
            { "createdAtUtc", UtcNow() },
            { "qualification", "same-build validation only; patch recovery deferred" },
            { "transport", "pointer-named strict routes reused only as bounded ZIP transport" },
            { "readerSha256", ReaderSha },
            { "profileSha256", ProfileSha },
            { "gameSha256", GameSha },
            { "oldTarget", oldIdentity.ToDictionary() },
            { "afterTarget", afterIdentity.ToDictionary() },
            { "panelExitCode", panelProcess.ExitCode },
            { "files", originals.Select(delegate(FileRecord record) { return record.ToDictionary(); }).ToArray() }
        });

        List<FileRecord> files = EnumerateEvidenceFiles(true);
        Require(files.Count <= MaximumFiles, "Evidence package exceeds the file-count ceiling.");
        long sourceBytes = files.Sum(delegate(FileRecord file) { return file.ByteLength; });
        Require(sourceBytes < MaximumZipBytes - 65536,
            "Evidence originals are too large for the strict receiver ceiling.");
        VerifyPackageManifestPins(Result("package-manifest.json"), files);
        CreateVerifiedArchive(ZipPath, files, MaximumZipBytes);
        FileInfo zip = new FileInfo(ZipPath);
        Require(zip.Length > 0 && zip.Length < MaximumZipBytes,
            "Evidence ZIP is empty or exceeds the strict 16 MiB receiver ceiling.");
        zipBytes = zip.Length;
        zipSha = HashFile(ZipPath);
        stage = CourierStage.Packaged;
        AppendStatus("PACKAGE READY");
        AppendStatus("ZIP SHA256: " + zipSha);
        AppendStatus("ZIP bytes: " + zipBytes.ToString(CultureInfo.InvariantCulture));
        AppendStatus("AFTER PID: " + afterIdentity.ProcessId.ToString(CultureInfo.InvariantCulture));
        AppendStatus("AFTER start ticks: " + afterIdentity.ProcessStartUtcTicks.ToString(CultureInfo.InvariantCulture));
    }

    internal static void CreateVerifiedArchive(string zipPath, IList<FileRecord> files, long maximumBytes)
    {
        Require(files != null && files.Count > 0 && files.Count <= MaximumFiles,
            "Evidence archive requires a bounded nonempty file list.");
        Require(maximumBytes > 65536 && maximumBytes <= MaximumZipBytes,
            "Evidence archive byte ceiling is invalid.");
        string incomplete = zipPath + ".incomplete";
        Require(!File.Exists(zipPath) && !File.Exists(incomplete),
            "Evidence archive output already exists.");
        Dictionary<string, byte[]> snapshots = new Dictionary<string, byte[]>(StringComparer.Ordinal);
        long total = 0;
        foreach (FileRecord file in files)
        {
            Require(file != null && !snapshots.ContainsKey(file.RelativePath),
                "Evidence archive has a duplicate member.");
            FileInfo sourceInfo = new FileInfo(file.FullPath);
            Require(sourceInfo.Exists && (sourceInfo.Attributes & FileAttributes.ReparsePoint) == 0 &&
                    sourceInfo.Length == file.ByteLength && sourceInfo.Length <= int.MaxValue,
                "Evidence source changed after enumeration: " + file.RelativePath);
            byte[] body = File.ReadAllBytes(file.FullPath);
            Require(body.LongLength == file.ByteLength &&
                    string.Equals(HashBytes(body), file.Sha256, StringComparison.Ordinal),
                "Evidence source bytes changed after enumeration: " + file.RelativePath);
            total += body.LongLength;
            Require(total < maximumBytes - 65536,
                "Evidence originals are too large for the receiver ceiling.");
            snapshots.Add(file.RelativePath, body);
        }
        using (FileStream output = new FileStream(incomplete, FileMode.CreateNew, FileAccess.Write, FileShare.None))
        using (ZipArchive archive = new ZipArchive(output, ZipArchiveMode.Create, false, Encoding.UTF8))
        {
            foreach (FileRecord file in files)
            {
                ZipArchiveEntry entry = archive.CreateEntry(file.RelativePath, CompressionLevel.Optimal);
                using (Stream destination = entry.Open())
                {
                    byte[] body = snapshots[file.RelativePath];
                    destination.Write(body, 0, body.Length);
                }
            }
        }
        FileInfo staged = new FileInfo(incomplete);
        Require(staged.Length > 0 && staged.Length < maximumBytes,
            "Evidence ZIP is empty or exceeds its ceiling.");
        using (FileStream input = new FileStream(incomplete, FileMode.Open, FileAccess.Read, FileShare.Read))
        using (ZipArchive archive = new ZipArchive(input, ZipArchiveMode.Read, false, Encoding.UTF8))
        {
            Require(archive.Entries.Count == snapshots.Count,
                "Evidence ZIP member count differs after creation.");
            HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (ZipArchiveEntry entry in archive.Entries)
            {
                Require(seen.Add(entry.FullName) && snapshots.ContainsKey(entry.FullName),
                    "Evidence ZIP member set differs after creation.");
                byte[] expected = snapshots[entry.FullName];
                Require(entry.Length == expected.LongLength,
                    "Evidence ZIP member length differs after creation.");
                byte[] actual;
                using (Stream source = entry.Open())
                using (MemoryStream copy = new MemoryStream())
                {
                    source.CopyTo(copy);
                    actual = copy.ToArray();
                }
                Require(actual.SequenceEqual(expected) &&
                        string.Equals(HashBytes(actual),
                            files.First(delegate(FileRecord value) {
                                return string.Equals(value.RelativePath, entry.FullName, StringComparison.Ordinal);
                            }).Sha256, StringComparison.Ordinal),
                    "Evidence ZIP member bytes differ after creation.");
            }
        }
        string stagedSha = HashFile(incomplete);
        long stagedBytes = new FileInfo(incomplete).Length;
        File.Move(incomplete, zipPath);
        Require(new FileInfo(zipPath).Length == stagedBytes &&
                string.Equals(HashFile(zipPath), stagedSha, StringComparison.Ordinal),
            "Published evidence ZIP differs from the verified staging archive.");
    }

    private static void VerifyPackageManifestPins(string manifestPath, IList<FileRecord> files)
    {
        JavaScriptSerializer parser = new JavaScriptSerializer();
        Dictionary<string, object> root = parser.DeserializeObject(File.ReadAllText(manifestPath))
            as Dictionary<string, object>;
        Require(root != null && root.ContainsKey("files"),
            "Package manifest file declarations are unavailable.");
        object[] declarations = root["files"] as object[];
        Require(declarations != null, "Package manifest file declarations are invalid.");
        Dictionary<string, FileRecord> actual = new Dictionary<string, FileRecord>(StringComparer.Ordinal);
        foreach (FileRecord file in files)
        {
            if (!string.Equals(file.RelativePath, "package-manifest.json", StringComparison.Ordinal))
                actual.Add(file.RelativePath, file);
        }
        Require(declarations.Length == actual.Count,
            "Package manifest and evidence file sets differ.");
        HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (object item in declarations)
        {
            Dictionary<string, object> declaration = item as Dictionary<string, object>;
            Require(declaration != null && declaration.Count == 3 &&
                    declaration.ContainsKey("path") && declaration.ContainsKey("byteLength") &&
                    declaration.ContainsKey("sha256"),
                "Package manifest contains an invalid file declaration.");
            string path = declaration["path"] as string;
            Require(path != null && seen.Add(path) && actual.ContainsKey(path),
                "Package manifest contains an unknown or duplicate file declaration.");
            FileRecord file = actual[path];
            Require(Convert.ToInt64(declaration["byteLength"], CultureInfo.InvariantCulture) == file.ByteLength &&
                    string.Equals(declaration["sha256"] as string, file.Sha256, StringComparison.Ordinal),
                "Package manifest pin differs from evidence bytes: " + path);
        }
    }

    private void Declare()
    {
        RequireStage(CourierStage.Packaged);
        VerifyInstalledPins();
        VerifyCurrentZip();
        string body = "RR2PTRZIP1|" + zipSha + "|" +
            zipBytes.ToString(CultureInfo.InvariantCulture) + "|" +
            afterIdentity.ProcessId.ToString(CultureInfo.InvariantCulture) + "|" +
            afterIdentity.ProcessStartUtcTicks.ToString(CultureInfo.InvariantCulture) + "|" +
            GameSha + "|" + ReaderSha;
        byte[] bytes = Encoding.ASCII.GetBytes(body);
        HttpWebRequest request = NewRequest(ClaimUrl, "text/plain", bytes.Length);
        using (Stream stream = request.GetRequestStream())
            stream.Write(bytes, 0, bytes.Length);
        int status = GetStatus(request);
        Require(status == 201, "Claim receiver did not return HTTP 201.");
        WriteNewJson(Result("declare-receipt.json"), new Dictionary<string, object> {
            { "schemaVersion", 1 },
            { "purpose", "gui-evidence-package-pointer-protocol-claim" },
            { "protocolReusedForTransportOnly", true },
            { "declaredAtUtc", UtcNow() },
            { "httpStatus", status },
            { "zipSha256", zipSha },
            { "zipByteLength", zipBytes },
            { "afterTarget", afterIdentity.ToDictionary() },
            { "gameSha256", GameSha },
            { "readerSha256", ReaderSha }
        });
        stage = CourierStage.Declared;
        AppendStatus("Declaration accepted. Parent must now replace claim service with upload service.");
    }

    private void Upload()
    {
        RequireStage(CourierStage.Declared);
        VerifyInstalledPins();
        VerifyCurrentZip();
        HttpWebRequest request = NewRequest(UploadUrl, "application/octet-stream", zipBytes);
        using (Stream destination = request.GetRequestStream())
        using (FileStream source = new FileStream(ZipPath, FileMode.Open, FileAccess.Read, FileShare.Read))
            source.CopyTo(destination);
        int status = GetStatus(request);
        Require(status == 201, "Upload receiver did not return HTTP 201.");
        WriteNewJson(Result("upload-receipt.json"), new Dictionary<string, object> {
            { "schemaVersion", 1 },
            { "purpose", "gui-evidence-package-pointer-protocol-upload" },
            { "protocolReusedForTransportOnly", true },
            { "uploadedAtUtc", UtcNow() },
            { "httpStatus", status },
            { "zipSha256", zipSha },
            { "zipByteLength", zipBytes },
            { "afterTarget", afterIdentity.ToDictionary() }
        });
        stage = CourierStage.Uploaded;
        AppendStatus("UPLOAD ACCEPTED: HTTP 201. Host must independently verify received bytes.");
    }

    private static HttpWebRequest NewRequest(string url, string contentType, long contentLength)
    {
        HttpWebRequest request = (HttpWebRequest)WebRequest.Create(url);
        request.Method = "POST";
        request.ContentType = contentType;
        request.ContentLength = contentLength;
        request.Timeout = CommandTimeoutMilliseconds;
        request.ReadWriteTimeout = CommandTimeoutMilliseconds;
        request.AllowAutoRedirect = false;
        request.KeepAlive = false;
        request.Proxy = null;
        return request;
    }

    private static int GetStatus(HttpWebRequest request)
    {
        try
        {
            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
                return (int)response.StatusCode;
        }
        catch (WebException exception)
        {
            HttpWebResponse response = exception.Response as HttpWebResponse;
            if (response == null)
                throw;
            using (response)
                return (int)response.StatusCode;
        }
    }

    private CommandResult RunReader(string label, string arguments)
    {
        VerifyInstalledPins();
        string stdoutPath = Result(label + ".stdout.txt");
        string stderrPath = Result(label + ".stderr.txt");
        string receiptPath = Result(label + ".command.json");
        Require(!File.Exists(stdoutPath) && !File.Exists(stderrPath) && !File.Exists(receiptPath),
            "Command evidence already exists for " + label + ".");

        ProcessStartInfo start = new ProcessStartInfo();
        start.FileName = InstalledReader;
        start.Arguments = arguments;
        start.WorkingDirectory = InstallRoot;
        start.UseShellExecute = false;
        start.CreateNoWindow = true;
        start.RedirectStandardOutput = true;
        start.RedirectStandardError = true;
        DateTime started = DateTime.UtcNow;
        int exitCode = -1;
        bool timedOut = false;
        string stdout;
        string stderr;
        using (Process process = new Process())
        {
            process.StartInfo = start;
            if (!process.Start())
                throw new InvalidOperationException("CLI process did not start.");
            Task<string> stdoutTask = process.StandardOutput.ReadToEndAsync();
            Task<string> stderrTask = process.StandardError.ReadToEndAsync();
            if (!process.WaitForExit(CommandTimeoutMilliseconds))
            {
                timedOut = true;
                process.Kill();
                process.WaitForExit();
            }
            else
            {
                exitCode = process.ExitCode;
            }
            stdout = stdoutTask.GetAwaiter().GetResult();
            stderr = stderrTask.GetAwaiter().GetResult();
        }
        WriteNewText(stdoutPath, stdout);
        WriteNewText(stderrPath, stderr);
        WriteNewJson(receiptPath, new Dictionary<string, object> {
            { "schemaVersion", 1 },
            { "purpose", "bounded-validation-cli-invocation" },
            { "label", label },
            { "startedAtUtc", started.ToString("O", CultureInfo.InvariantCulture) },
            { "completedAtUtc", UtcNow() },
            { "timeoutMilliseconds", CommandTimeoutMilliseconds },
            { "timedOut", timedOut },
            { "killedOwnCliOnly", timedOut },
            { "exitCode", exitCode },
            { "readerSha256", ReaderSha },
            { "argumentsSha256", HashBytes(Encoding.UTF8.GetBytes(arguments)) },
            { "stdoutSha256", HashBytes(Encoding.UTF8.GetBytes(stdout)) },
            { "stderrSha256", HashBytes(Encoding.UTF8.GetBytes(stderr)) }
        });
        if (timedOut)
            throw new TimeoutException("The owned CLI exceeded 20 seconds and was terminated.");
        return new CommandResult(exitCode, stdoutPath, stderrPath);
    }

    private GameIdentity GetExactlyOneGame()
    {
        Process[] games = Process.GetProcessesByName("rift_x64");
        try
        {
            Require(games.Length == 1, "Expected exactly one rift_x64 process; found " +
                games.Length.ToString(CultureInfo.InvariantCulture) + ".");
            Process game = games[0];
            int pid = game.Id;
            long ticks = game.StartTime.ToUniversalTime().Ticks;
            string path = game.MainModule.FileName;
            string sha = HashFile(path);
            Require(string.Equals(sha, GameSha, StringComparison.Ordinal),
                "The game executable SHA differs; patch recovery is deferred.");
            Require(!game.HasExited && game.Id == pid && game.StartTime.ToUniversalTime().Ticks == ticks,
                "Game identity changed during inspection.");
            return new GameIdentity(pid, ticks, path, sha);
        }
        finally
        {
            DisposeAll(games);
        }
    }

    private static bool ExactProcessStillAlive(GameIdentity identity)
    {
        try
        {
            using (Process process = Process.GetProcessById(identity.ProcessId))
                return !process.HasExited &&
                    process.StartTime.ToUniversalTime().Ticks == identity.ProcessStartUtcTicks;
        }
        catch (ArgumentException)
        {
            return false;
        }
    }

    private void WritePointerRequest(string path, GameIdentity identity)
    {
        WriteNewJson(path, new Dictionary<string, object> {
            { "schemaVersion", 1 },
            { "evidenceKind", "native-pointer-follow-request/1" },
            { "target", new Dictionary<string, object> {
                { "processId", identity.ProcessId },
                { "processStartUtcTicks", identity.ProcessStartUtcTicks },
                { "executableSha256", identity.ExecutableSha256 }
            }},
            { "rootRva", "0x32E0200" },
            { "offsets", new string[] { "0x0" } },
            { "terminalByteLength", 816 },
            { "maxDurationMilliseconds", 5000 }
        });
    }

    private void RequireSampleIdentity(string path, GameIdentity expected)
    {
        FileInfo info = new FileInfo(path);
        Require(info.Exists && info.Length > 0 && info.Length <= 8L * 1024L * 1024L,
            "Sampler report size is invalid.");
        Dictionary<string, object> root = serializer.DeserializeObject(File.ReadAllText(path))
            as Dictionary<string, object>;
        Require(root != null, "Sampler report is not a JSON object.");
        Dictionary<string, object> samples = root["samples"] as Dictionary<string, object>;
        Require(samples != null && string.Equals(samples["status"] as string, "complete", StringComparison.Ordinal),
            "Sampler report status is not complete.");
        Require(Convert.ToInt32(samples["requestedSamples"], CultureInfo.InvariantCulture) == 3 &&
                Convert.ToInt32(samples["completedSamples"], CultureInfo.InvariantCulture) == 3,
            "Sampler report did not retain exactly 3 of 3 reads.");
        Dictionary<string, object> identity = samples["identity"] as Dictionary<string, object>;
        Require(identity != null &&
                Convert.ToInt32(identity["processId"], CultureInfo.InvariantCulture) == expected.ProcessId &&
                Convert.ToInt64(identity["processStartUtcTicks"], CultureInfo.InvariantCulture) == expected.ProcessStartUtcTicks &&
                string.Equals(identity["executableSha256"] as string, expected.ExecutableSha256, StringComparison.Ordinal),
            "Sampler report identity differs from the freshly acquired target.");
    }

    private void WriteIdentity(string name, string purpose, GameIdentity identity)
    {
        WriteNewJson(Result(name), new Dictionary<string, object> {
            { "schemaVersion", 1 },
            { "purpose", purpose },
            { "observedAtUtc", UtcNow() },
            { "target", identity.ToDictionary() },
            { "courierSha256", CourierSha() },
            { "readerSha256", ReaderSha },
            { "profileSha256", ProfileSha },
            { "candidateOnly", true }
        });
    }

    private void AppendIdentity(string label, GameIdentity identity)
    {
        AppendStatus(label + " PID: " + identity.ProcessId.ToString(CultureInfo.InvariantCulture));
        AppendStatus(label + " start ticks: " + identity.ProcessStartUtcTicks.ToString(CultureInfo.InvariantCulture));
        AppendStatus(label + " game SHA256: " + identity.ExecutableSha256);
    }

    private List<FileRecord> EnumerateEvidenceFiles(bool includeManifest)
    {
        Require(Directory.Exists(ResultsRoot), "Results directory is unavailable.");
        Require(!IsReparse(ResultsRoot), "Results root is a reparse point.");
        List<FileRecord> result = new List<FileRecord>();
        Stack<string> pending = new Stack<string>();
        pending.Push(ResultsRoot);
        int directoryCount = 0;
        while (pending.Count > 0)
        {
            string current = pending.Pop();
            Require(!IsReparse(current), "Evidence tree contains a reparse directory.");
            directoryCount++;
            Require(directoryCount <= MaximumFiles, "Evidence tree exceeds 2048 directories.");
            foreach (string directory in Directory.GetDirectories(current, "*", SearchOption.TopDirectoryOnly))
            {
                Require(!IsReparse(directory), "Evidence tree contains a reparse directory.");
                pending.Push(directory);
            }
            foreach (string path in Directory.GetFiles(current, "*", SearchOption.TopDirectoryOnly))
            {
                Require(!IsReparse(path), "Evidence tree contains a reparse file.");
                string extension = Path.GetExtension(path).ToLowerInvariant();
                Require(extension == ".json" || extension == ".jsonl" || extension == ".txt",
                    "Evidence tree contains a non-allowlisted file type: " + Path.GetFileName(path));
                string relative = path.Substring(ResultsRoot.Length).TrimStart(Path.DirectorySeparatorChar)
                    .Replace(Path.DirectorySeparatorChar, '/');
                if (!includeManifest && string.Equals(relative, "package-manifest.json", StringComparison.Ordinal))
                    continue;
                FileInfo info = new FileInfo(path);
                result.Add(new FileRecord(path, relative, info.Length, HashFile(path)));
                Require(result.Count <= MaximumFiles, "Evidence tree exceeds 2048 files.");
            }
        }
        result.Sort(delegate(FileRecord left, FileRecord right) {
            return string.CompareOrdinal(left.RelativePath, right.RelativePath);
        });
        return result;
    }

    private void VerifyCurrentZip()
    {
        Require(afterIdentity != null && File.Exists(ZipPath), "Packaged ZIP is unavailable.");
        FileInfo info = new FileInfo(ZipPath);
        Require(info.Length == zipBytes && string.Equals(HashFile(ZipPath), zipSha, StringComparison.Ordinal),
            "Packaged ZIP bytes changed after creation.");
    }

    private void VerifyInstalledPins()
    {
        config.VerifyInstallRootConfinement();
        VerifyPinnedFile(InstalledReader, ReaderBytes, ReaderSha, "installed reader");
        VerifyPinnedFile(InstalledProfile, ProfileBytes, ProfileSha, "installed profile");
    }

    private void RequirePanelRunning()
    {
        Require(panelProcess != null && panelProcessStartUtcTicks > 0 &&
                ProcessMatchesStart(panelProcess, panelProcessStartUtcTicks),
            "The exact Courier-launched panel process is no longer running.");
    }

    internal static bool ProcessMatchesStart(Process process, long expectedStartUtcTicks)
    {
        if (process == null || expectedStartUtcTicks <= 0)
            return false;
        try
        {
            return !process.HasExited &&
                process.StartTime.ToUniversalTime().Ticks == expectedStartUtcTicks;
        }
        catch (InvalidOperationException)
        {
            return false;
        }
        catch (System.ComponentModel.Win32Exception)
        {
            return false;
        }
    }

    private static void VerifyPinnedFile(string path, long bytes, string sha, string label)
    {
        FileInfo info = new FileInfo(path);
        Require(info.Exists && (info.Attributes & FileAttributes.ReparsePoint) == 0,
            label + " is missing or symbolic.");
        Require(info.Length == bytes, label + " byte length differs.");
        Require(string.Equals(HashFile(path), sha, StringComparison.Ordinal), label + " SHA-256 differs.");
    }

    private static void CopyNew(string source, string destination)
    {
        using (FileStream input = new FileStream(source, FileMode.Open, FileAccess.Read, FileShare.Read))
        using (FileStream output = new FileStream(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            input.CopyTo(output);
    }

    private void TryLogAction(string action, bool succeeded, int? exitCode, string error)
    {
        if (!Directory.Exists(ResultsRoot))
            return;
        try
        {
            Dictionary<string, object> entry = new Dictionary<string, object>();
            entry.Add("schemaVersion", 1);
            entry.Add("purpose", "xyz-interface-validation-courier-action");
            entry.Add("utc", UtcNow());
            entry.Add("action", action);
            entry.Add("succeeded", succeeded);
            entry.Add("exitCode", exitCode.HasValue ? (object)exitCode.Value : null);
            entry.Add("error", error);
            entry.Add("courierSha256", CourierSha());
            entry.Add("readerSha256", ReaderSha);
            entry.Add("profileSha256", ProfileSha);
            string line = serializer.Serialize(entry) + Environment.NewLine;
            lock (logGate)
            {
                using (FileStream stream = new FileStream(ActionLog, FileMode.Append, FileAccess.Write, FileShare.Read))
                using (StreamWriter writer = new StreamWriter(stream, new UTF8Encoding(false)))
                    writer.Write(line);
            }
        }
        catch (Exception exception)
        {
            AppendStatus("Action log warning: " + exception.GetType().Name);
        }
    }

    private void WriteNewJson(string path, object value)
    {
        WriteNewText(path, serializer.Serialize(value) + Environment.NewLine);
    }

    private static void WriteNewText(string path, string value)
    {
        using (FileStream stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.Read))
        using (StreamWriter writer = new StreamWriter(stream, new UTF8Encoding(false)))
            writer.Write(value);
    }

    private string CourierSha()
    {
        return HashFile(Assembly.GetExecutingAssembly().Location);
    }

    private static string HashFile(string path)
    {
        using (FileStream stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
        using (SHA256 sha = SHA256.Create())
            return ToHex(sha.ComputeHash(stream));
    }

    private static string HashBytes(byte[] bytes)
    {
        using (SHA256 sha = SHA256.Create())
            return ToHex(sha.ComputeHash(bytes));
    }

    private static string ToHex(byte[] bytes)
    {
        StringBuilder result = new StringBuilder(bytes.Length * 2);
        foreach (byte value in bytes)
            result.Append(value.ToString("X2", CultureInfo.InvariantCulture));
        return result.ToString();
    }

    private static string Quote(string value)
    {
        Require(value.IndexOf('"') < 0 && value.IndexOf('\r') < 0 && value.IndexOf('\n') < 0,
            "Generated path cannot be quoted safely.");
        return "\"" + value + "\"";
    }

    private string Result(string name)
    {
        return Path.Combine(ResultsRoot, name);
    }

    private static string UtcNow()
    {
        return DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture);
    }

    private void RequireStage(CourierStage required)
    {
        Require(stage == required, "Action is out of sequence; current stage is " + stage.ToString() + ".");
    }

    private static void Require(bool condition, string message)
    {
        if (!condition)
            throw new InvalidOperationException(message);
    }

    private static bool IsReparse(string path)
    {
        return (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0;
    }

    private static void DisposeAll(IEnumerable<Process> processes)
    {
        foreach (Process process in processes)
            process.Dispose();
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        if (busy)
        {
            e.Cancel = true;
            AppendStatus("Wait for the bounded action to finish before closing the courier.");
            return;
        }
        base.OnFormClosing(e);
    }
}

internal sealed class CourierConfig
{
    private const int MaximumConfigBytes = 512;
    private const long MaximumReaderBytes = 200L * 1024L * 1024L;
    private const long MaximumProfileBytes = 8L * 1024L;
    private static readonly Regex Wire = new Regex(
        @"\ARR2XYZCOURIER1\|([a-z0-9](?:[a-z0-9-]{0,46}[a-z0-9])?)\|([0-9A-F]{64})\|([1-9][0-9]{0,8})\|([0-9A-F]{64})\|([1-9][0-9]{0,5})\|([0-9A-F]{64})\z",
        RegexOptions.CultureInvariant);
    private static readonly Regex PropertyName = new Regex(
        "\\\"([^\\\"]+)\\\"\\s*:", RegexOptions.CultureInvariant);
    private static readonly HashSet<string> Reserved = new HashSet<string>(StringComparer.OrdinalIgnoreCase) {
        "con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "com5",
        "com6", "com7", "com8", "com9", "lpt1", "lpt2", "lpt3", "lpt4",
        "lpt5", "lpt6", "lpt7", "lpt8", "lpt9"
    };
    private static readonly HashSet<string> ProfileKeys = new HashSet<string>(StringComparer.Ordinal) {
        "schemaVersion", "contractVersion", "fieldId", "executableSha256",
        "rootRva", "xyzOffsets", "qualification", "evidenceReference"
    };

    internal readonly string RunId;
    internal readonly string ReaderSha;
    internal readonly long ReaderBytes;
    internal readonly string ProfileSha;
    internal readonly long ProfileBytes;
    internal readonly string GameSha;
    internal readonly string ConfigSha;
    internal readonly string SourceDirectory;

    internal string InstallRoot { get { return Path.Combine(@"C:\RIFT_TRANSFER\XYZ", RunId); } }
    private string SourceReader { get { return Path.Combine(SourceDirectory, "RiftReader2.Live.exe"); } }
    private string SourceProfile { get { return Path.Combine(SourceDirectory, "position-candidate-profile.json"); } }

    private CourierConfig(string runId, string readerSha, long readerBytes,
        string profileSha, long profileBytes, string gameSha, string configSha,
        string sourceDirectory)
    {
        RunId = runId;
        ReaderSha = readerSha;
        ReaderBytes = readerBytes;
        ProfileSha = profileSha;
        ProfileBytes = profileBytes;
        GameSha = gameSha;
        ConfigSha = configSha;
        SourceDirectory = sourceDirectory;
    }

    internal static CourierConfig Load(string sourceDirectory)
    {
        Require(!string.IsNullOrEmpty(sourceDirectory), "Courier source directory is unavailable.");
        string configPath = Path.Combine(sourceDirectory, "courier-config.txt");
        FileInfo info = new FileInfo(configPath);
        Require(info.Exists && (info.Attributes & FileAttributes.ReparsePoint) == 0,
            "courier-config.txt is missing or symbolic.");
        Require(info.Length > 0 && info.Length <= MaximumConfigBytes,
            "Courier configuration is outside the 512-byte bound.");
        byte[] raw = File.ReadAllBytes(configPath);
        Require(raw.Length == info.Length, "Courier configuration changed while reading.");
        foreach (byte value in raw)
            Require(value <= 0x7F, "Courier configuration must be ASCII.");
        string text = Encoding.ASCII.GetString(raw);
        if (text.EndsWith("\r\n", StringComparison.Ordinal))
            text = text.Substring(0, text.Length - 2);
        else if (text.EndsWith("\n", StringComparison.Ordinal))
            text = text.Substring(0, text.Length - 1);
        Require(text.IndexOf('\r') < 0 && text.IndexOf('\n') < 0,
            "Courier configuration must be one line.");
        Match match = Wire.Match(text);
        Require(match.Success, "Courier configuration wire format is invalid.");
        string runId = match.Groups[1].Value;
        Require(!Reserved.Contains(runId), "Courier run ID is a reserved Windows name.");
        long readerBytes = ParseBounded(match.Groups[3].Value, MaximumReaderBytes, "reader");
        long profileBytes = ParseBounded(match.Groups[5].Value, MaximumProfileBytes, "profile");
        return new CourierConfig(runId, match.Groups[2].Value, readerBytes,
            match.Groups[4].Value, profileBytes, match.Groups[6].Value,
            HashBytes(raw), sourceDirectory);
    }

    internal void VerifySourcePayloads()
    {
        VerifyPlainExistingAncestors(SourceDirectory, "Courier source directory");
        VerifyPinnedFile(SourceReader, ReaderBytes, ReaderSha, "source reader");
        VerifyPinnedFile(SourceProfile, ProfileBytes, ProfileSha, "source profile");
        ValidateProfile(File.ReadAllText(SourceProfile, Encoding.UTF8));
    }

    internal void VerifyInstallRootConfinement()
    {
        string expected = Path.GetFullPath(Path.Combine(@"C:\RIFT_TRANSFER\XYZ", RunId));
        Require(string.Equals(expected, Path.GetFullPath(InstallRoot), StringComparison.OrdinalIgnoreCase),
            "Courier install root escaped the fixed guest directory.");
        DirectoryInfo current = new DirectoryInfo(expected);
        while (current != null)
        {
            if (current.Exists)
                Require((current.Attributes & FileAttributes.ReparsePoint) == 0,
                    "Courier install-root ancestor is a reparse point.");
            else
                Require(!File.Exists(current.FullName),
                    "Courier install-root ancestor is an existing file.");
            current = current.Parent;
        }
    }

    private static void VerifyPlainExistingAncestors(string path, string label)
    {
        DirectoryInfo current = new DirectoryInfo(Path.GetFullPath(path));
        while (current != null)
        {
            if (current.Exists)
                Require((current.Attributes & FileAttributes.ReparsePoint) == 0,
                    label + " has a reparse ancestor.");
            else
                Require(!File.Exists(current.FullName), label + " has a file ancestor.");
            current = current.Parent;
        }
    }

    private void ValidateProfile(string text)
    {
        MatchCollection names = PropertyName.Matches(text);
        Require(names.Count == ProfileKeys.Count, "Position profile has unexpected or duplicate properties.");
        HashSet<string> found = new HashSet<string>(StringComparer.Ordinal);
        foreach (Match name in names)
            Require(ProfileKeys.Contains(name.Groups[1].Value) && found.Add(name.Groups[1].Value),
                "Position profile has unexpected or duplicate properties.");
        JavaScriptSerializer serializer = new JavaScriptSerializer();
        Dictionary<string, object> profile = serializer.DeserializeObject(text) as Dictionary<string, object>;
        Require(profile != null && profile.Count == ProfileKeys.Count,
            "Position profile must be an exact JSON object.");
        foreach (string key in ProfileKeys)
            Require(profile.ContainsKey(key), "Position profile is missing " + key + ".");
        Require(profile["schemaVersion"] != null && profile["schemaVersion"].GetType() == typeof(int) &&
                Convert.ToInt32(profile["schemaVersion"], CultureInfo.InvariantCulture) == 1 &&
                string.Equals(profile["contractVersion"] as string, "native-position-profile/1", StringComparison.Ordinal) &&
                string.Equals(profile["fieldId"] as string, "player.position.xyz", StringComparison.Ordinal) &&
                string.Equals(profile["qualification"] as string, "candidate-only", StringComparison.Ordinal) &&
                string.Equals(profile["executableSha256"] as string, GameSha, StringComparison.Ordinal),
            "Position profile contract or game-build identity differs.");
        string root = profile["rootRva"] as string;
        object[] offsets = profile["xyzOffsets"] as object[];
        Require(string.Equals(root, "0x32E0200", StringComparison.Ordinal) &&
                offsets != null && offsets.Length == 3,
            "Position profile must use the supported XYZ root recipe.");
        long previous = -1;
        foreach (object item in offsets)
        {
            string value = item as string;
            Require(value != null && Regex.IsMatch(value, @"\A0x[0-9A-F]+\z", RegexOptions.CultureInvariant),
                "Position profile XYZ offset is invalid.");
            long parsed = long.Parse(value.Substring(2), NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture);
            Require(parsed > previous && parsed <= 4092 && parsed % 4 == 0,
                "Position profile XYZ offsets must be increasing aligned float32 fields.");
            previous = parsed;
        }
        Require(string.Equals(offsets[0] as string, "0x320", StringComparison.Ordinal) &&
                string.Equals(offsets[1] as string, "0x324", StringComparison.Ordinal) &&
                string.Equals(offsets[2] as string, "0x328", StringComparison.Ordinal),
            "Position profile must use the supported XYZ offset recipe.");
        string reference = profile["evidenceReference"] as string;
        Require(reference != null && reference.Length > 0 && reference.Length <= 256 &&
                string.Equals(reference, reference.Trim(), StringComparison.Ordinal),
            "Position profile evidence reference is invalid.");
    }

    private static long ParseBounded(string value, long maximum, string label)
    {
        long parsed;
        Require(long.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out parsed) &&
                parsed > 0 && parsed <= maximum,
            "Courier " + label + " byte length is invalid.");
        return parsed;
    }

    private static void VerifyPinnedFile(string path, long expectedBytes, string expectedSha, string label)
    {
        FileInfo info = new FileInfo(path);
        Require(info.Exists && (info.Attributes & FileAttributes.ReparsePoint) == 0,
            label + " is missing or symbolic.");
        Require(info.Length == expectedBytes, label + " byte length differs.");
        using (FileStream stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
        using (SHA256 algorithm = SHA256.Create())
            Require(string.Equals(ToHex(algorithm.ComputeHash(stream)), expectedSha, StringComparison.Ordinal),
                label + " SHA-256 differs.");
    }

    private static string ToHex(byte[] bytes)
    {
        StringBuilder value = new StringBuilder(bytes.Length * 2);
        foreach (byte item in bytes)
            value.Append(item.ToString("X2", CultureInfo.InvariantCulture));
        return value.ToString();
    }

    private static string HashBytes(byte[] bytes)
    {
        using (SHA256 algorithm = SHA256.Create())
            return ToHex(algorithm.ComputeHash(bytes));
    }

    private static void Require(bool condition, string message)
    {
        if (!condition)
            throw new InvalidOperationException(message);
    }
}

internal enum CourierStage
{
    New,
    Installed,
    BeforeCaptured,
    PanelOpened,
    AbsentCaptured,
    AfterCaptured,
    Packaged,
    Declared,
    Uploaded
}

internal sealed class GameIdentity
{
    internal readonly int ProcessId;
    internal readonly long ProcessStartUtcTicks;
    internal readonly string ExecutablePath;
    internal readonly string ExecutableSha256;

    internal GameIdentity(int processId, long processStartUtcTicks, string executablePath, string executableSha256)
    {
        ProcessId = processId;
        ProcessStartUtcTicks = processStartUtcTicks;
        ExecutablePath = executablePath;
        ExecutableSha256 = executableSha256;
    }

    internal Dictionary<string, object> ToDictionary()
    {
        return new Dictionary<string, object> {
            { "processId", ProcessId },
            { "processStartUtcTicks", ProcessStartUtcTicks },
            { "executablePath", ExecutablePath },
            { "executableSha256", ExecutableSha256 }
        };
    }
}

internal sealed class CommandResult
{
    internal readonly int ExitCode;
    internal readonly string StdoutPath;
    internal readonly string StderrPath;

    internal CommandResult(int exitCode, string stdoutPath, string stderrPath)
    {
        ExitCode = exitCode;
        StdoutPath = stdoutPath;
        StderrPath = stderrPath;
    }
}

internal sealed class FileRecord
{
    internal readonly string FullPath;
    internal readonly string RelativePath;
    internal readonly long ByteLength;
    internal readonly string Sha256;

    internal FileRecord(string fullPath, string relativePath, long byteLength, string sha256)
    {
        FullPath = fullPath;
        RelativePath = relativePath;
        ByteLength = byteLength;
        Sha256 = sha256;
    }

    internal Dictionary<string, object> ToDictionary()
    {
        return new Dictionary<string, object> {
            { "path", RelativePath },
            { "byteLength", ByteLength },
            { "sha256", Sha256 }
        };
    }
}
