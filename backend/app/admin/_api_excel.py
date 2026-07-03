"""接口 Excel 导入/导出的内部工具（编解码 + 校验，不直接触碰 DB）。"""
from typing import Any


HEADER_COLUMNS = ["name", "required", "expectValue", "example", "description"]
QUERY_COLUMNS = ["name", "type", "required", "example", "description"]
BODY_COLUMNS = ["contentType", "required", "example", "description"]
PARAM_MAPPING_COLUMNS = ["name", "in", "type", "required", "bindTo"]

MAIN_HEADERS = [
    "方法", "路径", "接口名", "启用", "分类", "分组", "数据源", "拓扑",
    "鉴权类型", "鉴权头名",
    "请求头", "Query 参数", "请求体",
    "SQL 语句", "响应模板", "参数映射",
    "静态响应体",
    "故障-延迟毫秒", "故障-错误率", "故障-错误状态码",
]

INSTRUCTION_SHEET_NAME = "_使用说明"
UNCATEGORIZED_SHEET_NAME = "未归类"
SHEET_NAME_MAX_LEN = 31
INVALID_SHEET_CHARS = ":\\/?*[]"

FIELD_SEP = "|"
RECORD_SEP = "\n"


class ExcelValidationError(Exception):
    """行级校验错误——被上层 parse_workbook 捕获并塞进 errors 列表。"""


def _format_field(value: Any) -> str:
    """把 Python 值渲染成单元格里的一段字段字符串。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def format_cell_list(records: list[dict], columns: list[str]) -> str:
    """把结构化记录列表序列化成“多行 + 竖线分隔”的单元格文本。

    空列表 -> 空字符串（不是 "|||"）。
    """
    if not records:
        return ""
    lines: list[str] = []
    for rec in records:
        fields = [_format_field(rec.get(col)) for col in columns]
        lines.append(FIELD_SEP.join(fields))
    return RECORD_SEP.join(lines)


_TRUE_TOKENS = {"是", "true", "1", "yes", "y"}
_FALSE_TOKENS = {"否", "false", "0", "no", "n", ""}


def _is_boolean_column(column: str) -> bool:
    """哪些列在解析时按 bool 处理。"""
    return column == "required"


def _parse_field(value: str, column: str) -> Any:
    """把单元格里的字段字符串解回 Python 值。"""
    stripped = value.strip()
    if _is_boolean_column(column):
        lower = stripped.lower()
        if lower in _TRUE_TOKENS:
            return True
        if lower in _FALSE_TOKENS:
            return False
        raise ExcelValidationError(f"必填列的值 '{value}' 无法识别（应为 是/否）")
    return stripped


def parse_cell_list(cell_text: str, columns: list[str], row_hint: str) -> list[dict]:
    """把“多行 + 竖线分隔”的单元格文本解析回记录列表。

    row_hint 用来在报错时给出 sheet/行/列的位置提示，如 "Sheet '网管A' 第 3 行 请求头"。
    """
    if cell_text is None or cell_text == "":
        return []
    records: list[dict] = []
    for line in cell_text.split(RECORD_SEP):
        line = line.strip()
        if not line:
            continue
        fields = line.split(FIELD_SEP)
        if len(fields) > len(columns):
            raise ExcelValidationError(
                f"{row_hint}：字段数 {len(fields)} 超过预期 {len(columns)}（列顺序：{columns}）"
            )
        while len(fields) < len(columns):
            fields.append("")
        record = {}
        for col, raw in zip(columns, fields):
            try:
                record[col] = _parse_field(raw, col)
            except ExcelValidationError as e:
                raise ExcelValidationError(f"{row_hint}：{e}") from e
        records.append(record)
    return records
