// Offline UI screenshot + layout audit for the local NiceGUI dashboard.
//
// Requires Node 22+ (built-in fetch/WebSocket) and a local Google Chrome.
// It only loads http://127.0.0.1:<port> and captures screenshots/metrics; it
// never opens a serial port, sends PWM, uploads firmware or moves hardware.
//
// Usage:
//   # terminal 1: offline simulation dashboard (never LIVE)
//   PYTHONPATH=src .venv/bin/python -m tactile_gripper.ui --no-browser --demo \
//     --demo-profile HYBRID_6X6_FSR2 --data-root /tmp/gripper-ui-audit --port 8095
//
//   # terminal 2: capture 3 viewports x 3 pages
//   AUDIT_BASE=http://127.0.0.1:8095 OUT_DIR=/tmp/ui-audit LABEL=after \
//     node scripts/ui_screenshot_audit.mjs
//
// Env: AUDIT_BASE, OUT_DIR, LABEL, PAGES, VIEWPORTS, DEBUG_PORT, CHROME_PATH.
// Outputs <page>-<w>x<h>.png (viewport) and *-full.png (expanded scroll area)
// plus <LABEL>-audit.json with card/column geometry and overflow candidates.
// No dependencies beyond Node's built-in fetch/WebSocket and local Chrome.
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';

const CHROME = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const DEBUG_PORT = Number(process.env.DEBUG_PORT || 9411);
const OUT = process.env.OUT_DIR || '/tmp/ui-audit-out';
const BASE = process.env.AUDIT_BASE || 'http://127.0.0.1:8095';
const LABEL = process.env.LABEL || 'after';
const PAGES = (process.env.PAGES || 'live,experiments,analysis').split(',');
const VIEWPORTS = (process.env.VIEWPORTS || '1440x900,1280x800,1920x1080')
  .split(',')
  .map((item) => item.split('x').map(Number));
const PATH = { live: '/', experiments: '/experiments', analysis: '/analysis' };

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForJson(url, timeout = 30000) {
  const deadline = Date.now() + timeout;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return await response.json();
    } catch (error) {
      lastError = error;
    }
    await sleep(250);
  }
  throw new Error(`cannot reach ${url}: ${lastError}`);
}

function connect(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    let seq = 0;
    const pending = new Map();
    const listeners = [];
    ws.onopen = () => resolve(api);
    ws.onerror = (event) => reject(new Error(`websocket error: ${event?.message || 'unknown'}`));
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.id && pending.has(message.id)) {
        const entry = pending.get(message.id);
        pending.delete(message.id);
        if (message.error) entry.reject(new Error(message.error.message));
        else entry.resolve(message.result);
        return;
      }
      if (message.method) listeners.forEach((fn) => fn(message));
    };
    const api = {
      send(method, params = {}) {
        return new Promise((res, rej) => {
          const id = ++seq;
          pending.set(id, { resolve: res, reject: rej });
          ws.send(JSON.stringify({ id, method, params }));
        });
      },
      on(fn) {
        listeners.push(fn);
      },
      close() {
        ws.close();
      },
    };
  });
}

const METRICS_JS = `(() => {
  const visible = (el) => {
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const rect = (el) => {
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
  };
  const cards = [...document.querySelectorAll('.card')].filter(visible).map((el, i) => {
    const title = el.querySelector('.card-title, .card-kicker, .metric-value');
    return { i, ...rect(el), title: (title ? title.innerText : '').trim().slice(0, 40) };
  });
  const cols = [...document.querySelectorAll('.grid-12 > [class*="col-"]')].filter(visible).map((el) => ({
    cls: (el.className.split(' ').find((c) => /^col-[0-9]+$/.test(c)) || ''),
    ...rect(el),
  }));
  const overflowers = [...document.querySelectorAll('body *')].filter(visible).map((el) => ({
    tag: el.tagName,
    cls: String(el.className || '').slice(0, 70),
    ...rect(el),
    clientWidth: el.clientWidth,
    scrollWidth: el.scrollWidth,
    clientHeight: el.clientHeight,
    scrollHeight: el.scrollHeight,
  })).filter((el) => (el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 4) || (el.scrollHeight > el.clientHeight + 2 && el.clientHeight > 4)).slice(0, 80);
  const main = document.querySelector('.main-area');
  return {
    innerWidth, innerHeight,
    bodyScrollWidth: document.body.scrollWidth,
    mainScrollHeight: main ? main.scrollHeight : null,
    mainClientHeight: main ? main.clientHeight : null,
    cards, cols, overflowers,
  };
})()`;

async function evaluate(cdp, expression) {
  const result = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.text || 'evaluate failed');
  }
  return result.result.value;
}

async function waitReady(cdp, timeout = 25000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    try {
      const ready = await evaluate(cdp, `document.readyState === 'complete' && !!document.querySelector('.page-title')`);
      if (ready) return;
    } catch {
      // navigation in flight
    }
    await sleep(200);
  }
  throw new Error('page did not become ready');
}

async function auditPage(cdp, page, width, height, errors) {
  errors.length = 0;
  const url = BASE + PATH[page];
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width, height, deviceScaleFactor: 1, mobile: false, screenWidth: width, screenHeight: height,
  });
  await cdp.send('Page.navigate', { url });
  await waitReady(cdp);
  await sleep(2000);
  await evaluate(cdp, `document.querySelectorAll('.q-notification').forEach((node) => node.remove())`);
  if (page === 'analysis') {
    const clicked = await evaluate(cdp, `(() => {
      const button = [...document.querySelectorAll('button')].find((item) => item.innerText.includes('加载实验'));
      if (button) { button.click(); return true; }
      return false;
    })()`);
    if (clicked) await sleep(1800);
  }
  await sleep(600);
  const metrics = await evaluate(cdp, METRICS_JS);
  const shot = await cdp.send('Page.captureScreenshot', { format: 'png' });
  await writeFile(`${OUT}/${page}-${width}x${height}.png`, Buffer.from(shot.data, 'base64'));

  // Full-page audit aid: let the internal scroll container expand.
  await evaluate(cdp, `(() => {
    const main = document.querySelector('.main-area');
    if (main) { main.style.height = 'auto'; main.style.overflow = 'visible'; }
    const shell = document.querySelector('.app-shell');
    if (shell) { shell.style.height = 'auto'; shell.style.overflow = 'visible'; }
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) { sidebar.style.height = 'auto'; sidebar.style.minHeight = '100vh'; }
    return true;
  })()`);
  await sleep(500);
  const fullHeight = Math.min(await evaluate(cdp, `Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)`), 8000);
  // Resize the real viewport instead of captureBeyondViewport so scroll containers
  // keep their normal clipping in the full-page audit image.
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width, height: fullHeight, deviceScaleFactor: 1, mobile: false, screenWidth: width, screenHeight: fullHeight,
  });
  await sleep(600);
  const full = await cdp.send('Page.captureScreenshot', { format: 'png' });
  await writeFile(`${OUT}/${page}-${width}x${height}-full.png`, Buffer.from(full.data, 'base64'));

  return { page, width, height, metrics, consoleErrors: [...errors] };
}

async function main() {
  await mkdir(OUT, { recursive: true });
  const profileDir = `/tmp/chrome-audit-${LABEL}-${Date.now()}`;
  const chrome = spawn(CHROME, [
    '--headless=new', '--disable-gpu', '--disable-crash-reporter', '--no-first-run',
    '--no-default-browser-check', `--remote-debugging-port=${DEBUG_PORT}`,
    `--user-data-dir=${profileDir}`, '--window-size=1440,900', 'about:blank',
  ], { stdio: 'ignore' });
  const report = { label: LABEL, base: BASE, viewports: [], console: [], pageErrors: [] };
  try {
    await waitForJson(`http://127.0.0.1:${DEBUG_PORT}/json/version`);
    const target = await (await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/new?about:blank`, { method: 'PUT' })).json();
    const cdp = await connect(target.webSocketDebuggerUrl);
    const errors = [];
    cdp.on((message) => {
      if (message.method === 'Runtime.exceptionThrown') {
        const detail = message.params.exceptionDetails;
        errors.push(`exception: ${detail.text} ${detail.exception?.description || ''}`.trim());
      } else if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') {
        errors.push(`console: ${message.params.args.map((arg) => arg.value ?? arg.description ?? '').join(' ')}`.trim());
      } else if (message.method === 'Log.entryAdded' && message.params.entry.level === 'error') {
        errors.push(`log: ${message.params.entry.text}`);
      }
    });
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Log.enable');
    for (const [width, height] of VIEWPORTS) {
      for (const page of PAGES) {
        const result = await auditPage(cdp, page, width, height, errors);
        report.viewports.push(result);
        console.log(`captured ${LABEL} ${page} ${width}x${height} cards=${result.metrics.cards.length} errors=${result.consoleErrors.length}`);
      }
    }
    cdp.close();
  } finally {
    chrome.kill('SIGKILL');
  }
  await writeFile(`${OUT}/${LABEL}-audit.json`, JSON.stringify(report, null, 2));
  console.log(`wrote ${OUT}/${LABEL}-audit.json`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
