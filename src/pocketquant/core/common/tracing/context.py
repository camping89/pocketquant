import contextvars

from pocketquant.core.common.uuid import generate_id_str

request_id_contextvar: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def get_correlation_id() -> str:
    correlation_id = request_id_contextvar.get()
    return correlation_id if correlation_id else generate_id_str()


def set_correlation_id(request_id: str) -> contextvars.Token:
    return request_id_contextvar.set(request_id)
