"""
Shared lookup for values in a gitignored local_config.py -- searches the
repo root first, then one directory above it (some people deliberately
keep local_config.py outside the git working tree entirely, see
DEBUG_LOG.md #6). Used for OPENROUTER_API_KEY (live_backend.py has its own
copy of this, written first) and now for `name` (metrics.py).

local_config.py, at either location, looks like:
    OPENROUTER_API_KEY = "sk-or-..."
    name = "Karthik"
"""
import os
import sys


def _search_dirs():
    this_dir = os.path.dirname(os.path.abspath(__file__))   # agent_a/
    repo_root = os.path.dirname(this_dir)
    parent_dir = os.path.dirname(repo_root)
    return [repo_root, parent_dir]


def get_local_config_value(attr: str, default=None):
    for d in _search_dirs():
        if d not in sys.path:
            sys.path.insert(0, d)
        try:
            import local_config
            val = getattr(local_config, attr, None)
            if val:
                return val
        except ImportError:
            continue
    return default
