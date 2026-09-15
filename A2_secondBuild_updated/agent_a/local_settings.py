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
import importlib.util
import tempfile


def _search_dirs():
    this_dir = os.path.dirname(os.path.abspath(__file__))   # agent_a/
    repo_root = os.path.dirname(this_dir)
    parent_dir = os.path.dirname(repo_root)
    return [repo_root, parent_dir]


def _load_config_file(path):
    if not os.path.isfile(path):
        return {}
    spec = importlib.util.spec_from_file_location("a2_local_config_runtime", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {key: value for key, value in vars(module).items() if not key.startswith("_")}


def load_local_config():
    for directory in _search_dirs():
        path = os.path.join(directory, "local_config.py")
        if os.path.isfile(path):
            return _load_config_file(path)
    return {}


def get_local_config_value(attr: str, default=None):
    value = load_local_config().get(attr, default)
    return default if value is None else value


def save_local_config(updates: dict):
    """Atomically update the gitignored machine-local configuration."""
    values = load_local_config()
    values.update(updates)
    supported = (str, int, float, bool, type(None), list, tuple, dict)
    allowed = {
        "name", "OPENROUTER_API_KEY", "python_path", "default_model",
        "MODEL_CATALOG", "tool_interface_version",
    }
    allowed.update(key for key, value in values.items() if isinstance(value, supported))
    lines = []
    for key in sorted(allowed):
        if key in values:
            lines.append(f"{key} = {values[key]!r}\n")

    path = os.path.join(_search_dirs()[0], "local_config.py")
    directory = os.path.dirname(path)
    fd, temp_path = tempfile.mkstemp(prefix="local_config_", suffix=".tmp", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    return path
