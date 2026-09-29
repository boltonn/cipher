"""Accept camelCase or snake_case query parameters interchangeably.

Every query key is mirrored in the other case before routing, so a param
declared as `dataset_id` (plain `Query`) and a camelCase-aliased pydantic query
model field both resolve whichever spelling the client sent. Without this,
FastAPI fills a query model's camelCase alias with its default and that default
wins over an explicit snake_case value.
"""

from urllib.parse import parse_qsl, urlencode

from pydantic.alias_generators import to_camel, to_snake
from starlette.types import ASGIApp, Receive, Scope, Send


def mirror_query_case(query_string: bytes) -> bytes:
    """Return ``query_string`` with each key also present in its other case (camel <-> snake)."""
    pairs = parse_qsl(query_string.decode("latin-1"), keep_blank_values=True)
    keys = {k for k, _ in pairs}
    mirrored = []
    for key, value in pairs:
        twin = to_snake(key) if key != to_snake(key) else to_camel(key)
        if twin != key and twin not in keys:
            mirrored.append((twin, value))
    if not mirrored:
        return query_string
    return urlencode([*pairs, *mirrored]).encode("latin-1")


class QueryCaseMiddleware:
    """Pure-ASGI middleware applying `mirror_query_case` to every HTTP request."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Mirror the query string's keys, then hand off to the wrapped app."""
        if scope["type"] == "http" and scope.get("query_string"):
            scope = {**scope, "query_string": mirror_query_case(scope["query_string"])}
        await self.app(scope, receive, send)
