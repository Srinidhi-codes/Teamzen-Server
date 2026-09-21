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
# 0.70 allows robust matching even with glasses, camera flash, or lighting shifts,
# while safely rejecting different individuals (whose distance is typically > 0.90).
FACE_DISTANCE_THRESHOLD = 0.70

# Stored face_match_score is similarity in [0, 1] for audit display
FACE_MATCH_THRESHOLD = 0.30
