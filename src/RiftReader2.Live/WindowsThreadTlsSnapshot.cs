using System.Diagnostics;
using System.Runtime.InteropServices;

namespace RiftReader2.Live;

internal sealed record NativeThreadEpoch(int Id, long Created, ulong Teb);
internal static class WindowsThreadTlsSnapshot
{
    [StructLayout(LayoutKind.Sequential)] private struct ClientId { public IntPtr Process, Thread; }
    [StructLayout(LayoutKind.Sequential)] private struct Tbi { public int ExitStatus; public IntPtr Teb; public ClientId Client; public UIntPtr Affinity; public int Priority, BasePriority; }
    [DllImport("kernel32.dll", SetLastError = true)] private static extern IntPtr OpenThread(uint access, bool inherit, uint id);
    [DllImport("kernel32.dll")] private static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool GetThreadTimes(IntPtr handle, out long created, out long exit, out long kernel, out long user);
    [DllImport("ntdll.dll")] private static extern int NtQueryInformationThread(IntPtr handle, int cls, out Tbi info, int length, out int returned);
    internal static IReadOnlyList<NativeThreadEpoch> Capture(int pid)
    {
        using var process = Process.GetProcessById(pid);
        var threads = process.Threads;
        if (threads.Count is < 1 or > 256) throw new InvalidDataException("Thread enumeration outside bound.");
        var result = new List<NativeThreadEpoch>();
        foreach (ProcessThread thread in threads)
        {
            var id = thread.Id; var handle = OpenThread(0x40, false, (uint)id);
            if (handle == IntPtr.Zero) throw new InvalidDataException("Cannot query every target thread.");
            try
            {
                if (NtQueryInformationThread(handle, 0, out var info, Marshal.SizeOf<Tbi>(), out _) != 0 || info.ExitStatus != 259 ||
                    info.Client.Process.ToInt64() != pid || info.Client.Thread.ToInt64() != id ||
                    !GetThreadTimes(handle, out var created, out _, out _, out _) || created <= 0)
                    throw new InvalidDataException("Thread epoch query failed.");
                var teb = CurrentBuildPlayerLookup.Pointer((ulong)info.Teb.ToInt64(), 0x1788);
                result.Add(new(id, created, teb));
            }
            finally { CloseHandle(handle); thread.Dispose(); }
        }
        if (result.Select(x => x.Id).Distinct().Count() != result.Count || result.Select(x => x.Teb).Distinct().Count() != result.Count)
            throw new InvalidDataException("Duplicate thread identity.");
        return result.OrderBy(x => x.Id).ToArray();
    }
}
