import ssl
import httpx
from pathlib import Path
from typing import Any

from agent.terminology.models import ExpandResult, LookupResult, SubsumesResult, Candidate


class TerminologyClient:
    def __init__(self, config: dict[str, Any]):
        self.base_url = config["base_url"]
        self.timeout = config.get("timeout_seconds", 30)
        self.max_retries = config.get("max_retries", 3)
        self.backoff = config.get("backoff_seconds", 2)

        self.cert_path = config.get("client_cert_path")
        self.key_path = config.get("client_key_path")
        self.ca_bundle_path = config.get("ca_bundle_path")

        self._client: httpx.Client | None = None
        self._code_cache: dict[str, dict[str, Any]] = {}

    def _get_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client

        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

        if self.ca_bundle_path and Path(self.ca_bundle_path).exists():
            ssl_context.load_verify_locations(self.ca_bundle_path)

        if self.cert_path and self.key_path:
            if Path(self.cert_path).exists() and Path(self.key_path).exists():
                ssl_context.load_cert_chain(self.cert_path, self.key_path)

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            verify=ssl_context
        )
        return self._client

    def expand(
        self,
        vs_url: str,
        filter_text: str,
        count: int = 10
    ) -> ExpandResult:
        client = self._get_client()
        url = f"/ValueSet/$expand?url={vs_url}&filter={filter_text}&count={count}"

        for attempt in range(self.max_retries):
            try:
                response = client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    contains = data.get("expansion", {}).get("contains", [])
                    return ExpandResult(
                        candidates=[
                            Candidate(
                                code=item.get("code", ""),
                                display=item.get("display", ""),
                                system=item.get("system", vs_url)
                            )
                            for item in contains
                        ],
                        total=data.get("expansion", {}).get("total", len(contains)),
                        query=filter_text,
                        vs_url=vs_url
                    )
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
        return ExpandResult(candidates=[], total=0, query=filter_text, vs_url=vs_url)

    def lookup(
        self,
        system: str,
        code: str
    ) -> LookupResult | None:
        cache_key = f"{system}:{code}"
        if cache_key in self._code_cache:
            return LookupResult(**self._code_cache[cache_key])

        client = self._get_client()
        url = f"/CodeSystem/$lookup?system={system}&code={code}"

        for attempt in range(self.max_retries):
            try:
                response = client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    params = data.get("parameter", [])

                    display = code
                    properties = {}

                    for param in params:
                        name = param.get("name")
                        if name == "display":
                            display = param.get("valueString", code)
                        elif name == "property":
                            prop_name = None
                            prop_value = None
                            for part in param.get("part", []):
                                if part.get("name") == "code":
                                    prop_name = part.get("valueCode")
                                elif part.get("name") == "value":
                                    prop_value = (
                                        part.get("valueString")
                                        or part.get("valueCode")
                                        or part.get("valueBoolean")
                                    )
                            if prop_name and prop_value is not None:
                                properties[prop_name] = str(prop_value)

                    result = LookupResult(
                        code=code,
                        display=display,
                        system=system,
                        properties=properties
                    )
                    self._code_cache[cache_key] = result.model_dump()
                    return result
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
        return None

    def subsumes(
        self,
        system: str,
        code: str,
        ancestor: str
    ) -> SubsumesResult:
        client = self._get_client()
        url = f"/CodeSystem/$subsumes?system={system}&code={code}&ancestor={ancestor}"

        for attempt in range(self.max_retries):
            try:
                response = client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    params = data.get("parameter", [])
                    outcome = next(
                        (p.get("valueCode") for p in params if p.get("name") == "outcome"),
                        None
                    )
                    return SubsumesResult(
                        code=code,
                        ancestor=ancestor,
                        is_subsumed=(outcome == "subsumed")
                    )
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
        return SubsumesResult(code=code, ancestor=ancestor, is_subsumed=False)

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
