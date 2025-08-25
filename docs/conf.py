import sys
import os

sys.path.insert(0, os.path.abspath('..'))

from inotify_simple import __version__

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
    'sphinx_rtd_theme',
]

root_doc = 'index'
project = 'inotify-simple'
copyright = '2016, Chris Billington'
version = __version__
release = '.'.join(__version__.split('.')[:2])

autodoc_member_order = 'bysource'
autoclass_content = 'both'

intersphinx_mapping = {'python': ('https://docs.python.org/3/', None)}
html_theme = 'sphinx_rtd_theme'


# Make full source as a separate file:
with open('../inotify_simple.py') as f:
    with open('fullsource.py', 'w') as g:
        docstring = False
        prev_line_blank = False
        for line in f:
            blank = not line.strip()
            if line.strip().startswith('"""'):
                docstring = True
            comment = line.strip().startswith('#')
            all_ = '__all__' in line
            version_ = '__version__' in line
            if not (docstring or comment or (blank and prev_line_blank)):
                g.write(line.split('#')[0].rstrip() + '\n')
            if line.strip().endswith('"""'):
                docstring = False
            prev_line_blank = blank
