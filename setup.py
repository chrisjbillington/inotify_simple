#!/usr/bin/env python

# To upload a version to PyPI, run:
#    python setup.py sdist upload
# If the package is not registered with PyPI yet, do so with:
#     python setup.py register

import sys
if 'sdist' in sys.argv:
    import pypandoc
    with open('README', 'w') as f:
        f.write(pypandoc.convert('README.md', 'rst', format='markdown'))

import os
from distutils.core import setup

__version__ = '1.2.0'

DESCRIPTION = ("A simple wrapper around inotify. No fancy bells and whistles, " +
               "just a literal wrapper with ctypes. Only 127 lines of code!")

# Auto generate a __version__ package for the package to import
with open(os.path.join('inotify_simple', '__version__.py'), 'w') as f:
    f.write("__version__ = '%s'\n" % __version__)

setup(name='inotify_simple',
      version=__version__,
      description=DESCRIPTION,
      long_description=open('README').read(),
      author='Chris Billington',
      author_email='chrisjbillington@gmail.com',
      url='https://github.com/chrisjbillington/inotify_simple',
      license="BSD",
      packages=["inotify_simple"]
      )
