from __future__ import annotations

import asyncio
import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:12864/api/astrbot"
DEFAULT_TIMEOUT_SECONDS = 10.0
PLUGIN_DIR = Path(__file__).resolve().parent
LOG_DIR = PLUGIN_DIR / "logs"
LOG_FILE = LOG_DIR / "manual_bridge.log"
SNAPSHOT_DIR = PLUGIN_DIR / "temp"
CACHE_DIR = PLUGIN_DIR / "cache"


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_snapshot_dir() -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


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
        _ensure_snapshot_dir()
        _ensure_cache_dir()
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
            return self._response(False, message="API token is not configured.")

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
            return self._response(False, message="Steam64 must be a 17-digit number.")
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
        return await self.request_json("me", "POST", {"qqNumber": clean_text(qq_number), "qqName": clean_text(qq_name)})

    async def unbind_me(self, qq_number: str, qq_name: str) -> dict[str, Any]:
        return await self.request_json("unbind", "POST", {"qqNumber": clean_text(qq_number), "qqName": clean_text(qq_name)})

    async def download_my_snapshot(self, qq_number: str, qq_name: str) -> dict[str, Any]:
        return await self._download_snapshot(
            f"{self.base_url.rstrip('/')}/me/snapshot",
            SNAPSHOT_DIR / f"player_snapshot_{clean_text(qq_number) or 'unknown'}.png",
            {"qqNumber": clean_text(qq_number), "qqName": clean_text(qq_name)},
            method="POST",
            save_to_file=True,
            return_base64=False,
        )

    async def download_server_info_snapshot(self) -> dict[str, Any]:
        local_path = CACHE_DIR / "server_info_snapshot.png"
        result = await self._download_image(
            f"{self.base_url.rstrip('/')}/server-info/snapshot",
            local_path,
        )
        if result.get("ok"):
            return result

        self.log("WARN", f"primary server-info snapshot download failed, retrying latest path={result}")
        latest = await self._download_image(
            f"{self.base_url.rstrip('/')}/server-info/snapshot/latest",
            local_path,
        )
        if latest.get("ok"):
            latest["fallback"] = "latest"
        return latest

    async def _download_snapshot(
        self,
        url: str,
        file_path: Path,
        payload: dict[str, Any] | None,
        method: str,
        *,
        save_to_file: bool,
        return_base64: bool,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_token}"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        else:
            body = None

        def do_request() -> dict[str, Any]:
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                content_type = clean_text(response.headers.get("Content-Type", ""))
                image_bytes = response.read()
                if not content_type.lower().startswith("image/"):
                    raw = image_bytes.decode("utf-8", errors="replace")
                    return self._response(False, status=response.status, body=self._loads(raw), message=raw)
                result: dict[str, Any] = self._response(True, status=response.status, content_type=content_type, size=len(image_bytes))
                if save_to_file:
                    file_path.write_bytes(image_bytes)
                    result["file_path"] = str(file_path)
                if return_base64:
                    result["base64"] = base64.b64encode(image_bytes).decode("ascii")
                return result

        self.log("INFO", f"request {method} {url}")
        try:
            result = await asyncio.to_thread(do_request)
            self.log("INFO", f"snapshot response {method} {url} status={result.get('status')} path={result.get('file_path', '-')} size={result.get('size', 0)}")
            return result
        except urllib.error.HTTPError as error:
            try:
                raw = error.read().decode("utf-8", errors="replace")
            except Exception:
                raw = ""
            self.log("ERROR", f"snapshot http_error {method} {url} status={error.code} body={raw}")
            return self._response(False, status=error.code, body=self._loads(raw), error="HTTPError", message=raw or str(error))
        except urllib.error.URLError as error:
            self.log("ERROR", f"snapshot url_error {method} {url} message={error.reason or error}")
            return self._response(False, status=0, body={}, error="URLError", message=str(error.reason or error))
        except Exception as error:
            self.log("ERROR", f"snapshot exception {method} {url} message={error}")
            return self._response(False, status=0, body={}, error=error.__class__.__name__, message=str(error))

    async def _download_image(self, url: str, file_path: Path) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_token}"}

        def do_request() -> dict[str, Any]:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                content_type = clean_text(response.headers.get("Content-Type", ""))
                image_bytes = response.read()
                if not content_type.lower().startswith("image/"):
                    raw = image_bytes.decode("utf-8", errors="replace")
                    return self._response(False, status=response.status, body=self._loads(raw), message=raw)
                file_path.write_bytes(image_bytes)
                return self._response(True, status=response.status, file_path=str(file_path), content_type=content_type, size=len(image_bytes))

        self.log("INFO", f"request GET {url}")
        try:
            result = await asyncio.to_thread(do_request)
            self.log("INFO", f"snapshot image response GET {url} status={result.get('status')} path={result.get('file_path', '-')} size={result.get('size', 0)}")
            return result
        except urllib.error.HTTPError as error:
            try:
                raw = error.read().decode("utf-8", errors="replace")
            except Exception:
                raw = ""
            self.log("ERROR", f"snapshot image http_error GET {url} status={error.code} body={raw}")
            return self._response(False, status=error.code, body=self._loads(raw), error="HTTPError", message=raw or str(error))
        except urllib.error.URLError as error:
            self.log("ERROR", f"snapshot image url_error GET {url} message={error.reason or error}")
            return self._response(False, status=0, body={}, error="URLError", message=str(error.reason or error))
        except Exception as error:
            self.log("ERROR", f"snapshot image exception GET {url} message={error}")
            return self._response(False, status=0, body={}, error=error.__class__.__name__, message=str(error))

    def format_bind_result(self, qq_number: str, qq_name: str, result: dict[str, Any]) -> str:
        if not result.get("ok"):
            return self.format_error("bind", result)
        body = result.get("body") if isinstance(result, dict) else {}
        data = body.get("data") if isinstance(body, dict) else {}
        payload = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
        player = payload.get("player") if isinstance(payload, dict) else None
        if isinstance(player, dict):
            player_name = clean_text(player.get("gameName") or player.get("name") or "Unknown Player")
            player_steam64 = clean_text(player.get("steam64") or "Unknown Steam64")
            return f"Successfully bound {qq_name} ({qq_number}) to {player_name} ({player_steam64})."
        return f"Successfully bound {qq_name} ({qq_number})."

    @staticmethod
    def format_error(action_name: str, result: dict[str, Any]) -> str:
        body = result.get("body") if isinstance(result, dict) else {}
        if isinstance(body, dict):
            message = clean_text(body.get("message") or body.get("error"))
            if message:
                return f"{action_name} failed: {message}"
        message = clean_text(result.get("message") or result.get("error") or "request failed")
        return f"{action_name} failed: {message}"

    def format_my_info(self, qq_number: str, qq_name: str, result: dict[str, Any]) -> str:
        if not result.get("ok"):
            return self.format_error("query my info", result)
        body = result.get("body") if isinstance(result, dict) else {}
        data = body.get("data") if isinstance(body, dict) else {}
        payload = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
        player = payload.get("player") if isinstance(payload, dict) else {}
        if not isinstance(player, dict):
            return f"No binding info found for {qq_name} ({qq_number})."

        game_name = clean_text(player.get("gameName") or player.get("name") or "Unknown Player")
        steam64 = clean_text(player.get("steam64") or "Unknown Steam64")
        eos_id = clean_text(player.get("eosID") or "Unknown EOS ID")
        game_seconds = player.get("gameSeconds")
        game_hours = player.get("gameHours")
        if game_hours is None:
            try:
                game_hours = round(float(game_seconds or 0) / 3600, 2)
            except Exception:
                game_hours = 0

        return (
            f"Binding info: {qq_name} ({qq_number})\n"
            f"Player name: {game_name}\n"
            f"Steam64: {steam64}\n"
            f"EOS ID: {eos_id}\n"
            f"Game hours: {game_hours}"
        )

    def format_server_info(self, result: dict[str, Any]) -> str:
        if not result.get("ok"):
            return self.format_error("server info", result)
        body = result.get("body") if isinstance(result, dict) else {}
        data = body.get("data") if isinstance(body, dict) else {}
        payload = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
        server_info = payload.get("serverInfo") if isinstance(payload, dict) else {}
        if not isinstance(server_info, dict):
            return "No server info available."

        server = server_info.get("server") if isinstance(server_info.get("server"), dict) else {}
        match = server_info.get("match") if isinstance(server_info.get("match"), dict) else {}
        population = server_info.get("population") if isinstance(server_info.get("population"), dict) else {}
        warmup = server_info.get("warmup") if isinstance(server_info.get("warmup"), dict) else {}
        return (
            f"Server info: {clean_text(server.get('serverName') or server.get('serverId') or 'Unknown Server')}\n"
            f"Map: {clean_text(match.get('map') or 'Unknown')}\n"
            f"Layer: {clean_text(match.get('layer') or 'Unknown')}\n"
            f"Mode: {clean_text(match.get('mode') or 'Unknown')}\n"
            f"Players: {clean_text(population.get('players') or 0)}/{clean_text(population.get('maxPlayers') or '?')}, Queue: {clean_text(population.get('queue') or 0)}\n"
            f"Warmup: {'On' if warmup.get('isWarmup') else 'Off'}"
        )

    def format_unbind_result(self, qq_number: str, qq_name: str, result: dict[str, Any]) -> str:
        if not result.get("ok"):
            return self.format_error("unbind", result)
        body = result.get("body") if isinstance(result, dict) else {}
        data = body.get("data") if isinstance(body, dict) else {}
        payload = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
        player = payload.get("player") if isinstance(payload, dict) else None
        if isinstance(player, dict):
            game_name = clean_text(player.get("gameName") or player.get("name") or "Unknown Player")
            return f"Successfully unbound {qq_name} ({qq_number}) from {game_name}."
        return f"Successfully unbound {qq_name} ({qq_number})."
