from __future__ import absolute_import
from .inotify_simple import  *
try:
    from .__version__ import __version__
except ImportError:
    __version__ = None
