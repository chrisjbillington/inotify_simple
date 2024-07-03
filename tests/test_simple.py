import os
from io import UnsupportedOperation

from inotify_simple import INotify, flags, PY2
import pytest
from tests import assert_events_match, assert_takes_between, watcher_and_dir, short_timeout, raises_ebadfd

CLOSED_FILE_EXCEPTION_TYPE = ValueError if PY2 else UnsupportedOperation

@pytest.mark.parametrize('oneshot', (True, False))
@pytest.mark.parametrize('check_empty_first', (True, False))
def test_create(check_empty_first, oneshot):
    f = flags.CREATE
    if oneshot:
        f |= flags.ONESHOT
    with watcher_and_dir(f) as (watcher, tmpdir):
        if check_empty_first:
            assert watcher.read(timeout=short_timeout()) == []
        open(tmpdir + '/foo', 'w').write('')
        assert_events_match(watcher.read(timeout=short_timeout()), 1, mask=flags.CREATE,  name='foo')
        open(tmpdir + '/bar', 'w').write('')
        if oneshot:
            assert watcher.read(timeout=short_timeout()) == []
        else:
            assert_events_match(watcher.read(timeout=short_timeout()), 1, mask=flags.CREATE, name='bar')
        assert watcher.read(timeout=short_timeout()) == []


@pytest.mark.parametrize('zero_first', (True, False))
def test_zero_and_nonzero_timeouts(zero_first):
    with watcher_and_dir(flags.CREATE | flags.ONESHOT) as (watcher, tmpdir):
        for _ in range(3):
            if zero_first:
                assert watcher.read(timeout=short_timeout()) == []
            with assert_takes_between(0.15):
                assert watcher.read(timeout=150) == []
            if not zero_first:
                assert watcher.read(timeout=short_timeout()) == []

@pytest.mark.parametrize('first_timeout', (None, 0, 10))
@pytest.mark.parametrize('second_timeout', (None, 0, 10))
@pytest.mark.parametrize('check_empty_first', (True, False))
def test_mixed_timeouts(check_empty_first, first_timeout, second_timeout):
    with watcher_and_dir(flags.CREATE) as (watcher, tmpdir):
        if check_empty_first:
            assert watcher.read(timeout=short_timeout()) == []
        open(tmpdir + '/foo', 'w').flush()
        assert_events_match(watcher.read(timeout=first_timeout), 1, mask=flags.CREATE, name='foo')
        open(tmpdir + '/bar', 'w').flush()
        assert_events_match(watcher.read(timeout=second_timeout), 1, mask=flags.CREATE, name='bar')
        assert watcher.read(timeout=short_timeout()) == []


@pytest.mark.parametrize('read_before_close', (True, False))
def test_close(read_before_close):
    with watcher_and_dir(flags.CREATE | flags.ONESHOT) as (watcher, tmpdir):
        assert not watcher.closed
        assert watcher.fileno() is not None

        if read_before_close:
            open(tmpdir + '/foo', 'w').write('')
            assert_events_match(watcher.read(timeout=short_timeout()), 1, mask=flags.CREATE, name='foo')

        for _ in range(3):  # Make sure close is idempotent
            watcher.close()
            assert watcher.closed
        with pytest.raises(ValueError, match='I/O operation on closed file'):
            watcher.fileno()

        with pytest.raises(ValueError, match='I/O operation on closed file'):
            watcher.add_watch(tmpdir, flags.CREATE)

        with pytest.raises(ValueError, match='I/O operation on closed file'):
            assert watcher.read(timeout=short_timeout()) == []


@pytest.mark.parametrize('raw_close', (True, False))
def test_closed_descriptor_errors(raw_close):
    with watcher_and_dir(flags.CREATE | flags.ONESHOT) as (watcher, tmpdir):
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
            with pytest.raises(ValueError, match='I/O operation on closed file'):
                watcher.fileno()
            with raises_ebadfd():
                os.read(fileno, 1)
            with pytest.raises(ValueError, match='I/O operation on closed file'):
                watcher.read(timeout=0)


def test_write_errors():
    with watcher_and_dir(flags.CREATE | flags.ONESHOT) as (watcher, tmpdir):
        fileno = watcher.fileno()
        with raises_ebadfd():
            os.write(fileno, b'a')
        with pytest.raises(CLOSED_FILE_EXCEPTION_TYPE, match='File not open for writing'):
            watcher.write(b'a')
        open(tmpdir + '/foo', 'w').write('')
        assert_events_match(watcher.read(timeout=short_timeout()), 1, mask=flags.CREATE,  name='foo')
        with raises_ebadfd():
            os.write(fileno, b'a')
        with pytest.raises(CLOSED_FILE_EXCEPTION_TYPE, match='File not open for writing'):
            watcher.write(b'a')

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
    with pytest.raises(ValueError, match='I/O operation on closed file'):
        watcher.fileno()
    watcher.close()
    os.close(fileno)
    watcher.close()
