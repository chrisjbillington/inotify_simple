from setuptools import setup

from inotify_simple import __version__

DESCRIPTION = ("A simple wrapper around inotify. No fancy bells and whistles, " +
               "just a literal wrapper with ctypes. Under 100 lines of code!")

setup(name='inotify_simple',
      version=__version__,
      description=DESCRIPTION,
      long_description=open('README.md').read(),
      long_description_content_type='text/markdown',
      author='Chris Billington',
      author_email='chrisjbillington@gmail.com',
      url='https://github.com/chrisjbillington/inotify_simple',
      license="BSD",
      py_modules=["inotify_simple"],
      python_requires=">=2.7, !=3.0.*, !=3.1.*"
      )
