import os
import sys
import enum
import collections
import struct
import select
import time
import ctypes
from errno import EINTR
from termios import FIONREAD
from fcntl import ioctl


if sys.version_info.major < 3:
    # For Python 2, we work with bytestrings. If the user passes in a unicode
    # string, it will be encoded with the filesystem encoding before use:
    _fsencoding = sys.getfilesystemencoding()
    try:
        import pathlib
    except ImportError:
        _fsencode = lambda s: s.encode(_fsencoding)
    else:
        # If the user passes a Path object it will be converted to bytes:
        _fsencode = lambda s: bytes(s) if isinstance(s, pathlib.Path) else s.encode(_fsencoding)
    # And we will not decode bytestrings in inotify events, we will simply
    # give the user bytestrings back:
    _fsdecode = lambda s: s
    # In 32-bit Python < 3 the inotify constants don't fit in an IntEnum and
    # will cause an OverflowError. Overwiting the IntEnum with a LongEnum
    # fixes this problem.
    class LongEnum(long, enum.Enum): pass
    _EnumType = LongEnum

else:
    # For Python 3, we work with (unicode) strings. We use os.fsencode and
    # os.fsdecode, which are used by standard-library functions that return
    # paths, and are able to round-trip possibly incorrectly encoded
    # filepaths:
    if sys.version_info.major == 3 and  sys.version_info.minor < 6:
        # On Python < 3.6, os.fsencode does not accept pathlike objects, so we
        # must convert them to strings before encoding with fsencode:
        try:
            import pathlib
        except ImportError:
            _fsencode = os.fsencode
        else:
            _fsencode = lambda p: os.fsencode(str(p) if isinstance(p, pathlib.Path) else p)
    else:
        _fsencode = os.fsencode
    _fsdecode = os.fsdecode
    _EnumType = enum.IntEnum

__all__ = ['flags', 'masks', 'parse_events', 'INotify', 'Event']

_libc = None

def _ensure_libc_loaded():
    global _libc
    if _libc is None:
        _libc = ctypes.cdll.LoadLibrary('libc.so.6')
        _libc.__errno_location.restype = ctypes.POINTER(ctypes.c_int)

def _libc_call(function, *args):
    """Wrapper which raises errors and retries on EINTR."""
    while True:
        rc = function(*args)
        if rc == -1:
            errno = _libc.__errno_location().contents.value
            if errno  == EINTR:
                # retry
                continue
            else:
                raise OSError(errno, os.strerror(errno))
        return rc


class INotify(object):
    def __init__(self):
        """Object wrapper around ``inotify_init()`` which stores the inotify file
        descriptor. Raises an OSError on failure. :func:`~inotify_simple.INotify.close`
        should be called when no longer needed. Can be used as a context manager to
        ensure it is closed. This object has a `fileno()` method, and so can be used
        directly with `select()` or other functions expecting a file-like object."""
        #: The inotify file descriptor returned by ``inotify_init()``. You are
        #: free to use it directly with ``os.read`` if you'd prefer not to call
        #: :func:`~inotify_simple.INotify.read` for some reason.
        _ensure_libc_loaded()
        self.fd = _libc_call(_libc.inotify_init)
        self._poller = select.poll()
        self._poller.register(self.fd)

    def add_watch(self, path, mask):
        """Wrapper around ``inotify_add_watch()``. Returns the watch
        descriptor or raises an OSError on failure.

        Args:
            path (py3 str or bytes, py2 unicode or str): The path to watch.
                If ``str`` in python3 or ``unicode`` in python2, will be encoded with
                the filesystem encoding before being passed to
                ``inotify_add_watch()``. This method also accepts
                ``pathlib.Path`` objects.

            mask (int): The mask of events to watch for. Can be constructed by
                bitwise-ORing :class:`~inotify_simple.flags` together.

        Returns:
            int: watch descriptor"""
        if not isinstance(path, bytes):
            path = _fsencode(path)
        return _libc_call(_libc.inotify_add_watch, self.fd, path, mask)

    def rm_watch(self, wd):
        """Wrapper around ``inotify_rm_watch()``. Raises OSError on failure.

        Args:
            wd (int): The watch descriptor to remove"""
        _libc_call(_libc.inotify_rm_watch, self.fd, wd)

    def read(self, timeout=None, read_delay=None):
        """Read the inotify file descriptor and return the resulting list of
        :attr:`~inotify_simple.Event` namedtuples (wd, mask, cookie, name).

        Args:
            timeout (int): The time in milliseconds to wait for events if
                there are none. If `negative or `None``, block until there are
                events.

            read_delay (int): The time in milliseconds to wait after the first
                event arrives before reading the buffer. This allows further
                events to accumulate before reading, which allows the kernel
                to consolidate like events and can enhance performance when
                there are many similar events.

        Returns:
            list: list of :attr:`~inotify_simple.Event` namedtuples"""
        # Wait for the first event:
        pending = self._poller.poll(timeout)
        if not pending:
            # Timed out, no events
            return []
        if read_delay is not None:
            # Wait for more events to accumulate:
            time.sleep(read_delay/1000.0)
        # How much data is available to read?
        bytes_avail = ctypes.c_int()
        ioctl(self.fd, FIONREAD, bytes_avail)
        buffer_size = bytes_avail.value
        # Read and parse it:
        data = os.read(self.fd, buffer_size)
        events = parse_events(data)
        return events

    def close(self):
        """Close the inotify file descriptor, if not already closed"""
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def fileno(self):
        """Return the file number of the underlying inotify file descriptor"""
        return self.fd

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


#: A ``namedtuple`` (wd, mask, cookie, name) for an inotify event.
#: ``namedtuple`` objects are very lightweight to instantiate and access, whilst
#: being human readable when printed, which is useful for debugging and
#: logging. For best performance, note that element access by index is about
#: four times faster than by name. Note: in Python 2, name is a bytestring,
#: not a unicode string. In Python 3 it is a string decoded with ``os.fsdecode()``.
Event = collections.namedtuple('Event', ['wd', 'mask', 'cookie', 'name'])

_EVENT_STRUCT_FORMAT = 'iIII'
_EVENT_STRUCT_SIZE = struct.calcsize(_EVENT_STRUCT_FORMAT)


def parse_events(data):
    """Parse data read from an inotify file descriptor into list of
    :attr:`~inotify_simple.Event` namedtuples (wd, mask, cookie, name). This
    function can be used if you have decided to call ``os.read()`` on the
    inotify file descriptor yourself, instead of calling
    :func:`~inotify_simple.INotify.read`.

    Args:
        data (bytes): A bytestring as read from an inotify file descriptor
    Returns:
        list: list of :attr:`~inotify_simple.Event` namedtuples"""
    events = []
    offset = 0
    buffer_size = len(data)
    while offset < buffer_size:
        wd, mask, cookie, namesize = struct.unpack_from(_EVENT_STRUCT_FORMAT, data, offset)
        offset += _EVENT_STRUCT_SIZE
        name = _fsdecode(ctypes.c_buffer(data[offset:offset + namesize], namesize).value)
        offset += namesize
        events.append(Event(wd, mask, cookie, name))
    return events


class flags(_EnumType):
    """Inotify flags as defined in ``inotify.h`` but with ``IN_`` prefix
    omitted. Includes a convenience method for extracting flags from a mask.
    """
    ACCESS = 0x00000001  #: File was accessed
    MODIFY = 0x00000002  #: File was modified
    ATTRIB = 0x00000004  #: Metadata changed
    CLOSE_WRITE = 0x00000008  #: Writable file was closed
    CLOSE_NOWRITE = 0x00000010  #: Unwritable file closed
    OPEN = 0x00000020  #: File was opened
    MOVED_FROM = 0x00000040  #: File was moved from X
    MOVED_TO  = 0x00000080  #: File was moved to Y
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
        """Convenience method. Return a list of every flag in a mask."""
        return [flag for flag in cls.__members__.values() if flag & mask]


class masks(_EnumType):
    """Convenience masks as defined in ``inotify.h`` but with ``IN_`` prefix
    omitted."""
    #: helper event mask equal to ``flags.CLOSE_WRITE | flags.CLOSE_NOWRITE``
    CLOSE = (flags.CLOSE_WRITE | flags.CLOSE_NOWRITE)
    #: helper event mask equal to ``flags.MOVED_FROM | flags.MOVED_TO``
    MOVE = (flags.MOVED_FROM | flags.MOVED_TO)

    #: bitwise-OR of all the events that can be passed to
    #: :func:`~inotify_simple.INotify.add_watch`
    ALL_EVENTS  = (flags.ACCESS | flags.MODIFY | flags.ATTRIB | flags.CLOSE_WRITE |
                   flags.CLOSE_NOWRITE | flags.OPEN | flags.MOVED_FROM |
                   flags.MOVED_TO | flags.DELETE | flags.CREATE | flags.DELETE_SELF |
                   flags.MOVE_SELF)





