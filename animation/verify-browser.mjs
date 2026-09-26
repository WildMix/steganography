// Offline browser verification. Uses an existing Chrome/Chromium, with no npm dependencies.
// Set CHROME_PATH if Chromium is not in the local Playwright browser cache.
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdir, readdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(root, 'artifacts', 'animation');
await mkdir(output, { recursive: true });
let executable = process.env.CHROME_PATH;
if (!executable && process.env.LOCALAPPDATA) {
  const cache = path.join(process.env.LOCALAPPDATA, 'ms-playwright');
  if (existsSync(cache)) for (const entry of (await readdir(cache)).sort().reverse()) {
    if (!entry.startsWith('chromium-')) continue;
    const candidate = path.join(cache, entry, 'chrome-win64', 'chrome.exe');
    if (existsSync(candidate)) { executable = candidate; break; }
  }
}
if (!executable) throw new Error('Set CHROME_PATH to an existing Chrome/Chromium executable.');
const chrome = spawn(executable, [
  '--headless=new', '--remote-debugging-port=0', '--no-first-run', '--no-default-browser-check',
  '--disable-background-networking', '--disable-component-update', '--disable-sync',
  `--user-data-dir=${path.join(output, 'browser-profile')}`, 'about:blank',
], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
let ws;
try {
  const endpoint = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Chromium startup timed out')), 15000);
    let stderr = '';
    chrome.on('error', reject);
    chrome.stderr.on('data', chunk => { stderr += chunk; const match = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/); if (match) { clearTimeout(timer); resolve(match[1]); } });
    chrome.on('exit', code => { clearTimeout(timer); reject(new Error(`Chromium exited ${code}: ${stderr.slice(-1500)}`)); });
  });
  ws = new WebSocket(endpoint);
  await new Promise((resolve, reject) => { ws.addEventListener('open', resolve, { once: true }); ws.addEventListener('error', reject, { once: true }); });
  let sequence = 0, sessionId;
  const pending = new Map(), errors = [], externalRequests = [], loadWaiters = [];
  ws.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (message.id) { const item = pending.get(message.id); if (!item) return; pending.delete(message.id); clearTimeout(item.timer); message.error ? item.reject(new Error(JSON.stringify(message.error))) : item.resolve(message.result); }
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails);
    if (message.method === 'Page.loadEventFired') loadWaiters.splice(0).forEach(resolve => resolve());
    if (message.method === 'Network.requestWillBeSent' && /^https?:/.test(message.params.request.url)) externalRequests.push(message.params.request.url);
  });
  function send(method, params = {}, target = sessionId) {
    return new Promise((resolve, reject) => {
      const id = ++sequence;
      const timer = setTimeout(() => { pending.delete(id); reject(new Error(`Timed out: ${method}`)); }, 15000);
      pending.set(id, { resolve, reject, timer });
      ws.send(JSON.stringify({ id, method, params, ...(target ? { sessionId: target } : {}) }));
    });
  }
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  ({ sessionId } = await send('Target.attachToTarget', { targetId, flatten: true }));
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
  const url = pathToFileURL(path.join(root, 'animation', 'index.html')).href;
  async function navigate(destination) {
    const loaded = new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Page load timed out')), 15000);
      loadWaiters.push(() => { clearTimeout(timer); resolve(); });
    });
    await send('Page.navigate', { url: destination });
    await loaded;
  }
  await navigate(url);
  async function evaluate(expression) {
    const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
  async function ready() {
    for (let i = 0; i < 100; i++) {
      if (await evaluate(`document.readyState === 'complete' && !!document.querySelector('#chapter-title')?.textContent`)) return;
      await new Promise(resolve => setTimeout(resolve, 40));
    }
    throw new Error('Animation failed to initialize');
  }
  async function click(selector) { await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`); }
  async function text(selector) { return evaluate(`document.querySelector(${JSON.stringify(selector)}).textContent`); }
  async function seek(seconds) { await evaluate(`document.querySelector('#seek').value=${seconds}; document.querySelector('#seek').dispatchEvent(new Event('input', {bubbles:true}))`); }
  async function capture(name) {
    await evaluate(`document.fonts.ready.then(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))))`);
    const result = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
    await writeFile(path.join(output, `${name}.png`), Buffer.from(result.data, 'base64'));
  }
  await ready();
  assert.equal(await evaluate(`document.querySelectorAll('[data-chapter]').length`), 17);
  assert.match(await text('#chapter-title'), /One picture/);
  // Let local SVG image resources finish loading before taking screenshots.
  await evaluate(`Promise.all(['cover','stego','costs'].map(name=>new Promise((resolve,reject)=>{const img=new Image();img.onload=resolve;img.onerror=reject;img.src='assets/'+name+'.png'})))`);
  await seek(16); await capture('01-overview-desktop');
  await click('#chapters-toggle');
  assert.equal(await evaluate(`document.querySelector('#chapter-list').hidden`), false);
  await click('[data-chapter="2"]');
  assert.match(await text('#drawing'), /648 target bits/);
  await click('[data-value="fixed"]');
  assert.match(await text('#drawing'), /13,104 target bits/);
  await click('[data-value="auto"]');
  assert.match(await text('#drawing'), /10 bytes of padding/);
  await click('#chapters-toggle');
  await capture('03-budget-desktop');
  await click('[data-chapter="6"]');
  await seek(147); // reveal the XOR result in this chapter
  await click('[data-action="unmask"]');
  assert.match(await text('#drawing'), /Recovered byte/);
  await click('[data-chapter="10"]');
  await click('[data-action="pixel"][data-value="0"]');
  assert.match(await text('#drawing'), /Both equations match · total change cost 8/);
  await click('[data-action="cheapest"]');
  assert.match(await text('#drawing'), /Both equations match · total change cost 3/);
  await capture('11-equations-desktop');
  await click('[data-action="reset-pixels"]');
  assert.match(await text('#drawing'), /Equations do not match yet/);
  await click('[data-action="cheapest"]'); await click('#replay'); await click('#play');
  assert.match(await text('#drawing'), /Equations do not match yet/);
  // Exhaust every interactive flip pattern and independently check the visible answers/cost.
  for (let pattern = 0; pattern < 16; pattern++) {
    await click('[data-action="reset-pixels"]');
    const flips = [0,1,2,3].map(i => (pattern >> i) & 1);
    for (let i = 0; i < 4; i++) if (flips[i]) await click(`[data-action="pixel"][data-value="${i}"]`);
    const parity = [0,0,1,0].map((v,i) => v ^ flips[i]);
    const valid = (parity[0] ^ parity[1]) === 1 && (parity[0] ^ parity[2] ^ parity[3]) === 0;
    const cost = flips.reduce((sum,v,i) => sum + v * [8,1,2,5][i], 0);
    assert.ok((await text('#drawing')).includes(`${valid ? 'Both equations match' : 'Equations do not match yet'} · total change cost ${cost}`));
  }
  // Visit every chapter and check that the SVG stays within its viewBox.
  const sceneOverflow = [];
  for (let i = 0; i < 17; i++) {
    await click(`[data-chapter="${i}"]`);
    const start = await evaluate(`Number(document.querySelector('#seek').value)`);
    const next = i < 16 ? await evaluate(`(()=>{document.querySelector('[data-chapter="${i+1}"]').click();return Number(document.querySelector('#seek').value)})()`) : await evaluate(`Number(document.querySelector('#seek').max)`);
    await seek(start + (next - start) * .9);
    const overflow = await evaluate(`Array.from(document.querySelectorAll('#drawing text')).filter(e=>{const b=e.getBBox();return b.x < 0 || b.x+b.width > 900 || b.y < 0 || b.y+b.height > 560}).map(e=>e.textContent)`);
    if (overflow.length) sceneOverflow.push({ chapter: i + 1, overflow });
  }
  assert.deepEqual(sceneOverflow, []);
  await click('[data-chapter="11"]'); await seek(290); await capture('12-trellis-desktop');
  await click('[data-chapter="13"]'); await seek(340); await capture('14-balancing-desktop');
  await click('[data-action="sign"]');
  assert.match(await text('#drawing'), /\+1 change/);
  await click('[data-action="sign"]');
  assert.match(await text('#drawing'), /−1 change/);
  await click('[data-chapter="12"]');
  await click('[data-action="overlay"]'); assert.match(await text('#drawing'), /72changed pixels/);
  await click('[data-action="overlay"]'); assert.match(await text('#drawing'), /0changed pixels/);
  await click('[data-chapter="14"]');
  await evaluate(`document.querySelector('#compare').value=0;document.querySelector('#compare').dispatchEvent(new Event('input',{bubbles:true}))`);
  assert.equal(await evaluate(`document.querySelector('#compare-clip rect').getAttribute('width')`), '0');
  // Playback advances, pausing freezes position, and final playback stops cleanly.
  await click('[data-chapter="0"]'); await click('#play');
  const initial = await evaluate(`Number(document.querySelector('#seek').value)`);
  await new Promise(resolve => setTimeout(resolve, 650));
  await click('#play');
  const paused = await evaluate(`Number(document.querySelector('#seek').value)`);
  assert.ok(paused > initial);
  await new Promise(resolve => setTimeout(resolve, 150));
  assert.equal(await evaluate(`Number(document.querySelector('#seek').value)`), paused);
  const total = await evaluate(`Number(document.querySelector('#seek').max)`);
  await seek(total - .1); await click('#play');
  await new Promise(resolve => setTimeout(resolve, 350));
  assert.equal(await text('#play-label'), 'Play again');
  await capture('17-recovered-desktop');
  // Keyboard navigation and mobile layout.
  await evaluate('document.activeElement.blur()');
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowLeft', code: 'ArrowLeft' });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'ArrowLeft', code: 'ArrowLeft' });
  assert.match(await text('#chapter-title'), /Read the relationships/);
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 1050, deviceScaleFactor: 1, mobile: true });
  await click('[data-chapter="0"]'); await seek(16); await evaluate('window.scrollTo(0,0)');
  assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth'), true);
  await capture('01-overview-mobile');
  await click('[data-chapter="10"]'); await click('[data-action="cheapest"]'); await evaluate('window.scrollTo(0,300)');
  assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth'), true);
  await capture('11-equations-mobile');
  for (const width of [320, 768, 1024]) {
    await send('Emulation.setDeviceMetricsOverride', { width, height: 1050, deviceScaleFactor: 1, mobile: width < 800 });
    for (let i = 0; i < 17; i++) {
      await click(`[data-chapter="${i}"]`);
      assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth'), true, `Overflow at width ${width}, chapter ${i + 1}`);
    }
  }
  // Local-file deep link and reduced-motion mode also load independently.
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
  await navigate(`${url}?reduced-motion-check=1#chapter=17`); await ready();
  assert.match(await text('#chapter-title'), /HELLO again/);
  assert.equal(await text('#play-label'), 'Continue');
  await click('[data-chapter="10"]');
  assert.match(await text('#drawing'), /Both equations match · total change cost 3/);
  await click('[data-action="pixel"][data-value="0"]');
  assert.match(await text('#drawing'), /Equations do not match yet · total change cost 11/);
  assert.deepEqual(errors, []);
  assert.deepEqual(externalRequests, []);
  const result = { passed: true, chapters: 17, durationSeconds: total, toyPatternsChecked: 16, errors, externalRequests, checks: ['file URL', 'frame arithmetic', 'XOR reversal', 'pixel equations', 'SVG bounds', 'balancing toggle', 'markers', 'comparison slider', 'play/pause/end', 'mobile width', 'deep link', 'reduced motion'] };
  await writeFile(path.join(output, 'verification.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
  await send('Browser.close', {}, undefined).catch(() => {});
} finally {
  if (ws) ws.close();
  chrome.kill();
}
