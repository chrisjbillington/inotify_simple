import errno
from sys import version_info, getfilesystemencoding
import os
from enum import Enum, IntEnum
from collections import namedtuple
from struct import unpack_from, calcsize
from threading import Lock
import time
from ctypes import CDLL, get_errno, c_int
from ctypes.util import find_library
from errno import EINTR
from termios import FIONREAD
from fcntl import ioctl
from io import FileIO

PY2 = version_info.major < 3
if PY2:
    monotonic = time.time
    fsencode = lambda s: s if isinstance(s, str) else s.encode(getfilesystemencoding())
    # In 32-bit Python < 3 the inotify constants don't fit in an IntEnum:
    IntEnum = type('IntEnum', (long, Enum), {})
else:
    monotonic = time.monotonic
    from os import fsencode, fsdecode


__version__ = '1.3.5'

__all__ = ['Event', 'INotify', 'flags', 'masks', 'parse_events']

_libc = None


def _libc_call(function, *args):
    """Wrapper which raises errors and retries on EINTR."""
    while True:
        rc = function(*args)
        if rc != -1:
            return rc
        errno = get_errno()
        if errno != EINTR:
            raise OSError(errno, os.strerror(errno))


#: A ``namedtuple`` (wd, mask, cookie, name) for an inotify event. On Python 3 the
#: :attr:`~inotify_simple.Event.name`  field is a ``str`` decoded with
#: ``os.fsdecode()``, on Python 2 it is ``bytes``.
Event = namedtuple('Event', ['wd', 'mask', 'cookie', 'name'])

_EVENT_FMT = 'iIII'
_EVENT_SIZE = calcsize(_EVENT_FMT)

class INotify(FileIO):

    #: The inotify file descriptor returned by ``inotify_init()``. You are
    #: free to use it directly with ``os.read`` if you'd prefer not to call
    #: :func:`~inotify_simple.INotify.read` for some reason. Also available as
    #: :func:`~inotify_simple.INotify.fileno`
    fd = property(FileIO.fileno)

    def __init__(self, inheritable=False, nonblocking=False, closefd=True):
        """File-like object wrapping ``inotify_init1()``. Raises ``OSError`` on failure.

        Can be used as a context manager to ensure it is closed, and can be used
        directly by functions expecting a file-like object, such as ``select``, or with
        functions expecting a file descriptor via :func:`~inotify_simple.INotify.fileno`.

        Args:
            inheritable (bool): whether the inotify file descriptor will be inherited by
                child processes. The default,``False``, corresponds to passing the
                ``IN_CLOEXEC`` flag to ``inotify_init1()``. Setting this flag when
                opening filedescriptors is the default behaviour of Python standard
                library functions since PEP 446. On Python < 3.3, the file descriptor
                will be inheritable and this argument has no effect, one must instead
                use fcntl to set FD_CLOEXEC to make it non-inheritable.

            nonblocking (bool): whether to open the inotify file descriptor in
                nonblocking mode, corresponding to passing the ``IN_NONBLOCK`` flag to
                ``inotify_init1()``. This does not affect the normal behaviour of
                :func:`~inotify_simple.INotify.read`, which uses ``poll()`` to control
                blocking behaviour according to the given timeout, but will cause other
                reads of the file descriptor (for example if the application reads data
                manually with ``os.read(fd)``) to raise ``BlockingIOError`` if no data
                is available.

            closefd (bool): Whether to close the underlying file descriptor when this
                object is garbage collected or when close() is called. See
                :func:`~io.FileIO.__init__` for more information."""

        try:
            libc_so = find_library('c')
        except RuntimeError: # Python on Synology NASs raises a RuntimeError
            libc_so = None
        global _libc; _libc = _libc or CDLL(libc_so or 'libc.so.6', use_errno=True)
        O_CLOEXEC = getattr(os, 'O_CLOEXEC', 524288) # Only defined in Python 3.3+
        flags = (not inheritable) * O_CLOEXEC | bool(nonblocking) * os.O_NONBLOCK
        fileno = _libc_call(_libc.inotify_init1, flags)
        super(INotify, self).__init__(fileno, mode='rb', closefd=closefd)

        # If supported, disable inheritability across fork(), not just exec via CLOEXEC:
        if not inheritable and hasattr(os, 'set_inheritable'):
            os.set_inheritable(fileno, False)
        self._read_lock = Lock()
        self._poller = None

    def add_watch(self, path, mask):
        """Wrapper around ``inotify_add_watch()``. Returns the watch
        descriptor or raises an ``OSError`` on failure.

        This method is idempotent and thread safe: repeated or concurrent calls to
        :func:`~inotify_simple.INotify.add_watch` for the same ``path`` will return
        the same watch descriptor integer. Calling :func:`~inotify_simple.INotify.add_watch`
        multiple times for the same ``path`` with different ``mask`` values will
        modify the watcher in-place.

        .. note::
            If a watch exists whose ``mask`` subscribes to events of a given type,
            and that watch is modified with a new ``mask`` that unsubscribes from
            that event type, subsequent calls to :func:`~inotify_simple.INotify.read`
            may still return events of the originally-subscribed type due to queueing.

        Args:
            path (str, bytes, or PathLike): The path to watch. Will be encoded with
                ``os.fsencode()`` before being passed to ``inotify_add_watch(2)``.

            mask (int): The mask of events to watch for. Can be constructed by
                bitwise-ORing :class:`~inotify_simple.flags` together.

        Returns:
            int: A watch descriptor"""
        # Explicit conversion of Path to str required on Python < 3.6
        path = str(path) if hasattr(path, 'parts') else path
        return _libc_call(_libc.inotify_add_watch, self.fileno(), fsencode(path), mask)

    def rm_watch(self, wd):
        """Wrapper around ``inotify_rm_watch()``. Raises ``OSError`` on failure.

        .. note::
            After removing a watch, subsequent or concurrent calls to
            :func:`~inotify_simple.INotify.read` may return events of type
            :attr:`~inotify_simple.flags.IGNORED` with empty ``name`` fields indicating
            events related to removed watches. These events may be observed even when
            filesystem modifications on a path are performed after a call to
            :func:`~inotify_simple.INotify.rm_watch` for that path.

        Args:
            wd (int): The watch descriptor to remove"""
        _libc_call(_libc.inotify_rm_watch, self.fileno(), wd)

    def read(self, timeout=None, read_delay=None):
        """Read the inotify file descriptor and return the resulting
        :attr:`~inotify_simple.Event` namedtuples (wd, mask, cookie, name).

        This method is thread safe; concurrent readers will not block unexpectedly or
        receive duplicate events.

        Args:
            timeout (int): The time in milliseconds to wait for events if there are
                none. If negative or ``None``, block until there are events. If zero,
                return immediately if there are no events to be read.

            read_delay (int): If there are no events immediately available for reading,
                then this is the time in milliseconds to wait after the first event
                arrives before reading the file descriptor. This allows further events
                to accumulate before reading, which allows the kernel to coalesce like
                events and can decrease the number of events the application needs to
                process. However, this also increases the risk that the event queue will
                overflow due to not being emptied fast enough.

        Returns:
            list: A list of :attr:`~inotify_simple.Event` namedtuples

        .. note::
            Like other blocking reads on non-file objects (e.g. pipes), closing an
            `:func:`~inotify_simple.INotify` object while another thread is calling
            ``read()`` with a timeout of ``None`` is not guaranteed to unblock the
            blocked ``read()``.
        """

        if timeout is None:
            if not self._read_lock.acquire():
                return []
        else:
            t0 = monotonic()
            if not self._read_lock.acquire(int(round(timeout / 1000.0))):
                return []
            timeout -= (round(monotonic() - t0) * 1000)
        try:
            # Cache the poller on the object
            if self._poller is None:
                # Runtime import to allow this module to remain partially functional on OSes or pythons where poll()
                # is not available.
                from select import poll

                self._poller = poll()
                self._poller.register(self.fileno())

            # If timeout is None, poll until events arrive (poll() will never return an empty list):
            if timeout is None:
                self._poller.poll()
            # Poll for the remaining timeout, if any. If we've used up the remaining timeout, poll once anyway:
            elif not self._poller.poll(max(timeout, 0)):
                return []
            # If events have arrived but we want to wait for additional events to be coalesced by the kernel, wait for
            # some additional time:
            if read_delay is not None:
                time.sleep(read_delay / 1000.0)
            return self._readall()
        finally:
            self._read_lock.release()

    def _readall(self):
        bytes_avail = c_int()
        ioctl(self, FIONREAD, bytes_avail)
        value_to_read = bytes_avail.value
        if value_to_read == 0 and not self.closed:
            # If there isn't anything to read, it's probably a race condition/bug, *except* in the case of a closed
            # underlying file descriptor, in which case we should proceed and raise an error from the call to read():
            try:
                os.fstat(self.fileno())
                raise ValueError('Bug: read will fail {}'.format(self.closed))
            except (OSError, IOError) as ex:  # IOError included for python 2 compatibility
                if ex.errno != errno.EBADF:
                    raise
                value_to_read = 1
            except ValueError as ex:
                if 'I/O operation on closed file' not in str(ex):
                    raise
                value_to_read = 1

        return parse_events(super(FileIO, self).read(value_to_read))


def parse_events(data):
    """Unpack data read from an inotify file descriptor into 
    :attr:`~inotify_simple.Event` namedtuples (wd, mask, cookie, name). This function
    can be used if the application has read raw data from the inotify file
    descriptor rather than calling :func:`~inotify_simple.INotify.read`.

    Args:
        data (bytes): A bytestring as read from an inotify file descriptor.
        
    Returns:
        list: A list of :attr:`~inotify_simple.Event` namedtuples"""
    pos = 0
    events = []
    while pos < len(data):
        wd, mask, cookie, namesize = unpack_from(_EVENT_FMT, data, pos)
        pos += _EVENT_SIZE + namesize
        name = data[pos - namesize : pos].split(b'\x00', 1)[0]
        events.append(Event(wd, mask, cookie, name if PY2 else fsdecode(name)))
    return events


class flags(IntEnum):
    """Inotify flags as defined in ``inotify.h`` but with ``IN_`` prefix omitted.
    Includes a convenience method :func:`~inotify_simple.flags.from_mask` for extracting
    flags from a mask."""
    ACCESS = 0x00000001  #: File was accessed
    MODIFY = 0x00000002  #: File was modified
    ATTRIB = 0x00000004  #: Metadata changed
    CLOSE_WRITE = 0x00000008  #: Writable file was closed
    CLOSE_NOWRITE = 0x00000010  #: Unwritable file closed
    OPEN = 0x00000020  #: File was opened
    MOVED_FROM = 0x00000040  #: File was moved from X
    MOVED_TO = 0x00000080  #: File was moved to Y
    CREATE = 0x00000100  #: Subfile was created
    DELETE = 0x00000200  #: Subfile was deleted
    DELETE_SELF = 0x00000400  #: Self was deleted
    MOVE_SELF = 0x00000800  #: Self was moved

    UNMOUNT = 0x00002000  #: Backing fs was unmounted
    Q_OVERFLOW = 0x00004000  #: Event queue overflowed
    IGNORED = 0x00008000  #: File was ignored

    ONLYDIR = 0x01000000  #: only watch the path if it is a directory
    DONT_FOLLOW = 0x02000000  #: don't follow a sym link
    EXCL_UNLINK = 0x04000000  #: exclude events on unlinked objects
    MASK_ADD = 0x20000000  #: add to the mask of an already existing watch
    ISDIR = 0x40000000  #: event occurred against dir
    ONESHOT = 0x80000000  #: only send event once

    @classmethod
    def from_mask(cls, mask):
        """Convenience method that returns a list of every flag in a mask."""
        return [flag for flag in cls.__members__.values() if flag & mask]


class masks(IntEnum):
    """Convenience masks as defined in ``inotify.h`` but with ``IN_`` prefix omitted."""
    #: helper event mask equal to ``flags.CLOSE_WRITE | flags.CLOSE_NOWRITE``
    CLOSE = flags.CLOSE_WRITE | flags.CLOSE_NOWRITE
    #: helper event mask equal to ``flags.MOVED_FROM | flags.MOVED_TO``
    MOVE = flags.MOVED_FROM | flags.MOVED_TO

    #: bitwise-OR of all the events that can be passed to
    #: :func:`~inotify_simple.INotify.add_watch`
    ALL_EVENTS  = (flags.ACCESS | flags.MODIFY | flags.ATTRIB | flags.CLOSE_WRITE |
        flags.CLOSE_NOWRITE | flags.OPEN | flags.MOVED_FROM | flags.MOVED_TO | 
        flags.CREATE | flags.DELETE| flags.DELETE_SELF | flags.MOVE_SELF)
