""" Defines the HTML File Session type
"""
from __future__ import absolute_import

from os.path import abspath, normpath, split, join, relpath, splitext
import logging
from six import string_types

from ..objects import PlotContext
from .base_html_session import BaseHTMLSession

logger = logging.getLogger(__file__)

class HTMLFileSession(BaseHTMLSession):
    """ Produces a pile of static HTML, suitable for exporting a plot
    as a standalone HTML file.  This includes a template around the
    plot and includes all the associated JS and CSS for the plot.
    """

    title = "Bokeh Plot"

    # TODO: Why is this not in bokehjs_dir, but rather outside of it?
    js_files = ["js/bokeh.js"]
    css_files = ["css/bokeh.css"]

    js_files_dev = ['js/vendor/requirejs/require.js', 'js/config.js']
    css_files_dev = ['js/vendor/bootstrap/bootstrap-bokeh-2.0.4.css', 'css/continuum.css', 'css/main.css']

    # Template files used to generate the HTML
    js_template = "plots.js"
    div_template = "plots.html"     # template for just the plot <div>
    html_template = "base.html"     # template for the entire HTML file

    # Used to compute the relative paths to JS and CSS if they are not
    # inlined into the output
    rootdir = abspath(split(__file__)[0])

    def __init__(self, filename="bokehplot.html", plot=None, title=None):
        self.filename = filename
        if title is not None:
            self.title = title
        super(HTMLFileSession, self).__init__(plot=plot)
        self.plotcontext = PlotContext()
        self.add(self.plotcontext)
        self.raw_js_objs = []

    def _file_paths(self, files, minified):
        if minified:
            files = [ root + ".min" + ext for (root, ext) in map(splitext, files) ]

        return [ self.static_path(file) for file in files ]

    def static_path(self, path):
        return normpath(join(self.server_static_dir, path))

    def js_paths(self, minified=True, dev=False):
        files = self.js_files_dev if dev else self.js_files
        return self._file_paths(files, False if dev else minified)

    def css_paths(self, minified=True, dev=False):
        files = self.css_files_dev if dev else self.css_files
        return self._file_paths(files, False if dev else minified)

    def raw_js_snippets(self, obj):
        self.raw_js_objs.append(obj)

    def get_resources(self, resources, rootdir):
        if resources not in ['inline', 'relative', 'relative-dev', 'absolute', 'absolute-dev']:
            raise ValueError("wrong value for 'resources' parameter, expected 'inline', 'relative(-dev)' or 'absolute(-dev)', got %r" % resources)

        if not resources.startswith("relative") and rootdir:
            raise ValueError("setting 'rootdir' makes sense only when 'resources' is set to 'relative'")

        raw_js, js_files = [], []
        raw_css, css_files = [], []

        dev = resources.endswith('-dev')
        if dev:
            resources = resources[:-4]

        js_paths = self.js_paths(dev=dev)
        css_paths = self.css_paths(dev=dev)
        base_url = self.static_path("js")

        if resources == "inline" and not dev:
            raw_js = self._inline_files(js_paths)
            raw_css = self._inline_files(css_paths)
        elif resources == "relative":
            rootdir = rootdir or self.rootdir
            js_files = [ relpath(p, rootdir) for p in js_paths ]
            css_files = [ relpath(p, rootdir) for p in css_paths ]
            base_url = relpath(base_url, rootdir)
        elif resources == "absolute":
            js_files = list(js_paths)
            css_files = list(css_paths)

        if dev:
            require = 'require.config({ baseUrl: "%s" });' % base_url
            raw_js.append(require)

        def pad(text, n=4):
            return "\n".join([ " "*n + line for line in text.split("\n") ])

        wrapper = lambda code: '$(function() {\n%s\n});' % pad(code)

        if dev:
            js_wrapper = lambda code: 'require(["jquery", "main"], function($, Bokeh) {\n%s\n});' % pad(wrapper(code))
        else:
            js_wrapper = wrapper

        return (raw_js, js_files), (raw_css, css_files), js_wrapper

    def dumps(self, resources="inline", rootdir=None):
        """ Returns the HTML contents as a string

        **resources** can be `inline`, `relative` or `absolute`.

        If **resources** is set to `relative` then **rootdir** can be specified
        to indicate the base directory from which the path to the various static
        files should be computed.
        """
        # FIXME: Handle this more intelligently
        pc_ref = self.get_ref(self.plotcontext)
        elementid = self.make_id()

        jscode = self._load_template(self.js_template).render(
                    elementid = elementid,
                    modelid = pc_ref["id"],
                    modeltype = pc_ref["type"],
                    all_models = self.serialize_models())

        (raw_js, js_files), (raw_css, css_files), js_wrapper = self.get_resources(resources, rootdir)
        plot_div = self._load_template(self.div_template).render(elementid=elementid)

        html = self._load_template(self.html_template).render(
                    js_snippets = [js_wrapper(jscode)],
                    html_snippets = [plot_div] + [o.get_raw_js() for o in self.raw_js_objs],
                    rawjs = raw_js, rawcss = raw_css,
                    jsfiles = js_files, cssfiles = css_files,
                    title = self.title)

        return html

    def embed_js(self, plot_id, static_root_url):
        # FIXME: Handle this more intelligently
        pc_ref = self.get_ref(self.plotcontext)
        elementid = self.make_id()

        jscode = self._load_template('embed_direct.js').render(
            host = "",
            static_root_url=static_root_url,
            elementid = elementid,
            modelid = pc_ref["id"],
            modeltype = pc_ref["type"],
            plotid = plot_id,
            all_models = self.serialize_models())

        return jscode.encode("utf-8")

    def save(self, filename=None, resources="inline", rootdir=None):
        """ Saves the file contents. Uses self.filename if **filename** is not
        provided. Overwrites the contents.

        **resources** can be `inline`, `relative` or `absolute`.

        If **resources** is set to `relative` then **rootdir** can be specified
        to indicate the base directory from which the path to the various static
        files should be computed.
        """
        s = self.dumps(resources, rootdir)
        if filename is None:
            filename = self.filename
        with open(filename, "wb") as f:
            f.write(s.encode("utf-8"))
        return

    def view(self, new=False, autoraise=True):
        """ Opens a browser to view the file pointed to by this sessions.

        **new** can be None, "tab", or "window" to view the file in the
        existing page, a new tab, or a new windows.  **autoraise** causes
        the browser to be brought to the foreground; this may happen
        automatically on some platforms regardless of the setting of this
        variable.
        """
        new_map = { False: 0, "window": 1, "tab": 2 }
        file_url = "file://" + abspath(self.filename)

        try:
            import webbrowser
            webbrowser.open(file_url, new=new_map[new], autoraise=autoraise)
        except (SystemExit, KeyboardInterrupt):
            raise
        except:
            pass

    def dumpjson(self, pretty=True, file=None):
        """ Returns a JSON string representing the contents of all the models
        stored in this session, or write it to a file object or file name.

        If **pretty** is True, then return a string suitable for human reading,
        otherwise returns a compact string.

        If a file object is provided, then the output is appended to it.  If a
        file name is provided, then it opened for overwrite, and not append.

        Mostly intended to be used for debugging.
        """
        if pretty:
            indent = 4
        else:
            indent = None
        s = self.serialize_models(indent=indent)
        if file is not None:
            if isinstance(file, string_types):
                with open(file, "w") as f:
                    f.write(s)
            else:
                file.write(s)
        else:
            return s
