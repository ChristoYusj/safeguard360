"""
PPE detection adapter for gate compliance.
"""
from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, Optional

from app.config.settings import get_settings


class PpeDetector:
    """Lazy PPE detector with graceful fallback when YOLO is unavailable."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._init_lock = Lock()
        self._model = None
        self._import_error = ""

        try:
            import ultralytics  # noqa: F401

            self.available = True
        except Exception as exc:  # pragma: no cover - depends on local env
            self.available = False
            self._import_error = str(exc)

    def describe(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "model": self.settings.PPE_MODEL,
            "message": (
                "PPE detector is ready."
                if self.available
                else "PPE detector is unavailable. Gate entry will fall back to face recognition only."
            ),
            "import_error": self._import_error or None,
        }

    def _resolve_model_path(self) -> str:
        """Resolve PPE_MODEL against MODELS_DIR when it's a bare filename.

        Lets the user drop a Roboflow-exported .pt file into data/models/
        and reference it by name in .env (e.g. PPE_MODEL=construction-safety.pt)
        without hard-coding a full path. Falls back to the raw value so
        that canonical names like yolo11n.pt still auto-download via
        ultralytics' hub resolver.
        """
        raw = (self.settings.PPE_MODEL or "").strip()
        if not raw:
            return raw
        # If the value already contains a separator, trust it as-is.
        if os.sep in raw or "/" in raw or os.path.isabs(raw):
            return raw
        candidate = Path(self.settings.resolved_models_dir) / raw
        if candidate.exists():
            return str(candidate)
        return raw

    def _ensure_model(self) -> None:
        if self._model is not None or not self.available:
            return

        with self._init_lock:
            if self._model is not None:
                return

            from ultralytics import YOLO  # pragma: no cover - optional dep

            self._model = YOLO(self._resolve_model_path())

    @staticmethod
    def _expand_face_bbox(face_bbox, frame_width: int, frame_height: int):
        x1, y1, x2, y2 = [float(value) for value in face_bbox]
        face_width = max(x2 - x1, 1.0)
        face_height = max(y2 - y1, 1.0)

        roi = [
            max(0.0, x1 - face_width * 0.65),
            max(0.0, y1 - face_height * 0.35),
            min(float(frame_width), x2 + face_width * 0.65),
            min(float(frame_height), y2 + face_height * 3.4),
        ]
        return roi

    @staticmethod
    def _bbox_overlap_ratio(box_a, box_b) -> float:
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b
        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)
        if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
            return 0.0
        inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
        box_area = max((ax2 - ax1) * (ay2 - ay1), 1.0)
        return inter_area / box_area

    @staticmethod
    def _bbox_center_inside(box_a, box_b) -> bool:
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b
        center_x = (ax1 + ax2) / 2.0
        center_y = (ay1 + ay2) / 2.0
        return bx1 <= center_x <= bx2 and by1 <= center_y <= by2

    @staticmethod
    def _map_detection_label(label: str) -> Optional[str]:
        normalized = label.strip().lower().replace("-", " ").replace("_", " ")
        # Strip doubled whitespace and collapse.
        normalized = " ".join(normalized.split())

        # Reject explicit "negative" classes used by datasets like Roboflow's
        # construction-safety-gsnvb ("NO-Hardhat", "NO-Safety Vest", etc.).
        # Without this, "hardhat" in "no hardhat" would erroneously map to
        # helmet and silently pass a non-compliant worker.
        if normalized.startswith("no ") or " no " in f" {normalized} ":
            return None
        if normalized.startswith("missing") or "without" in normalized:
            return None

        if any(token in normalized for token in ["helmet", "hardhat", "hard hat"]):
            return "helmet"
        if any(
            token in normalized
            for token in ["vest", "high visibility", "high vis", "reflective"]
        ):
            return "vest"
        return None

    def analyze_subject(
        self,
        image_bgr,
        face_bbox,
        required_items: Iterable[str],
    ) -> Dict[str, Any]:
        required = [str(item).strip() for item in required_items if str(item).strip()]
        details = {
            "status": "skipped",
            "required_items": required,
            "detected_items": [],
            "missing_items": [],
            "detector_confidences": {},
            "override_used": False,
            "override_reason_type": None,
            "detector_available": self.available,
            "detector_message": None,
        }

        if not required:
            details["detector_message"] = "No PPE items are currently required."
            return details

        if image_bgr is None or getattr(image_bgr, "size", 0) == 0 or face_bbox is None:
            details["status"] = "uncertain"
            details["detector_message"] = "No valid frame was available for PPE evaluation."
            return details

        if not self.available:
            details["status"] = "unavailable"
            details["detector_message"] = self.describe()["message"]
            return details

        try:
            self._ensure_model()
            results = self._model.predict(image_bgr, verbose=False, conf=0.2)
        except Exception as exc:  # pragma: no cover - optional dep
            details["status"] = "unavailable"
            details["detector_message"] = f"PPE detector failed to run: {exc}"
            return details

        if not results:
            details["status"] = "uncertain"
            details["detector_message"] = "PPE detector returned no results."
            return details

        frame_height, frame_width = image_bgr.shape[:2]
        subject_roi = self._expand_face_bbox(face_bbox, frame_width, frame_height)
        boxes = getattr(results[0], "boxes", None)
        names = getattr(results[0], "names", {}) or {}
        if boxes is None:
            details["status"] = "uncertain"
            details["detector_message"] = "PPE detector returned no bounding boxes."
            return details

        matched_confidences: Dict[str, float] = {}
        for box in boxes:
            cls_list = getattr(box, "cls", None)
            conf_list = getattr(box, "conf", None)
            xyxy_list = getattr(box, "xyxy", None)
            if cls_list is None or conf_list is None or xyxy_list is None:
                continue

            class_index = int(cls_list[0].item() if hasattr(cls_list[0], "item") else cls_list[0])
            confidence = float(conf_list[0].item() if hasattr(conf_list[0], "item") else conf_list[0])
            label = str(names.get(class_index, class_index))
            mapped_item = self._map_detection_label(label)
            if not mapped_item or mapped_item not in required:
                continue

            bbox = [
                float(value.item() if hasattr(value, "item") else value)
                for value in xyxy_list[0]
            ]
            if (
                self._bbox_overlap_ratio(bbox, subject_roi) < 0.05
                and not self._bbox_center_inside(bbox, subject_roi)
            ):
                continue

            previous_confidence = matched_confidences.get(mapped_item, 0.0)
            if confidence > previous_confidence:
                matched_confidences[mapped_item] = confidence

        details["detector_confidences"] = matched_confidences
        details["detected_items"] = sorted(matched_confidences.keys())
        details["missing_items"] = [
            item for item in required if item not in matched_confidences
        ]

        if len(details["missing_items"]) == 0:
            details["status"] = "compliant"
            details["detector_message"] = "Required PPE detected."
        elif details["detected_items"]:
            details["status"] = "non_compliant"
            details["detector_message"] = "One or more required PPE items are missing."
        else:
            details["status"] = "uncertain"
            details["detector_message"] = "The worker was seen, but PPE items could not be confirmed."

        return details


ppe_detector = PpeDetector()
