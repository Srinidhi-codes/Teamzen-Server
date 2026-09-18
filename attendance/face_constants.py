"""
Face attendance constants — must stay in sync with frontend/lib/face/constants.ts
and mobile faceDescriptor.

v2 uses FaceNet-style 128-d embeddings (face-api). Match metric is Euclidean distance
(lower = closer). Server recomputes distance from the live punch descriptor vs enrollment;
clients cannot bypass by sending faceVerified=true alone.
"""

# FaceNet 128-d descriptors from @vladmandic/face-api
FACE_DESCRIPTOR_DIM = 128

# Euclidean distance threshold. Standard SFace/FaceNet default is 0.60–0.65.
# 0.65 prevents false rejections from slight head tilts or lighting variations
# while reliably rejecting impostors (whose distance is typically > 0.90).
FACE_DISTANCE_THRESHOLD = 0.65

# Stored face_match_score is similarity in [0, 1] for audit display: max(0, 1 - distance)
FACE_MATCH_THRESHOLD = 0.35  # minimum similarity (= 1 - max distance)
