#!/usr/bin/env python

# To upload a version to PyPI, run:
#    python setup.py sdist upload
# If the package is not registered with PyPI yet, do so with:
#     python setup.py register

from distutils.core import setup

__version__ = '1.0.0'

DESCRIPTION = \
    """A simple wrapper around inotify. No fancy bells and whistles, just a
    literal wrapper with ctypes. Only 95 lines of code!
"""

setup(name='inotify_simple',
      version=__version__,
      description=DESCRIPTION,
      author='Chris Billington',
      author_email='chrisjbillington@gmail.com',
      url='https://github.org/cbillington/inotify_simple',
      license="BSD",
      py_modules=["inotify_simple"]
      )
