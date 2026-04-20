// Typed fetch wrappers against the FastAPI backend.
// In dev, Vite proxies /api → http://127.0.0.1:8000; in prod same-origin.

export type CropMode =
  | "auto"
  | "center"
  | "event"
  | "webcam_chat_stack"
  | "webcam_chat_stack_bottom"
  | "bottom_split_stack";

export type FollowMode = "auto" | "face" | "person" | "off";
export type FollowSmoothing = "low" | "medium" | "high";
export type Platform = "youtube" | "tiktok" | "facebook" | "instagram";
export type PublishMode = "api" | "browser";

export interface StartRunRequest {
  source: string;
  num_clips?: number;
  ollama_model?: string;
  whisper_model?: string;
  min_duration?: number;
  max_duration?: number;
  burn_captions?: boolean;
  smart_crop?: boolean;
  crop_mode?: CropMode;
  focus_region?: "full" | "center";
  letterbox_full_width?: boolean;
  follow_mode?: FollowMode;
  follow_smoothing?: FollowSmoothing;
}

export interface JobSummary {
  id: string;
  run_folder: string;
  source: string;
  status: "pending" | "running" | "done" | "failed" | "cancelled";
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  error: string | null;
  last_stage: string | null;
  last_message: string | null;
  progress: number;
}

export interface ShortInfo {
  file: string;
  title: string;
  transcript: string;
  url: string;
}

export interface RunDetail {
  run_folder: string;
  source: string;
  source_label: string;
  full_transcript: string;
  shorts: ShortInfo[];
}

export interface ProgressEvent {
  stage: string;
  message: string;
  progress: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

export const api = {
  health: () => request<{ ok: boolean; version: string }>("/api/health"),

  startRun: (body: StartRunRequest) =>
    request<JobSummary>("/api/runs", { method: "POST", body: JSON.stringify(body) }),

  listRuns: () => request<JobSummary[]>("/api/runs"),

  getRun: (runFolder: string) => request<RunDetail>(`/api/runs/${runFolder}`),

  uploadSource: async (file: File): Promise<{ path: string; name: string }> => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/uploads", { method: "POST", body: fd });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return res.json();
  },

  shortStreamUrl: (runFolder: string, filename: string) =>
    `/api/shorts/${runFolder}/${filename}`,
};

export function subscribeToRun(
  runFolder: string,
  onEvent: (e: ProgressEvent) => void,
  onEnd?: (finalStatus: string, error: string | null) => void,
): () => void {
  const es = new EventSource(`/api/runs/${runFolder}/progress`);
  es.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data) as ProgressEvent;
      onEvent(data);
    } catch {
      /* ignore malformed */
    }
  };
  es.addEventListener("end", (msg: MessageEvent) => {
    try {
      const data = JSON.parse(msg.data) as { status: string; error: string | null };
      onEnd?.(data.status, data.error);
    } catch {
      onEnd?.("done", null);
    }
    es.close();
  });
  es.onerror = () => {
    // EventSource retries automatically; we close when the job is over.
  };
  return () => es.close();
}
