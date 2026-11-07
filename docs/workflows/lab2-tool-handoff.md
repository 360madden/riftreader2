# One-handoff Lab 2 inspection

Use one model-facing tool call to run the guarded native/UI inspection and load
its verified image. This removes the avoidable model-dispatch gap between a
finished command and the image tool. It does not change model settings or remove
the workflow's checks. The driver is fixed to Lab 2 and never sends game input.

In `functions.exec`, use the following recipe with a fresh directory. All
dependent operations are awaited inside the same invocation. The default outer
30-second yield window normally covers this short workflow; do not lower it just
to return an unfinished operation to the model.

```javascript
const output = "C:\\work\\riftreader2\\artifacts\\e2e-latency-20261106\\lab2-tool-" + Date.now();
let result = await tools.exec_command({
  cmd: "& 'C:\\Python314\\python.exe' 'scripts/inspect_lab2_tool.py' '--output' '" + output + "'",
  workdir: "C:\\work\\riftreader2",
  max_output_tokens: 2000
});
let stdout = result.output;
while (result.session_id !== undefined) {
  result = await tools.write_stdin({session_id: result.session_id, chars: "", max_output_tokens: 2000});
  stdout += result.output;
}
if (result.exit_code !== 0) throw new Error("Inspection blocked; retained run: " + output);
const delivered = JSON.parse(stdout);
if (delivered.status !== "verified-awaiting-visual-review" ||
    delivered.image !== output + "\\capture\\image.bmp" ||
    !/^[0-9A-F]{64}$/.test(delivered.imageSha256)) {
  throw new Error("Unexpected delivery; retained run: " + output);
}
const picture = await tools.view_image({path: delivered.image});
image(picture.image_url);
text(delivered);
```

The output path is built only from a fixed prefix and a numeric timestamp, so
the PowerShell literal argument above contains no user-supplied shell text. On a
failure, inspect the retained run's failure receipt. Never infer success from a
submitted job, an unfinished session or an old artifact. Do not automatically
rerun a failed operation under the same output path.

`inspect_lab2_tool.py` calls the existing joined workflow and checks delivery
paths, bounded artifacts, matching report/capture receipts and source image SHA.
It emits compact JSON only after successful final inventory and verified
watchdog release. It keeps native values explicitly candidate-only. Its status
remains `verified-awaiting-visual-review`: the assistant must inspect the returned
pixels before describing the visual outcome. The returned SHA binds the source
BMP; the image tool may resize or transcode its display.
The compact delivery expresses `nativeVitals.metrics.unitKey` as a decimal
string so JavaScript preserves the exact 64-bit value. The source report retains
its original integer representation; other metrics keep their original types.

## A preauthorized fresh confirmation

When the task already calls for a second independent read-only observation, use
`--confirm-output` to perform exactly two observations in one command. Each runs
the complete original admission, native acquisition, leased screenshot and
cleanup. The second is not conditional on an interpretation of the first image.
Both images return after both operations and their comparison pass. Continue to
use separate calls whenever the next action requires that interpretation.

```javascript
const prefix = "C:\\work\\riftreader2\\artifacts\\e2e-latency-20261106\\lab2-confirm-" + Date.now();
const roots = [prefix + "a", prefix + "b"];
let command = await tools.exec_command({
  cmd: "& 'C:\\Python314\\python.exe' 'scripts/inspect_lab2_tool.py' '--output' '" +
       roots[0] + "' '--confirm-output' '" + roots[1] + "'",
  workdir: "C:\\work\\riftreader2", max_output_tokens: 4000
});
let stdout = command.output;
while (command.session_id !== undefined) {
  command = await tools.write_stdin({session_id: command.session_id, chars: "", max_output_tokens: 4000});
  stdout += command.output;
}
if (command.exit_code !== 0) throw new Error("Confirmation blocked; retained runs: " + roots.join(", "));
const pair = JSON.parse(stdout);
if (pair.status !== "confirmed-awaiting-visual-review" || pair.confirmation !== "passed" ||
    pair.observations?.length !== 2) throw new Error("Unexpected confirmation");
for (let i = 0; i < 2; i++) {
  const item = pair.observations[i];
  if (item.status !== "verified-awaiting-visual-review" ||
      item.image !== roots[i] + "\\capture\\image.bmp" || !/^[0-9A-F]{64}$/.test(item.imageSha256)) {
    throw new Error("Unexpected confirmation image");
  }
}
const pictures = await Promise.allSettled(pair.observations.map(item => tools.view_image({path: item.image})));
for (const picture of pictures) {
  if (picture.status !== "fulfilled") throw new Error("Image delivery failed; retained runs: " + roots.join(", "));
}
for (const picture of pictures) image(picture.value.image_url);
text(pair);
```

The driver rejects reused output roots, changed identity pins, reused capture or
request IDs, reused native source paths and timestamps that fail to advance. It
rebinds both deliveries before publishing `confirmation.json` under the second
run. If either operation fails, its artifacts remain but no successful pair or
image list is returned. Neither stable values nor identical pixels are a failure;
this verifies new observations, not changed-state semantics.

The same pattern can orchestrate Workbridge run/status/output calls when local
execution is unavailable, but that connector path needs its own timing evidence.
Do not claim that changing local orchestration modifies ChatGPT's internal model
latency. OpenAI's [latency guide](https://developers.openai.com/api/docs/guides/latency-optimization)
recommends reducing sequential request round trips and handling deterministic
steps in code; this workflow applies that principle to command completion and
image delivery.
