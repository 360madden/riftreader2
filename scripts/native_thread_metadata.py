"""Build the bounded read-only thread metadata console executable on Windows."""
from pathlib import Path
import base64
import subprocess


def build_thread_metadata_executable(output_path: Path) -> Path:
    output_path = Path(output_path).resolve()
    if output_path.suffix.lower() != '.exe':
        raise ValueError('output must be an .exe path')
    source = output_path.with_suffix('.cs')
    # CreateNew prevents confusing a prior executable or source with this build.
    with source.open('x', encoding='utf-8') as f:
        f.write(_SOURCE)
    def literal(path):
        return "'" + str(path).replace("'", "''") + "'"
    command = f"Add-Type -Path {literal(source)} -OutputAssembly {literal(output_path)} -OutputType ConsoleApplication"
    encoded = base64.b64encode(command.encode('utf-16le')).decode('ascii')
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                   check=True, capture_output=True, timeout=60)
    return output_path


_SOURCE = r'''
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

class ThreadMetadata {
 [StructLayout(LayoutKind.Sequential)] struct ClientId { public IntPtr Process, Thread; }
 [StructLayout(LayoutKind.Sequential)] struct Tbi { public int ExitStatus; public IntPtr Teb; public ClientId Client; public UIntPtr Affinity; public int Priority, BasePriority; }
 [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint access, bool inherit, uint id);
 [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenThread(uint access, bool inherit, uint id);
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
 [DllImport("kernel32.dll", SetLastError=true)] static extern bool IsWow64Process(IntPtr h, out bool wow);
 [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetThreadTimes(IntPtr h, out long creation, out long exit, out long kernel, out long user);
 [DllImport("ntdll.dll")] static extern int NtQueryInformationThread(IntPtr h, int cls, out Tbi info, int length, out int returned);
 static string Q(string s) { var b = new StringBuilder("\""); foreach(char c in s) { if(c=='\\' || c=='\"') { b.Append('\\'); b.Append(c); } else if(c < 32) b.AppendFormat("\\u{0:X4}", (int)c); else b.Append(c); } return b.Append('"').ToString(); }
 static Process Epoch(int pid, long ticks, string sha, string image) {
  Process p = Process.GetProcessById(pid);
  string path = p.MainModule.FileName;
  IntPtr h = OpenProcess(0x1000, false, (uint)pid);
  if(h == IntPtr.Zero) throw new Exception("Cannot query target architecture");
  try { bool wow; if(!IsWow64Process(h, out wow) || wow) throw new Exception("Target must be x64"); } finally { CloseHandle(h); }
  string hash; using(var f = File.OpenRead(path)) using(var alg = SHA256.Create()) hash = BitConverter.ToString(alg.ComputeHash(f)).Replace("-", "");
  if(p.StartTime.ToUniversalTime().Ticks != ticks || !String.Equals(path, image, StringComparison.OrdinalIgnoreCase) || !String.Equals(hash, sha, StringComparison.OrdinalIgnoreCase)) throw new Exception("Target identity mismatch");
  return p;
 }
 static int Main(string[] a) {
  try {
   if(a.Length != 5 || !Environment.Is64BitProcess || !Environment.Is64BitOperatingSystem) throw new Exception("Expected x64 and PID startTicks SHA256 imagePath outputPath");
   int pid; long ticks;
   if(!Int32.TryParse(a[0], out pid) || pid <= 0 || !Int64.TryParse(a[1], out ticks) || ticks <= 0 || a[2].Length != 64 || !System.Text.RegularExpressions.Regex.IsMatch(a[2], "^[0-9a-fA-F]{64}$") || !Path.IsPathRooted(a[3]) || !Path.IsPathRooted(a[4])) throw new Exception("Invalid arguments");
   var p = Epoch(pid,ticks,a[2],a[3]); var threads = p.Threads;
   var rows = new List<string>(); var failures = new List<string>(); int attempted = 0;
   foreach(ProcessThread t in threads) {
    if(attempted == 256) break; attempted++;
    IntPtr h = OpenThread(0x40,false,(uint)t.Id);
    if(h == IntPtr.Zero) { failures.Add(t.Id.ToString()); continue; }
    try {
     Tbi info; int returned; long created, exited, kernel, user;
     int status = NtQueryInformationThread(h,0,out info,Marshal.SizeOf(typeof(Tbi)),out returned);
     long teb = info.Teb.ToInt64();
     if(status != 0 || info.ExitStatus != 259 || info.Client.Process.ToInt64() != pid || info.Client.Thread.ToInt64() != t.Id || teb <= 0 || teb > 0x00007FFFFFFFFFFF || !GetThreadTimes(h,out created,out exited,out kernel,out user) || created <= 0) { failures.Add(t.Id.ToString()); continue; }
     rows.Add("{\"threadId\":"+t.Id+",\"startUtcTicks\":"+Q((created+504911232000000000L).ToString())+",\"tebAddress\":"+Q("0x"+teb.ToString("X"))+"}");
    } finally { CloseHandle(h); }
   }
   using(Epoch(pid,ticks,a[2],a[3])) {} p.Dispose();
   string json = "{\"processId\":"+pid+",\"processStartUtcTicks\":"+Q(ticks.ToString())+",\"executablePath\":"+Q(a[3])+",\"executableSha256\":"+Q(a[2].ToUpperInvariant())+",\"threads\":["+String.Join(",",rows.ToArray())+"],\"enumerated\":"+threads.Count+",\"attempted\":"+attempted+",\"failed\":"+failures.Count+",\"failedThreadIds\":["+String.Join(",",failures.ToArray())+"],\"partial\":"+((failures.Count>0 || threads.Count>256)?"true":"false")+"}";
   byte[] bytes = new UTF8Encoding(false).GetBytes(json);
   using(var f = new FileStream(a[4], FileMode.CreateNew, FileAccess.Write, FileShare.None)) f.Write(bytes,0,bytes.Length);
   return 0;
  } catch(Exception e) { Console.Error.WriteLine(e.Message); return 1; }
 }
}
'''
