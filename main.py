import time
from astrbot.api.event import filter
from astrbot.api.all import Star, Context, AstrBotConfig, logger
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent

class 群变动通知(Star):
    """监听入群/移除群聊事件，发送私聊通知给指定QQ号"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        通知目标 = config["notify_qq"]
        if 通知目标.strip().isdigit():
            self.通知目标 = int(通知目标)
        else:
            self.通知目标 = None
            logger.error("配置【接收通知的QQ号】需填写整数qq号")
        self.入群通知开关 = config["enable_increase"]
        self.退群通知开关 = config["enable_decrease"]
        启用群列表 = config["enabled_groups"]
        启用群列表 = 启用群列表.strip().split("\n")
        启用群列表 = [ i for i in 启用群列表 if i ]
        if 'all' in 启用群列表:
            self.监听所有群 = True
            self.启用群列表 = set()
        else:
            self.监听所有群 = False
            self.启用群列表 = set(启用群列表)
        logger.debug(f"插件初始化完成，监听所有群: {self.监听所有群}, 指定群列表: {self.启用群列表}, 入群通知: {self.入群通知开关}, 退群通知: {self.退群通知开关}")

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=9999)
    async def 监听入口(self, event: AiocqhttpMessageEvent):
        """监听群聊事件，筛选入群/退群通知"""
        raw = event.message_obj.raw_message
        if not raw or raw.get("post_type") != "notice":
            return

        notice_type = raw.get("notice_type")
        group_id = str(raw.get("group_id", 0))

        # 群组过滤
        if not self.监听所有群 and group_id not in self.启用群列表:
            logger.debug(f"群 {group_id} 不在启用列表中，忽略")
            return

        if not self.通知目标:
            logger.error("接收通知的QQ号未配置或无效，无法发送通知")
            return

        if notice_type == "group_increase" and self.入群通知开关:
            logger.debug(f"检测到入群事件，群 {group_id}，开始处理")
            await self._处理入群事件(event, raw)
        elif notice_type == "group_decrease" and self.退群通知开关:
            logger.debug(f"检测到退群事件，群 {group_id}，开始处理")
            await self._处理退群事件(event, raw)

    async def _处理入群事件(self, event: AiocqhttpMessageEvent, raw: dict):
        """处理入群事件"""
        group_id = raw.get("group_id", 0)
        user_id = raw.get("user_id", 0)
        operator_id = raw.get("operator_id", 0)
        sub_type = raw.get("sub_type", "")

        logger.debug(f"获取群 {group_id} 信息")
        group_name = await self._获取群名(event, group_id)
        user_name = await self._获取昵称(event, user_id)
        operator_name = await self._获取昵称(event, operator_id) if operator_id else "未知"

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        if sub_type == "invite":
            方式 = f"💌 被 {operator_name} ({operator_id}) 邀请入群"
        else:
            方式 = f"✅ 被管理员 {operator_name} ({operator_id}) 同意入群"

        通知内容 = (
            f"📢 入群通知\n"
            f"━━━━━━━━━━━━━━\n"
            f"👤 成员：\n    {user_id}\n    {user_name}\n\n"
            f"👥 群聊：\n    {group_id}\n    {group_name}\n\n"
            f"{方式}\n\n"
            f"⏰ 时间: {now}\n"
            f"━━━━━━━━━━━━━━"
        )

        await self._发送通知(event, 通知内容, f"{user_name}({user_id}) 加入 {group_name}({group_id})")

    async def _处理退群事件(self, event: AiocqhttpMessageEvent, raw: dict):
        """处理退群/踢人事件"""
        group_id = raw.get("group_id", 0)
        user_id = raw.get("user_id", 0)
        operator_id = raw.get("operator_id", 0)
        sub_type = raw.get("sub_type", "")

        group_name = await self._获取群名(event, group_id)
        user_name = await self._获取昵称(event, user_id)

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        if sub_type == "kick":
            operator_name = await self._获取昵称(event, operator_id) if operator_id else "未知"
            方式 = f"🚫 被管理员 {operator_name} ({operator_id}) 踢出群聊"
        elif sub_type == "leave":
            方式 = "🚪 主动退出群聊"
        else:
            方式 = "❌ 离开群聊"

        通知内容 = (
            f"📢 退群通知\n"
            f"━━━━━━━━━━━━━━\n"
            f"👤 成员：\n    {user_id}\n    {user_name}\n\n"
            f"👥 群聊：\n    {group_id}\n    {group_name}\n\n"
            f"{方式}\n\n"
            f"⏰ 时间: {now}\n"
            f"━━━━━━━━━━━━━━"
        )

        await self._发送通知(event, 通知内容, f"{user_name}({user_id}) 离开 {group_name}({group_id})")

    async def _发送通知(self, event: AiocqhttpMessageEvent, message: str, log_msg: str):
        """发送私聊通知"""
        try:
            await event.bot.call_action("send_private_msg", user_id=self.通知目标, message=message)
            logger.info(f"[群变动通知] 已通知: {log_msg}")
        except Exception as e:
            logger.error(f"[群变动通知] 发送失败: {e}", exc_info=True)

    @staticmethod
    async def _获取群名(event: AiocqhttpMessageEvent, group_id: int) -> str:
        try:
            info = await event.bot.call_action("get_group_info", group_id=group_id)
            return info.get("group_name", str(group_id))
        except Exception as e:
            logger.debug(f"获取群名失败，群号 {group_id}: {e}")
            return str(group_id)

    @staticmethod
    async def _获取昵称(event: AiocqhttpMessageEvent, user_id: int) -> str:
        try:
            info = await event.bot.call_action("get_stranger_info", user_id=user_id)
            return info.get("nickname", str(user_id))
        except Exception as e:
            logger.debug(f"获取昵称失败，QQ号 {user_id}: {e}")
            return str(user_id)