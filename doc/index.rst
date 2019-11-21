
========================
inotify_simple |release|
========================

`Chris Billington <mailto:chrisjbillington@gmail.com>`_, |today|


.. contents::
    :local:


``inotify_simple`` is a simple Python wrapper around
`inotify <http://man7.org/linux/man-pages/man7/inotify.7.html>`_.
No fancy bells and whistles, just a literal wrapper with ctypes. Only 131
lines of code!

``inotify_init()`` is wrapped as a class that does little more than hold the
resulting inotify file descriptor. A ``read()`` method is provided which reads
available data from the file descriptor and returns events as a list of
``namedtuple`` objects after unpacking them with the ``struct`` module.
``inotify_add_watch()`` and ``inotify_rm_watch()`` are wrapped with no changes
at all, taking and returning watch descriptor integers that calling code is
expected to keep track of itself, just as one would use inotify from C. Works
with Python 2.7 or Python >= 3.2.

`View on PyPI <http://pypi.python.org/pypi/inotify_simple>`_
| `Fork me on GitHub <https://github.com/chrisjbillington/inotify_simple>`_
| `Read the docs <http://inotify_simple.readthedocs.org>`_

------------
Installation
------------

to install ``inotify_simple``, run:

.. code-block:: bash

    $ pip3 install inotify_simple

or to install from source:

.. code-block:: bash

    $ python3 setup.py install

.. note::
    If on Python < 3.4, you'll need the backported `enum34 module.
    <https://pypi.python.org/pypi/enum34>`_


------------
Introduction
------------

There are many inotify python wrappers out there. `I found them all
unsatisfactory <https://xkcd.com/927/>`_. Most are far too high-level for my
tastes, and the supposed convenience they provide actually limits one from
using inotify in ways other than those the author imagined. Others are C
extensions, requiring compilation for different platforms and Python versions,
rather than a pure python module using ctypes. This one is pretty low-level
and really just does what inotify itself does and nothing more. So hopefully
if I've written it right, it will remain functional well into the future with
no changes, recompilation or attention on my part.


-------------
Example usage
-------------

.. code-block:: python
    :name: example.py

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

.. code-block:: bash
    :name: output

    $ python example.py
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

Note that the flags, since they are defined with an ``enum.IntEnum``, print as
what they are called rather than their integer values. However they are still
just integers and so can be bitwise-ANDed and ORed etc with masks etc. The
:func:`~inotify_simple.flags.from_mask` method bitwise-ANDs a mask with all
possible flags and returns a list of matches. This is for convenience and
useful for debugging which events are coming through, but performance critical
code should generally bitwise-AND masks with flags of interest itself so as to
not do unnecessary checks.

.. note::
    On Python 2, you should use ``inotify_simple`` with bytestrings (``str``).
    You *can* pass ``unicode`` strings to
    :func:`~inotify_simple.INotify.add_watch` if you like, and if you do they
    will be encoded with the filesystem encoding before being passed to the
    underlying C API. However, filesystems do not enforce that filepaths must
    actually use the declared filesystem encoding, and so some filepaths may
    not even be valid UTF8 or whatever your filesystem encoding is. Whilst the
    encoding that :func:`~inotify_simple.INotify.add_watch` does will work
    fine, your own code's decoding prior to that may break for some filepaths.
    If you want your code to work with all filepaths, resist the temptation to
    guess the encoding, and keep your paths as bytestrings. In Python 2,
    :attr:`~inotify_simple.Event` namedtuples do not decode the 'name' field -
    it is left as a bytestring.

    Python 3.2 solved this problem with ``os.fsdecode()``, ``os.fsdecode()``,
    which use the ``surrogateescape`` error handler, allowing incorrectly
    encoded filepaths to survive the round trip of decoding and encoding
    unchanged. So when using ``inotify_simple`` with Python 3, use ``str``
    filepaths.

----------------
Module reference
----------------


.. autoclass:: inotify_simple.INotify
    :members:

.. autoclass:: inotify_simple.Event

.. autofunction:: inotify_simple.parse_events

.. autoclass:: inotify_simple.flags
    :members:

.. autoclass:: inotify_simple.masks
    :members:

----------------
Full source code
----------------

Presented here for ease of verifying that this wrapper is as sensible
as it claims to be (comments stripped - see source on github to see comments).

.. literalinclude:: fullsource.py
