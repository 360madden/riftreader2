"""Bounded synthetic vmrun/HTTP transfer comparison on the existing VMnet8 network.

Only random test bytes are served. No game input, network settings, credentials
in URLs, directory listing, arbitrary paths, or persistent listener.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import statistics
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_xyz_workflow as w
from scripts.vmware_guest_session import GuestSession
from scripts.serve_guest_native_scout import BIND, GUEST, PORT


class TransferHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup(); self.connection.settimeout(5)

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.transfer(False)

    def do_POST(self):
        self.transfer(True)

    def transfer(self, upload):
        key = ('POST' if upload else 'GET', self.path)
        with self.server.lock:
            item = self.server.routes.pop(key, None) if self.client_address[0] == GUEST else None
        if item is None:
            self.send_error(404); return
        data = item['data']; started = time.monotonic()
        if upload:
            if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Length') != str(len(data)):
                self.send_error(400); return
            received = bytearray()
            while len(received) < len(data):
                remaining = 30 - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('bounded upload expired')
                self.connection.settimeout(min(5, remaining))
                chunk = self.rfile.read(min(65536, len(data) - len(received)))
                if not chunk:
                    raise EOFError('short upload')
                received.extend(chunk)
            if received != data:
                self.send_error(422); return
            body = item['sha256'].encode('ascii')
        else:
            body = data
        self.send_response(200); self.send_header('Content-Length', str(len(body)))
        self.send_header('Content-Type', 'application/octet-stream'); self.send_header('Cache-Control', 'no-store')
        self.end_headers(); self.wfile.write(body)
        with self.server.lock:
            self.server.completed.append(dict(method=key[0], case=item['case'], bytes=len(data), verified=upload))


def run(config, output, repetitions=3, sizes=(512*1024, 8*1024*1024), include_http=True):
    if repetitions not in (1, 2, 3) or not sizes or any(type(n) is not int or not 1024 <= n <= 16*1024*1024 for n in sizes):
        raise ValueError('Benchmark bounds exceeded')
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    cfg, profile, _ = w.read_config(Path(config)); guard = w.HostGuard(cfg, profile, output)
    w.save(output/'before.json', w.sanitize(guard.status()))
    server = None
    if include_http:
        server = ThreadingHTTPServer((BIND, PORT), TransferHandler)
        server.daemon_threads = True; server.lock = threading.Lock(); server.routes = {}; server.completed = []
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
    guest_root = r'C:\RIFT_TRANSFER\RiftReader2Control\benchmark-' + uuid.uuid4().hex[:12]
    host_rows = []
    try:
        with GuestSession(Path(cfg['vmrun']), guard.native.vmx, guard.check) as guest:
            guest.powershell("$ErrorActionPreference='Stop';[IO.Directory]::CreateDirectory('" + guest_root + "')|Out-Null")
            for size in sizes:
                data = secrets.token_bytes(size); sha = w.digest(data); path = output/f'payload-{size}.bin'; path.write_bytes(data)
                for rep in range(1, repetitions + 1):
                    case = f'{size}-{rep}'; remote = guest_root+'\\'+case+'.bin'
                    guard.check()
                    start = time.perf_counter(); guest.run('copyFileFromHostToGuest', str(path.resolve()), remote, timeout=120)
                    host_rows.append(dict(method='vmrun', direction='host-to-guest', size=size, repetition=rep, seconds=time.perf_counter()-start))
                    start = time.perf_counter(); returned = guest.copy_from_guest(remote, output/(case+'-returned.bin'), timeout=120)
                    elapsed = time.perf_counter()-start
                    w.require(w.digest(returned.read_bytes()) == sha, 'VMware round-trip hash mismatch')
                    host_rows.append(dict(method='vmrun', direction='guest-to-host', size=size, repetition=rep, seconds=elapsed))
                    w.save(output/(case+'-vmrun-verified.json'), dict(bytes=size, sha256=sha,
                        roundTripVerified=True, credentialSource=guest.credential_source))
                    if not include_http:
                        print(json.dumps(dict(completedCase=case, rows=host_rows[-2:])), flush=True)
                        continue
                    down = '/download/'+uuid.uuid4().hex; up = '/upload/'+uuid.uuid4().hex
                    with server.lock:
                        for method, route in [('GET', down), ('POST', up)]:
                            server.routes[(method, route)] = dict(data=data, sha256=sha, case=case)
                    script = r'''$ErrorActionPreference='Stop'
try {
$source='__SOURCE__';$download='__DEST__'
function Hash($p){$s=[IO.File]::OpenRead($p);$h=[Security.Cryptography.SHA256]::Create();try{[BitConverter]::ToString($h.ComputeHash($s)).Replace('-','')}finally{$s.Dispose();$h.Dispose()}}
if((Hash $source) -ne '__SHA__'){throw 'vmrun-guest-hash-mismatch'}
$web=[Net.WebClient]::new();$web.Proxy=$null
try{
 $clock=[Diagnostics.Stopwatch]::StartNew();$web.DownloadFile('__GET__',$download);$clock.Stop();$down=$clock.Elapsed.TotalSeconds
 if((Hash $download) -ne '__SHA__'){throw 'http-download-hash-mismatch'}
 $clock.Restart();$reply=$web.UploadData('__POST__','POST',[IO.File]::ReadAllBytes($source));$clock.Stop();$up=$clock.Elapsed.TotalSeconds
 if([Text.Encoding]::ASCII.GetString($reply) -ne '__SHA__'){throw 'http-upload-hash-mismatch'}
 $rows=@(@{method='http';direction='host-to-guest';size=__SIZE__;repetition=__REP__;seconds=$down},@{method='http';direction='guest-to-host';size=__SIZE__;repetition=__REP__;seconds=$up})
 [IO.File]::WriteAllText('__RESULT__',($rows|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
}finally{$web.Dispose()}
}catch{[IO.File]::WriteAllText('__RESULT__',(@{error=$_.Exception.Message;line=$_.InvocationInfo.ScriptLineNumber}|ConvertTo-Json));throw}
'''.replace('__SOURCE__',remote).replace('__DEST__',remote+'.http').replace('__SHA__',sha).replace('__GET__',f'http://{BIND}:{PORT}'+down).replace('__POST__',f'http://{BIND}:{PORT}'+up).replace('__SIZE__',str(size)).replace('__REP__',str(rep)).replace('__RESULT__',guest_root+'\\'+case+'.json')
                    # Stage the script: large encoded command lines have crashed this vmrun build.
                    script_path = output / (case + '.ps1'); script_path.write_text(script)
                    script_remote = guest_root + '\\' + case + '.ps1'
                    guest.run('copyFileFromHostToGuest', str(script_path.resolve()), script_remote)
                    script_sha = w.digest(script_path.read_bytes())
                    command = ("$ErrorActionPreference='Stop';$p='" + script_remote +
                        "';if([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([IO.File]::ReadAllBytes($p))).Replace('-','') -ne '" +
                        script_sha + "'){throw 'script-hash-mismatch'};& ([scriptblock]::Create([IO.File]::ReadAllText($p)))")
                    start = time.perf_counter()
                    try:
                        guest.powershell(command, timeout=90)
                    except Exception:
                        guest.copy_from_guest(guest_root+'\\'+case+'.json', output/(case+'-error.json'))
                        raise
                    pipeline = time.perf_counter()-start
                    guest.copy_from_guest(guest_root+'\\'+case+'.json', output/(case+'.json'))
                    http_rows = w.load(output/(case+'.json'))
                    host_rows.extend(http_rows)
                    w.save(output/(case+'-verified.json'),dict(bytes=size, sha256=sha, verifiedBothDirections=True,
                        httpPairIncludingGuestProcessSeconds=pipeline, credentialSource=guest.credential_source))
                    print(json.dumps(dict(completedCase=case, rows=host_rows[-4:])), flush=True)
    finally:
        if server is not None:
            server.shutdown(); server.server_close(); worker.join(timeout=5)
    if include_http:
        w.require(len(server.completed) == len(sizes)*repetitions*2, 'Incomplete HTTP benchmark')
    medians = []
    for size in sizes:
        for direction in ('host-to-guest','guest-to-host'):
            for method in (('vmrun','http') if include_http else ('vmrun',)):
                values = [r['seconds'] for r in host_rows if r['size']==size and r['direction']==direction and r['method']==method]
                median = statistics.median(values)
                medians.append(dict(size=size, direction=direction, method=method, medianSeconds=median, mibPerSecond=size/1048576/median))
    result = dict(rows=host_rows, medians=medians, verified=True, networkSettingsChanged=False,
        timingScope='vmrun: host command wall time including process/identity overhead; HTTP: guest file+network time. Per-case records also retain HTTP pair including guest process overhead.',
        repetitions=repetitions, guestDirectory=guest_root, listenerClosed=True, httpCompared=include_http)
    w.save(output/'results.json',result);w.save(output/'after.json',w.sanitize(guard.status()))
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'artifacts/xyz-workflow.json')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repetitions',type=int,default=3)
    parser.add_argument('--skip-http', action='store_true', help='Measure only the VMware Tools path; open no network listener')
    args=parser.parse_args();result=run(args.config,args.output,args.repetitions,include_http=not args.skip_http)
    print(json.dumps(dict(medians=result['medians'],verified=result['verified'])),flush=True)
