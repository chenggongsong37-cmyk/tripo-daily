"""Vercel Python function entrypoint for the Tripo daily web UI."""
from http.server import BaseHTTPRequestHandler
from tripo_daily.web import Handler as LocalHandler, PAGE

class handler(BaseHTTPRequestHandler):
    """Adapt the local HTTP handler to Vercel's Python runtime."""
    def log_message(self, *_):
        return

    def _dispatch(self, method):
        # The report UI and API use only request path and write to the response.
        # Reuse the tested local handler methods, while Vercel supplies the socket.
        if method == "GET":
            return LocalHandler.do_GET(self)
        return LocalHandler.do_POST(self)

    def do_GET(self):
        return self._dispatch("GET")

    def do_POST(self):
        return self._dispatch("POST")
