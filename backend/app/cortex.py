"""Snowflake Cortex chat completions over the REST API.

POST https://<account>.snowflakecomputing.com/api/v2/cortex/v1/chat/completions
with a programmatic access token (PAT). The body and the streamed chunks follow
the OpenAI chat completions shape. See docs/snowflake-cortex.md for the
Snowflake-side setup (PAT, CORTEX_USER role, network policy, cross-region).
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.config import settings

PATH = "/api/v2/cortex/v1/chat/completions"
EM_DASH, EN_DASH = chr(0x2014), chr(0x2013)


class CortexError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def clean(text: str) -> str:
    """House style: plain hyphens, never em dashes."""
    return text.replace(EM_DASH, " - ").replace(EN_DASH, "-")


def _explain(status: int, body: str) -> str:
    if status == 401:
        return (
            "Snowflake rejected the access token. Check SNOWFLAKE_PAT, that it has not expired, "
            "and that a network policy allows this server's IP."
        )
    if status == 403:
        return "The Snowflake user's default role cannot use Cortex. Grant it SNOWFLAKE.CORTEX_USER."
    if status == 400 and "model" in body.lower():
        return (
            f"Cortex refused the model {settings.cortex_model!r}. It may not be available in this region: "
            "ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION', or set CORTEX_MODEL to another model."
        )
    if status == 429:
        return "Snowflake Cortex is rate limiting this account. Try again in a moment."
    return f"Snowflake Cortex returned HTTP {status}: {body[:300]}"


class CortexClient:
    def __init__(
        self,
        account: str | None = None,
        token: str | None = None,
        model: str | None = None,
        timeout_s: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        # None means "use the settings"; an explicit value (even empty) wins.
        account = settings.snowflake_account if account is None else account
        account = (account or "").strip().lower().replace("_", "-")
        self.token = settings.snowflake_pat if token is None else token
        self.model = model or settings.cortex_model
        self.url = f"https://{account}.snowflakecomputing.com{PATH}"
        self.timeout = httpx.Timeout(timeout_s or settings.cortex_timeout_s, connect=10.0)
        self.transport = transport
        self.configured = bool(account and self.token)

    def _headers(self, stream: bool) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Snowflake-Authorization-Token-Type": "PROGRAMMATIC_ACCESS_TOKEN",
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
        }

    def _body(self, messages: list[dict], stream: bool, max_tokens: int, temperature: float) -> dict:
        return {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, transport=self.transport)

    async def complete(self, messages: list[dict], max_tokens: int = 600, temperature: float = 0.2) -> str:
        async with self._client() as client:
            try:
                response = await client.post(
                    self.url, headers=self._headers(False), json=self._body(messages, False, max_tokens, temperature)
                )
            except httpx.HTTPError as err:
                raise CortexError(502, f"Could not reach Snowflake Cortex: {err}") from err
        if response.status_code != 200:
            raise CortexError(response.status_code, _explain(response.status_code, response.text))
        data = response.json()
        return clean(data["choices"][0]["message"]["content"] or "")

    async def open_stream(
        self, messages: list[dict], max_tokens: int = 800, temperature: float = 0.3
    ) -> AsyncIterator[str]:
        """Starts the request and raises CortexError before any text is yielded.

        Returns an async iterator of text deltas that closes the connection when done.
        """
        client = self._client()
        request = client.build_request(
            "POST", self.url, headers=self._headers(True), json=self._body(messages, True, max_tokens, temperature)
        )
        try:
            response = await client.send(request, stream=True)
        except httpx.HTTPError as err:
            await client.aclose()
            raise CortexError(502, f"Could not reach Snowflake Cortex: {err}") from err
        if response.status_code != 200:
            body = (await response.aread()).decode("utf-8", "replace")
            await response.aclose()
            await client.aclose()
            raise CortexError(response.status_code, _explain(response.status_code, body))

        async def deltas() -> AsyncIterator[str]:
            try:
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[len("data:"):].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    for choice in chunk.get("choices") or []:
                        text = (choice.get("delta") or {}).get("content")
                        if text:
                            yield clean(text)
            finally:
                await response.aclose()
                await client.aclose()

        return deltas()
