
========================
inotify_simple |release|
========================

`Chris Billington <mailto:chrisjbillington@gmail.com>`_, |today|


.. contents::
    :local:


``inotify_simple`` is a simple Python wrapper around
`inotify <http://man7.org/linux/man-pages/man7/inotify.7.html>`_.
No fancy bells and whistles, just a literal wrapper with ctypes. Only ~100
lines of code!

``inotify_init1()`` is wrapped as a file-like object, :class:`~inotify_simple.INotify`,
holding the inotify file descriptor. :func:`~~inotify_simple.INotify.read` reads
available data from the file descriptor and returns events as
:attr:`~inotify_simple.Event` namedtuples after unpacking them with the ``struct``
module. ``inotify_add_watch()`` and ``inotify_rm_watch()`` are wrapped with no changes
at all, taking and returning watch descriptor integers that calling code is expected to
keep track of itself, just as one would use inotify from C. Works with Python 2.7 and
Python >= 3.2.

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

There are many inotify python wrappers out there. `I found them all unsatisfactory
<https://xkcd.com/927/>`_. Most are far too high-level for my tastes, and the supposed
convenience they provide actually limits one from using inotify in ways other than those
the author imagined. Others are C extensions, requiring compilation for different
platforms and Python versions, rather than a pure python module using ctypes. This one
is pretty low-level and really just does what inotify itself does and nothing more. So
hopefully if I've written it right, it will remain functional well into the future with
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
    Event(wd=1, mask=1073742080, cookie=0, name='foo')
        flags.CREATE
        flags.ISDIR
    Event(wd=1, mask=256, cookie=0, name='test.txt')
        flags.CREATE
    Event(wd=1, mask=2, cookie=0, name='test.txt')
        flags.MODIFY
    Event(wd=1, mask=512, cookie=0, name='test.txt')
        flags.DELETE
    Event(wd=1, mask=1073742336, cookie=0, name='foo')
        flags.DELETE
        flags.ISDIR
    Event(wd=1, mask=1024, cookie=0, name='')
        flags.DELETE_SELF
    Event(wd=1, mask=32768, cookie=0, name='')
        flags.IGNORED

Note that the flags, since they are defined with an ``enum.IntEnum``, print as
what they are called rather than their integer values. However they are still
just integers and so can be bitwise-ANDed and ORed etc with masks etc. The
:func:`~inotify_simple.flags.from_mask` method bitwise-ANDs a mask with all
possible flags and returns a list of matches. This is for convenience and
useful for debugging which events are coming through, but performance critical
code should generally bitwise-AND masks with flags of interest itself so as to
not do unnecessary checks.


---------------
Tips and tricks
---------------

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Gracefully exit a blocking :meth:`.read`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is common for an application to block indefinitely on a :meth:`.read` while
waiting for events to be received. However it can be challenging to manage its
shutdown.

When used without a timeout, the :meth:`.read` uses :func:`~select.poll` on the
internal file descriptor only. This call will return if there is an event on one
of the file descriptors it monitors.

The idea to correctly unblock the :meth:`.read` is to add a file descriptor to be
processed in addition to the internal descriptor. This new file descriptor will
only be used to exit the application. Usually a :func:`~os.pipe` is used for
this purpose.

The `inotify_simple` module is not intended to have such a high-level mechanism.
But it can be done directly in the user application by wrapping the calls to
:obj:`.INotify`.

Such a wrapper should:

- Have an :obj:`.INotify` object.
- Have a :func:`~os.pipe`.
- Run :func:`~select.select` or :func:`~select.poll` on both previous object
  descriptors.
- Retrieve the inotify events by calling :meth:`.read` with ``timeout=0`` (so
  the underlying :func:`~select.poll` is not called).
- Send dummy data to the `pipe` when a stop has been requested.

An example wrapper class implementing :obj:`~threading.Thread` can be found
below:


.. code-block:: python
   :emphasize-lines: 15,18-19,27-29,32-33,38-41,45-47

    import os
    import select
    import threading

    from inotify_simple import INotify, masks, flags

    class InotifyThread(threading.Thread):
        def __init__(self, path):
            self.__path = path

            # Initialize the parent class
            threading.Thread.__init__(self)

            # Create an inotify object
            self.__inotify = INotify()

            # Create a pipe
            self.__read_fd, write_fd = os.pipe()
            self.__write = os.fdopen(write_fd, "wb")

        def run(self):
            # Watch the current directory
            self.__inotify.add_watch(self.__path, masks.ALL_EVENTS)

            while True:
                # Wait for inotify events or a write in the pipe
                rlist, _, _ = select.select(
                    [self.__inotify.fileno(), self.__read_fd], [], []
                )

                # Print all inotify events
                if self.__inotify.fileno() in rlist:
                    for event in self.__inotify.read(timeout=0):
                        flags = [f.name for f in flags.from_mask(event.mask)]
                        print(f"{event} {flags}")

                # Close everything properly if requested
                if self.__read_fd in rlist:
                    os.close(self.__read_fd)
                    self.__inotify.close()
                    return

        def stop(self):
            # Request for stop by writing in the pipe
            if not self.__write.closed:
                self.__write.write(b"\x00")
                self.__write.close()


.. ------------------
.. Usage with asyncio
.. ------------------

.. Traditional asynchronous code may use ``select()`` and ``poll()`` to ensure

.. When calling this method from async code using ``asyncio``, you will want to
.. ensure it does not block. In this case, you must not use ``read_delay``, and you
.. must ensure the file descriptor is ready for reading before calling this method
.. (in which case ``timeout`` is irrelevant). You can reproduce the effect of
.. ``read_delay``

.. .. code-block:: python

..     test = 7


----------------
Module reference
----------------

.. autoclass:: inotify_simple.INotify
    :show-inheritance:
    :members: add_watch, rm_watch, read, close, fileno, fd

.. autoclass:: inotify_simple.Event
    :show-inheritance:
    :members: wd, mask, cookie, name

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
