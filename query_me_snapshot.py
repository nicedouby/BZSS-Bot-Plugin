from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib import error, request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch player snapshot PNG from BZSS Panel AstrBot bridge.")
    parser.add_argument("--base-url", required=True, help="Bridge base url, for example: http://BZSW-Panel.site:12864/api/astrbot")
    parser.add_argument("--token", required=True, help="AstrBot bridge api token")
    parser.add_argument("--qq-number", required=True, help="QQ number")
    parser.add_argument("--qq-name", required=True, help="QQ display name")
    parser.add_argument("--output", default="player_snapshot.png", help="Output png path")
    parser.add_argument("--timeout", type=float, default=15.0, help="Request timeout in seconds")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    endpoint = f"{base_url}/me/snapshot"
    payload = json.dumps({
        "qqNumber": args.qq_number,
        "qqName": args.qq_name,
    }).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {args.token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with request.urlopen(req, timeout=args.timeout) as resp:
            body = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            if "image/png" not in content_type.lower():
                print(f"请求成功但不是 PNG: {content_type}")
                print(body.decode("utf-8", errors="replace"))
                return 1
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}")
        print(body)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"请求失败: {exc}")
        return 1

    output_path = Path(args.output).expanduser().resolve()
    output_path.write_bytes(body)
    print(f"已保存玩家快照: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
