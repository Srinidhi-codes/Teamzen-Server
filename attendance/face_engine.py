import os
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List, Any
from attendance.face_constants import FACE_DISTANCE_THRESHOLD
import gc

MODELS_DIR = Path(__file__).resolve().parent / "models_ai"
DET_MODEL_PATH = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
REC_MODEL_PATH = MODELS_DIR / "face_recognition_sface_2021dec.onnx"

_detector: Optional[cv2.FaceDetectorYN] = None
_recognizer: Optional[cv2.FaceRecognizerSF] = None

import threading
_model_lock = threading.Lock()


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

    # Prevent OOM crashes on low-memory servers (e.g. Render 512MB RAM):
    # Camera photos from modern phones are often 12MP-24MP (3000x4000).
    # Processing unscaled images through OpenCV DNN buffers allocates >1.5GB RAM,
    # causing Linux kernel OOM killer to terminate Daphne with 502 Bad Gateway.
    MAX_DIM = 320
    h, w = img.shape[:2]
    if max(h, w) > MAX_DIM:
        scale = MAX_DIM / float(max(h, w))
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        h, w = img.shape[:2]

    with _model_lock:
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

    with _model_lock:
        # Crop and align face
        aligned_face = recognizer.alignCrop(img, face)
    
        # Extract 128-d feature
        feature = recognizer.feature(aligned_face)

    # L2 normalize feature
    norm_feature = feature[0]
    norm = np.linalg.norm(norm_feature)
    if norm > 0:
        norm_feature = norm_feature / norm

    # Force cleanup to prevent memory spikes between requests
    del img
    del nparr
    del aligned_face
    gc.collect()


    return [float(x) for x in norm_feature], confidence


def match_faces(desc1: List[float], desc2: Any) -> Tuple[float, float, bool]:
    """
    Compares a 128-d live face descriptor against one or more enrolled descriptors.
    desc2 can be a single 128-d list or a list of 128-d lists (e.g. with/without glasses).
    Returns:
        (best_euclidean_distance: float, similarity_score: float, is_match: bool)
    """
    if not desc1 or len(desc1) != 128:
        raise ValueError("Live descriptor must have length 128.")

    if isinstance(desc2, list) and len(desc2) > 0 and isinstance(desc2[0], list):
        templates = [t for t in desc2 if len(t) == 128]
    elif isinstance(desc2, list) and len(desc2) == 128 and not isinstance(desc2[0], list):
        templates = [desc2]
    else:
        raise ValueError("Enrolled descriptor must be a 128-d vector or list of 128-d vectors.")

    if not templates:
        raise ValueError("No valid 128-d enrolled template found.")

    v1 = np.array(desc1, dtype=np.float32)
    norm1 = np.linalg.norm(v1)
    if norm1 > 0:
        v1 = v1 / norm1

    best_dist = float("inf")
    best_cos = -1.0
    matched = False

    for t in templates:
        v2 = np.array(t, dtype=np.float32)
        norm2 = np.linalg.norm(v2)
        if norm2 > 0:
            v2 = v2 / norm2

        dot = float(np.dot(v1, v2))
        euc_dist = float(np.linalg.norm(v1 - v2))

        # Matches if within calibrated distance threshold or cosine similarity threshold
        is_match = euc_dist <= FACE_DISTANCE_THRESHOLD or dot >= 0.40

        if euc_dist < best_dist:
            best_dist = euc_dist
            best_cos = dot
            matched = is_match

    # Mathematical cosine similarity mapped to [0, 1]
    similarity = max(0.0, min(1.0, 1.0 - (best_dist ** 2) / 2.0))

    return best_dist, similarity, matched
