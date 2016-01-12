import os
import enum
import collections
import struct
import select
import time
import ctypes
from errno import EINTR
from termios import FIONREAD
from fcntl import ioctl


_libc = ctypes.cdll.LoadLibrary('libc.so.6')
_libc.__errno_location.restype = ctypes.POINTER(ctypes.c_int)

def _libc_call(function, *args):
    while True:
        rc = function(*args)
        if rc == -1:
            errno = _libc.__errno_location().contents.value
            if errno  == EINTR:
                continue
            else:
                raise OSError(errno, os.strerror(errno))
        return rc


class INotify():
    def __init__(self):
        self.fd = _libc_call(_libc.inotify_init)
        self._poller = select.poll()
        self._poller.register(self.fd)

    def add_watch(self, path, mask):
        return _libc_call(_libc.inotify_add_watch, self.fd, path.encode('utf8'), mask)

    def rm_watch(self, wd):
        _libc_call(_libc.inotify_rm_watch, self.fd, wd)

    def read(self, timeout=None, read_delay=None):
        pending = self._poller.poll(timeout)
        if pending and read_delay is not None:
            time.sleep(read_delay/1000.0)
        bytes_avail = ctypes.c_int()
        ioctl(self.fd, FIONREAD, bytes_avail)
        buffer_size = bytes_avail.value
        data = os.read(self.fd, buffer_size)
        events = parse_events(data)
        return events

    def close(self):
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


Event = collections.namedtuple('Event', ['wd', 'mask', 'cookie', 'name'])

_EVENT_STRUCT_FORMAT = 'iIII'
_EVENT_STRUCT_SIZE = struct.calcsize(_EVENT_STRUCT_FORMAT)


def parse_events(data):
    events = []
    offset = 0
    buffer_size = len(data)
    while offset < buffer_size:
        wd, mask, cookie, namesize = struct.unpack_from(_EVENT_STRUCT_FORMAT, data, offset)
        offset += _EVENT_STRUCT_SIZE
        name = ctypes.c_buffer(data[offset:offset + namesize], namesize).value.decode('utf8')
        offset += namesize
        events.append(Event(wd, mask, cookie, name))
    return events


class flags(enum.IntEnum):
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
        return [flag for flag in cls.__members__.values() if flag & mask]


class masks(enum.IntEnum):
    CLOSE = (flags.CLOSE_WRITE | flags.CLOSE_NOWRITE)
    MOVE = (flags.MOVED_FROM | flags.MOVED_TO)

    ALL_EVENTS  = (flags.ACCESS | flags.MODIFY | flags.ATTRIB | flags.CLOSE_WRITE |
                   flags.CLOSE_NOWRITE | flags.OPEN | flags.MOVED_FROM |
                   flags.MOVED_TO | flags.DELETE | flags.CREATE | flags.DELETE_SELF |
                   flags.MOVE_SELF)





