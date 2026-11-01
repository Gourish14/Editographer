/** API shapes. Spec: specs/07-api-and-data.md */

export interface Project {
  readonly id: string;
  readonly name: string;
  readonly createdAt: string;
}

export type AssetType = 'VIDEO' | 'PHOTO' | 'MUSIC';
export type AnalysisStatus = 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED';

export interface Asset {
  readonly id: string;
  readonly projectId: string;
  readonly type: AssetType;
  readonly filename: string;
  readonly sizeBytes: number;
  readonly analysisStatus: AnalysisStatus;
  readonly durationSec: number | null;
  readonly width: number | null;
  readonly height: number | null;
  readonly fps: number | null;
  readonly cameraMode: string | null;
  readonly logProfile: string | null;
  readonly createdAt: string;
}

export type RenderStatus =
  | 'QUEUED'
  | 'ANALYZING'
  | 'PLANNING'
  | 'COMPOSING'
  | 'UPSCALING'
  | 'ENCODING'
  | 'DONE'
  | 'FAILED'
  | 'CANCELLED';

export interface RenderSettings {
  readonly ratio: string;
  readonly quality: string;
  readonly fps: number;
  readonly style: string;
  readonly mode: string;
  readonly lengthSec: number | null;
  readonly prompt: string | null;
  readonly coolMode: boolean;
  readonly seed: number;
  /** "Render tonight": the render waits in the queue until this ISO time. */
  readonly startAt: string | null;
  /** The tap that picks the subject to follow in 360 footage. */
  readonly followPoint: FollowPoint | null;
}

export interface FollowPoint {
  /** 0 to 1 from the left of the frame. */
  readonly x: number;
  /** 0 to 1 from the top of the frame. */
  readonly y: number;
  readonly timeSec: number;
  /** The 360 clip the point was tapped on. Null means the first 360 clip. */
  readonly assetId: string | null;
}

export type NewRender = Partial<Omit<RenderSettings, 'seed'>>;

export interface EditPlanSummary {
  readonly style: string;
  readonly segments: readonly { readonly effects: readonly unknown[] }[];
  readonly log: readonly string[];
}

export interface Render {
  readonly id: string;
  readonly projectId: string;
  readonly settings: RenderSettings;
  readonly status: RenderStatus;
  readonly stage: string | null;
  readonly progress: number;
  readonly editPlan: EditPlanSummary | null;
  readonly previewReady: boolean;
  readonly finalReady: boolean;
  readonly error: string | null;
  readonly createdAt: string;
  readonly finishedAt: string | null;
}

export interface ProjectDetail {
  readonly project: Project;
  readonly assets: readonly Asset[];
  readonly renders: readonly Render[];
}

export interface StylePreset {
  readonly id: string;
  readonly name: string;
}

export interface GpuStatus {
  readonly name: string;
  readonly vramFreeMb: number;
  readonly tempC: number;
}

export interface SystemStatus {
  readonly workerOnline: boolean;
  readonly workerBusy: boolean;
  readonly ollamaOnline: boolean;
  readonly gpu: GpuStatus | null;
}

export interface WaveformSection {
  readonly kind: string;
  readonly start: number;
  readonly end: number;
}

export interface Waveform {
  readonly durationSec: number;
  readonly peaks: readonly number[];
  readonly beats: readonly number[];
  readonly downbeats: readonly number[];
  readonly sections: readonly WaveformSection[];
}

export interface ProblemDetail {
  readonly detail?: string;
  readonly errorCode?: string;
  readonly requestId?: string;
}

export type RenderEvent =
  | {
      readonly type: 'progress';
      readonly stage: string;
      readonly percent: number;
      readonly message: string;
    }
  | { readonly type: 'preview-ready' }
  | { readonly type: 'done' }
  | { readonly type: 'failed'; readonly error: string };
