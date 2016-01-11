import sys
import os

sys.path.insert(0, os.path.abspath('..'))

# Pull the version string out of setup.py without importing it
with open('../setup.py') as f:
    for line in f:
        if '__version__' in line:
            __version__ = eval(line.split('=')[1])
            break

extensions = [
    'sphinx.ext.autodoc',
    'sphinxcontrib.napoleon',
]

master_doc = 'index'
project = u'inotify_simple'
copyright = u'2016, Chris Billington'
version = __version__
release = '.'.join(__version__.split('.')[:-1])

autodoc_member_order = 'bysource'
autoclass_content = 'both'

# Monkeypatch add_directive_header method of AttributeDocumenter to not show
# values of attributes, autodoc doesn't seem to be able to find them anyway
# for our enums - they all come out as None.
from sphinx.ext.autodoc import AttributeDocumenter, ClassLevelDocumenter

def add_directive_header(self, sig):
    ClassLevelDocumenter.add_directive_header(self, sig)

AttributeDocumenter.add_directive_header = add_directive_header
