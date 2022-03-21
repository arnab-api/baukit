# show.py
#
# An abbreviated way to output simple HTML layout of text and images
# into a python notebook.
#
# - show a PIL image to show an inline HTML <img>.
# - show an array of items to vertically stack them, centered in a block.
# - show an array of arrays to horizontally lay them out as inline blocks.
# - show an array of tuples to create a table.

import PIL.Image
import base64
import collections
from contextlib import contextmanager
import io
import IPython
import types
import re
import sys
import inspect
from html import escape

def show(*args):
    '''
    The main function.  Calls the IPython display function to show the
    HTML-rendered arguments.
    '''
    display(html(*args))

def html(*args):
    '''
    Renders the arguments into an HtmlString without displaying directly.
    '''
    out = []
    with enter_tag(out=out):
        for x in args:
            render(x, out)
    return HtmlString(''.join(out))

def bare_html(*args):
    '''
    Without an outermost element, renders the arguments as an HtmlString.
    '''
    out = []
    for x in args:
        render(x, out)
    return HtmlString(''.join(out))

def raw_html(*args):
    '''
    Produces an HtmlString from strings, without escaping or any fanciness.
    '''
    out = []
    return HtmlString(''.join(str(x) for x in args))

@contextmanager
def enter_tag(*args, out=None, **kwargs):
    '''
    Context manager for creating and emitting a tag and its matching
    end-tag.  When the tag is created, any current defaults and options
    to the styles and attributes are merged if present.

    For example:

    ```
    out = []
    with show.enter_tag('div', id='d38', style(topMargin='8px'), out=out):
        out.append('inside the div')
    ```

    The tags are merged with options, merged with the following precedence:
        (1) Explicit tag, attr, or style options rentered before entering.
        (2) Any tag, attr, and style specified on the `with` line.
        (3) Child options specified by a parent.

    Parent options are overwritten by `with` options, which can be
    overwritten by a user who specifies explicit tag options when
    rendering.
    '''
    global tag_stack
    if len(tag_stack) and tag_stack[-1] is not None:
        default_tag = tag_stack[-1]
    else:
        default_tag = HORIZONTAL
    current_tag = default_tag(*args, **kwargs)
    current_tag.update(*tag_modifications)
    tag_modifications.clear()
    tag_stack.append(current_tag.child)
    try:
        if out is not None:
            out.append(current_tag.begin())
        yield current_tag
        if out is not None:
            out.append(current_tag.end())
    finally:
        tag_modifications.clear()
        tag_stack.pop()

def emit_tag(*args, out=None, **kwargs):
    '''
    Emits the specified tag, applying any current defaults and options
    to the styles and attributes.  Options are handled as with enter_tag.

    If no `out` array is provided, returns the tag as a string.
    '''
    emit_out = [] if out is None else out
    with enter_tag(*args, out=emit_out, **kwargs):
        if out is None:
            return ''.join(emit_out)

HTML_EMPTY = set(('area base br col embed hr img input keygen '
                  'link meta param source track wbr').split(' '))

CSS_UNITS = dict([(k, unit) for keys, unit in [
  ('width height min-width max-width min-height max-height', 'px'),
  ('left right top bottom', 'px'),
  ('font-size', 'px'),
  ('border border-left border-right border-top border-bottom '
    'border-width border-left-width border-right-width '
    'border-top-width border-bottom-width', 'px'),
  ('margin margin-left margin-right margin-top margin-bottom', 'px'),
  ('padding padding-left padding-right padding-top padding-bottom', 'px'),
] for k in keys.split(' ')])

def hyphenateCamelKeys(d):
    return {re.sub('([A-Z]+)', r'-\1', k).lower() : v for k, v in d.items()}

def styleValue(v, k):
    if isinstance(v, (int, float)) and k in CSS_UNITS:
        return f'{v}{CSS_UNITS[k]}'
    return str(v)

class Style(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **hyphenateCamelKeys(kwargs))
    def update(self, *args, **kwargs):
        super().update(*args, **hyphenateCamelKeys(kwargs))
    def __call__(self, **kwargs):
        result = Style(**self, **hyphenateCamelKeys(kwargs))
        return result
    def __str__(self):
        return ';'.join(f'{k}:{styleValue(v, k)}'
                for k, v in self.items() if v is not None)

def style(*args, **kwargs):
    return Style(*args, **kwargs)

class Attr(dict):
    def __call__(self, **kwargs):
        result = Attr(**self, **kwargs)
        if 'style' in result and not result['style']:
            del result['style']
        return result
    def __str__(self):
        return ''.join(f' {k}' if v is None else f' {k}="{escape(str(v))}"'
                for k, v in self.items())

def attr(*args, **kwargs):
    return Attr(*args, **kwargs)

class ChildTag:
    def __init__(self, child):
        assert child is None or isinstance(child, Tag)
        self.child = child

class Tag:
    def __init__(self, *args, **kwargs):
        self.tag = 'div'
        self.attrs = Attr()
        self.style = Style()
        self.child = None
        self.update(*args, **kwargs)
    def update(self, *args, **kwargs):
        if len(args) > 0 and isinstance(args[0], str):
            self.tag = args[0].lower()
            args = args[1:]
        for arg in args:
            if isinstance(arg, Tag):
                self.tag = arg.tag
                self.attrs.update(arg.attrs)
                self.style.update(arg.style)
                self.child = arg.child
            elif isinstance(arg, Attr):
                self.attrs.update(arg)
            elif isinstance(arg, Style):
                self.style.update(arg)
            elif isinstance(arg, ChildTag):
                self.child = arg.child
            elif arg is None:
                continue
            else:
                assert False, f'arg {arg} is not Tag or Attr or Style'
        self.attrs.update(**kwargs)
    def begin(self):
        return f'<{self.tag}{self.attrs(style=str(self.style))}>'
    def end(self):
        return '' if self.tag in HTML_EMPTY else f'</{self.tag}>'
    def __call__(self, *args, **kwargs):
        result = Tag(self)
        result.update(*args, **kwargs)
        return result
    def __str__(self):
        return self.begin()
    def __repr__(self):
        return str(self)


# This is the default loop for nesting children: horizontal layout by default,
# and then vertical layout for nested arrays; then horizontal within those, etc.
HORIZONTAL = Tag(
        style(display='flex', flex='1', flexFlow='row wrap', gap='3px',
            alignItems='center'))
VERTICAL = Tag(
        style(display='flex', flex='1', flexFlow='column', gap='3px'),
        ChildTag(HORIZONTAL))
HORIZONTAL.update(ChildTag(VERTICAL))
INLINE = Tag(
        style(display='inline-flex', flexFlow='row wrap', gap='3px',
            alignItems='center'),
        ChildTag(VERTICAL))

tag_stack = [INLINE]
tag_modifications = []

def modify_tag(*args):
    tag_modifications.extend(args)

def render(obj, out):
    for detector, renderer in RENDERING_RULES:
        if (isinstance(obj, detector) if isinstance(detector, (type, tuple)) else detector(obj)):
            if renderer(obj, out) is not False:
                return
    # Fallback: convert object to string and then apply HTML escaping.
    render_str(obj, out)

def render_str(obj, out):
    '''
    Strings must be escaped.
    '''
    s = str(obj)
    if '\n' in s:
        render_pre(s, out)
        return
    with enter_tag(out=out):
        out.append(escape(s))

def render_html(obj, out):
    '''
    Use _repr_html_() when available and non-None.
    '''
    h = obj._repr_html_()
    if h is None:
        return False
    out.append(h)

def render_list(obj, out):
    '''
    Lists are divs containin divs, alternating row-inline and column flex layout.
    '''
    with enter_tag(out=out):
        for v in obj:
            render(v, out)

def render_dict(obj, out):
    '''
    Dicts become tables.
    '''
    with enter_tag('table', style(display=None, width='100%'), ChildTag(None), out=out):
        for k, v in obj.items():
            with enter_tag('tr', out=out):
                out.append(row.begin())
                with enter_tag('td', ChildTag(HORIZONTAL), out=out):
                    out.append(escape(str(k)))
                with enter_tag('td', ChildTag(HORIZONTAL), out=out):
                    render(v, out)

def render_image(obj, out):
    '''
    Images and figures become <img> tags.
    '''
    try:
        buf = io.BytesIO()
        if hasattr(obj, 'save'): # Like a PIL.Image.Image
            obj.save(buf, format='png')
        elif hasattr(obj, 'savefig'): # Like a matplotlib.figure.Figure
            obj.savefig(buf, format='png', bbox_inches='tight')
        else:
            assert False
        src = 'data:image/png;base64,' + (
                base64.b64encode(buf.getvalue()).decode('utf-8'))
        buf.close()
    except:
        return False
    emit_tag('img', attr(src=src), style(flex='0'), out=out)

def render_pre(obj, out):
    '''
    Long multiline text data types are rendered in <pre> tags.
    '''
    s = str(obj)
    with enter_tag('pre', out=out):
        out.append(escape(s))

def render_modifications(obj, out):
    '''
    Allows Tag, Attr, Style, ChildTag objects to modify the next tag to output.
    '''
    assert isinstance(obj, (Tag, Attr, Style, ChildTag))
    modify_tag(obj)

def subclass_of(clsname):
    '''
    Detects if obj is a subclass of a class named clsname, without requiring import
    of the class.
    '''
    def test(obj):
        for x in inspect.getmro(type(obj)):
            if clsname == x.__module__ + '.' + x.__name__:
                return True
        return False
    return test

RENDERING_RULES = [
        # Special tag modifications
        ((Style, Attr, Tag, ChildTag), render_modifications),
        # Objects with an html repr
        ((lambda x: hasattr(x, '_repr_html_')), render_html),
        # Strings should not be treated as lists
        (str, render_str),
        # Dictionaries: render as table
        (collections.abc.Mapping, render_dict),
        # PIL images
        (subclass_of('PIL.Image.Image'), render_image),
        # Matplotlib figures
        (subclass_of('matplotlib.figure.Figure'), render_image),
        # Numpy, pytorch arrays
        (lambda x: hasattr(x, 'shape') and hasattr(x, 'dtype'), render_pre),
        # Generators and lists: recurse
        ((lambda x: hasattr(x, '__iter__')), render_list),
]


class HtmlString(str):
    '''
    A string that contains HTML, and that returns itself as _repr_html_.
    It does no escaping, and just interprets strings as markup.
    '''
    def __new__(cls, s):
        return super().__new__(cls, s)
    def _repr_html_(self):
        return self
    def __add__(self, other):
        return HtmlString(super().__add__(other))
    def __mul__(self, other):
        return HtmlString(super().__mul__(other))
    def __rmul__(self, other):
        return HtmlString(super().__rmul__(other))
    def __mod__(self, other):
        return HtmlString(super().__mod__(other))
    def format(self, *args, **kwargs):
        return HtmlString(super().format(*args, **kwargs))
    def format_map(self, mapping):
        return HtmlString(super().format_map(mapping))
    def expandtabs(self, tabsize=8):
        return HtmlString(super().expandtabs(tabsize=tabsize))
    def join(self, iterable):
        return HtmlString(super().join(iterable))
    def ljust(self, width, fillchar=' '):
        return HtmlString(super().ljust(width, fillchar=fillchar))
    def lstrip(self, chars=None):
        return HtmlString(super().lstrip(chars))
    def removeprefix(self, prefix):
        return HtmlString(super().removeprefix(prefix))
    def removesuffix(self, suffix):
        return HtmlString(super().removesuffix(suffix))
    def replace(self, old, new, count=-1):
        return HtmlString(super().replace(old, new, count=count))
    def rjust(self, width, fillchar=' '):
        return HtmlString(super().rjust(width, fillchar=fillchar))
    def rstrip(self, chars=None):
        return HtmlString(super().rstrip(chars))
    def strip(self, chars=None):
        return HtmlString(super().strip(chars))
    def translate(self, table):
        return HtmlString(super().translate(table))
    def capitalize(self):
        return HtmlString(super().capitalize())
    def casefold(self):
        return HtmlString(super().casefold())
    def swapcase(self):
        return HtmlString(super().swapcase())
    def lower(self):
        return HtmlString(super().lower())
    def title(self):
        return HtmlString(super().title())
    def upper(self):
        return HtmlString(super().upper())
    def zfill(self, width):
        return HtmlString(super().zfill(width))

class CallableModule(types.ModuleType):
    def __init__(self):
        # or super().__init__(__name__) for Python 3
        types.ModuleType.__init__(self, __name__)
        self.__dict__.update(sys.modules[__name__].__dict__)

    def __call__(self, x=None, *args, **kwargs):
        show(x, *args, **kwargs)


sys.modules[__name__] = CallableModule()
