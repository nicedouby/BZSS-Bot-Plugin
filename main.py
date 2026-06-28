from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register

@register("bzss_bot_plugin", "Antigravity", "BZSS Bot Plugin", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("服务器信息")
    async def server_info(self, event: AstrMessageEvent):
        """查询服务器信息"""
        qq = event.get_sender_id()
        nickname = event.get_sender_name()
        yield event.plain_result(f"您好，{nickname}（QQ：{qq}），暂时不支持服务器信息指令。")

    @filter.command("预留位查询")
    async def query_reserved(self, event: AstrMessageEvent):
        """预留位查询"""
        qq = event.get_sender_id()
        nickname = event.get_sender_name()
        yield event.plain_result(f"您好，{nickname}（QQ：{qq}），暂时不支持预留位查询指令。")

    @filter.command("绑定steam id")
    async def bind_steam(self, event: AstrMessageEvent):
        """绑定steam id"""
        qq = event.get_sender_id()
        nickname = event.get_sender_name()
        yield event.plain_result(f"您好，{nickname}（QQ：{qq}），暂时不支持绑定steam id指令。")
