"""pytest plugin: record which repository files each test opens or lists.

Uses the `open`, `os.listdir` and `os.scandir` audit events (PEP 578), so it sees
open(), os.open(), pathlib reads, glob and the like inside the test process; reads by
subprocesses or external servers are invisible. Reads outside any test (collection,
import time) are recorded with an empty nodeid. Python sources and caches are skipped.

    pytest -p lab_reads ...    # writes $LAB_READS (default lab-reads.tsv)

Output, deduplicated: nodeid, kind (read/write/list), repo-relative path.
"""

import os
import sys

import pytest

SKIP_SUFFIXES = (".py", ".pyc", ".pyi", ".so", ".pth")
SKIP_PARTS = ("/__pycache__/", "/.git/", "/.venv/", "/.pytest_cache/", "/.mypy_cache/", "/pytest-cache-files-")
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC

_root = None
_current = ""
_seen = set()


def _kind(event, args):
    if event != "open":
        return "list"
    mode, flags = args[1], args[2] if len(args) > 2 else 0
    if isinstance(mode, str):
        return "write" if any(c in mode for c in "wax+") else "read"
    return "write" if isinstance(flags, int) and flags & WRITE_FLAGS else "read"


def _hook(event, args):
    if event not in ("open", "os.listdir", "os.scandir") or _root is None:
        return
    try:
        path = args[0]
        if path is None or isinstance(path, int):  # fd-based, or listdir(".")
            path = "." if path is None else None
        if path is None:
            return
        path = os.fsdecode(path)
        if path.endswith(SKIP_SUFFIXES):
            return
        full = os.path.abspath(path)
        if not full.startswith(_root) or any(p in full + "/" for p in SKIP_PARTS):
            return
        _seen.add((_current, _kind(event, args), full[len(_root):] or "."))
    except Exception:  # an exception here would surface in the code under test
        pass


def pytest_configure(config):
    global _root
    _root = str(config.rootpath) + os.sep
    sys.addaudithook(_hook)  # cannot be removed; inert once _root is None


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    global _current
    _current = item.nodeid


def pytest_runtest_logfinish(nodeid, location):
    global _current
    _current = ""


def pytest_unconfigure(config):
    global _root
    _root = None
    out = os.environ.get("LAB_READS", "lab-reads.tsv")
    with open(out, "w") as f:
        f.write("nodeid\tkind\tpath\n")
        for row in sorted(_seen):
            f.write("\t".join(row) + "\n")
