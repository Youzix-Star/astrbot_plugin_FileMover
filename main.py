import asyncio
import os
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
from astrbot.api.web import route, GET, POST, PluginUploadFile, json_response, error_response
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .src.utils import (
    extract_software_name,
    build_folder_mapping,
    find_matching_folder,
    format_move_result,
    format_mapping_display,
)

PLUGIN_NAME = "astrbot_plugin_FileMover"

class FileMoverPlugin(Star):
    def __init__(self, context: Context, config: Optional[Dict] = None):
        super().__init__(context)
        self.config = config if config else {}

        # 映射规则
        mapping_list = self.config.get("folder_mapping", [])
        self.folder_mapping: Dict[str, str] = build_folder_mapping(mapping_list)

        # Bot 相关
        self.bot = None
        self._is_llbot = False

        # WebUI 上传目录
        self.upload_dir = Path(get_astrbot_plugin_data_path()) / PLUGIN_NAME / "uploads"
        self.upload_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[群文件归档] 插件已加载，配置了 {len(self.folder_mapping)} 条映射规则")
        logger.info(f"[群文件归档] 上传目录: {self.upload_dir}")

    # ========== Web 路由（使用 @route 装饰器） ==========

    @route("/groups", method=GET)
    async def api_get_groups(self, request):
        """获取群列表"""
        await self._try_bind_bot()
        if not self.bot:
            return error_response("未连接到 Bot", status_code=503)

        try:
            result = await self.bot.api.call_action("get_group_list")
            groups = result.get("data", result) if isinstance(result, dict) else []
            return json_response({"groups": groups})
        except Exception as e:
            logger.error(f"获取群列表失败: {e}")
            return error_response(str(e), status_code=500)

    @route("/folders", method=GET)
    async def api_get_folders(self, request):
        """获取根目录文件夹"""
        await self._try_bind_bot()
        if not self.bot:
            return error_response("未连接到 Bot", status_code=503)

        group_id = request.query.get("group_id", type=int)
        if not group_id:
            return error_response("缺少 group_id", status_code=400)

        try:
            if self._is_llbot:
                result = await self.bot.api.call_action("get_group_root_files", group_id=group_id)
            else:
                result = await self.bot.api.call_action("get_group_root_files", group_id=group_id, file_count=2000)

            data = result.get("data", result) if isinstance(result, dict) else {}
            folders = data.get("folders", [])
            return json_response({"folders": folders})
        except Exception as e:
            logger.error(f"获取文件夹列表失败: {e}")
            return error_response(str(e), status_code=500)

    @route("/upload", method=POST)
    async def api_upload_and_distribute(self, request):
        """上传并分发"""
        await self._try_bind_bot()
        if not self.bot:
            return error_response("未连接到 Bot", status_code=503)

        # 解析表单
        form = await request.form()
        files = await request.files()

        upload: PluginUploadFile | None = files.get("file")
        if not isinstance(upload, PluginUploadFile):
            return error_response("未上传文件", status_code=400)

        # 目标群
        target_groups_str = form.get("target_groups", "")
        if not target_groups_str:
            return error_response("请选择目标群", status_code=400)
        target_groups = [g.strip() for g in target_groups_str.split(",") if g.strip()]
        if not target_groups:
            return error_response("请选择目标群", status_code=400)

        # 目标文件夹（可选）
        target_folder = form.get("target_folder", "").strip()

        # 是否自动分类
        auto_classify = form.get("auto_classify", "false").lower() == "true"

        # 保存临时文件
        temp_id = str(uuid.uuid4())[:8]
        original_name = Path(upload.filename).name
        temp_name = f"{temp_id}_{original_name}"
        temp_path = self.upload_dir / temp_name
        await upload.save(temp_path)

        # 分发结果
        results = []
        for group_id in target_groups:
            try:
                gid = int(group_id)
                folder_id = None

                if auto_classify:
                    # 自动分类：提取软件名并匹配映射
                    software = extract_software_name(original_name)
                    if software:
                        matched_folder = find_matching_folder(software, self.folder_mapping)
                        if matched_folder:
                            target_folder = matched_folder  # 覆盖

                if target_folder:
                    folder_id = await self._get_or_create_folder(gid, target_folder)

                # 上传文件
                await self._upload_file_to_group(gid, str(temp_path), original_name, folder_id)
                results.append({"group_id": group_id, "success": True})
            except Exception as e:
                logger.error(f"分发到群 {group_id} 失败: {e}")
                results.append({"group_id": group_id, "success": False, "error": str(e)})

        # 清理临时文件
        try:
            os.remove(temp_path)
        except Exception:
            pass

        return json_response({
            "results": results,
            "total": len(results),
            "success_count": sum(1 for r in results if r["success"]),
            "failed_count": sum(1 for r in results if not r["success"])
        })

    # ========== 辅助方法 ==========
    async def _get_or_create_folder(self, group_id: int, folder_name: str) -> Optional[str]:
        """获取或创建文件夹，返回 folder_id"""
        folders = await self._get_folders(group_id)
        for folder in folders:
            if folder.get("folder_name") == folder_name:
                return folder.get("folder_id")

        # 创建
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
        except Exception as e:
            logger.error(f"创建文件夹失败: {e}")
        return None

    async def _upload_file_to_group(self, group_id: int, file_path: str, file_name: str, folder_id: Optional[str] = None):
        """上传文件到群"""
        if self._is_llbot:
            params = {"group_id": group_id, "file": file_path, "name": file_name}
            if folder_id:
                params["folder_id"] = folder_id
            await self.bot.api.call_action("upload_group_file", **params)
        else:
            params = {"group_id": group_id, "file": file_path, "name": file_name}
            if folder_id:
                params["folder"] = folder_id
            await self.bot.api.call_action("upload_group_file", **params)

    async def _get_folders(self, group_id: int) -> List[Dict]:
        """获取根目录文件夹"""
        try:
            if self._is_llbot:
                result = await self.bot.api.call_action("get_group_root_files", group_id=group_id)
            else:
                result = await self.bot.api.call_action("get_group_root_files", group_id=group_id, file_count=2000)
            data = result.get("data", result) if isinstance(result, dict) else {}
            return data.get("folders", [])
        except Exception:
            return []

    # ========== Bot 绑定 ==========
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

    async def terminate(self):
        logger.info("[群文件归档] 插件已卸载")

    # ========== 原有指令（完整保留） ==========

    # ---- 获取根目录文件 ----
    async def _get_root_files(self, group_id: int) -> List[Dict]:
        try:
            if self._is_llbot:
                result = await self.bot.api.call_action("get_group_root_files", group_id=group_id)
            else:
                result = await self.bot.api.call_action("get_group_root_files", group_id=group_id, file_count=2000)
            data = result.get("data", result) if isinstance(result, dict) else {}
            files = data.get("files", [])
            for f in files:
                f["current_folder_id"] = "/"
                f["current_folder_path"] = ""
            return files
        except Exception as e:
            logger.error(f"[群文件归档] 获取根目录文件失败: {e}")
            return []

    # ---- 递归获取所有文件 ----
    async def _get_all_files(self, group_id: int) -> List[Dict]:
        all_files = []
        folders_to_scan = [(None, "")]
        while folders_to_scan:
            folder_id, folder_path = folders_to_scan.pop(0)
            try:
                if folder_id is None:
                    if self._is_llbot:
                        result = await self.bot.api.call_action("get_group_root_files", group_id=group_id)
                    else:
                        result = await self.bot.api.call_action("get_group_root_files", group_id=group_id, file_count=2000)
                else:
                    if self._is_llbot:
                        result = await self.bot.api.call_action("get_group_files_by_folder", group_id=group_id, folder_id=folder_id)
                    else:
                        result = await self.bot.api.call_action("get_group_files_by_folder", group_id=group_id, folder_id=folder_id, file_count=2000)

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

    # ---- 移动文件 ----
    async def _move_file(self, group_id: int, file_id: str, current_parent: str, target_folder_id: str) -> bool:
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

    # ---- 调试模式 ----
    async def _debug_files(self, group_id: int, scan_all: bool = False) -> str:
        if scan_all:
            all_files = await self._get_all_files(group_id)
            mode = "所有文件"
        else:
            all_files = await self._get_root_files(group_id)
            mode = "根目录文件"

        lines = [f"📁 扫描范围：{mode}", f"📊 文件总数：{len(all_files)}\n"]
        matched = 0
        unmatched = 0
        skipped = 0

        for f in all_files:
            fname = f.get("file_name", "")
            current_path = f.get("current_folder_path", "")
            sname = extract_software_name(fname)
            target = find_matching_folder(sname, self.folder_mapping) if sname else None

            status = ""
            if current_path:
                status = f"（已在文件夹：{current_path}）"
                skipped += 1
            elif target:
                status = f"→ {target}"
                matched += 1
            else:
                status = "（无匹配规则）"
                unmatched += 1

            lines.append(f"  {fname}")
            lines.append(f"    软件名：{sname or '无法提取'} {status}")

        lines.append(f"\n📈 统计：")
        lines.append(f"  可归档：{matched} 个")
        lines.append(f"  无规则：{unmatched} 个")
        lines.append(f"  已分类：{skipped} 个")
        return "\n".join(lines)

    # ---- 指令：/fm ----
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.command("fm", alias={"归档", "文件归档", "自动归档"})
    async def on_file_move_command(self, event: AstrMessageEvent):
        await self._ensure_bot_bound(event)
        group_id_str = event.get_group_id()
        if not group_id_str:
            yield event.plain_result("此指令只能在群聊中使用。")
            return

        group_id = int(group_id_str)
        if not self.bot:
            yield event.plain_result("未获取到 Bot 实例，请稍后重试。")
            return

        if not self.folder_mapping:
            yield event.plain_result("未配置映射规则。")
            return

        command_parts = event.message_str.split()
        args = [p.lower() for p in command_parts[1:]] if len(command_parts) > 1 else []
        scan_all = "all" in args
        debug_mode = "debug" in args

        if debug_mode:
            debug_result = await self._debug_files(group_id, scan_all)
            yield event.plain_result(debug_result)
            return

        # 正常归档
        if scan_all:
            yield event.plain_result("扫描所有文件中...")
            all_files = await self._get_all_files(group_id)
        else:
            yield event.plain_result("扫描根目录文件中...\n（/fm all 扫描全部）")
            all_files = await self._get_root_files(group_id)

        existing_folders = await self._get_folders(group_id)
        existing_folder_ids = {f["folder_name"]: f["folder_id"] for f in existing_folders}

        results = []
        skipped = []
        folder_cache = {}

        for file_info in all_files:
            file_name = file_info.get("file_name", "")
            file_id = file_info.get("file_id", "")
            current_folder_id = file_info.get("current_folder_id", "/")
            if not file_name or not file_id:
                continue

            software_name = extract_software_name(file_name)
            if not software_name:
                skipped.append(f"{file_name}（无法提取软件名）")
                continue

            target_folder_name = find_matching_folder(software_name, self.folder_mapping)
            if not target_folder_name:
                skipped.append(f"{file_name}（无匹配规则）")
                continue

            current_folder_path = file_info.get("current_folder_path", "")
            if current_folder_path == target_folder_name:
                skipped.append(f"{file_name}（已在目标文件夹）")
                continue

            target_folder_id = None
            if target_folder_name in folder_cache:
                target_folder_id = folder_cache[target_folder_name]
            elif target_folder_name in existing_folder_ids:
                target_folder_id = existing_folder_ids[target_folder_name]
                folder_cache[target_folder_name] = target_folder_id
            else:
                target_folder_id = await self._get_or_create_folder(group_id, target_folder_name)
                if target_folder_id:
                    folder_cache[target_folder_name] = target_folder_id
                    existing_folder_ids[target_folder_name] = target_folder_id

            if not target_folder_id:
                results.append({"file_name": file_name, "success": False, "error": "创建文件夹失败"})
                continue

            success = await self._move_file(group_id, file_id, current_folder_id, target_folder_id)
            results.append({"file_name": file_name, "folder": target_folder_name, "success": success, "error": "移动失败" if not success else None})
            await asyncio.sleep(0.5)

        report = format_move_result(results)
        if skipped and not results:
            report += "\n\n跳过的文件：\n" + "\n".join(f"  {s}" for s in skipped[:10])
            if len(skipped) > 10:
                report += f"\n  ...共 {len(skipped)} 个"

        yield event.plain_result(report)

    # ---- 指令：/fmrules ----
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.command("fmrules", alias={"归档规则", "查看规则"})
    async def on_show_rules_command(self, event: AstrMessageEvent):
        report = format_mapping_display(self.folder_mapping)
        yield event.plain_result(report)

    # ---- 指令：/fmtest ----
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.command("fmtest", alias={"测试归档"})
    async def on_test_command(self, event: AstrMessageEvent):
        command_parts = event.message_str.split()
        if len(command_parts) < 2:
            yield event.plain_result("用法：/测试归档 <文件名>")
            return

        file_name = command_parts[1]
        software_name = extract_software_name(file_name)
        target_folder = find_matching_folder(software_name, self.folder_mapping) if software_name else None

        lines = [
            f"文件名：{file_name}",
            f"软件名：{software_name or '无法提取'}",
            f"目标文件夹：{target_folder or '未匹配'}",
        ]
        if not software_name:
            lines.append("\n提示：文件名需要包含 _ 或 -")
        elif not target_folder:
            lines.append(f"\n提示：需添加 \"{software_name}\" 的映射")

        yield event.plain_result("\n".join(lines))