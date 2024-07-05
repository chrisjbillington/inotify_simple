import errno
import shutil
import subprocess
import warnings
from contextlib import contextmanager
from functools import wraps
from io import UnsupportedOperation
from tempfile import mkdtemp

import pytest

from inotify_simple import Event, INotify, flags, monotonic, PY2


def memoize(func):
    _memo = []

    @wraps(func)
    def inner(*args, **kwargs):
        if not len(_memo):
            _memo.append(func(*args, **kwargs))
            assert _memo[0] > 0
        return _memo[0]

    return inner


# Equivalent of tempfile.TemporaryDirectory for python 2 support:
@contextmanager
def tempdir():
    rv = mkdtemp()
    try:
        yield rv
    finally:
        shutil.rmtree(rv)


# HACK: estimate and validate the time it takes to do short things (read a ready event or poll then give up), multiply
# that by 4, and return that value in milliseconds. For use in tests that want a short timeout (to keep tests quick)
# but not a zero timeout so as not to accidentally only test zero cases.
@memoize
def short_timeout():
    times = []
    with tempdir() as td:
        watcher = INotify()
        watcher.add_watch(td, flags.CREATE)
        t0 = monotonic()
        assert watcher.read(timeout=0) == []
        times.append(monotonic() - t0)

    with tempdir() as td:
        watcher = INotify()
        watcher.add_watch(td, flags.CREATE)
        open(td + "/foo", "w").write("")
        t0 = monotonic()
        assert len(watcher.read(timeout=0)) > 0
        times.append(monotonic() - t0)

    calibrated_timeout = round(max(times) * 5 * 1000)
    return max(calibrated_timeout, 10)


def assert_events_match(events, count, **kwargs):
    keys = set(kwargs.keys())
    assert keys.issubset(
        Event._fields
    ), "Invalid kwargs {}; should be a subset of {}".format(keys, Event._fields)

    def matches(event):
        return all(getattr(event, k) == v for k, v in kwargs.items())

    matching = list(filter(matches, events))
    if count is None or (count > 0 and len(matching) == 0):
        assert len(matching), "No events matched the predicate {}: {}".format(
            kwargs, events
        )
    else:
        assert (
            len(matching) == count
        ), "Expected {} events to match the predicate {}, but {} matched: {}".format(
            count, kwargs, len(matching), events
        )


@contextmanager
def raises_ebadfd():
    # Checking for multiple exception types since Python 2 some (but not all) sites raise IOError; Python 3 converted
    # everything to OSError.
    etype = (OSError, IOError) if PY2 else OSError
    with pytest.raises(etype) as exc_info:
        yield
    assert exc_info.value.errno == errno.EBADF


@contextmanager
def raises_einval():
    with pytest.raises(OSError) as exc_info:
        yield
    assert exc_info.value.errno == errno.EINVAL


@contextmanager
def raises_not_open_for_writing():
    # Exception type changed between Python 2 and 3.
    etype = ValueError if PY2 else UnsupportedOperation

    # Checking for multiple exception types since they changed between Python 2 and 3.
    with pytest.raises(etype, match="File not open for writing"):
        yield


@contextmanager
def assert_takes_between(min_time, max_time=float("inf")):
    t0 = monotonic()
    yield
    duration = monotonic() - t0
    assert (
        max_time >= duration >= min_time
    ), "Expected duration of {} is not between {} and {}".format(
        duration,
        round(min_time, 3),
        round(max_time, 3),
    )


@contextmanager
def watcher_and_dir(f, **kwargs):
    try:
        with tempdir() as td:
            watcher = INotify(**kwargs)
            watcher.add_watch(td, f)
            yield watcher, td
    finally:
        try:
            watcher.close()
        except (OSError, IOError) as ex:
            if "Bad file descriptor" not in str(ex):
                raise


@memoize
def try_to_increase_watches():
    for sysctl in ("max_user_instances", "max_user_watches", "max_queued_events"):
        sysctl = "fs.inotify.{}=524288".format(sysctl)
        try:
            subprocess.check_call(("sysctl", sysctl))
        except subprocess.CalledProcessError:
            warnings.warn(
                "Could not increase{}; test may fail with overflow (if not root, try sudo; if in a container, try running with --privileged)".format(
                    sysctl
                )
            )
    maxwatches = int(
        subprocess.check_output(("sysctl", "-n", "fs.inotify.max_user_watches")).strip()
    )
    maxqueue = int(
        subprocess.check_output(
            ("sysctl", "-n", "fs.inotify.max_queued_events")
        ).strip()
    )
    return min((maxqueue, maxwatches)) - 1


# Ugly backport of multiprocessing.cpu_count() to support python 2:
@memoize
def cpu_count():
    try:
        from multiprocessing import cpu_count

        return cpu_count()
    except ImportError:
        found = []
        for line in open("/proc/cpuinfo", "r").readlines():

            parts = line.split()
            if parts and parts[0].lower() == "processor":
                found.append(int(parts[-1]))
        return max(found)
