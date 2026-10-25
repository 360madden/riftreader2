#!/usr/bin/env node
// Independent local-browser smoke for a previously exported discovery-compilation/1 JSON.
// No npm dependencies, remote service, RIFT process, or VMware interaction.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath, pathToFileURL } from "node:url";

const repo = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const html = join(repo, "scripts", "discovery_explorer.html");
const compilationPath = resolve(repo, process.argv[2] || "artifacts/discovery-preview-20261024-01.json");
const browsers = process.platform === "win32"
  ? ["C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
     "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"]
  : ["/usr/bin/google-chrome", "/usr/bin/chromium"];
const executable = browsers.find(existsSync);

function need(condition, message) {
  if (!condition) throw Error(message);
}
async function until(task, label, ms = 12000) {
  const end = Date.now() + ms;
  let lastError = null;
  while (Date.now() < end) {
    try {
      const result = await task();
      if (result) return result;
    } catch (error) { lastError = error; }
    await delay(100);
  }
  throw Error("Timed out: " + label + (lastError ? ": " + lastError.message : ""));
}

async function run() {
  need(executable, "Chrome/Edge unavailable; install a local Chromium browser.");
  need(existsSync(html), "Missing scripts/discovery_explorer.html.");
  need(existsSync(compilationPath),
    "Missing compilation JSON; run the synthetic export in docs/reference/discovery-compilation.md first.");
  const expected = JSON.parse(readFileSync(compilationPath, "utf8"));
  need(expected.contractVersion === "discovery-compilation/1" && Array.isArray(expected.records),
    "Input must be discovery-compilation/1 JSON.");

  const temp = mkdtempSync(join(tmpdir(), "rr2-browser-smoke-"));
  const profile = join(temp, "browser-profile");
  const downloadDir = join(temp, "downloads");
  mkdirSync(downloadDir);
  let processHandle = null;
  let socket = null;
  try {
    processHandle = spawn(executable, [
      "--headless=new", "--disable-gpu", "--disable-background-networking",
      "--no-first-run", "--no-default-browser-check", "--no-proxy-server",
      "--remote-debugging-port=0", "--remote-allow-origins=*",
      "--user-data-dir=" + profile, "about:blank"
    ], { stdio: "ignore", windowsHide: true });
    const port = await until(() => {
      if (processHandle.exitCode !== null) throw Error("Browser exited " + processHandle.exitCode);
      const portFile = join(profile, "DevToolsActivePort");
      return existsSync(portFile) ? Number(readFileSync(portFile, "utf8").split(/\r?\n/)[0]) : null;
    }, "browser DevTools startup");
    const target = await until(async () => {
      const response = await fetch("http://127.0.0.1:" + port + "/json/list");
      const entries = await response.json();
      return entries.find(t => t.type === "page" && t.webSocketDebuggerUrl);
    }, "browser page target");

    socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((ok, fail) => {
      socket.addEventListener("open", ok, { once: true });
      socket.addEventListener("error", fail, { once: true });
    });
    let nextId = 0;
    const waiting = new Map();
    socket.addEventListener("message", event => {
      const message = JSON.parse(event.data);
      if (!waiting.has(message.id)) return;
      const pending = waiting.get(message.id);
      waiting.delete(message.id);
      clearTimeout(pending.timer);
      if (message.error) pending.reject(Error(JSON.stringify(message.error)));
      else pending.resolve(message.result || {});
    });
    const call = (method, params = {}) => new Promise((ok, fail) => {
      const id = ++nextId;
      const timer = setTimeout(() => {
        waiting.delete(id); fail(Error("DevTools call timeout: " + method));
      }, 8000);
      waiting.set(id, { resolve: ok, reject: fail, timer });
      socket.send(JSON.stringify({ id, method, params }));
    });
    const evaluate = async expression => {
      const response = await call("Runtime.evaluate",
        { expression, returnByValue: true, awaitPromise: true });
      if (response.exceptionDetails)
        throw Error("Browser script error: " + JSON.stringify(response.exceptionDetails));
      return response.result?.value;
    };
    await call("Page.enable");
    await call("Runtime.enable");
    await call("Page.navigate", { url: pathToFileURL(html).href });
    await until(() => evaluate('document.readyState === "complete" && !!document.getElementById("file")'),
      "local explorer page load");
    await call("Page.setDownloadBehavior", { behavior: "allow", downloadPath: downloadDir });

    const dom = await call("DOM.getDocument");
    const file = await call("DOM.querySelector", { nodeId: dom.root.nodeId, selector: "#file" });
    need(file.nodeId, "Missing local file picker.");
    await call("DOM.setFileInputFiles", { nodeId: file.nodeId, files: [compilationPath] });
    await until(async () => (await evaluate('document.getElementById("loadStatus").textContent'))
      .startsWith("Loaded "), "compilation file picker");
    const total = await evaluate('Number(document.getElementById("totalCount").textContent)');
    assert.equal(total, expected.records.length, "compilation record count");

    const selectedStatus = expected.records.find(r => r.status)?.status;
    need(selectedStatus, "Need at least one discovery record.");
    const matchingStatus = expected.records.filter(r => r.status === selectedStatus).length;
    const filteredStatus = await evaluate(`(() => {
      const el=document.getElementById("status");
      el.value=${JSON.stringify(selectedStatus)};
      el.dispatchEvent(new Event("change",{bubbles:true}));
      return Number(document.getElementById("visibleCount").textContent);
    })()`);
    assert.equal(filteredStatus, matchingStatus, "status filter count");

    const sourcePin = expected.records[0].evidenceSha256;
    need(sourcePin?.length === 64, "Expected SHA-256 on first record.");
    const matchingPin = expected.records.filter(r => r.evidenceSha256 === sourcePin).length;
    const filteredPin = await evaluate(`(() => {
      const status=document.getElementById("status");
      status.value="";status.dispatchEvent(new Event("change",{bubbles:true}));
      const search=document.getElementById("search");
      search.value=${JSON.stringify(sourcePin)};
      search.dispatchEvent(new Event("input",{bubbles:true}));
      return Number(document.getElementById("visibleCount").textContent);
    })()`);
    assert.equal(filteredPin, matchingPin, "evidence hash search count");

    await evaluate('document.querySelector("thead [data-sort=observedAtUtc]").click()');
    const sorted = await evaluate('document.querySelector("thead [data-sort=observedAtUtc]").parentElement.getAttribute("aria-sort")');
    assert.equal(sorted, "ascending", "time sort indicator");

    await evaluate('document.getElementById("csv").click()');
    const csvPath = join(downloadDir, "riftreader2-filtered.csv");
    await until(() => existsSync(csvPath) &&
      !readdirSync(downloadDir).some(name => name.endsWith(".crdownload")), "CSV download");
    const csvText = readFileSync(csvPath, "utf8");
    assert.equal(csvText.trimEnd().split("\n").length, 1 + matchingPin, "CSV selected row count");
    need(csvText.includes(sourcePin), "CSV omitted evidence digest");

    await evaluate('document.getElementById("json").click()');
    const jsonPath = join(downloadDir, "riftreader2-filtered.json");
    await until(() => existsSync(jsonPath) &&
      !readdirSync(downloadDir).some(name => name.endsWith(".crdownload")), "JSON download");
    const selected = JSON.parse(readFileSync(jsonPath, "utf8"));
    assert.equal(selected.selectedRecords, matchingPin, "JSON selection count");
    assert.equal(selected.records.length, matchingPin, "JSON download row count");
    assert.ok(selected.records.every(r => r.evidenceSha256 === sourcePin), "JSON leaked other evidence");
    console.log(JSON.stringify({ status: "passed", browser: executable,
      loadedRecords: total, statusMatches: matchingStatus, shaMatches: matchingPin,
      timeSort: sorted, csvRows: matchingPin, jsonRows: selected.records.length }));
  } finally {
    if (socket && socket.readyState <= WebSocket.OPEN) socket.close();
    if (processHandle && processHandle.exitCode === null) {
      processHandle.kill();
      await Promise.race([
        new Promise(ok => processHandle.once("exit", ok)),
        delay(1500)
      ]);
    }
    try { rmSync(temp, { recursive: true, force: true, maxRetries: 8, retryDelay: 200 }); }
    catch (error) { console.error("Browser test temporary profile cleanup:", error.message); }
  }
}
run().catch(error => { console.error("Discovery browser smoke FAILED:", error); process.exitCode = 1; });
