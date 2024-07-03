import os

import pytest

from inotify_simple import flags
from tests import watcher_and_dir, assert_events_match, short_timeout, assert_takes_between, raises_ebadfd
from threading import Timer

# NB these tests may flake. That is somewhat the cost of doing business: the point of these tests is to validate
# timings in the presence of concurrency and indeterminate load conditions. If flakes cause problems here, consider:
# 1. Using a retry loop (manually or via e.g. 'pytest-retry').
# 2. Increasing INTERVAL_SECONDS and/or SLOP_SECONDS.
# 3. Skipping the test or falling back to run it manually.
SLOP_SECONDS = 0.1
INTERVAL_SECONDS = 0.2


@pytest.mark.parametrize('timeout', (None, (INTERVAL_SECONDS + SLOP_SECONDS) * 1000))
def test_wakeup(timeout):
    with watcher_and_dir(flags.CREATE | flags.ONESHOT) as (watcher, tmpdir):
        timer = Timer(INTERVAL_SECONDS, lambda: open(tmpdir + '/foo', 'w').write(''))
        try:
            timer.start()
            assert_events_match(watcher.read(timeout=timeout), 1, mask=flags.CREATE, name='foo')
        finally:
            timer.cancel()


@pytest.mark.parametrize('raw_close', (True, False))
@pytest.mark.parametrize('read_first', (None, 'success', 'fail'))
def test_close_while_waiting(read_first, raw_close):
    with watcher_and_dir(flags.CREATE | flags.ONESHOT) as (watcher, tmpdir):
        if read_first == 'success':
            open(tmpdir + '/foo', 'w').write('')
            assert_events_match(watcher.read(timeout=short_timeout()), 1, mask=flags.CREATE, name='foo')
        if read_first == 'fail':
            assert watcher.read(timeout=short_timeout()) == []


        if raw_close:
            func = lambda: os.close(watcher.fileno())
            cmgr = raises_ebadfd()
        else:
            func = watcher.close
            cmgr = pytest.raises(ValueError, match='I/O operation on closed file')
        timer = Timer(INTERVAL_SECONDS, func)
        try:
            timer.start()
            with cmgr, assert_takes_between(INTERVAL_SECONDS - SLOP_SECONDS, INTERVAL_SECONDS + SLOP_SECONDS):
                watcher.read(timeout=1000)
        finally:
            timer.cancel()
