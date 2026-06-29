from __future__ import annotations

import argparse
from pathlib import Path
from urllib import error, request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch server info snapshot PNG from BZSS Panel AstrBot bridge.")
    parser.add_argument("--base-url", required=True, help="Bridge base url, for example: http://BZSW-Panel.site:12864/api/astrbot")
    parser.add_argument("--token", required=True, help="AstrBot bridge api token")
    parser.add_argument("--output", default="server_info_snapshot.png", help="Output png path")
    parser.add_argument("--timeout", type=float, default=60.0, help="Request timeout in seconds")
    return parser.parse_args()


def _download(endpoint: str, token: str, timeout: float) -> bytes | None:
    req = request.Request(
        endpoint,
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            if "image/png" not in content_type.lower():
                print(f"请求成功但不是 PNG: {content_type}")
                print(body.decode("utf-8", errors="replace"))
                return None
            return body
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code} @ {endpoint}")
        print(body)
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"请求失败 @ {endpoint}: {exc}")
        return None


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    endpoints = [
        f"{base_url}/server-info/snapshot",
        f"{base_url}/server-info/snapshot/latest",
    ]

    output_path = Path(args.output).expanduser().resolve()
    for endpoint in endpoints:
        body = _download(endpoint, args.token, args.timeout)
        if body is None:
            continue
        output_path.write_bytes(body)
        print(f"已保存服务器信息快照: {output_path}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
