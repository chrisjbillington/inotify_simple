import os

from inotify_simple import INotify, flags
import pytest
from tests import (
    assert_events_match,
    watcher_and_dir,
    short_timeout,
    raises_ebadfd,
    raises_not_open_for_writing,
)


@pytest.mark.parametrize("read_before_close", (True, False))
def test_close(read_before_close):
    with watcher_and_dir(flags.CREATE | flags.ONESHOT) as (watcher, tempdir):
        assert not watcher.closed
        assert watcher.fileno() is not None

        if read_before_close:
            open(tempdir + "/foo", "w").write("")
            assert_events_match(
                watcher.read(timeout=short_timeout()), 1, mask=flags.CREATE, name="foo"
            )

        for _ in range(3):  # Make sure close is idempotent
            watcher.close()
            assert watcher.closed
        with pytest.raises(ValueError, match="I/O operation on closed file"):
            watcher.fileno()

        with pytest.raises(ValueError, match="I/O operation on closed file"):
            watcher.add_watch(tempdir, flags.CREATE)

        with pytest.raises(ValueError, match="I/O operation on closed file"):
            assert watcher.read(timeout=short_timeout()) == []


@pytest.mark.parametrize("raw_close", (True, False))
def test_closed_descriptor_errors(raw_close):
    with watcher_and_dir(flags.CREATE | flags.ONESHOT) as (watcher, tempdir):
        fileno = watcher.fileno()
        os.fstat(fileno)
        if raw_close:
            os.close(fileno)
        else:
            watcher.close()
        with raises_ebadfd():
            os.fstat(fileno)

        # Make sure the error codes from write change after close:
        if raw_close:
            assert watcher.fileno() is not None
            with raises_ebadfd():
                watcher.read(timeout=0)

        else:
            with pytest.raises(ValueError, match="I/O operation on closed file"):
                watcher.fileno()
            with raises_ebadfd():
                os.read(fileno, 1)
            with pytest.raises(ValueError, match="I/O operation on closed file"):
                watcher.read(timeout=0)


def test_write_errors():
    with watcher_and_dir(flags.CREATE | flags.ONESHOT) as (watcher, tempdir):
        fileno = watcher.fileno()
        with raises_ebadfd():
            os.write(fileno, b"a")
        with raises_not_open_for_writing():
            watcher.write(b"a")
        open(tempdir + "/foo", "w").write("")
        assert_events_match(
            watcher.read(timeout=short_timeout()), 1, mask=flags.CREATE, name="foo"
        )
        with raises_ebadfd():
            os.write(fileno, b"a")
        with raises_not_open_for_writing():
            watcher.write(b"a")


def _get_watcher_fileno(**kwargs):
    watcher = INotify(**kwargs)
    return watcher.fileno()


def test_autoclose():
    fileno = _get_watcher_fileno()
    with raises_ebadfd():
        os.close(fileno)

    fileno = _get_watcher_fileno(closefd=False)
    os.close(fileno)

    watcher = INotify(closefd=False)
    fileno = watcher.fileno()
    watcher.close()
    with pytest.raises(ValueError, match="I/O operation on closed file"):
        watcher.fileno()
    watcher.close()
    os.close(fileno)
    watcher.close()
