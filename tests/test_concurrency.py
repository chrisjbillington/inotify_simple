import os
import warnings

import pytest

from inotify_simple import flags
from tests import (
    watcher_and_dir,
    assert_events_match,
    short_timeout,
    assert_takes_between,
    raises_ebadfd,
    try_to_increase_watches,
    cpu_count,
)
from threading import Timer, Event, Thread, current_thread

try:
    from queue import Queue
except ImportError:
    from Queue import Queue

# NB these tests may flake. That is somewhat the cost of doing business: the point of these tests is to validate
# timings in the presence of concurrency and indeterminate load conditions. If flakes cause problems here, consider:
# 1. Using a retry loop (manually or via e.g. 'pytest-retry').
# 2. Increasing INTERVAL_SECONDS and/or SLOP_SECONDS.
# 3. Skipping the test or falling back to run it manually.
SLOP_SECONDS = 0.1
INTERVAL_SECONDS = 0.2
SLEEP_SECONDS_AFTER_GENERATING_MAX_EVENTS = 0.5


@pytest.mark.parametrize("timeout", (None, (INTERVAL_SECONDS + SLOP_SECONDS) * 1000))
def test_wakeup(timeout):
    with watcher_and_dir(flags.CREATE | flags.ONESHOT) as (watcher, tempdir):
        timer = Timer(INTERVAL_SECONDS, lambda: open(tempdir + "/foo", "w").write(""))
        try:
            timer.start()
            assert_events_match(
                watcher.read(timeout=timeout), 1, mask=flags.CREATE, name="foo"
            )
        finally:
            timer.cancel()


@pytest.mark.parametrize("raw_close", (True, False))
@pytest.mark.parametrize("read_first", (None, "success", "fail"))
def test_close_while_waiting(read_first, raw_close):
    with watcher_and_dir(flags.CREATE | flags.ONESHOT) as (watcher, tempdir):
        if read_first == "success":
            open(tempdir + "/foo", "w").write("")
            assert_events_match(
                watcher.read(timeout=short_timeout()), 1, mask=flags.CREATE, name="foo"
            )
        if read_first == "fail":
            assert watcher.read(timeout=short_timeout()) == []

        if raw_close:
            func = lambda: os.close(watcher.fileno())
            cmgr = raises_ebadfd()
        else:
            func = watcher.close
            cmgr = pytest.raises(ValueError, match="I/O operation on closed file")
        timer = Timer(INTERVAL_SECONDS, func)
        try:
            timer.start()
            with cmgr, assert_takes_between(
                INTERVAL_SECONDS - SLOP_SECONDS, INTERVAL_SECONDS + SLOP_SECONDS
            ):
                watcher.read(timeout=1000)
        finally:
            timer.cancel()


def generate_changes(basedir, queue, done, maxevents):
    created = 0
    while not done.is_set():
        for i in range(maxevents):
            if i % 100 == 0 and done.is_set():
                break
            os.mkdir("{}/{}.temp".format(basedir, created))
            created += 1
        done.wait(SLEEP_SECONDS_AFTER_GENERATING_MAX_EVENTS)

    queue.put_nowait((current_thread().ident, created))


def read_changes(watcher, wait_in_poll, read_wait_seconds, queue, done):
    consecutive_empty_reads = 0
    finished = False
    ident = current_thread().ident
    timeout = read_wait_seconds * 1000 if wait_in_poll else 0
    while True:
        rv = watcher.read(timeout=timeout)
        if len(rv):
            consecutive_empty_reads = 0
            queue.put_nowait((ident, rv))
        elif finished:
            # Once the done flag is set, poll until nothing comes out:
            return
        else:
            consecutive_empty_reads += 1
            finished = consecutive_empty_reads > 2 and done.is_set()
        if not len(rv) and not wait_in_poll:
            done.wait(read_wait_seconds)


# NB: To run more extensive concurrency/torture tests, increase the below parameters and run on bare metal. Be aware
# that this will cause the test suite to take a very long time:
@pytest.mark.parametrize("read_wait_seconds", (0, 0.05))
@pytest.mark.parametrize("wait_in_poll", (True, False))
@pytest.mark.parametrize("torture_seconds", (0.25, 1))
@pytest.mark.parametrize("num_readers", sorted({1, 2, 4, cpu_count()}))
def test_torture_concurrent_reads(
    num_readers, torture_seconds, wait_in_poll, read_wait_seconds
):
    stop_generating = Event()
    stop_reading = Event()
    queue = Queue()
    with watcher_and_dir(flags.CREATE | flags.Q_OVERFLOW) as (watcher, tempdir):
        generator = Thread(
            target=generate_changes,
            args=(tempdir, queue, stop_generating, try_to_increase_watches()),
            name="inotify test file change event generator",
        )
        generator.start()
        threads = []
        for i in range(num_readers):
            threads.append(
                Thread(
                    target=read_changes,
                    args=(
                        watcher,
                        wait_in_poll,
                        read_wait_seconds,
                        queue,
                        stop_reading,
                    ),
                    name="inotify test reader {}".format(i),
                )
            )
            threads[-1].start()
        stop_generating.wait(torture_seconds)
        stop_generating.set()
        generator.join()
        stop_reading.set()
        for thread in threads:
            thread.join()

    observed = 0
    observed_threads = set()
    expected = None
    while not queue.empty():
        tid, value = queue.get_nowait()
        if tid == generator.ident:
            assert expected is None
            expected = value
        else:
            observed_threads.add(tid)
            assert not any(ev.mask & flags.Q_OVERFLOW for ev in value)
            observed += len(value)

    assert expected is not None
    assert observed == expected

    expected_read_sources = {t.ident for t in threads}
    # NB: There is no way to make this test deterministically pass even a little bit, so it's relegated to a
    # warning instead.
    if observed_threads != expected_read_sources:
        warnings.warn(
            "Not all workers read events ({} workers; {} read events)".format(
                num_readers, len(observed_threads)
            )
        )
