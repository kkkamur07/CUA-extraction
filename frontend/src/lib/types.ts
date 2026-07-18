export type CropROI = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type TrackKind = "screen" | "keyboard";

export type TrackSelection = {
  roi: CropROI;
  start: number;
  end: number;
  preview_timestamp: number;
};

export type ProjectSelection = {
  id: string;
  video: string;
  fps: number;
  frame_width: number;
  frame_height: number;
  /** Screen track flattened for existing YOLO/CLI scripts. */
  preview_timestamp: number;
  roi: CropROI;
  start: number;
  end: number;
  screen: TrackSelection;
  keyboard: TrackSelection;
};

export type VideoInfo = {
  name: string;
  id: string;
  path: string;
  sizeBytes: number;
  hasSelection: boolean;
};

export type AnnotationRecord = {
  label: string;
  frame_number: number;
  timestamp_seconds: number;
  x: number;
  y: number;
  width: number;
  height: number;
  center_x: number;
  center_y: number;
  ambiguous: boolean;
  path: string;
  track: TrackKind;
};

export function defaultTrack(
  width: number,
  height: number,
  duration: number,
): TrackSelection {
  return {
    roi: {
      x: 0,
      y: 0,
      width: Math.max(16, width),
      height: Math.max(16, height),
    },
    start: 0,
    end: duration,
    preview_timestamp: 0,
  };
}

export function flattenScreen(selection: ProjectSelection): ProjectSelection {
  return {
    ...selection,
    preview_timestamp: selection.screen.preview_timestamp,
    roi: selection.screen.roi,
    start: selection.screen.start,
    end: selection.screen.end,
  };
}

/** One labeled tutorial step: Action + Intent over a shared time range. */
export type ActionIntentPair = {
  action: string;
  intent: string;
  start_t: number;
  end_t: number;
  /** Optional verbatim transcript evidence (keyboard_detector convention). */
  quote?: string;
};

/** Cursor observation published as a Raw event. */
export type CursorRawEvent = {
  type: "cursor";
  t: number;
  x: number;
  y: number;
  confidence: number;
  click_candidate: boolean;
};

/** Keystroke published as a Raw event (physical press–release). */
export type KeystrokeRawEvent = {
  type: "keystroke";
  key: string;
  press_t: number;
  release_t: number;
  clipped: boolean;
};

export type RawEvent = CursorRawEvent | KeystrokeRawEvent;

/**
 * Published unit for one Processing run: Workflow summary, Action–Intent pairs,
 * and Raw events (cursor observations + keystrokes).
 */
export type WorkflowSample = {
  id: string;
  summary: string;
  action_intent_pairs: ActionIntentPair[];
  raw_events: RawEvent[];
};
