"""Shared OpenCV frame helpers for annotation + extraction."""

from __future__ import annotations

import cv2
import numpy as np


def read_frame(video: cv2.VideoCapture, frame_number: int) -> np.ndarray | None:
    video.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    ok, frame = video.read()
    return frame if ok else None
