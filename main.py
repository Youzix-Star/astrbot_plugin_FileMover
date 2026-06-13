import asyncio
import time
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


class FolderSession:
    """文件夹选择会话"""
    def __init__(self, group_id: int, user_id: int, folders: List[Dict]):
        self.group_id = group_id
        self.user_id = user_id
        self.folders = folders
        self.timestamp = time.time()
    
    def is_expired(self, timeout: int = 300) -> bool:
        return time.time() - self.timestamp > timeout
    
    def get_folder_by_index(self, index: int) -> Optional[Dict]:
        if 1 <= index <= len(self.folders):
            return self.folders[index - 1]
        return None


class FileMoverPlugin(Star):
    """群文件自动归档插件"""

    def __init__(self, context: Context, config: Optional[Dict] = None):
        super().__init__(context)
        self.config = config if config else {}

        mapping_list = self.config.get("folder_mapping", [])
        self.folder_mapping: Dict[str, str] = build_folder_mapping(mapping_list)

        self.bot = None
        self._is_llbot = False
        
        # 文件夹选择会话 {f"{group_id}_{user_id}": FolderSession}
        self.folder_sessions: Dict[str, FolderSession] = {}

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

    async def _get_all_files(self, group_id: int) -> List[Dict]:
        """递归获取群内所有文件"""
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
                    file_info["relative_path"] = f"{folder_path}/{file_info.get('file_name', '')}" if folder_path else file_info.get('file_name', '')
                    all_files.append(file_info)
                for folder in data.get("folders", []):
                    fid = folder.get("folder_id")
                    fname = folder.get("folder_name", "")
                    new_path = f"{folder_path}/{fname}" if folder_path else fname
                    folders_to_scan.append((fid, new_path))
            except Exception as e:
                logger.error(f"[群文件归档] 获取文件列表失败: {e}")
        return all_files

    async def _get_folders(self, group_id: int, parent_id: str = None) -> List[Dict]:
        """获取文件夹列表"""
        try:
            if parent_id is None:
                result = await self.bot.api.call_action("get_group_root_files", group_id=group_id)
            else:
                result = await self.bot.api.call_action("get_group_files_by_folder", group_id=group_id, folder_id=parent_id)
            data = result.get("data", result) if isinstance(result, dict) else {}
            folders = data.get("folders", [])
            for f in folders:
                f["parent_id"] = parent_id or "/"
            return folders
        except Exception as e:
            logger.error(f"[群文件归档] 获取文件夹列表失败: {e}")
            return []

    async def _get_files_in_folder(self, group_id: int, folder_id: str) -> List[Dict]:
        """获取指定文件夹内的文件"""
        try:
            result = await self.bot.api.call_action("get_group_files_by_folder", group_id=group_id, folder_id=folder_id)
            data = result.get("data", result) if isinstance(result, dict) else {}
            return data.get("files", [])
        except Exception as e:
            logger.error(f"[群文件归档] 获取文件夹内文件失败: {e}")
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

    async def _get_file_url(self, group_id: int, file_id: str) -> Optional[str]:
        """获取文件下载链接"""
        try:
            result = await self.bot.api.call_action("get_group_file_url", group_id=group_id, file_id=file_id)
            data = result.get("data", result) if isinstance(result, dict) else {}
            return data.get("url")
        except Exception as e:
            logger.error(f"[群文件归档] 获取文件链接失败: {e}")
            return None

    async def _upload_file(self, group_id: int, file_url: str, file_name: str, folder_id: str = "/") -> bool:
        """上传文件到群"""
        try:
            if self._is_llbot:
                await self.bot.api.call_action("upload_group_file", group_id=group_id, file=file_url, name=file_name, folder_id=folder_id)
            else:
                await self.bot.api.call_action("upload_group_file", group_id=group_id, file=file_url, name=file_name, folder=folder_id, folder_id=folder_id)
            return True
        except Exception as e:
            logger.error(f"[群文件归档] 上传文件 '{file_name}' 失败: {e}")
            return False

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

    # ==================== 指令：获取文件夹列表 ====================

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.command("folders", alias={"文件夹列表", "获取文件夹"})
    async def on_list_folders_command(self, event: AstrMessageEvent):
        """获取群内所有文件夹列表"""
        await self._ensure_bot_bound(event)
        
        group_id_str = event.get_group_id()
        if not group_id_str:
            yield event.plain_result("❌ 此指令只能在群聊中使用。")
            return

        group_id = int(group_id_str)
        user_id = int(event.get_sender_id())

        if not self.bot:
            yield event.plain_result("❌ 未获取到 Bot 实例，请稍后重试。")
            return

        # 获取所有文件夹（递归）
        all_folders = []
        await self._collect_folders_recursive(group_id, None, "", all_folders)

        if not all_folders:
            yield event.plain_result("📁 群内没有文件夹。")
            return

        # 保存会话
        session_key = f"{group_id}_{user_id}"
        self.folder_sessions[session_key] = FolderSession(group_id, user_id, all_folders)

        # 格式化输出
        lines = [f"📁 群文件夹列表（共 {len(all_folders)} 个）：\n"]
        for i, folder in enumerate(all_folders, 1):
            path = folder.get("display_path", folder.get("folder_name", ""))
            lines.append(f"  [{i}] {path}")

        lines.append("\n💡 回复数字选择文件夹，用于跨群复制")
        lines.append("⏰ 会话有效期：5分钟")

        yield event.plain_result("\n".join(lines))

    async def _collect_folders_recursive(self, group_id: int, parent_id: str, current_path: str, result: List[Dict]):
        """递归收集所有文件夹"""
        folders = await self._get_folders(group_id, parent_id)
        for folder in folders:
            folder_name = folder.get("folder_name", "")
            folder_id = folder.get("folder_id", "")
            display_path = f"{current_path}/{folder_name}" if current_path else folder_name
            
            folder["display_path"] = display_path
            folder["full_path"] = display_path
            result.append(folder)
            
            # 递归获取子文件夹
            await self._collect_folders_recursive(group_id, folder_id, display_path, result)

    # ==================== 指令：跨群复制文件夹 ====================

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.command("copyfolder", alias={"复制文件夹", "转载文件夹"})
    async def on_copy_folder_command(self, event: AstrMessageEvent):
        """将选中的文件夹复制到目标群"""
        await self._ensure_bot_bound(event)

        group_id_str = event.get_group_id()
        if not group_id_str:
            yield event.plain_result("❌ 此指令只能在群聊中使用。")
            return

        group_id = int(group_id_str)
        user_id = int(event.get_sender_id())
        command_parts = event.message_str.split()

        if len(command_parts) < 3:
            yield event.plain_result(
                "❓ 用法: /复制文件夹 <序号> <目标群号>\n\n"
                "先使用 /文件夹列表 获取文件夹，然后选择序号。"
            )
            return

        # 获取序号和目标群号
        try:
            folder_index = int(command_parts[1])
            target_group_id = int(command_parts[2])
        except ValueError:
            yield event.plain_result("❌ 序号和目标群号必须是数字。")
            return

        # 检查会话
        session_key = f"{group_id}_{user_id}"
        session = self.folder_sessions.get(session_key)
        if not session or session.is_expired():
            yield event.plain_result("❌ 会话已过期，请重新使用 /文件夹列表。")
            return

        # 获取选中的文件夹
        selected_folder = session.get_folder_by_index(folder_index)
        if not selected_folder:
            yield event.plain_result(f"❌ 序号错误，有效范围：1-{len(session.folders)}")
            return

        folder_name = selected_folder.get("folder_name", "")
        folder_id = selected_folder.get("folder_id", "")
        folder_path = selected_folder.get("display_path", folder_name)

        yield event.plain_result(
            f"📁 开始复制文件夹...\n"
            f"  源文件夹: {folder_path}\n"
            f"  目标群: {target_group_id}\n"
            f"  这可能需要一些时间，请耐心等待。"
        )

        # 执行复制
        stats = await self._copy_folder_to_group(
            source_group_id=group_id,
            target_group_id=target_group_id,
            source_folder_id=folder_id,
            folder_name=folder_name,
            folder_path=""
        )

        # 发送报告
        report = self._format_copy_result(stats, folder_path, target_group_id)
        yield event.plain_result(report)

    async def _copy_folder_to_group(
        self,
        source_group_id: int,
        target_group_id: int,
        source_folder_id: str,
        folder_name: str,
        folder_path: str,
        target_parent_id: str = "/"
    ) -> Dict:
        """递归复制文件夹到目标群"""
        stats = {
            "folders_created": 0,
            "files_copied": 0,
            "files_failed": 0,
        }

        # 1. 在目标群创建文件夹
        target_folder_id = await self._create_folder(target_group_id, folder_name)
        if not target_folder_id:
            logger.error(f"[跨群复制] 创建目标文件夹失败: {folder_name}")
            return stats
        stats["folders_created"] += 1

        # 2. 获取源文件夹内的文件
        source_files = await self._get_files_in_folder(source_group_id, source_folder_id)
        
        # 3. 复制文件
        for file_info in source_files:
            file_name = file_info.get("file_name", "")
            file_id = file_info.get("file_id", "")
            
            if not file_name or not file_id:
                continue

            # 获取文件下载链接
            file_url = await self._get_file_url(source_group_id, file_id)
            if not file_url:
                stats["files_failed"] += 1
                continue

            # 上传到目标群
            success = await self._upload_file(target_group_id, file_url, file_name, target_folder_id)
            if success:
                stats["files_copied"] += 1
            else:
                stats["files_failed"] += 1
            
            await asyncio.sleep(1)

        # 4. 递归处理子文件夹
        sub_folders = await self._get_folders(source_group_id, source_folder_id)
        for sub_folder in sub_folders:
            sub_name = sub_folder.get("folder_name", "")
            sub_id = sub_folder.get("folder_id", "")
            sub_path = f"{folder_path}/{sub_name}" if folder_path else sub_name
            
            sub_stats = await self._copy_folder_to_group(
                source_group_id=source_group_id,
                target_group_id=target_group_id,
                source_folder_id=sub_id,
                folder_name=sub_name,
                folder_path=sub_path,
                target_parent_id=target_folder_id
            )
            
            stats["folders_created"] += sub_stats["folders_created"]
            stats["files_copied"] += sub_stats["files_copied"]
            stats["files_failed"] += sub_stats["files_failed"]

        return stats

    def _format_copy_result(self, stats: Dict, folder_path: str, target_group_id: int) -> str:
        """格式化复制结果"""
        lines = [
            f"✅ 文件夹复制完成！\n",
            f"📁 源文件夹: {folder_path}",
            f"🎯 目标群: {target_group_id}",
            f"",
            f"📊 统计:",
            f"  • 创建文件夹: {stats['folders_created']} 个",
            f"  • 复制文件: {stats['files_copied']} 个",
        ]
        if stats['files_failed'] > 0:
            lines.append(f"  • 失败文件: {stats['files_failed']} 个")
        
        return "\n".join(lines)

    # ==================== 原有指令 ====================

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.command("fm", alias={"归档", "文件归档", "自动归档"})
    async def on_file_move_command(self, event: AstrMessageEvent):
        """扫描群文件并根据规则自动归档到对应文件夹"""
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

        yield event.plain_result("📁 开始扫描群文件并归档...\n这可能需要一些时间，请耐心等待。")

        all_files = await self._get_all_files(group_id)
        existing_folders = await self._get_folders(group_id)
        existing_folder_ids = {f["folder_name"]: f["folder_id"] for f in existing_folders}

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

            current_folder_path = file_info.get("current_folder_path", "")
            if current_folder_path == target_folder_name:
                continue

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

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.command("fmrules", alias={"归档规则", "查看规则"})
    async def on_show_rules_command(self, event: AstrMessageEvent):
        """显示当前配置的映射规则"""
        report = format_mapping_display(self.folder_mapping)
        yield event.plain_result(report)

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