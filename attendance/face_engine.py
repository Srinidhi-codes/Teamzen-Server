import os
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List
from attendance.face_constants import FACE_DISTANCE_THRESHOLD

MODELS_DIR = Path(__file__).resolve().parent / "models_ai"
DET_MODEL_PATH = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
REC_MODEL_PATH = MODELS_DIR / "face_recognition_sface_2021dec.onnx"

_detector: Optional[cv2.FaceDetectorYN] = None
_recognizer: Optional[cv2.FaceRecognizerSF] = None


def _get_models() -> Tuple[cv2.FaceDetectorYN, cv2.FaceRecognizerSF]:
    global _detector, _recognizer
    if _detector is None or _recognizer is None:
        if not DET_MODEL_PATH.exists() or not REC_MODEL_PATH.exists():
            raise RuntimeError(
                f"Face recognition models missing in {MODELS_DIR}. "
                "Ensure face_detection_yunet_2023mar.onnx and face_recognition_sface_2021dec.onnx are present."
            )
        # Initialize detector with optimized threshold for glasses / flash / low light
        _detector = cv2.FaceDetectorYN.create(
            str(DET_MODEL_PATH),
            "",
            (320, 320),
            score_threshold=0.35,
            nms_threshold=0.3,
            top_k=5000,
        )
        _recognizer = cv2.FaceRecognizerSF.create(str(REC_MODEL_PATH), "")
    return _detector, _recognizer


def _enhance_contrast_for_detection(img: np.ndarray) -> np.ndarray:
    """Apply CLAHE (Histogram Equalization) to assist detection under flash / backlight / glasses glare."""
    try:
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        limg = cv2.merge((cl, a, b))
        return cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
    except Exception:
        return img


def extract_face_descriptor_from_bytes(image_bytes: bytes) -> Tuple[List[float], float]:
    """
    Given raw image bytes (JPEG/PNG/WebP), detect face and extract 128-dimensional embedding.
    Supports specs, camera flash glare, and varied lighting using multi-stage detection.
    Returns:
        (descriptor: List[float], detection_confidence: float)
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Invalid image file or format.")

    h, w, _ = img.shape
    detector, recognizer = _get_models()

    # Dynamic input size adaptation
    detector.setInputSize((w, h))
    _, faces = detector.detect(img)

    # Fallback 1: CLAHE contrast enhancement (handles camera flash reflection & specs glare)
    if faces is None or len(faces) == 0:
        enhanced_img = _enhance_contrast_for_detection(img)
        _, faces = detector.detect(enhanced_img)
        if faces is not None and len(faces) > 0:
            img = enhanced_img

    if faces is None or len(faces) == 0:
        raise ValueError("No face detected in the photo. Please face the camera and try again.")

    if len(faces) > 1:
        # Filter secondary background faces
        high_conf_faces = [f for f in faces if f[-1] >= 0.6]
        if len(high_conf_faces) > 1:
            raise ValueError("Multiple faces detected in photo. Only one person should be in frame.")

    face = faces[0]
    confidence = float(face[-1])

    # Crop and align face
    aligned_face = recognizer.alignCrop(img, face)

    # Extract 128-d feature
    feature = recognizer.feature(aligned_face)

    # L2 normalize feature
    norm_feature = feature[0]
    norm = np.linalg.norm(norm_feature)
    if norm > 0:
        norm_feature = norm_feature / norm

    return [float(x) for x in norm_feature], confidence


def match_faces(desc1: List[float], desc2: List[float]) -> Tuple[float, float, bool]:
    """
    Compares two 128-d face descriptors.
    Returns:
        (cosine_distance: float, similarity_score: float, is_match: bool)
    """
    if len(desc1) != 128 or len(desc2) != 128:
        raise ValueError("Both descriptors must have length 128.")

    v1 = np.array(desc1, dtype=np.float32)
    v2 = np.array(desc2, dtype=np.float32)

    # Cosine similarity
    dot = np.dot(v1, v2)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 1.0, 0.0, False

    cos_sim = float(dot / (norm1 * norm2))
    # Euclidean distance
    euc_dist = float(np.linalg.norm(v1 - v2))

    # Resilient matching threshold (handles glasses, flash glare, and head turns like Apple FaceID)
    is_match = euc_dist <= FACE_DISTANCE_THRESHOLD or cos_sim >= 0.30
    similarity = max(0.0, min(1.0, (cos_sim + 1.0) / 2.0))

    return euc_dist, similarity, is_match
