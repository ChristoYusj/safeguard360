"""
Face recognition adapter.

This module keeps a stable interface for enrollment and live recognition while
allowing the underlying embedding provider to be swapped later.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from app.config.settings import get_settings


@dataclass
class FaceEmbeddingResult:
    """Result of attempting to extract a face embedding from an image."""

    status: str
    provider: str
    model: str
    message: str = ""
    faces_detected: int = 0
    vectors: List[List[float]] = field(default_factory=list)
    bbox: Optional[List[float]] = None
    image_size: Optional[Dict[str, int]] = None
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )

    def to_payload(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["embedding_count"] = len(self.vectors)
        payload["ready"] = bool(self.vectors)
        payload["version"] = 1
        return payload


class FaceRecognizer:
    """Lazy-loading face recognizer with MediaPipe validation fallback."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._init_lock = Lock()
        self._face_app = None
        self._face_detection = None
        self._insightface_import_error = ""

        try:
            import insightface  # noqa: F401

            self.available = True
        except Exception as exc:  # pragma: no cover - depends on local env
            self.available = False
            self._insightface_import_error = str(exc)

    def describe(self) -> Dict[str, Any]:
        """Return runtime capability information."""
        return {
            "available": self.available,
            "provider": "insightface" if self.available else "unavailable",
            "model": self.settings.FACE_MODEL,
            "message": (
                "Face recognition embeddings are ready."
                if self.available
                else (
                    "InsightFace is not installed yet. Enrollment images can be "
                    "validated and stored, but ArcFace embeddings are pending."
                )
            ),
            "import_error": self._insightface_import_error or None,
        }

    def _ensure_face_app(self) -> None:
        if self._face_app is not None or not self.available:
            return

        with self._init_lock:
            if self._face_app is not None:
                return

            from insightface.app import FaceAnalysis  # pragma: no cover - optional dep

            face_app = FaceAnalysis(
                name=self.settings.FACE_MODEL,
                root=self.settings.resolved_models_dir,
                providers=["CPUExecutionProvider"],
            )
            face_app.prepare(ctx_id=-1, det_size=(416, 416))
            self._face_app = face_app

    def _ensure_face_detection(self):
        if self._face_detection is not None:
            return self._face_detection

        with self._init_lock:
            if self._face_detection is not None:
                return self._face_detection

            import mediapipe as mp

            self._face_detection = mp.solutions.face_detection.FaceDetection(
                model_selection=0,
                min_detection_confidence=0.5,
            )
            return self._face_detection

    def _detect_faces_with_mediapipe(self, image_bgr) -> int:
        detector = self._ensure_face_detection()
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        results = detector.process(image_rgb)
        return len(results.detections or [])

    def analyze_faces(self, image_bgr) -> List[Dict[str, Any]]:
        """Return detected faces with embedding vectors when available."""
        if image_bgr is None or getattr(image_bgr, "size", 0) == 0:
            return []

        if not self.available:
            return []

        self._ensure_face_app()
        faces = self._face_app.get(image_bgr)
        analyzed_faces = []
        for face in faces:
            embedding = getattr(face, "normed_embedding", None)
            if embedding is None:
                embedding = getattr(face, "embedding", None)
            if embedding is None:
                continue

            bbox = [float(value) for value in face.bbox.tolist()]
            analyzed_faces.append(
                {
                    "bbox": bbox,
                    "embedding": embedding.astype("float32"),
                    "det_score": float(getattr(face, "det_score", 0.0)),
                    "landmark_2d_106": getattr(face, "landmark_2d_106", None),
                }
            )

        return analyzed_faces

    def extract_from_bgr(self, image_bgr) -> FaceEmbeddingResult:
        """Validate the image and extract a face embedding when possible."""
        if image_bgr is None or getattr(image_bgr, "size", 0) == 0:
            return FaceEmbeddingResult(
                status="invalid_image",
                provider="none",
                model=self.settings.FACE_MODEL,
                message="Enrollment image could not be decoded.",
            )

        height, width = image_bgr.shape[:2]
        image_size = {"width": int(width), "height": int(height)}

        if self.available:
            try:
                self._ensure_face_app()
                faces = self._face_app.get(image_bgr)
            except Exception as exc:  # pragma: no cover - optional dep
                return FaceEmbeddingResult(
                    status="recognizer_error",
                    provider="insightface",
                    model=self.settings.FACE_MODEL,
                    message=f"InsightFace failed to process the image: {exc}",
                    image_size=image_size,
                )

            if not faces:
                return FaceEmbeddingResult(
                    status="no_face_detected",
                    provider="insightface",
                    model=self.settings.FACE_MODEL,
                    message="No face was detected in the enrollment image.",
                    image_size=image_size,
                )

            best_face = max(
                faces,
                key=lambda face: (face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1]),
            )
            embedding = getattr(best_face, "normed_embedding", None)
            if embedding is None:
                embedding = getattr(best_face, "embedding", None)

            if embedding is None:
                return FaceEmbeddingResult(
                    status="recognizer_error",
                    provider="insightface",
                    model=self.settings.FACE_MODEL,
                    message="InsightFace returned a face without an embedding vector.",
                    faces_detected=len(faces),
                    image_size=image_size,
                )

            return FaceEmbeddingResult(
                status="ready",
                provider="insightface",
                model=self.settings.FACE_MODEL,
                faces_detected=len(faces),
                vectors=[embedding.astype("float32").tolist()],
                bbox=[float(value) for value in best_face.bbox.tolist()],
                image_size=image_size,
                message="Embedding generated successfully.",
            )

        faces_detected = self._detect_faces_with_mediapipe(image_bgr)
        if faces_detected == 0:
            return FaceEmbeddingResult(
                status="no_face_detected",
                provider="mediapipe-validation",
                model=self.settings.FACE_MODEL,
                message="No face was detected in the enrollment image.",
                image_size=image_size,
            )

        return FaceEmbeddingResult(
            status="pending_recognizer",
            provider="mediapipe-validation",
            model=self.settings.FACE_MODEL,
            faces_detected=faces_detected,
            image_size=image_size,
            message=(
                "Face detected and image stored. ArcFace embedding generation is "
                "pending until InsightFace is installed."
            ),
        )


def cosine_similarity(vector_a, vector_b) -> float:
    """Compute cosine similarity for two embedding vectors."""
    a = np.asarray(vector_a, dtype=np.float32)
    b = np.asarray(vector_b, dtype=np.float32)
    a_norm = np.linalg.norm(a)
    b_norm = np.linalg.norm(b)
    if a_norm == 0.0 or b_norm == 0.0:
        return 0.0
    return float(np.dot(a, b) / (a_norm * b_norm))


face_recognizer = FaceRecognizer()
