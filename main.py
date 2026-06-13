import asyncio
from typing import Dict, List, Optional

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger

from .src.utils import (
    extract_software_name,
    build_folder_mapping,
    find_matching_folder,
    format_move_result,
    format_mapping_display,
)


class FileMoverPlugin(Star):
    """群文件自动归档插件"""

    def __init__(self, context: Context, config: Optional[Dict] = None):
        super().__init__(context)
        self.config = config if config else {}

        mapping_list = self.config.get("folder_mapping", [])
        self.folder_mapping: Dict[str, str] = build_folder_mapping(mapping_list)

        self.bot = None
        self._is_llbot = False

        logger.info(f"[群文件归档] 插件已加载，配置了 {len(self.folder_mapping)} 条映射规则")

    def _is_supported_bot_client(self, client) -> bool:
        return bool(client and hasattr(client, "api") and hasattr(client.api, "call_action"))

    async def _try_bind_bot(self) -> bool:
        platform = self.context.get_platform(filter.PlatformAdapterType.AIOCQHTTP)
        if not platform or not hasattr(platform, "get_client"):
            return False
        bot_client = platform.get_client()
        if not self._is_supported_bot_client(bot_client):
            return False
        self.bot = bot_client
        await self._detect_llbot()
        return True

    async def _ensure_bot_bound(self, event: AstrMessageEvent):
        if self._is_supported_bot_client(self.bot):
            return
        candidate = getattr(event, "bot", None)
        if self._is_supported_bot_client(candidate):
            self.bot = candidate
            await self._detect_llbot()

    async def _detect_llbot(self):
        if not self.bot or not hasattr(self.bot, "api"):
            return
        try:
            version_info = await self.bot.api.call_action("get_version_info")
            app_name = version_info.get("app_name") if isinstance(version_info, dict) else None
            self._is_llbot = app_name == "LLOneBot"
        except Exception:
            self._is_llbot = False

    async def initialize(self):
        await self._try_bind_bot()

    # ==================== 文件操作 ====================

    async def _get_root_files(self, group_id: int) -> List[Dict]:
        """只获取根目录的文件（不扫描文件夹内）"""
        try:
            result = await self.bot.api.call_action("get_group_root_files", group_id=group_id)
            data = result.get("data", result) if isinstance(result, dict) else {}
            files = data.get("files", [])
            # 标记为根目录文件
            for f in files:
                f["current_folder_id"] = "/"
                f["current_folder_path"] = ""
            return files
        except Exception as e:
            logger.error(f"[群文件归档] 获取根目录文件失败: {e}")
            return []

    async def _get_all_files(self, group_id: int) -> List[Dict]:
        """递归获取群内所有文件（包括文件夹内）"""
        all_files = []
        folders_to_scan = [(None, "")]
        while folders_to_scan:
            folder_id, folder_path = folders_to_scan.pop(0)
            try:
                if folder_id is None:
                    result = await self.bot.api.call_action("get_group_root_files", group_id=group_id)
                else:
                    result = await self.bot.api.call_action("get_group_files_by_folder", group_id=group_id, folder_id=folder_id)

                data = result.get("data", result) if isinstance(result, dict) else {}
                for file_info in data.get("files", []):
                    file_info["current_folder_id"] = folder_id or "/"
                    file_info["current_folder_path"] = folder_path
                    all_files.append(file_info)
                for folder in data.get("folders", []):
                    fid = folder.get("folder_id")
                    fname = folder.get("folder_name", "")
                    new_path = f"{folder_path}/{fname}" if folder_path else fname
                    folders_to_scan.append((fid, new_path))
            except Exception as e:
                logger.error(f"[群文件归档] 获取文件列表失败: {e}")
        return all_files

    async def _get_folders(self, group_id: int) -> List[Dict]:
        """获取根目录下的所有文件夹"""
        try:
            result = await self.bot.api.call_action("get_group_root_files", group_id=group_id)
            data = result.get("data", result) if isinstance(result, dict) else {}
            return data.get("folders", [])
        except Exception as e:
            logger.error(f"[群文件归档] 获取文件夹列表失败: {e}")
            return []

    async def _create_folder(self, group_id: int, folder_name: str) -> Optional[str]:
        """创建文件夹，返回 folder_id"""
        try:
            if self._is_llbot:
                await self.bot.api.call_action("create_group_file_folder", group_id=group_id, name=folder_name)
            else:
                await self.bot.api.call_action("create_group_file_folder", group_id=group_id, folder_name=folder_name)
            await asyncio.sleep(1)
            folders = await self._get_folders(group_id)
            for folder in folders:
                if folder.get("folder_name") == folder_name:
                    return folder.get("folder_id")
            return None
        except Exception as e:
            logger.error(f"[群文件归档] 创建文件夹 '{folder_name}' 失败: {e}")
            return None

    async def _move_file(self, group_id: int, file_id: str, current_parent: str, target_folder_id: str) -> bool:
        """移动文件到目标文件夹"""
        try:
            if self._is_llbot:
                result = await self.bot.api.call_action("move_group_file", group_id=group_id, file_id=file_id, parent_directory=current_parent, target_directory=target_folder_id)
            else:
                result = await self.bot.api.call_action("move_group_file", group_id=group_id, file_id=file_id, current_parent_directory=current_parent, target_parent_directory=target_folder_id)
            if result is None:
                return True
            if isinstance(result, dict):
                if result.get("status") == "failed":
                    return False
                if result.get("ok") is True:
                    return True
            return True
        except Exception as e:
            logger.error(f"[群文件归档] 移动文件失败: {e}")
            return False

    # ==================== 指令：自动归档 ====================

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.command("fm", alias={"归档", "文件归档", "自动归档"})
    async def on_file_move_command(self, event: AstrMessageEvent):
        """扫描群文件并根据规则自动归档到对应文件夹
        
        用法：
        /fm - 只扫描根目录文件
        /fm all - 扫描所有文件（包括文件夹内）
        """
        await self._ensure_bot_bound(event)
        group_id_str = event.get_group_id()
        if not group_id_str:
            yield event.plain_result("❌ 此指令只能在群聊中使用。")
            return

        group_id = int(group_id_str)
        if not self.bot:
            yield event.plain_result("❌ 未获取到 Bot 实例，请稍后重试。")
            return

        if not self.folder_mapping:
            yield event.plain_result("❌ 未配置任何映射规则。\n\n请在插件配置中添加规则。")
            return

        # 解析参数
        command_parts = event.message_str.split()
        scan_all = len(command_parts) > 1 and command_parts[1].lower() == "all"

        if scan_all:
            yield event.plain_result("📁 开始扫描所有文件（包括文件夹内）并归档...\n这可能需要一些时间，请耐心等待。")
            all_files = await self._get_all_files(group_id)
        else:
            yield event.plain_result("📁 开始扫描根目录文件并归档...\n使用 /fm all 可扫描所有文件。")
            all_files = await self._get_root_files(group_id)

        existing_folders = await self._get_folders(group_id)
        existing_folder_ids = {f["folder_name"]: f["folder_id"] for f in existing_folders}

        logger.info(f"[群文件归档] 获取到 {len(all_files)} 个文件，扫描模式: {'全部' if scan_all else '仅根目录'}")

        results = []
        folder_cache = {}

        for file_info in all_files:
            file_name = file_info.get("file_name", "")
            file_id = file_info.get("file_id", "")
            current_folder_id = file_info.get("current_folder_id", "/")

            if not file_name or not file_id:
                continue

            software_name = extract_software_name(file_name)
            if not software_name:
                continue

            target_folder_name = find_matching_folder(software_name, self.folder_mapping)
            if not target_folder_name:
                continue

            # 检查是否已经在目标文件夹中
            current_folder_path = file_info.get("current_folder_path", "")
            if current_folder_path == target_folder_name:
                continue

            # 获取或创建目标文件夹
            target_folder_id = None
            if target_folder_name in folder_cache:
                target_folder_id = folder_cache[target_folder_name]
            elif target_folder_name in existing_folder_ids:
                target_folder_id = existing_folder_ids[target_folder_name]
                folder_cache[target_folder_name] = target_folder_id
            else:
                target_folder_id = await self._create_folder(group_id, target_folder_name)
                if target_folder_id:
                    folder_cache[target_folder_name] = target_folder_id
                    existing_folder_ids[target_folder_name] = target_folder_id

            if not target_folder_id:
                results.append({"file_name": file_name, "success": False, "error": "无法创建目标文件夹"})
                continue

            success = await self._move_file(group_id, file_id, current_folder_id, target_folder_id)
            results.append({"file_name": file_name, "folder": target_folder_name, "success": success, "error": "移动失败" if not success else None})
            await asyncio.sleep(0.5)

        report = format_move_result(results)
        yield event.plain_result(report)

    # ==================== 指令：查看规则 ====================

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.command("fmrules", alias={"归档规则", "查看规则"})
    async def on_show_rules_command(self, event: AstrMessageEvent):
        """显示当前配置的映射规则"""
        report = format_mapping_display(self.folder_mapping)
        yield event.plain_result(report)

    # ==================== 指令：测试提取 ====================

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.command("fmtest", alias={"测试归档"})
    async def on_test_command(self, event: AstrMessageEvent):
        """测试文件名提取效果，不会实际移动文件"""
        command_parts = event.message_str.split()
        if len(command_parts) < 2:
            yield event.plain_result("❓ 用法: /测试归档 <文件名>\n\n示例: /测试归档 QAuxv-v1.6.0.apk")
            return

        file_name = command_parts[1]
        software_name = extract_software_name(file_name)
        target_folder = find_matching_folder(software_name, self.folder_mapping) if software_name else None

        lines = [
            f"🧪 测试结果：\n",
            f"  文件名: {file_name}",
            f"  提取的软件名: {software_name or '(无法提取)'}",
            f"  匹配的文件夹: {target_folder or '(未匹配)'}",
        ]

        if not software_name:
            lines.append("\n💡 提示: 文件名需要包含 _ 或 - 分隔符")
        elif not target_folder:
            lines.append(f"\n💡 提示: 需要在配置中添加 \"{software_name}\" 的映射")

        yield event.plain_result("\n".join(lines))

    async def terminate(self):
        logger.info("[群文件归档] 插件已卸载")