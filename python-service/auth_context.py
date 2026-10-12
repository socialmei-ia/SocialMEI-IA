from contextvars import ContextVar

principal = ContextVar("socialmei_authenticated_principal", default=None)
