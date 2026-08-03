"""
Face attendance constants shared by GraphQL services and clients.
Client extracts a descriptor; server trusts face_verified only when org enables face mode,
and stores face_verified + match score. Geofence stays soft-flagged (is_within_geofence).
"""

# Cosine similarity threshold (higher = stricter). Client and server must agree.
FACE_MATCH_THRESHOLD = 0.72
