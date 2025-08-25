# inotify-simple 2.0

`inotify-simple` is a simple Python wrapper around
[inotify](http://man7.org/linux/man-pages/man7/inotify.7.html). No fancy bells and
whistles, just a literal wrapper with ctypes. Less than 100 lines of code!

`inotify_init1()` is wrapped as a file-like object, `INotify()`, holding the inotify
file descriptor. `INotify().read()` reads available data from the file descriptor and
returns events as `namedtuple` objects after unpacking them with the `struct` module.
`inotify_add_watch()` and `inotify_rm_watch()` are wrapped with no changes at all,
taking and returning watch descriptor integers that calling code is expected to keep
track of itself, just as one would use `inotify` from C. Requires Python 3.6 or higher.

[View on PyPI](http://pypi.python.org/pypi/inotify-simple) |
[View on GitHub](https://github.com/chrisjbillington/inotify_simple) |
[Read the docs](http://inotify-simple.readthedocs.io)

## Project status: stable

This project does not require much maintenance
to continue to to meet its goals. Do not panic if there
have been no commits in a long time, this is normal.

## Installation

to install `inotify-simple`, run:

```bash
$ pip install inotify-simple
```

or to install from source, clone this repository and run:

```bash
$ pip install .
```

## Introduction

There are many inotify python wrappers out there. [I found them all
unsatisfactory](https://xkcd.com/927/). Most are far too high-level for my
tastes, and the supposed convenience they provide actually limits one from
using inotify in ways other than those the author imagined. Others are C
extensions, requiring compilation for different platforms and Python versions,
rather than a pure python module using ctypes. This one is pretty low-level
and really just does what inotify itself does and nothing more. So hopefully
if I've written it right, it will remain functional well into the future with
no changes, recompilation or attention on my part.

## Example usage

```python
import os
from inotify_simple import INotify, flags

os.mkdir('/tmp/inotify_test')

inotify = INotify()
watch_flags = flags.CREATE | flags.DELETE | flags.MODIFY | flags.DELETE_SELF
wd = inotify.add_watch('/tmp/inotify_test', watch_flags)

# Now create, delete and modify some files in the directory being monitored:
os.chdir('/tmp/inotify_test')
# CREATE event for a directory:
os.system('mkdir foo')
# CREATE event for a file:
os.system('echo hello > test.txt')
# MODIFY event for the file:
os.system('echo world >> test.txt')
# DELETE event for the file
os.system('rm test.txt')
# DELETE event for the directory
os.system('rmdir foo')
os.chdir('/tmp')
# DELETE_SELF on the original directory. # Also generates an IGNORED event
# indicating the watch was removed.
os.system('rmdir inotify_test')

# And see the corresponding events:
for event in inotify.read():
    print(event)
    for flag in flags.from_mask(event.mask):
        print('    ' + str(flag))
```

This outputs the following:
```
Event(wd=1, mask=1073742080, cookie=0, name=u'foo')
    flags.CREATE
    flags.ISDIR
Event(wd=1, mask=256, cookie=0, name=u'test.txt')
    flags.CREATE
Event(wd=1, mask=2, cookie=0, name=u'test.txt')
    flags.MODIFY
Event(wd=1, mask=512, cookie=0, name=u'test.txt')
    flags.DELETE
Event(wd=1, mask=1073742336, cookie=0, name=u'foo')
    flags.DELETE
    flags.ISDIR
Event(wd=1, mask=1024, cookie=0, name=u'')
    flags.DELETE_SELF
Event(wd=1, mask=32768, cookie=0, name=u'')
    flags.IGNORED
```

Note that the flags, since they are defined with an `enum.IntEnum`, print as
what they are called rather than their integer values. However they are still
just integers and so can be bitwise-ANDed and ORed etc with masks etc. The
`flags.from_mask()` method bitwise-ANDs a mask with all possible flags and
returns a list of matches. This is for convenience and useful for debugging
which events are coming through, but performance critical code should
generally bitwise-AND masks with flags of interest itself so as to not do
unnecessary checks.

[See here](http://inotify-simple.readthedocs.io) for more.
