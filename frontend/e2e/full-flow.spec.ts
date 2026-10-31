import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

import { expect, Page, test } from '@playwright/test';

import { generateMedia } from './media';

/**
 * The whole app in a real browser: upload, analysis, settings, a Preview render, download,
 * regenerate, cancel, delete. Spec: specs/07-api-and-data.md#angular-screens
 */
const SHOTS = resolve(__dirname, '..', 'e2e-screenshots');
const DESKTOP = { width: 1280, height: 800 };
const PHONE = { width: 390, height: 844 };

let step = 0;

/** One screenshot at desktop width and one at phone width. */
async function shoot(page: Page, name: string): Promise<void> {
  step += 1;
  const label = `${String(step).padStart(2, '0')}-${name}`;
  for (const [kind, size] of [
    ['desktop', DESKTOP],
    ['phone', PHONE],
  ] as const) {
    await page.setViewportSize(size);
    await page.waitForTimeout(250);
    await page.screenshot({ path: resolve(SHOTS, `${label}-${kind}.png`), fullPage: true });
    if (kind === 'phone') {
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `${label} scrolls sideways on a phone`).toBeLessThanOrEqual(0);
    }
  }
  await page.setViewportSize(DESKTOP);
}

test('create, upload, analyze, render a preview, download, regenerate, cancel, delete', async ({
  page,
  request,
}) => {
  mkdirSync(SHOTS, { recursive: true });
  const media = generateMedia();
  const problems: string[] = [];
  page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error') {
      problems.push(`console: ${message.text()}`);
    }
  });
  await page.setViewportSize(DESKTOP);

  // Projects
  await page.goto('/');
  await expect(page.getByText('Worker online')).toBeVisible();
  await shoot(page, 'projects-empty');
  const name = `E2E ${Date.now()}`;
  await page.getByLabel('New project name').fill(name);
  await page.getByRole('button', { name: 'New project' }).click();
  await page.getByRole('link', { name }).click();
  await expect(page.getByRole('heading', { name })).toBeVisible();
  const projectUrl = page.url();
  const projectId = projectUrl.split('/').pop() ?? '';
  await shoot(page, 'project-empty');

  // Upload two clips and a song, then wait for analysis
  await page.getByLabel('Choose files to upload').setInputFiles([...media.clips, media.song]);
  await expect(page.getByRole('article')).toHaveCount(3);
  await expect(page.getByText('Ready')).toHaveCount(3, { timeout: 10 * 60_000 });
  await expect(page.getByRole('region', { name: 'Music' })).toBeVisible();
  await expect(page.locator('app-music-waveform .section').first()).toBeVisible();
  for (const image of await page.locator('app-asset-grid img').all()) {
    await expect
      .poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth))
      .toBeGreaterThan(0);
  }
  await shoot(page, 'project-analyzed');

  // Settings
  await page.getByRole('link', { name: 'Render' }).click();
  await expect(page.getByRole('heading', { name: 'Render settings' })).toBeVisible();
  await page.getByLabel('Render mode').click();
  await page.getByRole('option', { name: 'Preview' }).click();
  await shoot(page, 'render-settings');
  await page.getByRole('button', { name: 'Start render' }).click();

  // Live progress, then the video
  await expect(page.getByRole('region', { name: 'Progress' })).toBeVisible();
  // The bar moves while the render runs: some percentage above zero shows up before "done".
  const percentText = page.getByRole('region', { name: 'Progress' }).locator('.muted');
  await expect
    .poll(
      async () => {
        if (await page.locator('app-status-badge').filter({ hasText: 'done' }).count()) {
          return 100;
        }
        return Number.parseInt((await percentText.textContent().catch(() => '0')) ?? '0', 10);
      },
      { timeout: 10 * 60_000, intervals: [250] },
    )
    .toBeGreaterThan(0);
  await shoot(page, 'render-progress');
  await expect(page.locator('app-status-badge').filter({ hasText: 'done' })).toBeVisible({
    timeout: 12 * 60_000,
  });
  const video = page.locator('video');
  await expect(video).toBeVisible();
  await expect
    .poll(() => video.evaluate((element: HTMLVideoElement) => element.videoWidth))
    .toBeGreaterThan(0);
  const box = await video.boundingBox();
  expect(box && box.height > box.width, '9:16 render shows as a tall video').toBe(true);
  await shoot(page, 'render-done');

  // Download
  const downloading = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Download' }).click();
  const download = await downloading;
  expect(download.suggestedFilename()).toMatch(/\.mp4$/);

  // Make another version, then cancel it
  const firstUrl = page.url();
  await page.getByRole('button', { name: 'Make another version' }).click();
  await expect(page).not.toHaveURL(firstUrl);
  await expect(page.getByRole('region', { name: 'Progress' })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.locator('app-status-badge').filter({ hasText: 'cancelled' })).toBeVisible();
  await shoot(page, 'render-cancelled');

  // Project lists both renders; remove an asset; delete the project
  await page.getByRole('link', { name: 'Back to project' }).click();
  await expect(page.getByRole('region', { name: 'Renders' }).getByRole('link')).toHaveCount(2);
  await shoot(page, 'project-with-renders');
  await page.getByRole('button', { name: 'Remove' }).first().click();
  await expect(page.getByRole('article')).toHaveCount(2);
  await expect
    .poll(
      async () =>
        (await request.delete(`http://127.0.0.1:18080/api/projects/${projectId}`)).status(),
      {
        timeout: 60_000,
      },
    )
    .toBe(204);

  expect(problems, 'browser console errors').toEqual([]);
});

test('a 360 clip shows the WebGL preview and lets you pick a subject to follow', async ({
  page,
  request,
}) => {
  mkdirSync(SHOTS, { recursive: true });
  const media = generateMedia();
  const problems: string[] = [];
  page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`));
  await page.setViewportSize(DESKTOP);

  await page.goto('/');
  const name = `E2E 360 ${Date.now()}`;
  await page.getByLabel('New project name').fill(name);
  await page.getByRole('button', { name: 'New project' }).click();
  await page.getByRole('link', { name }).click();
  await expect(page.getByRole('heading', { name })).toBeVisible();
  const projectId = page.url().split('/').pop() ?? '';

  await page.getByLabel('Choose files to upload').setInputFiles(media.equirect);
  await expect(page.getByText('Ready')).toHaveCount(1, { timeout: 10 * 60_000 });
  await expect(page.locator('app-asset-grid').getByText('360', { exact: true })).toBeVisible();
  await shoot(page, '360-project');

  await page.goto(`/projects/${projectId}/render`);
  const canvas = page.getByRole('img', { name: /360 preview/ });
  await expect(canvas).toBeVisible();
  await expect(page.getByText('needs WebGL')).toHaveCount(0);
  // The canvas must show the frame, not a black box. A WebGL canvas cannot be read back with
  // drawImage once composited, so decode a screenshot of it instead.
  await canvas.scrollIntoViewIfNeeded();
  await expect
    .poll(async () => {
      const png = (await canvas.screenshot()).toString('base64');
      return page.evaluate(async (data) => {
        const bitmap = await createImageBitmap(
          await (await fetch(`data:image/png;base64,${data}`)).blob(),
        );
        const copy = document.createElement('canvas');
        copy.width = 64;
        copy.height = 36;
        const context = copy.getContext('2d');
        context?.drawImage(bitmap, 0, 0, 64, 36);
        const pixels = context?.getImageData(0, 0, 64, 36).data ?? new Uint8ClampedArray();
        let lit = 0;
        for (let index = 0; index < pixels.length; index += 4) {
          lit += pixels[index] + pixels[index + 1] + pixels[index + 2] > 60 ? 1 : 0;
        }
        return lit;
      }, png);
    })
    .toBeGreaterThan(500);
  const box = await canvas.boundingBox();
  if (box) {
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 120, box.y + box.height / 2, { steps: 6 });
    await page.mouse.up();
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  }
  await expect(page.getByText(/Following the spot at/)).toBeVisible();
  await shoot(page, '360-settings');

  const deleted = await request.delete(`http://127.0.0.1:18080/api/projects/${projectId}`);
  expect(deleted.ok()).toBe(true);
  expect(problems).toEqual([]);
});
