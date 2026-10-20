const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync(process.argv[2], 'utf8');
const source = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}

class EventTarget {
  constructor(id='') {
    this.id = id;
    this.listeners = new Map();
    this.textContent = '';
    this.className = '';
    this.value = '';
    this.checked = false;
    this.disabled = false;
    this.alt = '';
    this.src = '';
    this.captured = new Set();
  }
  addEventListener(type, callback) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(callback);
  }
  dispatch(type, properties={}) {
    const event = {
      type, target:this, button:0, buttons:0, pointerId:1, clientX:0, clientY:0,
      deltaY:0, movementX:0, movementY:0, key:'', repeat:false,
      ctrlKey:false, altKey:false, metaKey:false,
      defaultPrevented:false, preventDefault() { this.defaultPrevented = true; },
      ...properties,
    };
    for (const callback of this.listeners.get(type) || []) callback(event);
    return event;
  }
  focus() {}
  removeAttribute(name) { if (name === 'src') this.src = ''; }
  setPointerCapture(pointerId) { this.captured.add(pointerId); }
  hasPointerCapture(pointerId) { return this.captured.has(pointerId); }
  releasePointerCapture(pointerId) {
    if (!this.captured.delete(pointerId)) return;
    this.dispatch('lostpointercapture', {pointerId});
  }
}

function createPanel() {
  const ids = [
    'result','summary','statusResult','surface','screen','operatorState','reviewState',
    'armedState','reviewNote','reviewCheck','armButton','captureButton','recoverButton',
    'stopButton','statusButton','mouseButton','pointerMode',
  ];
  const elements = Object.fromEntries(ids.map(id => [id, new EventTarget(id)]));
  elements.pointerMode.value = 'drag';
  elements.mouseButton.value = '';
  const document = new EventTarget('document');
  document.hidden = false;
  document.focused = true;
  document.pointerLockElement = null;
  document.getElementById = id => elements[id];
  document.hasFocus = () => document.focused;
  document.exitPointerLock = () => {
    if (document.pointerLockElement === null) return;
    document.pointerLockElement = null;
    document.dispatch('pointerlockchange');
  };
  const window = new EventTarget('window');
  const timers = new Map();
  let nextTimer = 1;
  const setTimeoutFake = (callback, milliseconds=0) => {
    const id = nextTimer++;
    timers.set(id, {callback, milliseconds, interval:false});
    return id;
  };
  const setIntervalFake = (callback, milliseconds=0) => {
    const id = nextTimer++;
    timers.set(id, {callback, milliseconds, interval:true});
    return id;
  };
  const clearTimer = id => timers.delete(id);
  async function runTimers(maximumMilliseconds=100) {
    const ready = [...timers.entries()]
      .filter(([, timer]) => !timer.interval && timer.milliseconds <= maximumMilliseconds);
    for (const [id, timer] of ready) {
      timers.delete(id);
      timer.callback();
      await flush();
    }
  }

  const calls = [];
  const queued = new Map();
  function enqueue(path) {
    const item = deferred();
    if (!queued.has(path)) queued.set(path, []);
    queued.get(path).push(item);
    return item;
  }
  function defaultValue(path, body) {
    if (path === '/api/status') return {connected:true, marker:'status'};
    if (path === '/api/capture') return {
      captureId:'capture-1', imageBase64:'QQ==', reviewExpiresInSeconds:45,
    };
    if (path === '/api/arm') return {armToken:'arm-secret', expiresInSeconds:15};
    if (path === '/api/stop') return {recoveryRequired:false};
    if (path === '/api/release') return {recoveryRequired:false, armed:true};
    if (path === '/api/recover') return {recoveryRequired:false};
    if (path === '/api/action') return {
      result:{deliverySucceeded:true, releaseSucceeded:true, cancelled:false,
        targetLost:false, stateUncertain:false, requiresCallerDisarm:false},
      recoveryRequired:false, action:body.action,
    };
    throw new Error(`unexpected path ${path}`);
  }
  async function fetch(path, options={}) {
    const body = options.body ? JSON.parse(options.body) : null;
    calls.push({path, options, body});
    const queue = queued.get(path);
    const value = queue && queue.length ? await queue.shift().promise : defaultValue(path, body);
    if (value instanceof Error) throw value;
    const status = value && value.__status ? value.__status : 200;
    const payload = value && value.__payload ? value.__payload : value;
    return {ok:status >= 200 && status < 300, status, async json() { return payload; }};
  }

  elements.surface.requestPointerLock = () => {
    document.pointerLockElement = elements.surface;
    document.dispatch('pointerlockchange');
    return Promise.resolve();
  };
  const context = vm.createContext({
    console, document, window, fetch,
    location:{hash:'#operator-token', pathname:'/panel'},
    history:{replaceState() {}}, decodeURIComponent,
    setTimeout:setTimeoutFake, clearTimeout:clearTimer,
    setInterval:setIntervalFake, clearInterval:clearTimer,
    Date, Math, Number, JSON, Object, Array, Set, Boolean, Error, Promise,
  });
  vm.runInContext(source, context, {filename:'control_panel.html'});
  return {elements, document, window, calls, enqueue, runTimers};
}

async function flush() {
  for (let index = 0; index < 32; index += 1) await Promise.resolve();
}

async function captureAndPrepare(panel) {
  await panel.elements.captureButton.onclick();
  panel.elements.reviewCheck.checked = true;
  panel.elements.reviewCheck.dispatch('change');
  panel.elements.reviewNote.value = 'reviewed in world and chat closed';
  panel.elements.reviewNote.dispatch('input');
}

async function arm(panel) {
  await captureAndPrepare(panel);
  await panel.elements.armButton.onclick();
  assert.match(panel.elements.armedState.textContent, /^Armed/);
}

function callsFor(panel, path) { return panel.calls.filter(call => call.path === path); }

async function testPendingArmStopsOnBlurAndCannotDoubleSubmit() {
  const panel = createPanel();
  await captureAndPrepare(panel);
  const pendingArm = panel.enqueue('/api/arm');
  const first = panel.elements.armButton.onclick();
  const second = panel.elements.armButton.onclick();
  assert.strictEqual(callsFor(panel, '/api/arm').length, 1);
  assert.strictEqual(panel.elements.armButton.disabled, true);
  const pendingStop = panel.enqueue('/api/stop');
  panel.document.focused = false;
  panel.window.dispatch('blur');
  await flush();
  assert.strictEqual(callsFor(panel, '/api/stop').length, 1);
  pendingArm.resolve({armToken:'late-arm', expiresInSeconds:15});
  await Promise.all([first, second]);
  await flush();
  assert.strictEqual(callsFor(panel, '/api/stop').length, 1);
  pendingStop.resolve({recoveryRequired:false});
  await flush();
  assert.strictEqual(callsFor(panel, '/api/stop').length, 2);
  assert.strictEqual(panel.elements.armedState.textContent, 'Disarmed');
}

async function testUncertainArmOutcomeGetsCompensatingStop() {
  const panel = createPanel();
  await captureAndPrepare(panel);
  const failedArm = panel.enqueue('/api/arm');
  const arming = panel.elements.armButton.onclick();
  failedArm.reject(new Error('arm response lost'));
  await arming;
  await flush();
  assert.strictEqual(callsFor(panel, '/api/arm').length, 1);
  assert.strictEqual(callsFor(panel, '/api/stop').length, 2);
  assert.strictEqual(panel.elements.armedState.textContent, 'Disarmed');
  assert.strictEqual(panel.elements.captureButton.disabled, false);
}

async function testCaptureStopsAndDropsStaleHeldKey() {
  const panel = createPanel();
  await arm(panel);
  const oldAction = panel.enqueue('/api/action');
  panel.elements.surface.dispatch('keydown', {key:'w'});
  await flush();
  const capture = panel.elements.captureButton.onclick();
  await flush();
  assert.deepStrictEqual(panel.calls.slice(-2).map(call => call.path), ['/api/stop','/api/capture']);
  await capture;
  oldAction.resolve({
    result:{deliverySucceeded:true, releaseSucceeded:true, cancelled:true},
    recoveryRequired:false, action:{keys:['w'], wheelNotches:0},
  });
  await flush();
  panel.elements.reviewCheck.checked = true;
  panel.elements.reviewCheck.dispatch('change');
  panel.elements.reviewNote.value = 'new reviewed in world frame';
  panel.elements.reviewNote.dispatch('input');
  await panel.elements.armButton.onclick();
  panel.elements.mouseButton.value = 'right';
  panel.elements.mouseButton.dispatch('change');
  panel.elements.surface.dispatch('pointerdown', {pointerId:2, button:0, buttons:1, clientX:10, clientY:10});
  panel.elements.surface.dispatch('pointermove', {pointerId:2, buttons:1, clientX:11, clientY:10});
  await panel.runTimers(20);
  const action = callsFor(panel, '/api/action').at(-1).body.action;
  assert.deepStrictEqual(action.keys, []);
  assert.strictEqual(action.deltaX, 1);
}

async function testActionFailureClearsQueuedDragAndCapture() {
  const panel = createPanel();
  await arm(panel);
  panel.elements.mouseButton.value = 'right';
  panel.elements.mouseButton.dispatch('change');
  const failed = panel.enqueue('/api/action');
  panel.elements.surface.dispatch('pointerdown', {pointerId:3, button:0, buttons:1, clientX:0, clientY:0});
  panel.elements.surface.dispatch('pointermove', {pointerId:3, buttons:1, clientX:5, clientY:0});
  await panel.runTimers(20);
  panel.elements.surface.dispatch('pointermove', {pointerId:3, buttons:1, clientX:14, clientY:0});
  failed.reject(new Error('action rejected'));
  await flush();
  assert.strictEqual(panel.elements.armedState.textContent, 'Disarmed');
  assert.strictEqual(panel.elements.surface.captured.size, 0);
  await arm(panel);
  panel.elements.mouseButton.value = 'right';
  panel.elements.mouseButton.dispatch('change');
  panel.elements.surface.dispatch('pointerdown', {pointerId:4, button:0, buttons:1, clientX:20, clientY:20});
  panel.elements.surface.dispatch('pointermove', {pointerId:4, buttons:1, clientX:21, clientY:20});
  await panel.runTimers(20);
  const action = callsFor(panel, '/api/action').at(-1).body.action;
  assert.strictEqual(action.deltaX, 1);
}

async function testKeyReleaseResumesOnlyKeysStillHeld() {
  const panel = createPanel();
  await arm(panel);
  const firstAction = panel.enqueue('/api/action');
  const release = panel.enqueue('/api/release');
  panel.elements.surface.dispatch('keydown', {key:'w'});
  panel.elements.surface.dispatch('keydown', {key:'d'});
  panel.document.dispatch('keyup', {key:'w'});
  release.resolve({recoveryRequired:false, armed:true});
  firstAction.resolve({
    result:{deliverySucceeded:true, releaseSucceeded:true, cancelled:true},
    recoveryRequired:false, action:{keys:['w'], wheelNotches:0},
  });
  await flush();
  await panel.runTimers(0);
  const action = callsFor(panel, '/api/action').at(-1).body.action;
  assert.deepStrictEqual(action.keys, ['d']);
}

async function testReleaseFailureClearsPointerLockAndArm() {
  const panel = createPanel();
  await arm(panel);
  panel.elements.mouseButton.value = 'right';
  panel.elements.pointerMode.value = 'lock';
  panel.elements.surface.dispatch('pointerdown', {button:0, buttons:1});
  await flush();
  assert.strictEqual(panel.document.pointerLockElement, panel.elements.surface);
  panel.elements.surface.dispatch('keydown', {key:'w'});
  await flush();
  const failedRelease = panel.enqueue('/api/release');
  panel.document.dispatch('keyup', {key:'w'});
  failedRelease.reject(new Error('release rejected'));
  await flush();
  assert.strictEqual(panel.elements.armedState.textContent, 'Disarmed');
  assert.strictEqual(panel.document.pointerLockElement, null);
}

async function testStaleReleaseCannotDisarmNewSession() {
  const panel = createPanel();
  await arm(panel);
  panel.elements.surface.dispatch('keydown', {key:'w'});
  await flush();
  const oldRelease = panel.enqueue('/api/release');
  panel.document.dispatch('keyup', {key:'w'});
  const capture = panel.elements.captureButton.onclick();
  await capture;
  panel.elements.reviewCheck.checked = true;
  panel.elements.reviewCheck.dispatch('change');
  panel.elements.reviewNote.value = 'reviewed replacement frame';
  panel.elements.reviewNote.dispatch('input');
  await panel.elements.armButton.onclick();
  assert.match(panel.elements.armedState.textContent, /^Armed/);
  oldRelease.resolve({recoveryRequired:true, armed:false});
  await flush();
  assert.match(panel.elements.armedState.textContent, /^Armed/);
}

async function testStaleActionFinallyDoesNotPumpNewSession() {
  const panel = createPanel();
  await arm(panel);
  const oldAction = panel.enqueue('/api/action');
  panel.elements.surface.dispatch('keydown', {key:'w'});
  await flush();
  await panel.elements.captureButton.onclick();
  panel.elements.reviewCheck.checked = true;
  panel.elements.reviewCheck.dispatch('change');
  panel.elements.reviewNote.value = 'reviewed replacement frame';
  panel.elements.reviewNote.dispatch('input');
  await panel.elements.armButton.onclick();
  panel.elements.surface.dispatch('keydown', {key:'d'});
  oldAction.resolve({
    result:{deliverySucceeded:true, releaseSucceeded:true, cancelled:true},
    recoveryRequired:false, action:{keys:['w'], wheelNotches:0},
  });
  await flush();
  await panel.runTimers(0);
  assert.strictEqual(callsFor(panel, '/api/action').length, 1);
  panel.elements.surface.dispatch('keydown', {key:'a'});
  await flush();
  const action = callsFor(panel, '/api/action').at(-1).body.action;
  assert.deepStrictEqual(action.keys, ['a','d']);
}

async function testFocusoutAndModifiersReleaseMovement() {
  const focusPanel = createPanel();
  await arm(focusPanel);
  const action = focusPanel.enqueue('/api/action');
  focusPanel.elements.surface.dispatch('keydown', {key:'w'});
  focusPanel.elements.surface.dispatch('focusout');
  await flush();
  assert.strictEqual(callsFor(focusPanel, '/api/release').length, 1);
  action.resolve({
    result:{deliverySucceeded:true, releaseSucceeded:true, cancelled:true},
    recoveryRequired:false, action:{keys:['w'], wheelNotches:0},
  });
  await flush();

  const modifierPanel = createPanel();
  await arm(modifierPanel);
  modifierPanel.elements.surface.dispatch('keydown', {key:'w', ctrlKey:true});
  modifierPanel.elements.surface.dispatch('keydown', {key:'a', altKey:true});
  modifierPanel.elements.surface.dispatch('keydown', {key:'d', metaKey:true});
  await flush();
  assert.strictEqual(callsFor(modifierPanel, '/api/action').length, 0);
  modifierPanel.elements.surface.dispatch('keydown', {key:'w'});
  await flush();
  modifierPanel.elements.surface.dispatch('keydown', {key:'Control', ctrlKey:true});
  await flush();
  assert.strictEqual(callsFor(modifierPanel, '/api/release').length, 1);
}

async function testEveryExitOrderingUsesKeepaliveStop() {
  for (const firstExitEvent of ['blur', 'visibilitychange']) {
    const panel = createPanel();
    await arm(panel);
    const pendingStop = panel.enqueue('/api/stop');
    if (firstExitEvent === 'visibilitychange') {
      panel.document.hidden = true;
      panel.document.dispatch('visibilitychange');
    } else {
      panel.window.dispatch('blur');
    }
    panel.window.dispatch('pagehide');
    await flush();
    const stops = callsFor(panel, '/api/stop');
    assert.strictEqual(stops.length, 1);
    assert.strictEqual(stops[0].options.keepalive, true);
    assert.strictEqual(panel.elements.armedState.textContent, 'Disarmed');
    pendingStop.resolve({recoveryRequired:false});
    await flush();
  }
}

async function testRecoverAndStopSerializeLifecycle() {
  const panel = createPanel();
  await arm(panel);
  panel.elements.mouseButton.value = 'right';
  panel.elements.mouseButton.dispatch('change');
  panel.elements.surface.dispatch('pointerdown', {pointerId:5, button:0, buttons:1});
  await panel.elements.recoverButton.onclick();
  assert.deepStrictEqual(panel.calls.slice(-2).map(call => call.path), ['/api/stop','/api/recover']);
  assert.strictEqual(panel.elements.surface.captured.size, 0);

  await arm(panel);
  const pendingStop = panel.enqueue('/api/stop');
  panel.elements.stopButton.onclick();
  await flush();
  assert.strictEqual(panel.elements.captureButton.disabled, true);
  await panel.elements.captureButton.onclick();
  panel.window.dispatch('blur');
  assert.strictEqual(callsFor(panel, '/api/stop').length, 2);
  assert.strictEqual(callsFor(panel, '/api/capture').length, 2);
  pendingStop.resolve({recoveryRequired:false});
  await flush();
}

async function testStalePointerLockAndStatusCannotOverwrite() {
  const panel = createPanel();
  await arm(panel);
  panel.elements.mouseButton.value = 'right';
  panel.elements.pointerMode.value = 'lock';
  const lock = deferred();
  panel.elements.surface.requestPointerLock = () => lock.promise;
  panel.elements.surface.dispatch('pointerdown', {button:0, buttons:1});
  panel.elements.pointerMode.value = 'drag';
  panel.elements.pointerMode.dispatch('change');
  const before = panel.elements.operatorState.textContent;
  lock.reject(new Error('late rejection'));
  await flush();
  assert.strictEqual(panel.elements.operatorState.textContent, before);

  panel.elements.pointerMode.value = 'lock';
  const lateLock = deferred();
  panel.elements.surface.requestPointerLock = () => lateLock.promise;
  panel.elements.surface.dispatch('pointerdown', {button:0, buttons:1});
  panel.elements.pointerMode.value = 'drag';
  panel.elements.pointerMode.dispatch('change');
  panel.document.pointerLockElement = panel.elements.surface;
  panel.document.dispatch('pointerlockchange');
  await flush();
  assert.strictEqual(panel.document.pointerLockElement, null);
  assert.ok(callsFor(panel, '/api/stop').length >= 1);

  const status = panel.enqueue('/api/status');
  const statusCall = panel.elements.statusButton.onclick();
  panel.elements.result.textContent = 'action-evidence';
  status.resolve({connected:true, marker:'later-status'});
  await statusCall;
  assert.strictEqual(panel.elements.result.textContent, 'action-evidence');
  assert.match(panel.elements.statusResult.textContent, /later-status/);
  const failedStatus = panel.enqueue('/api/status');
  const failedStatusCall = panel.elements.statusButton.onclick();
  panel.elements.operatorState.textContent = 'release feedback';
  failedStatus.reject(new Error('status unavailable'));
  await failedStatusCall;
  assert.strictEqual(panel.elements.operatorState.textContent, 'release feedback');
  assert.match(panel.elements.statusResult.textContent, /Status failed/);
}

async function testLateSameModePointerLockCannotAttachToNewArm() {
  const panel = createPanel();
  await arm(panel);
  panel.elements.mouseButton.value = 'right';
  panel.elements.pointerMode.value = 'lock';
  const lateLock = deferred();
  panel.elements.surface.requestPointerLock = () => lateLock.promise;
  panel.elements.surface.dispatch('pointerdown', {button:0, buttons:1});
  panel.elements.stopButton.onclick();
  await flush();
  await arm(panel);
  panel.elements.mouseButton.value = 'right';
  panel.elements.pointerMode.value = 'lock';
  panel.document.pointerLockElement = panel.elements.surface;
  panel.document.dispatch('pointerlockchange');
  await flush();
  assert.strictEqual(panel.document.pointerLockElement, null);
  assert.strictEqual(panel.elements.armedState.textContent, 'Disarmed');
  lateLock.resolve();
  await flush();
}

async function testZeroWheelDoesNothing() {
  const panel = createPanel();
  await arm(panel);
  panel.elements.surface.dispatch('wheel', {deltaY:0});
  await flush();
  assert.strictEqual(callsFor(panel, '/api/action').length, 0);
  panel.elements.surface.dispatch('wheel', {deltaY:-1});
  await flush();
  panel.elements.surface.dispatch('wheel', {deltaY:1});
  await flush();
  assert.deepStrictEqual(
    callsFor(panel, '/api/action').map(call => call.body.action.wheelNotches), [1, -1]);
}

(async () => {
  await testPendingArmStopsOnBlurAndCannotDoubleSubmit();
  await testUncertainArmOutcomeGetsCompensatingStop();
  await testCaptureStopsAndDropsStaleHeldKey();
  await testActionFailureClearsQueuedDragAndCapture();
  await testKeyReleaseResumesOnlyKeysStillHeld();
  await testReleaseFailureClearsPointerLockAndArm();
  await testStaleReleaseCannotDisarmNewSession();
  await testStaleActionFinallyDoesNotPumpNewSession();
  await testFocusoutAndModifiersReleaseMovement();
  await testEveryExitOrderingUsesKeepaliveStop();
  await testRecoverAndStopSerializeLifecycle();
  await testStalePointerLockAndStatusCannotOverwrite();
  await testLateSameModePointerLockCannotAttachToNewArm();
  await testZeroWheelDoesNothing();
  process.stdout.write('control panel async regressions passed\n');
})().catch(error => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
