import re
from typing import Optional, List, Dict


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


def extract_folder_keyword(folder_name: str) -> str:
    """
    从文件夹名中提取关键词（第一个 （ 或 ( 之前的部分）

    示例：
        >>> extract_folder_keyword("模了个块（QQ TIM模块）")
        '模了个块'
        >>> extract_folder_keyword("QAuxv（QQ TIM模块）")
        'QAuxv'
        >>> extract_folder_keyword("TCQT（QQ模块）")
        'TCQT'
        >>> extract_folder_keyword("其他文件")
        '其他文件'
    """
    # 匹配中文括号 （ 或 英文括号 (
    match = re.match(r'^([^（(]+)', folder_name)
    if match:
        return match.group(1).strip()
    return folder_name.strip()


def find_matching_folder(software_name: str, folder_rules: List[str]) -> Optional[str]:
    """
    根据软件名查找匹配的文件夹

    Args:
        software_name: 从文件名中提取的软件名
        folder_rules: 文件夹名称列表

    Returns:
        匹配的文件夹完整名称，未匹配返回 None

    示例：
        >>> rules = ["模了个块（QQ TIM模块）", "QAuxv（QQ TIM模块）"]
        >>> find_matching_folder("模了个块", rules)
        '模了个块（QQ TIM模块）'
        >>> find_matching_folder("unknown", rules)
        None
    """
    if not software_name:
        return None

    software_name_lower = software_name.lower()

    for folder_name in folder_rules:
        keyword = extract_folder_keyword(folder_name)
        if keyword.lower() == software_name_lower:
            return folder_name

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