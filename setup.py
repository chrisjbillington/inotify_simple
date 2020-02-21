from setuptools import setup


DESCRIPTION = ("A simple wrapper around inotify. No fancy bells and whistles, " +
               "just a literal wrapper with ctypes. Under 100 lines of code!")

# Extract the version from the module without importinng it:
for line in open('inotify_simple.py'):
      if line.startswith('__version__'):
            __version__ = eval(line.split('=')[1])

setup(
    name='inotify_simple',
    version=__version__,
    description=DESCRIPTION,
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='Chris Billington',
    author_email='chrisjbillington@gmail.com',
    url='https://github.com/chrisjbillington/inotify_simple',
    license="BSD",
    py_modules=["inotify_simple"],
    install_requires=["enum34; python_version < '3.4'"],
    python_requires=">=2.7, !=3.0.*, !=3.1.*",
)
