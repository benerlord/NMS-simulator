"""画布 Excel 导入导出的内部工具（编解码 + 校验，不直接触碰 DB）。"""
import json as _json
from typing import Any, Optional


INSTRUCTION_SHEET_NAME = "_使用说明"
INDEX_SHEET_NAME = "_总表"
META_SHEET_NAME = "拓扑元信息"
NODE_GROUP_SHEET_NAME = "节点组"
NODE_GROUP_EDGE_STRATEGY_SHEET_NAME = "节点组边策略"
NODE_ALARM_SHEET_NAME = "节点告警"
NODE_GROUP_ALARM_SHEET_NAME = "节点组告警"

SHEET_NAME_MAX_LEN = 31
INVALID_SHEET_CHARS = ":\\/?*[]"

NODE_TYPE_MARKER = "__NODE_TYPE_CODE__"
EDGE_TYPE_MARKER = "__EDGE_TYPE_CODE__"
NODE_GROUP_MARKER = "__NODE_GROUP__"
NODE_GROUP_EDGE_STRATEGY_MARKER = "__NODE_GROUP_EDGE_STRATEGY__"
NODE_ALARM_MARKER = "__NODE_ALARM__"
NODE_GROUP_ALARM_MARKER = "__NODE_GROUP_ALARM__"

FIELD_SEP = "|"
RECORD_SEP = "\n"
PARAM_KV_SEP = ";"

NODE_FIXED_HEADERS = ["名称", "DN", "状态", "画布 X", "画布 Y", "所属组"]
EDGE_FIXED_HEADERS = ["源节点", "目标节点", "状态"]
NODE_GROUP_HEADERS = [
    "组名", "节点类型代码", "节点数量", "命名模板", "已展开",
    "画布 X", "画布 Y", "属性策略",
]
NODE_GROUP_EDGE_STRATEGY_HEADERS = [
    "源组名", "目标", "目标类型", "边类型代码", "模式", "K",
]
NODE_ALARM_FIXED_HEADERS = ["节点类型代码", "节点名称", "告警序号"]
NODE_GROUP_ALARM_FIXED_HEADERS = ["组名", "告警序号"]
META_HEADERS = ["字段", "值"]
INDEX_HEADERS = ["类别", "类型代码", "Sheet 名", "行数", "跳转"]

ALLOWED_STATUS = {"online", "offline", "unknown", "warning", "error"}
ALLOWED_STRATEGY = {"fixed", "random", "increment", "range"}
ALLOWED_MODE = {"modulo", "one_to_n", "all_to_all", "dense"}
ALLOWED_TARGET_KIND = {"组", "节点"}


class ExcelValidationError(Exception):
    """行级/致命校验错误。上层区分——parse_workbook 里被捕获归到 errors 就是行级；
    在打开文件/无数据 Sheet 场景直接抛就是致命。"""


def sanitize_sheet_name(name: str, used: set) -> str:
    """把 domain/nodeType/edgeType 名清洗成 Excel 合法 sheet 名并防重名。副作用：mutating used。"""
    sanitized = name
    for ch in INVALID_SHEET_CHARS:
        sanitized = sanitized.replace(ch, "_")
    if len(sanitized) > SHEET_NAME_MAX_LEN:
        sanitized = sanitized[:SHEET_NAME_MAX_LEN]
    if not sanitized.strip():
        sanitized = "未命名"
    if sanitized not in used:
        used.add(sanitized)
        return sanitized
    suffix = 2
    while True:
        tag = f"~{suffix}"
        base_max = SHEET_NAME_MAX_LEN - len(tag)
        candidate = sanitized[:base_max] + tag
        if candidate not in used:
            used.add(candidate)
            return candidate
        suffix += 1


# --- Attr strategy encoders/decoders ---

def format_attr_strategy_row(strategy: dict) -> str:
    """把一个 attr_strategy dict 序列化成 'field_key|strategy|k=v;k=v' 行。"""
    field_key = strategy["field_key"]
    stype = strategy["strategy"]
    params = []
    if stype == "fixed":
        params.append(f"fixedValue={strategy.get('fixed_value', '')}")
    elif stype == "random":
        pool = strategy.get("pool") or []
        params.append(f"pool={';'.join(str(x) for x in pool)}")
    elif stype == "increment":
        params.append(f"base={strategy.get('base', '')}")
        params.append(f"step={strategy.get('step', '')}")
    elif stype == "range":
        params.append(f"min={strategy.get('min', '')}")
        params.append(f"max={strategy.get('max', '')}")
    param_str = PARAM_KV_SEP.join(params)
    return f"{field_key}{FIELD_SEP}{stype}{FIELD_SEP}{param_str}"


def parse_attr_strategy_row(line: str, row_hint: str) -> dict:
    """把 'field_key|strategy|k=v;k=v' 行解回 dict。抛 ExcelValidationError 表示行级错误。"""
    parts = line.split(FIELD_SEP)
    if len(parts) < 2:
        raise ExcelValidationError(f"{row_hint}：属性策略格式错，缺字段名或策略类型")
    field_key = parts[0].strip()
    stype = parts[1].strip()
    param_str = FIELD_SEP.join(parts[2:]).strip() if len(parts) > 2 else ""

    if stype not in ALLOWED_STRATEGY:
        raise ExcelValidationError(
            f"{row_hint}：属性策略类型 '{stype}' 不合法（允许 {sorted(ALLOWED_STRATEGY)}）"
        )
    kv = {}
    if param_str:
        for pair in param_str.split(PARAM_KV_SEP):
            if "=" not in pair:
                continue
            k, v = pair.split("=", 1)
            kv[k.strip()] = v.strip()

    result: dict = {"field_key": field_key, "strategy": stype}
    if stype == "fixed":
        if "fixedValue" not in kv or not kv["fixedValue"]:
            raise ExcelValidationError(f"{row_hint}：fixed 策略缺 fixedValue")
        result["fixed_value"] = kv["fixedValue"]
    elif stype == "random":
        pool_str = kv.get("pool", "")
        if not pool_str:
            raise ExcelValidationError(f"{row_hint}：random 策略缺 pool")
        result["pool"] = [x for x in pool_str.split(";") if x]
    elif stype == "increment":
        if "base" not in kv or "step" not in kv:
            raise ExcelValidationError(f"{row_hint}：increment 策略缺 base 或 step")
        result["base"] = kv["base"]
        result["step"] = kv["step"]
    elif stype == "range":
        if "min" not in kv or "max" not in kv:
            raise ExcelValidationError(f"{row_hint}：range 策略缺 min 或 max")
        try:
            result["min"] = int(kv["min"])
            result["max"] = int(kv["max"])
        except ValueError:
            raise ExcelValidationError(f"{row_hint}：range 的 min/max 必须是整数")
    return result


# --- Edge strategy encoders/decoders ---

def format_edge_strategy_row(strategy: dict) -> str:
    """把一个 edge_strategy dict 序列化成 '源组名|目标|目标类型|边类型|模式|K' 行。"""
    k_str = "" if strategy.get("ratio_k") is None else str(strategy["ratio_k"])
    return FIELD_SEP.join([
        strategy["source_group_name"],
        strategy["target_name"],
        strategy["target_kind"],
        strategy["edge_type_code"],
        strategy["mode"],
        k_str,
    ])


def parse_edge_strategy_row(line: str, row_hint: str) -> dict:
    parts = line.split(FIELD_SEP)
    if len(parts) < 6:
        raise ExcelValidationError(
            f"{row_hint}：边策略字段数 {len(parts)} 不足 6（源组名|目标|目标类型|边类型|模式|K）"
        )
    if len(parts) > 6:
        raise ExcelValidationError(
            f"{row_hint}：边策略字段数 {len(parts)} 超过 6"
        )
    src, tgt, kind, etype, mode, k_str = [p.strip() for p in parts]
    if kind not in ALLOWED_TARGET_KIND:
        raise ExcelValidationError(
            f"{row_hint}：目标类型 '{kind}' 不合法（应为 组/节点）"
        )
    if mode not in ALLOWED_MODE:
        raise ExcelValidationError(
            f"{row_hint}：边策略模式 '{mode}' 不合法（允许 {sorted(ALLOWED_MODE)}）"
        )
    ratio_k: Optional[int] = None
    if k_str:
        try:
            ratio_k = int(k_str)
        except ValueError:
            raise ExcelValidationError(f"{row_hint}：K 值 '{k_str}' 必须是整数")
    if mode in ("modulo", "one_to_n") and ratio_k is None:
        raise ExcelValidationError(
            f"{row_hint}：{mode} 模式必须提供 K"
        )
    return {
        "source_group_name": src,
        "target_name": tgt,
        "target_kind": kind,
        "edge_type_code": etype,
        "mode": mode,
        "ratio_k": ratio_k,
    }
