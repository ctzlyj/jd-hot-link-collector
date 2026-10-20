"""Batch-local packager with the user-authorized original-price fallback.
Explicitly loads the SKILL package_live; never the older batch-local copy."""
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
BATCH = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL))
import package_live  # skill version  # noqa: E402

import os as _os
from pathlib import Path as _Path
from prior_receipts import activate as _activate_prior
_activate_prior(_os.environ['JD_COLLECTOR_ROOT'], _os.environ['JD_COLLECTOR_STATE_DIR'])

from original_price_fallback import attach_fallback  # noqa: E402
attach_fallback(package_live)

sys.path.insert(0, str(BATCH))
from package_with_artifacts import write_artifact  # noqa: E402
package_live.write_workbook = write_artifact
package_live.main()

