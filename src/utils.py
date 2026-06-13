import re
from typing import Optional, List, Dict, Any


def extract_software_name(file_name: str) -> Optional[str]:
    """
    从文件名中提取软件名（第一个 _ 或 - 之前的部分）

    示例：
        >>> extract_software_name("模了个块_5.4.apk")
        '模了个块'
        >>> extract_software_name("QAuxv-v1.6.0.r2968.68b64ac-arm64.apk")
        'QAuxv'
        >>> extract_software_name("TCQT-3.6.4.r515.fe27c90-release.apk")
        'TCQT'
        >>> extract_software_name("simple.txt")
        'simple'
    """
    if not file_name:
        return None

    # 去掉扩展名
    name = file_name.rsplit('.', 1)[0] if '.' in file_name else file_name

    # 截取第一个 _ 或 - 之前的部分
    match = re.match(r'^([^_-]+)', name)
    if match:
        result = match.group(1).strip()
        return result if result else None

    return None


def normalize_rule(rule: Any) -> Optional[Dict[str, str]]:
    """
    统一规则格式，支持两种配置方式：
    1. 字符串格式: "文件夹名（描述）" - 自动提取括号前内容作为关键词
    2. 字典格式: {"keyword": "关键词", "folder": "文件夹名"} - 显式指定

    示例：
        >>> normalize_rule("模了个块（QQ TIM模块）")
        {'keyword': '模了个块', 'folder': '模了个块（QQ TIM模块）'}
        >>> normalize_rule({"keyword": "QAuxv", "folder": "QAuxiliary（QQ TIM模块）"})
        {'keyword': 'QAuxv', 'folder': 'QAuxiliary（QQ TIM模块）'}
    """
    if isinstance(rule, str):
        # 字符串格式：自动提取括号前内容作为关键词
        match = re.match(r'^([^（(]+)', rule)
        keyword = match.group(1).strip() if match else rule.strip()
        return {"keyword": keyword, "folder": rule.strip()}

    if isinstance(rule, dict):
        keyword = rule.get("keyword", "").strip()
        folder = rule.get("folder", "").strip()
        if keyword and folder:
            return {"keyword": keyword, "folder": folder}

    return None


def find_matching_folder(software_name: str, folder_rules: List[Any]) -> Optional[str]:
    """
    根据软件名查找匹配的文件夹

    Args:
        software_name: 从文件名中提取的软件名
        folder_rules: 规则列表（支持字符串或字典格式）

    Returns:
        匹配的文件夹名称，未匹配返回 None

    示例：
        >>> rules = [
        ...     {"keyword": "QAuxv", "folder": "QAuxiliary（QQ TIM模块）"},
        ...     "TCQT（QQ模块）"
        ... ]
        >>> find_matching_folder("QAuxv", rules)
        'QAuxiliary（QQ TIM模块）'
        >>> find_matching_folder("TCQT", rules)
        'TCQT（QQ模块）'
    """
    if not software_name:
        return None

    software_name_lower = software_name.lower()

    for rule in folder_rules:
        normalized = normalize_rule(rule)
        if not normalized:
            continue

        if normalized["keyword"].lower() == software_name_lower:
            return normalized["folder"]

    return None


def format_move_result(results: List[Dict]) -> str:
    """
    格式化移动结果报告

    Args:
        results: 结果列表，每项包含 file_name, folder, success, error

    Returns:
        格式化的报告字符串
    """
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


def format_rules_display(folder_rules: List[Any]) -> str:
    """
    格式化规则显示

    Args:
        folder_rules: 规则列表

    Returns:
        格式化的显示字符串
    """
    if not folder_rules:
        return "📋 当前未配置任何归档规则。\n\n请在插件配置中添加规则。"

    lines = ["📋 当前归档规则：\n"]

    for rule in folder_rules:
        normalized = normalize_rule(rule)
        if normalized:
            lines.append(f"  • {normalized['keyword']} → {normalized['folder']}")

    lines.append(f"\n共 {len(folder_rules)} 条规则")
    lines.append("\n使用 /归档 执行文件归档")

    return "\n".join(lines)