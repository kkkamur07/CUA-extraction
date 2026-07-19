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

export type CornerMasks = {
  bottom_left: CropROI;
  bottom_right: CropROI;
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
  corner_masks: CornerMasks;
};

export type VideoInfo = {
  name: string;
  id: string;
  path: string;
  sizeBytes: number;
  hasSelection: boolean;
  /** True when published final artifacts exist under data/<id>/. */
  hasFinalOutput: boolean;
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

export function defaultCornerMasks(
  screen: CropROI,
  keyboard: CropROI,
): CornerMasks {
  const left = Math.max(screen.x, keyboard.x);
  const top = Math.max(screen.y, keyboard.y);
  const right = Math.min(screen.x + screen.width, keyboard.x + keyboard.width);
  const bottom = Math.min(screen.y + screen.height, keyboard.y + keyboard.height);
  const leftMask =
    left < right && top < bottom
      ? {
          x: 0,
          y: top - screen.y,
          width: right - screen.x,
          height: screen.height - (top - screen.y),
        }
      : {
          x: 0,
          y: Math.max(0, screen.height - Math.min(200, screen.height)),
          width: Math.min(360, screen.width),
          height: Math.min(200, screen.height),
        };
  const timerWidth = Math.min(300, screen.width);
  const timerY = Math.min(
    screen.height,
    Math.max(0, Math.round(screen.height * 0.45)),
  );
  return {
    bottom_left: leftMask,
    bottom_right: {
      x: screen.width - timerWidth,
      y: timerY,
      width: timerWidth,
      height: screen.height - timerY,
    },
  };
}

/** Cursor track filtering thresholds (applied to raw YOLO detections). */
export type CursorFilterCriteria = {
  min_confidence: number;
  min_move_px: number;
};

export const DEFAULT_CURSOR_FILTER: CursorFilterCriteria = {
  min_confidence: 0.4,
  min_move_px: 4,
};

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
