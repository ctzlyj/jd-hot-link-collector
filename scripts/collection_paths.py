"""Resolve the chosen collection output and its task-local checkpoints."""
import os
from pathlib import Path
import sys


def option(name):
    for index, arg in enumerate(sys.argv[1:], 1):
        if arg.startswith(name + '='):
            return arg.split('=', 1)[1]
        if arg == name and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return None


def resolve_root():
    root = option('--root') or os.environ.get('JD_COLLECTOR_ROOT')
    if not root:
        raise SystemExit('ROOT_REQUIRED: pass --root=<output-dir> or JD_COLLECTOR_ROOT')
    return Path(root).expanduser().resolve()


def resolve_stage(root, state_dir=None):
    root = Path(root).expanduser().resolve()
    explicit = state_dir or option('--state-dir')
    if explicit:
        return Path(explicit).expanduser().resolve()
    previous = os.environ.get('JD_COLLECTOR_ROOT')
    previous_stage = os.environ.get('JD_COLLECTOR_STATE_DIR')
    if previous_stage and (not previous or Path(previous).expanduser().resolve() == root):
        return Path(previous_stage).expanduser().resolve()
    return root / '.collector_state'