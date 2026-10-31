import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

/** Small generated media for the e2e run (no real footage, no 4K gate clips). */
export const MEDIA_DIR = resolve(__dirname, '..', 'e2e-media');

function ffmpeg(args: string[]): void {
  const result = spawnSync('ffmpeg', ['-y', '-loglevel', 'error', ...args], { encoding: 'utf8' });
  if (result.status !== 0) {
    throw new Error(`ffmpeg failed (is it on PATH? run scripts\\e2e.bat): ${result.stderr}`);
  }
}

function make(name: string, args: string[]): string {
  mkdirSync(MEDIA_DIR, { recursive: true });
  const path = resolve(MEDIA_DIR, name);
  if (!existsSync(path)) {
    ffmpeg([...args, path]);
  }
  return path;
}

const VIDEO_CODEC = ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-preset', 'veryfast'];

export function generateMedia(): { clips: string[]; song: string; equirect: string } {
  const clipA = make('clip-a.mp4', [
    '-f',
    'lavfi',
    '-i',
    'testsrc2=size=1280x720:rate=30:duration=8',
    '-f',
    'lavfi',
    '-i',
    'sine=frequency=330:duration=8',
    ...VIDEO_CODEC,
    '-c:a',
    'aac',
    '-shortest',
  ]);
  const clipB = make('clip-b.mp4', [
    '-f',
    'lavfi',
    '-i',
    'mandelbrot=size=1280x720:rate=30',
    '-t',
    '8',
    ...VIDEO_CODEC,
  ]);
  // A 120 BPM kick plus a hat: enough for beat tracking and a waveform with sections.
  const song = make('song.mp3', [
    '-f',
    'lavfi',
    '-i',
    "aevalsrc='0.8*sin(2*PI*(55+80*exp(-30*mod(t,0.5)))*t)*exp(-6*mod(t,0.5))+0.2*sin(2*PI*880*t)*exp(-25*mod(t+0.25,0.5))*(gte(t,12))':d=24:s=44100",
    '-c:a',
    'libmp3lame',
    '-b:a',
    '128k',
  ]);
  const equirect = make('pano.mp4', [
    '-f',
    'lavfi',
    '-i',
    'testsrc2=size=2048x1024:rate=30:duration=6',
    ...VIDEO_CODEC,
  ]);
  return { clips: [clipA, clipB], song, equirect };
}
