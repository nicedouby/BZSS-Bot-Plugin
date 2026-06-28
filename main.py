from importlib import util
from pathlib import Path

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


PLUGIN_DIR = Path(__file__).resolve().parent
BRIDGE_PATH = PLUGIN_DIR / "manual_bridge.py"


def _load_bridge_client():
    spec = util.spec_from_file_location("bzss_bot_plugin.manual_bridge", BRIDGE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load bridge client from {BRIDGE_PATH}")
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ManualBridgeClient


ManualBridgeClient = _load_bridge_client()


@register("bzss_bot_plugin", "Antigravity", "BZSS Bot Plugin", "1.2.0")
class MyPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config or {}
        self.bridge = ManualBridgeClient(
            base_url=self.config.get("base_url", "http://BZSW-Panel.site:12864/api/astrbot"),
            api_token=self.config.get("api_token", "awfasdaw"),
            timeout_seconds=self.config.get("timeout_seconds", 10.0),
        )

    def _sender(self, event: AstrMessageEvent) -> tuple[str, str]:
        qq = str(event.get_sender_id() or "").strip()
        nickname = str(event.get_sender_name() or "").strip() or qq
        return qq, nickname

    def _extract_tail(self, text: str, prefix: str) -> str:
        text = str(text or "").strip().lstrip("/")
        if text.startswith(prefix):
            return text[len(prefix):].strip()
        return text

    @filter.command("绑定steam id")
    async def bind_steam(self, event: AstrMessageEvent):
        qq, nickname = self._sender(event)
        steam64 = self._extract_tail(event.message_str, "绑定steam id")
        if not steam64:
            yield event.plain_result("用法: /绑定Steam ID <17位Steam64>")
            return

        self.bridge.log("INFO", f"astrbot bind command qq={qq} nickname={nickname} steam64={steam64}")
        result = await self.bridge.bind_steam(qq, nickname, steam64)
        if result.get("ok"):
            self.bridge.log("INFO", f"astrbot bind success qq={qq} nickname={nickname}")
            yield event.plain_result(self.bridge.format_bind_result(qq, nickname, result))
            return

        self.bridge.log("WARN", f"astrbot bind failed qq={qq} nickname={nickname} result={result}")
        yield event.plain_result(self.bridge.format_error("绑定", result))

    @filter.command("查询我的信息")
    async def query_my_info(self, event: AstrMessageEvent):
        qq, nickname = self._sender(event)
        self.bridge.log("INFO", f"astrbot query-me command qq={qq} nickname={nickname}")
        result = await self.bridge.query_me(qq, nickname)
        if result.get("ok"):
            self.bridge.log("INFO", f"astrbot query-me success qq={qq} nickname={nickname}")
            yield event.plain_result(self.bridge.format_my_info(qq, nickname, result))
            return

        self.bridge.log("WARN", f"astrbot query-me failed qq={qq} nickname={nickname} result={result}")
        yield event.plain_result(self.bridge.format_error("查询我的信息", result))
