import sys
import os

sys.path.insert(0, os.path.abspath('..'))

from inotify_simple import __version__

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
]

master_doc = 'index'
project = u'inotify_simple'
copyright = u'2016, Chris Billington'
version = __version__
release = '.'.join(__version__.split('.')[:-1])

autodoc_member_order = 'bysource'
autoclass_content = 'both'

on_rtd = os.environ.get('READTHEDOCS', None) == 'True'

if not on_rtd:  # only import and set the theme if we're building docs locally
    import sphinx_rtd_theme
    html_theme = 'sphinx_rtd_theme'
    html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]


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
