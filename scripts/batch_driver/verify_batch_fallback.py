"""Batch-local independent verifier with the same user-authorized fallback.
Patches the SKILL package_live before importing the SKILL verify_batch."""
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL))
import package_live  # skill version  # noqa: E402

from original_price_fallback import attach_fallback  # noqa: E402
attach_fallback(package_live)

import verify_batch  # skill version, binds the patched live_data  # noqa: E402
verify_batch.run()
