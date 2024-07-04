import pytest

from inotify_simple import flags
from tests import (
    assert_events_match,
    assert_takes_between,
    watcher_and_dir,
    short_timeout,
)


@pytest.mark.parametrize("oneshot", (True, False))
@pytest.mark.parametrize("check_empty_first", (True, False))
def test_create(check_empty_first, oneshot):
    f = flags.CREATE
    if oneshot:
        f |= flags.ONESHOT
    with watcher_and_dir(f) as (watcher, tempdir):
        if check_empty_first:
            assert watcher.read(timeout=short_timeout()) == []
        open(tempdir + "/foo", "w").write("")
        assert_events_match(
            watcher.read(timeout=short_timeout()), 1, mask=flags.CREATE, name="foo"
        )
        open(tempdir + "/bar", "w").write("")
        if oneshot:
            assert watcher.read(timeout=short_timeout()) == []
        else:
            assert_events_match(
                watcher.read(timeout=short_timeout()), 1, mask=flags.CREATE, name="bar"
            )
        assert watcher.read(timeout=short_timeout()) == []


@pytest.mark.parametrize("zero_first", (True, False))
def test_zero_and_nonzero_timeouts(zero_first):
    with watcher_and_dir(flags.CREATE | flags.ONESHOT) as (watcher, tempdir):
        for _ in range(3):
            if zero_first:
                assert watcher.read(timeout=short_timeout()) == []
            with assert_takes_between(0.15):
                assert watcher.read(timeout=150) == []
            if not zero_first:
                assert watcher.read(timeout=short_timeout()) == []


@pytest.mark.parametrize("first_timeout", (None, 0, 10))
@pytest.mark.parametrize("second_timeout", (None, 0, 10))
@pytest.mark.parametrize("check_empty_first", (True, False))
def test_mixed_timeouts(check_empty_first, first_timeout, second_timeout):
    with watcher_and_dir(flags.CREATE) as (watcher, tempdir):
        if check_empty_first:
            assert watcher.read(timeout=short_timeout()) == []
        open(tempdir + "/foo", "w").flush()
        assert_events_match(
            watcher.read(timeout=first_timeout), 1, mask=flags.CREATE, name="foo"
        )
        open(tempdir + "/bar", "w").flush()
        assert_events_match(
            watcher.read(timeout=second_timeout), 1, mask=flags.CREATE, name="bar"
        )
        assert watcher.read(timeout=short_timeout()) == []


def test_rm_watch():
    with watcher_and_dir(flags.CREATE) as (watcher, tempdir):
        wd = watcher.add_watch(tempdir, flags.CREATE)
        watcher.rm_watch(wd)
        open(tempdir + "/foo", "w").flush()
        assert_events_match(
            watcher.read(timeout=short_timeout()), 1, mask=flags.IGNORED, name=""
        )
        with pytest.raises(OSError, match="Invalid argument"):
            watcher.rm_watch(wd)
    with watcher_and_dir(flags.CREATE) as (watcher, tempdir):
        wd = watcher.add_watch(tempdir, flags.CREATE)
        watcher.rm_watch(wd)
        with pytest.raises(OSError, match="Invalid argument"):
            watcher.rm_watch(wd)
        assert_events_match(
            watcher.read(timeout=short_timeout()), 1, mask=flags.IGNORED, name=""
        )
