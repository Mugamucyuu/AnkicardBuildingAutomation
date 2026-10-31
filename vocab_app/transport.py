"""Small JSON transport. Never include request headers or response bodies in errors."""
import json
import time
from http.client import IncompleteRead
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

class ServiceError(RuntimeError):
    pass

def request_json(url, payload, *, headers=None, timeout=180, attempts=1):
    for attempt in range(attempts):
        try:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = Request(url, data=body, headers={"Content-Type": "application/json", **(headers or {})})
            with urlopen(req, timeout=timeout) as response:
                try:
                    body = response.read()
                except IncompleteRead as error:
                    # Some connections omit the final chunk marker despite delivering
                    # the full JSON. Accept only a complete, parseable document.
                    body = error.partial
                return json.loads(body)
        except HTTPError as error:
            status = error.code
            error.close()
            if status not in (429, 500, 502, 503, 504) or attempt + 1 == attempts:
                raise ServiceError("远程服务返回 HTTP " + str(status) + "；未记录响应正文。") from None
        except (URLError, TimeoutError, OSError):
            if attempt + 1 == attempts:
                raise ServiceError("远程服务连接失败或超时。") from None
        except (ValueError, UnicodeError):
            raise ServiceError("远程服务返回了无效 JSON。") from None
        time.sleep(2 ** attempt)
    raise ServiceError("请求次数必须至少为 1。")
