import re
from typing import Optional, List, Dict


def extract_software_name(file_name: str) -> Optional[str]:
    """从文件名中提取软件名（第一个 _ 或 - 之前的部分）"""
    if not file_name:
        return None
    name = file_name.rsplit('.', 1)[0] if '.' in file_name else file_name
    match = re.match(r'^([^_-]+)', name)
    if match:
        result = match.group(1).strip()
        return result if result else None
    return None


def build_folder_mapping(mapping_list: List[str]) -> Dict[str, str]:
    """将简写列表转换为字典映射"""
    result = {}
    for item in mapping_list:
        if not isinstance(item, str) or '=' not in item:
            continue
        parts = item.split('=', 1)
        keyword = parts[0].strip()
        folder = parts[1].strip()
        if keyword and folder:
            result[keyword] = folder
    return result


def find_matching_folder(software_name: str, folder_mapping: Dict[str, str]) -> Optional[str]:
    """根据软件名查找匹配的文件夹"""
    if not software_name or not folder_mapping:
        return None
    software_name_lower = software_name.lower()
    for keyword, folder_name in folder_mapping.items():
        if keyword.lower() == software_name_lower:
            return folder_name
    return None


def format_move_result(results: List[Dict]) -> str:
    """格式化移动结果报告"""
    if not results:
        return "没有需要移动的文件。"

    success = [r for r in results if r.get('success')]
    failed = [r for r in results if not r.get('success')]

    lines = ["📁 文件归档结果：\n"]

    if success:
        lines.append(f"✅ 成功移动 {len(success)} 个文件：")
        for r in success:
            lines.append(f"  • {r['file_name']} → {r['folder']}")

    if failed:
        lines.append(f"\n❌ 移动失败 {len(failed)} 个：")
        for r in failed:
            lines.append(f"  • {r['file_name']}：{r.get('error', '未知错误')}")

    if not success and not failed:
        lines.append("未找到需要归档的文件。")

    return "\n".join(lines)


def format_mapping_display(folder_mapping: Dict[str, str]) -> str:
    """格式化映射规则显示"""
    if not folder_mapping:
        return "📋 当前未配置任何映射规则。\n\n请在插件配置中添加规则，格式：\n关键词=文件夹名"

    lines = ["📋 当前映射规则：\n"]
    for keyword, folder_name in folder_mapping.items():
        lines.append(f"  • {keyword} → {folder_name}")

    lines.append(f"\n共 {len(folder_mapping)} 条规则")
    lines.append("\n使用 /归档 执行文件归档")

    return "\n".join(lines)