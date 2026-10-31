// Plays a finished render to the end in the installed Chrome and reads getVideoPlaybackQuality().
// Spec: specs/10-roadmap.md#phase-4--ultra-quality [T-412]. Started by scripts/phase4_gate.py.
//
// node phase4_playback.mjs <baseUrl> <renderId> <durationSec> <timeoutSec> <headed|headless> <out.json>
//
// Two pages are measured: a bare <video> on the download URL, and the app's own render page
// (/renders/<id>). Playwright comes from frontend/node_modules; the browser is the installed
// Chrome (channel "chrome"), so the machine's own hardware decoders are what get tested.
import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(here, '..', 'frontend', 'package.json'));
const { chromium } = require('@playwright/test');

const [baseUrl, renderId, durationArg, timeoutArg, display, out] = process.argv.slice(2);
const duration = Number(durationArg);
const timeoutMs = Number(timeoutArg) * 1000;
const download = `/api/renders/${renderId}/download`;

// Runs inside the page. Starts the video, waits for it to end, reports what Chrome says.
async function playThrough({ selector, src, timeout }) {
  let video = selector ? document.querySelector(selector) : null;
  if (!video) {
    video = document.createElement('video');
    video.muted = false;
    video.style.cssText = 'position:fixed;left:0;top:0;width:360px;height:640px;background:#000';
    document.body.append(video);
  }
  if (src) video.src = src;
  const log = { waiting: 0, stalled: 0, seeks: 0 };
  video.addEventListener('waiting', () => log.waiting++);
  video.addEventListener('stalled', () => log.stalled++);
  video.addEventListener('seeking', () => log.seeks++);
  await new Promise((resolve) => {
    if (video.readyState >= 1) return resolve();
    video.addEventListener('loadedmetadata', resolve, { once: true });
    video.addEventListener('error', resolve, { once: true });
  });
  const info = { width: video.videoWidth, height: video.videoHeight, duration: video.duration };
  const started = performance.now();
  const timeline = [];
  let playError = null;
  video.currentTime = 0;
  try {
    await video.play();
  } catch (error) {
    playError = String(error);
  }
  const ended = await new Promise((resolve) => {
    const tick = setInterval(() => {
      const quality = video.getVideoPlaybackQuality();
      timeline.push([
        Math.round(performance.now() - started),
        Number(video.currentTime.toFixed(2)),
        quality.totalVideoFrames,
        quality.droppedVideoFrames,
      ]);
      if (video.ended) done(true);
      if (video.error) done(false);
      if (performance.now() - started > timeout) done(false);
    }, 1000);
    function done(value) {
      clearInterval(tick);
      resolve(value);
    }
  });
  const quality = video.getVideoPlaybackQuality();
  return {
    ...info,
    ended,
    playError,
    error: video.error ? `${video.error.code}: ${video.error.message}` : null,
    totalFrames: quality.totalVideoFrames,
    droppedFrames: quality.droppedVideoFrames,
    corruptedFrames: quality.corruptedVideoFrames,
    currentTime: video.currentTime,
    playedSeconds: (performance.now() - started) / 1000,
    waitingEvents: log.waiting,
    stalledEvents: log.stalled,
    timelineSamples: timeline.length,
    timelineTail: timeline.slice(-3),
    timelineEvery30: timeline.filter((_, index) => index % 30 === 0),
    currentSrc: video.currentSrc,
  };
}

// What Chrome says about 10-bit HEVC before playing anything.
async function capabilities(page) {
  return page.evaluate(async () => {
    const probe = document.createElement('video');
    const types = {};
    for (const codec of ['hvc1.2.4.L186.B0', 'hvc1.2.4.L153.B0', 'hev1.2.4.L186.B0']) {
      types[codec] = probe.canPlayType(`video/mp4; codecs="${codec}"`);
    }
    let decoding = null;
    try {
      const info = await navigator.mediaCapabilities.decodingInfo({
        type: 'file',
        video: {
          contentType: 'video/mp4; codecs="hvc1.2.4.L186.B0"',
          width: 4320,
          height: 7680,
          bitrate: 100_000_000,
          framerate: 30,
        },
      });
      decoding = {
        supported: info.supported,
        smooth: info.smooth,
        powerEfficient: info.powerEfficient,
      };
    } catch (error) {
      decoding = { error: String(error) };
    }
    return { canPlayType: types, decoding8k: decoding };
  });
}

const browser = await chromium.launch({
  channel: 'chrome',
  headless: display === 'headless',
  args: ['--autoplay-policy=no-user-gesture-required'],
});
const result = { browser: browser.version(), channel: 'chrome', display, pages: {} };
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  page.on('console', (message) => {
    if (message.type() === 'error') console.log('[console error]', message.text());
  });
  await page.goto(`${baseUrl}/api/system`);
  result.capabilities = await capabilities(page);
  console.log('capabilities', JSON.stringify(result.capabilities));

  result.pages.download = await page.evaluate(playThrough, {
    selector: null,
    src: download,
    timeout: timeoutMs,
  });
  console.log('download page', JSON.stringify({ ...result.pages.download, timelineEvery30: undefined }));

  const app = await context.newPage();
  await app.goto(`${baseUrl}/renders/${renderId}`, { waitUntil: 'domcontentloaded' });
  await app.waitForSelector('video', { timeout: 60_000 });
  result.pages.appPage = await app.evaluate(playThrough, {
    selector: 'video',
    src: null,
    timeout: timeoutMs,
  });
  console.log('app page', JSON.stringify({ ...result.pages.appPage, timelineEvery30: undefined }));
} catch (error) {
  result.scriptError = String(error);
  console.log('script error', String(error));
} finally {
  await browser.close();
  result.expectedSeconds = duration;
  writeFileSync(out, JSON.stringify(result, null, 1));
}
