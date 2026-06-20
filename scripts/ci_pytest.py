"""CI pytest runner that force-exits after the session, bypassing the
interpreter-shutdown hang caused by leaked native-library child processes
(torch compile workers / multiprocessing resource_tracker). Coverage and
the --cov-fail-under gate are finalized inside pytest.main() before we
exit, so the gate is fully preserved."""
import os
import sys

import pytest

if __name__ == "__main__":
    rc = pytest.main(sys.argv[1:])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(int(rc))
