from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parent
BRIDGE_PATH = PLUGIN_DIR / "manual_bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bzss_bot_plugin.manual_bridge", BRIDGE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load bridge client from {BRIDGE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query current QQ-bound player info from BZSS Panel")
    parser.add_argument("--base-url", required=True, help="Example: http://BZSW-Panel.site:12864/api/astrbot")
    parser.add_argument("--token", required=True, help="AstrBot bridge token")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    parser.add_argument("--qq-number", required=True)
    parser.add_argument("--qq-name", required=True)
    return parser


def format_result(result: dict) -> str:
    body = result.get("body") if isinstance(result, dict) else {}
    data = body.get("data") if isinstance(body, dict) else {}
    player = data.get("player") if isinstance(data, dict) else {}
    detail = data.get("detail") if isinstance(data, dict) else {}

    lines = []
    lines.append(json.dumps(result, ensure_ascii=False, indent=2))
    if isinstance(player, dict):
        lines.append(
            "玩家："
            f"{player.get('gameName') or player.get('name') or '未知'} | "
            f"Steam64：{player.get('steam64') or '未知'} | "
            f"EOS ID：{player.get('eosID') or '未知'} | "
            f"游戏时长：{player.get('gameHours') if player.get('gameHours') is not None else '未知'} 小时"
        )
    else:
        lines.append("未找到绑定玩家。")

    if isinstance(detail, dict):
        summary = detail.get("summary") if isinstance(detail.get("summary"), dict) else {}
        if summary:
            lines.append(
                "摘要："
                f"gameSeconds={summary.get('gameSeconds')}, "
                f"steamGameSeconds={summary.get('steamGameSeconds')}, "
                f"serverSeconds={summary.get('serverSeconds')}"
            )
    return "\n".join(lines)


async def run_async(args: argparse.Namespace) -> int:
    bridge_module = load_bridge_module()
    client = bridge_module.ManualBridgeClient(
        base_url=args.base_url,
        api_token=args.token,
        timeout_seconds=args.timeout,
    )
    result = await client.request_json(
        "me",
        "POST",
        {
            "qqNumber": args.qq_number,
            "qqName": args.qq_name,
        },
    )
    print(format_result(result))
    return 0 if result.get("ok") else 1


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(run_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
