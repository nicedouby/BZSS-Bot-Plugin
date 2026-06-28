from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request


DEFAULT_BASE_URL = "http://127.0.0.1:12864/api/astrbot"
DEFAULT_TIMEOUT_SECONDS = 10.0
PLUGIN_DIR = Path(__file__).resolve().parent
LOG_DIR = PLUGIN_DIR / "logs"
LOG_FILE = LOG_DIR / "manual_bridge.log"


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def clean_text(value: object) -> str:
    return str(value or "").strip()


def normalize_steam64(value: object) -> str:
    text = clean_text(value)
    return text if re.fullmatch(r"\d{17}", text) else ""


def normalize_base_url(value: object) -> str:
    base_url = clean_text(value) or DEFAULT_BASE_URL
    base_url = base_url.rstrip("/")
    if base_url.endswith("/api/astrbot"):
        return base_url
    return f"{base_url}/api/astrbot"


def parse_timeout(value: object, default: float = DEFAULT_TIMEOUT_SECONDS) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


class ManualBridgeClient:
    def __init__(self, base_url: str, api_token: str, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.base_url = normalize_base_url(base_url)
        self.api_token = clean_text(api_token)
        self.timeout_seconds = parse_timeout(timeout_seconds)
        _ensure_log_dir()
        self.log("INFO", f"client initialized base_url={self.base_url}")

    def log(self, level: str, message: str) -> None:
        try:
            timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
            with LOG_FILE.open("a", encoding="utf-8") as handle:
                handle.write(f"[{timestamp}] [{level}] {message}\n")
        except Exception:
            pass

    def _loads(self, raw: str) -> dict[str, Any]:
        text = clean_text(raw)
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {"data": parsed}
        except json.JSONDecodeError:
            return {"raw": text}

    def _response(self, ok: bool, **payload: Any) -> dict[str, Any]:
        return {"ok": ok, **payload}

    async def request_json(self, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.api_token:
            self.log("WARN", "api_token missing")
            return self._response(False, message="未配置 api_token。")

        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_token}",
        }
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")

        def do_request() -> dict[str, Any]:
            request = urllib.request.Request(url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return self._response(True, status=response.status, body=self._loads(raw))

        self.log("INFO", f"request {method} {url} payload={json.dumps(payload, ensure_ascii=False) if payload else '{}'}")
        try:
            result = await asyncio.to_thread(do_request)
            self.log("INFO", f"response {method} {url} status={result.get('status')}")
            return result
        except urllib.error.HTTPError as error:
            try:
                raw = error.read().decode("utf-8", errors="replace")
            except Exception:
                raw = ""
            self.log("ERROR", f"http_error {method} {url} status={error.code} body={raw}")
            return self._response(False, status=error.code, body=self._loads(raw), error="HTTPError", message=raw or str(error))
        except urllib.error.URLError as error:
            self.log("ERROR", f"url_error {method} {url} message={error.reason or error}")
            return self._response(False, status=0, body={}, error="URLError", message=str(error.reason or error))
        except Exception as error:
            self.log("ERROR", f"exception {method} {url} message={error}")
            return self._response(False, status=0, body={}, error=error.__class__.__name__, message=str(error))

    async def bind_steam(self, qq_number: str, qq_name: str, steam64: str) -> dict[str, Any]:
        normalized = normalize_steam64(steam64)
        if not normalized:
            return self._response(False, message="Steam64 必须是 17 位数字。")
        return await self.request_json(
            "bind",
            "POST",
            {
                "qqNumber": clean_text(qq_number),
                "qqName": clean_text(qq_name),
                "steam64": normalized,
            },
        )

    async def query_status(self, qq_number: str, qq_name: str, kind: str = "snapshot") -> dict[str, Any]:
        payload: dict[str, Any] = {
            "qqNumber": clean_text(qq_number),
            "qqName": clean_text(qq_name),
        }
        normalized_kind = clean_text(kind)
        if normalized_kind and normalized_kind != "snapshot":
            payload["kind"] = normalized_kind
        return await self.request_json("query", "POST", payload)

    async def query_me(self, qq_number: str, qq_name: str) -> dict[str, Any]:
        return await self.request_json(
            "me",
            "POST",
            {
                "qqNumber": clean_text(qq_number),
                "qqName": clean_text(qq_name),
            },
        )

    async def unbind_me(self, qq_number: str, qq_name: str) -> dict[str, Any]:
        return await self.request_json(
            "unbind",
            "POST",
            {
                "qqNumber": clean_text(qq_number),
                "qqName": clean_text(qq_name),
            },
        )

    def format_bind_result(self, qq_number: str, qq_name: str, result: dict[str, Any]) -> str:
        if not result.get("ok"):
            return self.format_error("绑定", result)
        body = result.get("body") if isinstance(result, dict) else {}
        data = body.get("data") if isinstance(body, dict) else {}
        payload = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
        player = payload.get("player") if isinstance(payload, dict) else None
        if isinstance(player, dict):
            player_name = clean_text(player.get("gameName") or player.get("name") or "未知玩家")
            player_steam64 = clean_text(player.get("steam64") or "未知Steam64")
            return f"已成功为 {qq_name}（{qq_number}）绑定至 {player_name}（{player_steam64}）"
        return f"已成功为 {qq_name}（{qq_number}）完成绑定。"

    @staticmethod
    def format_error(action_name: str, result: dict[str, Any]) -> str:
        body = result.get("body") if isinstance(result, dict) else {}
        if isinstance(body, dict):
            message = clean_text(body.get("message") or body.get("error"))
            if message:
                return f"{action_name}失败：{message}"
        message = clean_text(result.get("message") or result.get("error") or "请求失败")
        return f"{action_name}失败：{message}"

    def format_my_info(self, qq_number: str, qq_name: str, result: dict[str, Any]) -> str:
        if not result.get("ok"):
            return self.format_error("查询我的信息", result)
        body = result.get("body") if isinstance(result, dict) else {}
        data = body.get("data") if isinstance(body, dict) else {}
        payload = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
        player = payload.get("player") if isinstance(payload, dict) else {}
        if not isinstance(player, dict):
            return f"未找到 {qq_name}（{qq_number}）的绑定信息。"

        game_name = clean_text(player.get("gameName") or player.get("name") or "未知玩家")
        steam64 = clean_text(player.get("steam64") or "未知Steam64")
        eos_id = clean_text(player.get("eosID") or "未知EOS ID")
        game_seconds = player.get("gameSeconds")
        game_hours = player.get("gameHours")
        if game_hours is None:
            try:
                game_hours = round(float(game_seconds or 0) / 3600, 2)
            except Exception:
                game_hours = 0

        return (
            f"绑定信息：{qq_name}（{qq_number}）\n"
            f"玩家名字：{game_name}\n"
            f"Steam64：{steam64}\n"
            f"EOS ID：{eos_id}\n"
            f"游戏时长：{game_hours} 小时"
        )

    def format_unbind_result(self, qq_number: str, qq_name: str, result: dict[str, Any]) -> str:
        if not result.get("ok"):
            return self.format_error("解绑我的信息", result)
        body = result.get("body") if isinstance(result, dict) else {}
        data = body.get("data") if isinstance(body, dict) else {}
        payload = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
        player = payload.get("player") if isinstance(payload, dict) else None
        if isinstance(player, dict):
            game_name = clean_text(player.get("gameName") or player.get("name") or "未知玩家")
            return f"已成功解除 {qq_name}（{qq_number}）与 {game_name} 的绑定"
        return f"已成功解除 {qq_name}（{qq_number}）的绑定"
