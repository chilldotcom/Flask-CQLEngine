from cqlengine.connection import setup
from cqlengine_session import clear, save, SessionManager, set_session_manager
from flask import _request_ctx_stack

try:
    from flask import _app_ctx_stack
except ImportError:
    _app_ctx_stack = None


__all__ = ('CQLEngine', )


__version__ = '0.1'


# Which stack should we use?  _app_ctx_stack is new in 0.9
context_stack = _app_ctx_stack or _request_ctx_stack
# We use appcontext because one might want to access the CQLEngine objects
# from a shell for example.


class CQLEngine(object):
    """CQLEngine database support for Flask."""
    def __init__(self, app=None):
        """
        If app argument provided then initialize cqlengine connection using
        application config values.

        If no app argument provided you should do initialization later with
        :meth:`init_app` method.

        :param app: Flask application instance.

        """
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """
        Read cqlengine settings from app configuration,
        initialize cqlengine connection and copy all public connection
        methods to current instance.

        :param app: Flask application instance.

        """
        # Put cqlengine to application extensions
        if not 'cqlengine' in app.extensions:
            app.extensions['cqlengine'] = {}

        # Initialize connection and store it to extensions
        hosts = app.config['CQLENGINE_HOSTS']
        port = int(app.config['CQLENGINE_PORT'])
        default_keyspace = app.config['CQLENGINE_DEFAULT_KEYSPACE']
        lazy_connect = app.config.get('CQLENGINE_LAZY_CONNECT', False)
        retry_connect = app.config.get('CQLENGINE_RETRY_CONNECT', False)
        setup_kwargs = app.config.get('CQLENGINE_SETUP_KWARGS', {})

        #hosts needs to be a list when passed to CQLEngine
        # but we want to support a comma separated string
        if isinstance(hosts, basestring):
            hosts = hosts.split(',')

        # additionally, CQLEngine wants bytes, not unicode
        hosts = map(bytes, hosts)

        # Configure cqlengine's global connection pool.
        setup(hosts,
              default_keyspace=default_keyspace,
              port=port,
              lazy_connect=lazy_connect,
              retry_connect=retry_connect,
              **setup_kwargs)
        set_session_manager(AppContextSessionManager())

        self.wrap_full_dispatch_request(app)

        @app.teardown_appcontext
        def clear_session(response_or_exc):
            """always clear when request is done"""
            clear()
            return response_or_exc

    def wrap_full_dispatch_request(self, app):
        """
        Wrap full_dispatch_request so that saves can be triggered
        after the response has been fully processed.

        wrapping full_dispatch_request allows exceptions generated during
        save to be handled by the normal exception handling in Flask.
        """
        old_full_dispatch_request = app.full_dispatch_request

        def new_full_dispatch_request():
            #if dispatch raises an exception, save will get skipped.
            #if the exception is handled, it's up to the handler to deal with save/clear
            response = old_full_dispatch_request()
            save()
            return response

        app.full_dispatch_request = new_full_dispatch_request


class AppContextSessionManager(SessionManager):
    def get_session(self):
        """Return current session for this context."""
        return getattr(context_stack.top, 'cqlengine_session', None)

    def set_session(self, session):
        """Make the given session the current session for this context."""
        context_stack.top.cqlengine_session = session
