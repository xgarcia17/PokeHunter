from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

try:
    import requests as _requests
except ImportError:  # pragma: no cover - only used when requests is absent
    _requests = None


if _requests is not None:
    RequestException = _requests.RequestException
    get = _requests.get
    post = _requests.post
else:
    class RequestException(Exception):
        pass

    @dataclass
    class _CompatResponse:
        status_code: int
        text: str

        def raise_for_status(self) -> None:
            if 400 <= self.status_code:
                raise RequestException(f"HTTP {self.status_code}: {self.text[:200]}")

        def json(self):
            return json.loads(self.text) if self.text else None

    def _with_params(url: str, params: dict[str, str] | None) -> str:
        if not params:
            return url
        parts = list(urlsplit(url))
        query = urlencode(params, doseq=True, safe="(),*:")
        parts[3] = query if not parts[3] else f"{parts[3]}&{query}"
        return urlunsplit(parts)

    def _request(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json_body=None,
        data=None,
        timeout: float | int = 30,
    ) -> _CompatResponse:
        body = data
        request_headers = dict(headers or {})
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        if isinstance(body, str):
            body = body.encode("utf-8")

        request = Request(
            _with_params(url, params),
            data=body,
            headers=request_headers,
            method=method.upper(),
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return _CompatResponse(response.status, response.read().decode("utf-8"))
        except HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
            return _CompatResponse(exc.code, payload)
        except URLError as exc:  # pragma: no cover - network dependent
            raise RequestException(str(exc)) from exc

    def get(url: str, *, headers=None, params=None, timeout=30):
        return _request("GET", url, headers=headers, params=params, timeout=timeout)

    def post(url: str, *, headers=None, json=None, data=None, timeout=30):
        return _request(
            "POST",
            url,
            headers=headers,
            json_body=json,
            data=data,
            timeout=timeout,
        )
