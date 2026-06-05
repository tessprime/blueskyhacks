import asyncio
import time

from atproto import AsyncClient
from atproto_client.client.base import InvokeType
from atproto_client.request import Response


class AsyncClientRateLimited(AsyncClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._remaining = None
        self._reset = None
        self._lock = asyncio.Lock()

    async def _invoke(self, invoke_type: InvokeType, **kwargs) -> Response:
        async with self._lock:
            if self._remaining == 0 and self._reset is not None:
                wait = max(0.0, self._reset - time.time())
                if wait:
                    await asyncio.sleep(wait + 0.5)

            response = await super()._invoke(invoke_type, **kwargs)

            if "ratelimit-remaining" in response.headers:
                server_remaining = int(response.headers["ratelimit-remaining"])
                server_reset = int(response.headers["ratelimit-reset"])

                if self._reset is None or server_reset > self._reset:
                    # New window — accept whatever the server says
                    self._remaining = server_remaining
                    self._reset = server_reset
                elif server_reset == self._reset:
                    # Same window — take the most pessimistic value
                    self._remaining = min(self._remaining, server_remaining)
            elif self._remaining is not None:
                self._remaining -= 1

            return response
