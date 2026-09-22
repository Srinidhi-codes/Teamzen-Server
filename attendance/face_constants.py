"""
Face attendance constants — must stay in sync with frontend/lib/face/constants.ts
and mobile faceDescriptor.

v2 uses FaceNet-style 128-d embeddings (face-api). Match metric is Euclidean distance
(lower = closer). Server recomputes distance from the live punch descriptor vs enrollment;
clients cannot bypass by sending faceVerified=true alone.
"""

# FaceNet 128-d descriptors from @vladmandic/face-api
FACE_DESCRIPTOR_DIM = 128

# Euclidean distance threshold. Lower = stricter.
# 0.85 allows robust matching even when transitioning between wearing spectacles
# vs no spectacles, lighting shifts, or camera glare (same person is typically 0.30 - 0.82),
# while safely rejecting different individuals (whose distance in OpenCV SFace is typically > 1.05 to 1.41).
FACE_DISTANCE_THRESHOLD = 0.85

# Stored face_match_score is similarity in [0, 1] for audit display
FACE_MATCH_THRESHOLD = 0.35
