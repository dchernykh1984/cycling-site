import threading

_thread_locals = threading.local()


def get_current_user():
    """Return the user stored for the current thread, or None."""
    return getattr(_thread_locals, "user", None)


class CurrentUserMiddleware:
    """Store request.user in a thread-local so signals can access it."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.user = getattr(request, "user", None)
        try:
            response = self.get_response(request)
        finally:
            _thread_locals.user = None
        return response
