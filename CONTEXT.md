# Cursor Video Dataset

This project extracts aligned multimodal tutorial evidence from screen-recorded videos: cursor motion, keystrokes, and narrated action–intent pairs.

## Language

**Source frame**: One original video frame processed at the source resolution and frame rate. A source frame may contain both the application screen and a keyboard view in a single composition.

**Crop ROI**: The rectangular application area selected from a source frame.
_Avoid_: Screen extraction

**Keyboard ROI**: The rectangular on-screen keyboard area selected from the same source frame. The keyboard view is geometrically fixed across the recording, so key identities can be recovered from that stable layout.
_Avoid_: Keyboard extraction (when that implies separate footage or a separate time range)

**Cursor observation**: A cursor position, confidence score, and optional click candidate associated with one source frame.

**Cursor annotation**: A human-drawn bounding box and cursor-class label on one **Crop ROI** frame, used as training evidence for the cursor detector.
_Avoid_: Template (when naming the concept; the on-disk folder may still be called `templates`)

**Cursor appearance class**: The visual kind recorded on a **Cursor annotation** (for example arrow, pencil, or crosshair). Used to stratify train/validation even when the detector itself is trained as one detection class.
_Avoid_: YOLO class (when meaning the annotation appearance label under a one-class detector)

**Processing run**: One extraction over a selected source video, time range, crop ROI, keyboard ROI, and cursor detector configuration.

**Click candidate**: A heuristic indication that a click may have occurred; it is not guaranteed mouse-event telemetry.

**Action**: The observable UI behavior the author performs during a span of the tutorial (for example, clicking a tool or dragging a face).

**Intent**: The narrated goal the author is trying to achieve during that same span (for example, creating a boss feature).

**Action–Intent pair**: One labeled tutorial step that binds an **Action** and an **Intent** to a shared time range. For the initial dataset, pairs are derived from author narration alone; cursor and keystroke tracks may later support more robust pairing but are not required for a valid pair.

**Workflow summary**: One speech-derived overview of the whole tutorial span covered by a processing run — the goal and outcome of the session, not a per-step label.

**Raw event**: A timestamped low-level observation recovered from video evidence (for example a cursor observation or a keystroke). Raw events are not Action–Intent pairs.

**Keystroke**: One recovered press–release interval for a single physical key in the **Keyboard ROI**, with press time, release time, and key identity. Modifier chords appear as overlapping keystrokes, not as a single combined symbol.
_Avoid_: Logical typed character (e.g. treating Shift+A as one event)

**Workflow sample**: The published unit for one processing run: a workflow summary, ordered action–intent pairs, and a raw-event stream.

## Relationships

- A **Processing run** contains zero or more **Cursor observations**.
- Each **Cursor observation** belongs to exactly one **Source frame**.
- A **Cursor annotation** belongs to exactly one **Source frame** and is drawn within the **Crop ROI**.
- A **Cursor annotation** has exactly one **Cursor appearance class**.
- **Cursor annotations** train the cursor detector that later produces **Cursor observations**.
- A **Processing run** uses exactly one **Crop ROI**, exactly one **Keyboard ROI**, and one selected time range.
- A **Click candidate** may be attached to a **Cursor observation**.
- An **Action–Intent pair** covers a contiguous time range within a **Processing run**.
- An **Action–Intent pair** has exactly one **Action** and exactly one **Intent**.
- A **Processing run** may contain zero or more **Action–Intent pairs**.
- A **Workflow sample** belongs to exactly one **Processing run**.
- A **Workflow sample** has exactly one **Workflow summary**.
- A **Workflow sample** contains zero or more **Action–Intent pairs** and zero or more **Raw events**.
- A **Cursor observation** is a kind of **Raw event**.
- A **Keystroke** is a kind of **Raw event**.
- A **Processing run** may contain zero or more **Keystrokes** recovered from its **Keyboard ROI**.

## Example dialogue

> **Dev:** Should we save every cropped image before detecting the cursor?
> **Domain expert:** No. A processing run should first produce cursor observations; cropped images and debug video are optional artifacts that can be generated later.

> **Dev:** Is an **Action–Intent pair** one label per frame?
> **Domain expert:** No. It is one labeled tutorial step over a time range, not a per-frame annotation.

> **Dev:** Must an **Action–Intent pair** match the cursor path in that range?
> **Domain expert:** Not for the initial dataset. Narration alone is enough; multimodal consistency is a later enrichment.

> **Dev:** Is the keyboard part of the **Crop ROI**?
> **Domain expert:** No. The application screen is the **Crop ROI**; the keyboard is a separate **Keyboard ROI** on the same **Source frame**.

> **Dev:** Is the **Workflow summary** just concatenated **Action–Intent** text?
> **Domain expert:** No. It is one speech-derived overview of the whole run; pairs remain the step-level layer.

> **Dev:** Are keystrokes part of an **Action–Intent pair**?
> **Domain expert:** No. Keystrokes and cursor observations belong in the **Raw event** stream of the **Workflow sample**.

> **Dev:** Is Shift+A one **Keystroke**?
> **Domain expert:** No. That is two overlapping **Keystrokes** — Shift and A each with their own press and release times.

## Flagged ambiguities

- “Selected frame” was resolved to every source frame in the selected time range for the initial high-quality run; no sampling is applied.
- “Click” was resolved to an approximate candidate inferred from video evidence, not exact operating-system mouse events.
- Speech-primary vs multimodal **Action–Intent** grounding was resolved: speech-primary for the initial dataset.
- Dual regions in one **Source frame** were resolved as **Crop ROI** (app) plus **Keyboard ROI** (keyboard), not separate screen/keyboard extractions.
- Published **Workflow sample** shape was resolved as summary + action–intent pairs + raw events.
- **Keystroke** was resolved as press–release per physical key (matching the working keyboard detector), not logical typed characters.
- Whether a timestamped **Speech transcript** is itself a published layer is deferred (keep as intermediate for now; revisit later).
- How tutorial **popups** (tip boxes / overlays) in the **Crop ROI** are handled is not yet resolved. They poison both the Crop ROI visual evidence and **Cursor observations**; handling is deferred (likely flag occlusion intervals later).
- “YOLO dataset” vs training source of truth was resolved: version **Cursor annotations** + selection + current detector weights; do not treat the exported image pack as the source of truth (it is regenerable from video + annotations).
- One-class detector vs multi-class labels was resolved: the detector predicts a single cursor class; **Cursor appearance classes** still drive proportional train/validation stratification so rare appearances are represented fairly in both splits.
