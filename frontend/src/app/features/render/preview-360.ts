import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  afterNextRender,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import {
  BackSide,
  Mesh,
  MeshBasicMaterial,
  PerspectiveCamera,
  Raycaster,
  Scene,
  SphereGeometry,
  SRGBColorSpace,
  TextureLoader,
  Vector2,
  WebGLRenderer,
} from 'three';

import { TapPoint, dragView, isTap, roundTap } from './equirect-math';

const FOV_DEG = 75;
const DEG = Math.PI / 180;

/**
 * Draggable 360 preview. Drag to look around, tap to pick the subject to follow. The tap leaves as
 * a point on the flat frame, ready for the worker. Spec: specs/08-osmo360.md#ui-additions
 */
@Component({
  selector: 'app-preview-360',
  template: `
    <canvas
      #canvas
      class="canvas"
      role="img"
      aria-label="360 preview. Drag to look around, tap to pick the subject to follow."
      (pointerdown)="down($event)"
      (pointermove)="move($event)"
      (pointerup)="up($event)"
      (pointercancel)="cancel()"
    ></canvas>
    @if (unavailable()) {
      <p class="muted">The 360 preview needs WebGL, which this browser does not offer.</p>
    }
  `,
  styles: `
    .canvas {
      display: block;
      width: 100%;
      aspect-ratio: 16 / 9;
      background: #000;
      border-radius: 8px;
      cursor: grab;
      touch-action: none;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Preview360 implements OnDestroy {
  /** An equirectangular (2:1) frame of the clip. */
  readonly imageUrl = input.required<string>();
  readonly picked = output<TapPoint>();

  protected readonly unavailable = signal(false);

  private readonly canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('canvas');
  private renderer: WebGLRenderer | null = null;
  private readonly scene = new Scene();
  private readonly camera = new PerspectiveCamera(FOV_DEG, 16 / 9, 0.1, 100);
  private sphere: Mesh | null = null;
  private yawDeg = 0;
  private pitchDeg = 0;
  private start: { x: number; y: number } | null = null;
  private last = { x: 0, y: 0 };

  constructor() {
    afterNextRender(() => this.setUp());
  }

  ngOnDestroy(): void {
    const material = this.sphere?.material as MeshBasicMaterial | undefined;
    this.sphere?.geometry.dispose();
    material?.map?.dispose();
    material?.dispose();
    this.renderer?.dispose();
  }

  protected down(event: PointerEvent): void {
    this.start = { x: event.clientX, y: event.clientY };
    this.last = { x: event.clientX, y: event.clientY };
    this.canvas().nativeElement.setPointerCapture?.(event.pointerId);
  }

  protected move(event: PointerEvent): void {
    if (!this.start) {
      return;
    }
    const view = dragView(
      this.yawDeg,
      this.pitchDeg,
      event.clientX - this.last.x,
      event.clientY - this.last.y,
      FOV_DEG,
      this.canvas().nativeElement.clientHeight,
    );
    this.yawDeg = view.yawDeg;
    this.pitchDeg = view.pitchDeg;
    this.last = { x: event.clientX, y: event.clientY };
    this.draw();
  }

  protected up(event: PointerEvent): void {
    const start = this.start;
    this.start = null;
    if (start && isTap(event.clientX - start.x, event.clientY - start.y)) {
      this.tap(event);
    }
  }

  protected cancel(): void {
    this.start = null;
  }

  private tap(event: PointerEvent): void {
    const box = this.canvas().nativeElement.getBoundingClientRect();
    if (!this.sphere || box.width === 0 || box.height === 0) {
      return;
    }
    const ndc = new Vector2(
      ((event.clientX - box.left) / box.width) * 2 - 1,
      -(((event.clientY - box.top) / box.height) * 2 - 1),
    );
    const caster = new Raycaster();
    caster.setFromCamera(ndc, this.camera);
    const hit = caster.intersectObject(this.sphere)[0];
    if (hit?.uv) {
      // uv origin is the bottom left of the texture, the frame's origin is the top left.
      this.picked.emit(roundTap({ x: hit.uv.x, y: 1 - hit.uv.y }));
    }
  }

  private setUp(): void {
    try {
      this.renderer = new WebGLRenderer({ canvas: this.canvas().nativeElement, antialias: true });
    } catch {
      this.unavailable.set(true);
      return;
    }
    const texture = new TextureLoader().load(this.imageUrl(), () => this.draw());
    texture.colorSpace = SRGBColorSpace;
    this.sphere = new Mesh(
      new SphereGeometry(10, 64, 32),
      new MeshBasicMaterial({ map: texture, side: BackSide }),
    );
    // Mirror x so the inside of the sphere shows the frame the right way round.
    this.sphere.scale.x = -1;
    this.scene.add(this.sphere);
    this.camera.rotation.order = 'YXZ';
    this.draw();
  }

  private draw(): void {
    const renderer = this.renderer;
    if (!renderer) {
      return;
    }
    const element = this.canvas().nativeElement;
    const width = element.clientWidth || 640;
    const height = element.clientHeight || 360;
    renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.camera.rotation.set(this.pitchDeg * DEG, this.yawDeg * DEG, 0);
    this.camera.updateMatrixWorld();
    renderer.render(this.scene, this.camera);
  }
}
