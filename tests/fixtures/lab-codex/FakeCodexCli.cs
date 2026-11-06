using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;
using System.Reflection;

[assembly: AssemblyVersion("0.165.0.0")]
[assembly: AssemblyFileVersion("0.165.0.0")]

internal static class FakeCodexCli
{
    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "--version")
        {
            Console.WriteLine("codex-cli 0.165.0-fake");
            return 0;
        }
        if (args.Length == 2 && args[0] == "login" && args[1] == "status")
        {
            Console.WriteLine("Logged in using ChatGPT");
            return 0;
        }
        if (args.Length == 2 && args[0] == "--owned-child")
        {
            File.WriteAllText(args[1], Process.GetCurrentProcess().Id.ToString());
            Thread.Sleep(Timeout.Infinite);
            return 0;
        }

        int execIndex = Array.IndexOf(args, "exec");
        int outputIndex = Array.IndexOf(args, "--output-last-message");
        if (execIndex < 0 || outputIndex < 0 || outputIndex + 1 >= args.Length)
        {
            Console.Error.WriteLine("fake-cli-unrecognized-arguments");
            return 64;
        }

        string output = Path.GetFullPath(args[outputIndex + 1]);
        string jobDirectory = Path.GetDirectoryName(output);
        if (String.IsNullOrEmpty(jobDirectory))
        {
            return 65;
        }
        File.WriteAllText(Path.Combine(jobDirectory, "fake-cli.pid"),
                          Process.GetCurrentProcess().Id.ToString());
        string task = Console.In.ReadToEnd();

        if (task.Contains("MODE_HANG"))
        {
            string childPid = Path.Combine(jobDirectory, "fake-child.pid");
            ProcessStartInfo start = new ProcessStartInfo();
            start.FileName = Process.GetCurrentProcess().MainModule.FileName;
            start.Arguments = "--owned-child " + Quote(childPid);
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            Process.Start(start);
            Console.Error.WriteLine("DO_NOT_REPORT_STDERR_SENTINEL");
            Thread.Sleep(Timeout.Infinite);
            return 0;
        }
        if (task.Contains("MODE_NONZERO"))
        {
            Console.Error.WriteLine("DO_NOT_REPORT_STDERR_SENTINEL");
            return 23;
        }
        if (task.Contains("MODE_INVALID_JSON"))
        {
            File.WriteAllText(output, "{not-json", new UTF8Encoding(false));
            return 0;
        }

        int hostTask = task.IndexOf("HOST TASK:\n", StringComparison.Ordinal);
        int markerLength = "HOST TASK:\n".Length;
        if (hostTask < 0)
        {
            hostTask = task.IndexOf("HOST TASK:\r\n", StringComparison.Ordinal);
            markerLength = "HOST TASK:\r\n".Length;
        }
        if (hostTask >= 0)
        {
            task = task.Substring(hostTask + markerLength);
        }
        File.WriteAllText(output, task.Trim(), new UTF8Encoding(false));
        return 0;
    }
}
