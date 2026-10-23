from datetime import datetime, UTC

from scdc.ai.config import demo_now

# "Now" for the business story: when a disruption is reported and what date the snapshot describes.
# SCDC_DEMO_NOW pins it to the demo day (20 Oct 2026) so impact scores match the script; unset = the real time.
# Audit times (activity log, approvals) keep the real clock: they record when someone actually acted.
# Always UTC, like every other timestamp the backend returns (the UI shows them in Malaysia time).
def now() -> datetime:
    demo = demo_now()
    return demo.astimezone(UTC) if demo else datetime.now(UTC)
