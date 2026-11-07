// Trusted functions.exec factory body. The caller reviews and pins this source.
return async function inspect(focus = "overview", options = {}) {
  const startedMs = Date.now();
  const base = "C:\\work\\riftreader2\\artifacts\\e2e-latency-20261106\\lab2-handoff-";
  if (!["overview", "health", "energy"].includes(focus)) throw new Error("Invalid focus");
  if (!options || typeof options !== "object" || Array.isArray(options) ||
      Object.keys(options).some(k => k !== "outputTag")) throw new Error("Invalid options");
  const tag = options.outputTag === undefined
    ? Date.now().toString() + "-" + Math.random().toString(36).slice(2)
    : options.outputTag;
  if (typeof tag !== "string" || !/^[A-Za-z0-9-]{1,96}$/.test(tag)) throw new Error("Invalid output tag");
  const root = base + tag;
  let previous;
  if (focus !== "overview") {
    previous = load("lab2-handoff-previous");
    if (!previous || typeof previous.root !== "string" || !previous.root.startsWith(base) ||
        !/^[A-Za-z0-9-]{1,96}$/.test(previous.root.slice(base.length)) ||
        !/^[0-9A-F]{64}$/.test(previous.sha) || previous.root === root)
      throw new Error("Missing or invalid reviewed observation metadata");
  }
  // Each displayed overview permits at most one continuation attempt.
  store("lab2-handoff-previous", null);
  let cmd = "& 'C:\\Python314\\python.exe' 'scripts/inspect_lab2_tool.py' '--output' '" + root + "'";
  if (previous) cmd += " '--reviewed-output' '" + previous.root + "' '--reviewed-image-sha256' '" + previous.sha + "' '--focus' '" + focus + "'";
  let result = await tools.exec_command({cmd, workdir: "C:\\work\\riftreader2", max_output_tokens: 2000});
  let output = result.output;
  while (result.session_id !== undefined) {
    result = await tools.write_stdin({session_id: result.session_id, chars: "", max_output_tokens: 2000});
    output += result.output;
  }
  if (result.exit_code !== 0) throw new Error("Inspection blocked; retained run: " + root);
  const delivered = JSON.parse(output);
  if (delivered.status !== "verified-awaiting-visual-review" ||
      delivered.image !== root + "\\capture\\image.bmp" || delivered.report !== root + "\\report.json" ||
      !/^[0-9A-F]{64}$/.test(delivered.imageSha256) ||
      (previous && (delivered.focus !== focus || delivered.reviewedOutput !== previous.root || delivered.reviewedImageSha256 !== previous.sha ||
                    delivered.qualification !== "candidate-only; semantics/passive-freshness/restart-unverified; UI review required" ||
                    !/^[0-9A-F]{64}$/.test(delivered.nativeSourceReportSha256) ||
                    !Object.prototype.hasOwnProperty.call(delivered, "selectedMetric"))))
    throw new Error("Unexpected delivery; retained run: " + root);
  const picture = await tools.view_image({path: delivered.image});
  image(picture.image_url);
  const imageReturnedMs = Date.now();
  const history = load("lab2-handoff-history");
  const entry = {focus, root, imageSha256: delivered.imageSha256, startedMs, imageReturnedMs,
                 workflowSeconds: delivered.workflowSeconds};
  if (previous) Object.assign(entry, {reviewedRoot: previous.root, reviewedImageSha256: previous.sha});
  store("lab2-handoff-history", [...(Array.isArray(history) ? history : []), entry]);
  if (focus === "overview") store("lab2-handoff-previous", {root, sha: delivered.imageSha256});
  const compact = {status: delivered.status, imageSha256: delivered.imageSha256, report: delivered.report};
  if (previous) Object.assign(compact, {focus, selectedMetric: delivered.selectedMetric,
                                        reviewedImageSha256: delivered.reviewedImageSha256,
                                        qualification: delivered.qualification,
                                        nativeSourceReportSha256: delivered.nativeSourceReportSha256});
  text(compact);
};
