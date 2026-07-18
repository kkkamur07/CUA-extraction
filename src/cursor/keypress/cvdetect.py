"""Automatic key-box detection from a keyboard crop.

The overlay keyboard is dark keys on a saturated green deck, so keys can be
segmented precisely: mask out the green, split touching keys with a small
erosion, take connected components, and rebuild boxes. Labels are then
transferred from a template layout (e.g. the hand-made default) by matching
box centers after a global offset correction.
"""

from __future__ import annotations

import cv2
import numpy as np

# erosion used to split keys that touch via shadows; boxes are re-grown by it
_SPLIT_PX = 2


def _key_mask(img_bgr: np.ndarray) -> np.ndarray:
    """1 where 'not green deck' (i.e. key-ish), cleaned up."""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    green = (h >= 30) & (h <= 95) & (s > 60) & (v > 40)
    mask = (~green).astype(np.uint8)
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def detect_boxes(img_bgr: np.ndarray) -> list[dict]:
    """Detected key boxes, normalized to the crop. Labels not assigned yet."""
    H, W = img_bgr.shape[:2]
    mask = _key_mask(img_bgr)
    er = cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=_SPLIT_PX)
    n, _, stats, _ = cv2.connectedComponentsWithStats(er, connectivity=4)

    boxes = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        # grow back what the erosion ate
        x -= _SPLIT_PX; y -= _SPLIT_PX; w += 2 * _SPLIT_PX; h += 2 * _SPLIT_PX
        # drop anything touching the crop border (outer frame, cut-off keys)
        if x <= 0 or y <= 0 or x + w >= W - 1 or y + h >= H - 1:
            continue
        rel = (w * h) / (W * H)
        if rel < 0.0006 or rel > 0.09:          # noise / frame chunks
            continue
        if w < W * 0.012 or h < H * 0.035:      # slivers
            continue
        if area / max(1, w * h) < 0.25:          # very sparse component
            continue
        boxes.append({"x": x, "y": y, "w": w, "h": h})

    boxes = _merge_contained(boxes)
    return [{"x": b["x"] / W, "y": b["y"] / H, "w": b["w"] / W, "h": b["h"] / H}
            for b in boxes]


def _merge_contained(boxes: list[dict]) -> list[dict]:
    """Drop boxes that live almost entirely inside a bigger one."""
    keep = []
    boxes = sorted(boxes, key=lambda b: b["w"] * b["h"], reverse=True)
    for b in boxes:
        inside = False
        for k in keep:
            ix = max(0, min(b["x"] + b["w"], k["x"] + k["w"]) - max(b["x"], k["x"]))
            iy = max(0, min(b["y"] + b["h"], k["y"] + k["h"]) - max(b["y"], k["y"]))
            if ix * iy > 0.75 * b["w"] * b["h"]:
                inside = True
                break
        if not inside:
            keep.append(b)
    return keep


def transfer_labels(detected: list[dict], template: list[dict]) -> tuple[list[dict], dict]:
    """Assign template labels to detected boxes (all coords normalized).

    1. estimate a global (dx, dy) between template and detections
    2. greedily match closest center pairs, each label used once
    """
    if not template:
        out = [{"label": f"?{i+1}", **b} for i, b in enumerate(detected)]
        return out, {"n_detected": len(detected), "n_matched": 0, "n_unmatched": len(detected)}

    def center(b):
        return (b["x"] + b["w"] / 2, b["y"] + b["h"] / 2)

    det_c = [center(b) for b in detected]
    tpl_c = [center(b) for b in template]

    # global offset correction (median of nearest-neighbour displacement)
    if det_c and tpl_c:
        disp = []
        for tc in tpl_c:
            d2 = [(tc[0] - dc[0]) ** 2 + (tc[1] - dc[1]) ** 2 for dc in det_c]
            j = int(np.argmin(d2))
            disp.append((det_c[j][0] - tc[0], det_c[j][1] - tc[1]))
        dx = float(np.median([d[0] for d in disp]))
        dy = float(np.median([d[1] for d in disp]))
        tpl_c = [(x + dx, y + dy) for x, y in tpl_c]

    pairs = []
    for ti, tc in enumerate(tpl_c):
        for di, dc in enumerate(det_c):
            dist = ((tc[0] - dc[0]) ** 2 + ((tc[1] - dc[1]) * 0.5) ** 2) ** 0.5
            cutoff = 0.75 * max(template[ti]["w"], detected[di]["w"],
                                template[ti]["h"], detected[di]["h"])
            if dist <= cutoff:
                pairs.append((dist, ti, di))
    pairs.sort()

    tpl_used, det_used = set(), {}
    for dist, ti, di in pairs:
        if ti in tpl_used or di in det_used:
            continue
        tpl_used.add(ti)
        det_used[di] = template[ti]["label"]

    out = []
    unk = 0
    for di, b in enumerate(detected):
        if di in det_used:
            out.append({"label": det_used[di], **b})
        else:
            unk += 1
            out.append({"label": f"?{unk}", **b})
    info = {"n_detected": len(detected), "n_matched": len(det_used), "n_unmatched": unk}
    return out, info


def autodetect(img_bgr: np.ndarray, template: list[dict] | None = None):
    boxes = detect_boxes(img_bgr)
    return transfer_labels(boxes, template or [])
