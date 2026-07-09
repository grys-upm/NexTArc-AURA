"""MongoDB collections for monitoring.

No ORM is used for telemetry; documents are accessed directly via Motor.
"""

DEVICE_STATES_COL = "device_states"
"""Collection name storing the current telemetry status for each device ID (upsert)."""

INFERENCE_RESULTS_COL = "inference_results"
"""Collection name storing historical YOLO inference result records (append-only)."""
