import { useState } from "react";
import { api, type StartRunRequest, type CropMode, type FollowMode, type FollowSmoothing } from "@/api/client";
import { Button, Card, CardBody, CardHeader, Input, Label, Select } from "./ui";

interface Props {
  busy: boolean;
  onStarted: (runFolder: string, source: string) => void;
  onError: (message: string) => void;
}

export function SourceForm({ busy, onStarted, onError }: Props) {
  const [mode, setMode] = useState<"url" | "upload">("url");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [numClips, setNumClips] = useState(10);
  const [maxDuration, setMaxDuration] = useState(60);
  const [model, setModel] = useState("mistral");
  const [cropMode, setCropMode] = useState<CropMode>("auto");
  const [followMode, setFollowMode] = useState<FollowMode>("auto");
  const [smoothing, setSmoothing] = useState<FollowSmoothing>("medium");
  const [advanced, setAdvanced] = useState(false);
  const [whisperModel, setWhisperModel] = useState("base");
  const [letterbox, setLetterbox] = useState(false);
  const [burnCaptions, setBurnCaptions] = useState(true);

  async function handleGenerate() {
    try {
      let source = "";
      if (mode === "url") {
        source = url.trim();
        if (!source) {
          onError("Paste a video URL or switch to Upload.");
          return;
        }
      } else {
        if (!file) {
          onError("Choose a video file to upload.");
          return;
        }
        const { path } = await api.uploadSource(file);
        source = path;
      }
      const body: StartRunRequest = {
        source,
        num_clips: numClips,
        ollama_model: model,
        whisper_model: whisperModel,
        max_duration: maxDuration,
        crop_mode: cropMode,
        follow_mode: followMode,
        follow_smoothing: smoothing,
        letterbox_full_width: letterbox,
        burn_captions: burnCaptions,
      };
      const job = await api.startRun(body);
      onStarted(job.run_folder, source);
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <Card>
      <CardHeader>
        <h2 className="text-sm font-semibold tracking-tight text-neutral-100">Source</h2>
        <p className="mt-0.5 text-xs text-neutral-400">
          Paste a YouTube / Twitch / Kick VOD URL or upload a local file.
        </p>
      </CardHeader>
      <CardBody className="space-y-5">
        <div className="inline-flex rounded-lg bg-neutral-800 p-1">
          <button
            type="button"
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              mode === "url" ? "bg-neutral-950 text-neutral-100" : "text-neutral-400 hover:text-neutral-200"
            }`}
            onClick={() => setMode("url")}
          >
            URL
          </button>
          <button
            type="button"
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              mode === "upload" ? "bg-neutral-950 text-neutral-100" : "text-neutral-400 hover:text-neutral-200"
            }`}
            onClick={() => setMode("upload")}
          >
            Upload file
          </button>
        </div>

        {mode === "url" ? (
          <div>
            <Label htmlFor="src-url">Video URL</Label>
            <Input
              id="src-url"
              className="mt-1.5"
              placeholder="https://youtube.com/watch?v=… | twitch.tv/videos/… | kick.com/…"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </div>
        ) : (
          <div>
            <Label>Video file</Label>
            <div className="mt-1.5 flex items-center gap-3">
              <label className="flex h-10 cursor-pointer items-center rounded-lg border border-dashed border-neutral-700 bg-neutral-900 px-3 text-sm text-neutral-300 hover:border-sky-500/60">
                <input
                  type="file"
                  accept="video/*"
                  className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
                Choose file…
              </label>
              <span className="truncate text-sm text-neutral-400">
                {file ? file.name : "no file selected"}
              </span>
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label htmlFor="num-clips">Max shorts ({numClips})</Label>
            <input
              id="num-clips"
              type="range"
              min={1}
              max={100}
              value={numClips}
              onChange={(e) => setNumClips(Number(e.target.value))}
              className="mt-2 w-full accent-sky-500"
            />
          </div>
          <div>
            <Label htmlFor="max-dur">Max clip length ({maxDuration}s)</Label>
            <input
              id="max-dur"
              type="range"
              min={30}
              max={90}
              step={5}
              value={maxDuration}
              onChange={(e) => setMaxDuration(Number(e.target.value))}
              className="mt-2 w-full accent-sky-500"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label htmlFor="crop">Layout</Label>
            <Select id="crop" className="mt-1.5" value={cropMode} onChange={(e) => setCropMode(e.target.value as CropMode)}>
              <option value="auto">Auto (detect)</option>
              <option value="center">Speaker only (center)</option>
              <option value="event">Event / news (group & action)</option>
              <option value="webcam_chat_stack">Streaming: webcam top, chat bottom</option>
              <option value="webcam_chat_stack_bottom">Streaming: webcam bottom-left, chat bottom-right</option>
              <option value="bottom_split_stack">Split screen (left & right stacked)</option>
            </Select>
          </div>
          <div>
            <Label htmlFor="follow">Follow subject</Label>
            <Select id="follow" className="mt-1.5" value={followMode} onChange={(e) => setFollowMode(e.target.value as FollowMode)}>
              <option value="auto">Auto (face → person)</option>
              <option value="face">Face only</option>
              <option value="person">Person (YOLO)</option>
              <option value="off">Off (static crop)</option>
            </Select>
          </div>
        </div>

        <div>
          <button
            type="button"
            className="text-xs text-neutral-400 hover:text-neutral-200"
            onClick={() => setAdvanced((v) => !v)}
          >
            {advanced ? "Hide advanced" : "Show advanced"}
          </button>
          {advanced && (
            <div className="mt-3 grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="adv-smooth">Follow smoothing</Label>
                <Select id="adv-smooth" className="mt-1.5" value={smoothing} onChange={(e) => setSmoothing(e.target.value as FollowSmoothing)}>
                  <option value="low">Low (snappy)</option>
                  <option value="medium">Medium</option>
                  <option value="high">High (very smooth)</option>
                </Select>
              </div>
              <div>
                <Label htmlFor="adv-ollama">Ollama model</Label>
                <Select id="adv-ollama" className="mt-1.5" value={model} onChange={(e) => setModel(e.target.value)}>
                  <option value="mistral">mistral</option>
                  <option value="llama3.1">llama3.1</option>
                  <option value="llama3.2">llama3.2</option>
                  <option value="llama3.3">llama3.3</option>
                  <option value="gemma2">gemma2</option>
                  <option value="phi3">phi3</option>
                </Select>
              </div>
              <div>
                <Label htmlFor="adv-whisper">Whisper model</Label>
                <Select id="adv-whisper" className="mt-1.5" value={whisperModel} onChange={(e) => setWhisperModel(e.target.value)}>
                  <option value="tiny">tiny</option>
                  <option value="base">base</option>
                  <option value="small">small</option>
                  <option value="medium">medium</option>
                  <option value="large-v3">large-v3</option>
                </Select>
              </div>
              <div className="flex items-end gap-4">
                <label className="flex items-center gap-2 text-xs text-neutral-300">
                  <input
                    type="checkbox"
                    className="size-4 accent-sky-500"
                    checked={burnCaptions}
                    onChange={(e) => setBurnCaptions(e.target.checked)}
                  />
                  Burn captions
                </label>
                <label className="flex items-center gap-2 text-xs text-neutral-300">
                  <input
                    type="checkbox"
                    className="size-4 accent-sky-500"
                    checked={letterbox}
                    onChange={(e) => setLetterbox(e.target.checked)}
                  />
                  Letterbox (no horizontal crop)
                </label>
              </div>
            </div>
          )}
        </div>

        <Button size="lg" className="w-full" disabled={busy} onClick={handleGenerate}>
          {busy ? "Working…" : "Generate shorts"}
        </Button>
      </CardBody>
    </Card>
  );
}
