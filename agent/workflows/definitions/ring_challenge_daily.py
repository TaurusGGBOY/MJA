from .batch23 import RING_CHALLENGE_DAILY_DEFINITION

# Compatibility export for older importers.  The canonical implementation is
# the evidence-driven definition in ``batch23``; it intentionally has no
# static ``transitions`` attribute because each transition depends on the
# current arena evidence (including the remaining 0/12 counter).
TRANSITIONS = {}

__all__ = ["RING_CHALLENGE_DAILY_DEFINITION", "TRANSITIONS"]
