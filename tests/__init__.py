import errno
import shutil
from contextlib import contextmanager
from tempfile import mkdtemp

import pytest

from inotify_simple import Event, INotify, flags, monotonic

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
def short_timeout(_cache=[]):
    if _cache:
        return _cache[0]
    times = []
    with tempdir() as tmpdir:
        watcher = INotify()
        watcher.add_watch(tmpdir, flags.CREATE)
        t0 = monotonic()
        assert watcher.read(timeout=0) == []
        times.append(monotonic() - t0)

    with tempdir() as tmpdir:
        watcher = INotify()
        watcher.add_watch(tmpdir, flags.CREATE)
        open(tmpdir + '/foo', 'w').write('')
        t0 = monotonic()
        assert len(watcher.read(timeout=0)) > 0
        times.append(monotonic() - t0)

    calibrated_timeout = round(max(times) * 5 * 1000)
    _cache.append(max(calibrated_timeout, 10))
    return _cache[0]


def assert_events_match(events, count, **kwargs):
    keys = set(kwargs.keys())
    assert keys.issubset(Event._fields), "Invalid kwargs {}; should be a subset of {}".format(keys, Event._fields)

    def matches(event):
        return all(getattr(event, k) == v for k, v in kwargs.items())

    matching = list(filter(matches, events))
    if count is None or (count > 0 and len(matching) == 0):
        assert len(matching), "No events matched the predicate {}: {}".format(kwargs, events)
    else:
        assert len(matching) == count, "Expected {} events to match the predicate {}, but {} matched: {}".format(count, kwargs, len(matching), events)

@contextmanager
def raises_ebadfd():
    # Checking for multiple exception types since they changed between python 2 and 3.
    with pytest.raises((OSError, IOError)) as exc_info:
        yield
    assert exc_info.value.errno == errno.EBADF

@contextmanager
def assert_takes_between(min_time, max_time=float('inf')):
    t0 = monotonic()
    yield
    duration = monotonic() - t0
    assert max_time >= duration >= min_time, "Expected duration of {} is not between {} and {}".format(
        duration,
        round(min_time, 3),
        round(max_time, 3),
    )


@contextmanager
def watcher_and_dir(f, **kwargs):
    try:
        with tempdir() as tmpdir:
            watcher = INotify(**kwargs)
            watcher.add_watch(tmpdir, f)
            yield watcher, tmpdir
    finally:
        try:
            watcher.close()
        except (OSError, IOError) as ex:
            if 'Bad file descriptor' not in str(ex):
                raise
