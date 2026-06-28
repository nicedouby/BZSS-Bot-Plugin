from __future__ import annotations

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


def usage() -> str:
    return (
        "Usage:\n"
        "  call_bridge.py --base-url <url> --token <token> bind --qq-number <qq> --qq-name <name> --steam64 <steam64>\n"
        "  call_bridge.py --base-url <url> --token <token> query --qq-number <qq> --qq-name <name> [--kind snapshot|warmup|modules|health]\n"
    )


def parse_args(argv: list[str]) -> dict[str, str]:
    args: dict[str, str] = {}
    command = ""
    i = 0
    while i < len(argv):
        item = argv[i]
        if item in {"bind", "query"}:
            command = item
            i += 1
            continue
        if item in {"--base-url", "--token", "--qq-number", "--qq-name", "--steam64", "--kind", "--timeout"}:
            if i + 1 >= len(argv):
                raise ValueError(f"Missing value for {item}")
            args[item] = argv[i + 1]
            i += 2
            continue
        if item in {"-h", "--help"}:
            args["--help"] = "1"
            i += 1
            continue
        raise ValueError(f"Unknown argument: {item}")

    if command:
        args["command"] = command
    return args


async def run_async(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
    except ValueError as error:
        print(str(error))
        print(usage())
        return 2

    if args.get("--help") == "1" or "command" not in args:
        print(usage())
        return 0

    base_url = args.get("--base-url", "")
    token = args.get("--token", "")
    timeout = args.get("--timeout", "10.0")

    bridge_module = load_bridge_module()
    client = bridge_module.ManualBridgeClient(
        base_url=base_url,
        api_token=token,
        timeout_seconds=timeout,
    )

    command = args["command"]
    if command == "bind":
        result = await client.bind_steam(
            args.get("--qq-number", ""),
            args.get("--qq-name", ""),
            args.get("--steam64", ""),
        )
    else:
        result = await client.query_status(
            args.get("--qq-number", ""),
            args.get("--qq-name", ""),
            args.get("--kind", "snapshot"),
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("ok"):
        if command == "bind":
            print(client.format_bind_result(args.get("--qq-number", ""), args.get("--qq-name", ""), result))
        return 0

    print(client.format_error(command, result))
    return 1


def main() -> int:
    return asyncio.run(run_async(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
