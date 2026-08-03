"""
Face attendance constants — must stay in sync with frontend/lib/face/constants.ts
and mobile faceDescriptor.

v2 uses FaceNet-style 128-d embeddings (face-api). Match metric is Euclidean distance
(lower = closer). Server recomputes distance from the live punch descriptor vs enrollment;
clients cannot bypass by sending faceVerified=true alone.
"""

# FaceNet 128-d descriptors from @vladmandic/face-api
FACE_DESCRIPTOR_DIM = 128

# Euclidean distance threshold (strict). Typical face-api default is 0.6;
# 0.5 reduces false accepts across different people.
FACE_DISTANCE_THRESHOLD = 0.5

# Stored face_match_score is similarity in [0, 1] for audit display: max(0, 1 - distance)
# Keep a soft floor so GraphQL clients that still send "score" aren't confused.
FACE_MATCH_THRESHOLD = 0.5  # minimum similarity (= 1 - max distance)
