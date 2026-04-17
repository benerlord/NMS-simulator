import sqlite3

NODE_TYPES: list[dict] = [
    {"code": "switch",     "name": "交换机",       "category": "physical",    "render_mode": "none",
     "fields": [("vendor", "厂商"), ("model", "型号"), ("ip", "IP")]},
    {"code": "router",     "name": "路由器",       "category": "physical",    "render_mode": "none",
     "fields": [("vendor", "厂商"), ("model", "型号"), ("ip", "IP")]},
    {"code": "server",     "name": "服务器",       "category": "physical",    "render_mode": "none",
     "fields": [("vendor", "厂商"), ("model", "型号"), ("ip", "IP")]},
    {"code": "firewall",   "name": "防火墙",       "category": "physical",    "render_mode": "none",
     "fields": [("vendor", "厂商"), ("model", "型号"), ("ip", "IP")]},
    {"code": "port",       "name": "端口",         "category": "physical",    "render_mode": "flat",
     "fields": [("type", "类型"), ("speed", "速率")]},
    {"code": "hypervisor", "name": "宿主机",       "category": "cloud",       "render_mode": "none",
     "fields": [("cpu", "CPU"), ("memory", "内存")]},
    {"code": "vm",         "name": "虚拟机",       "category": "cloud",       "render_mode": "flat",
     "fields": [("cpu", "CPU"), ("memory", "内存"), ("os", "操作系统")]},
    {"code": "ecs",        "name": "弹性云服务器", "category": "cloud",       "render_mode": "none",
     "fields": [("flavor", "规格"), ("zone", "可用区")]},
    {"code": "pod",        "name": "Pod",          "category": "application", "render_mode": "none",
     "fields": [("namespace", "命名空间")]},
    {"code": "container",  "name": "容器",         "category": "application", "render_mode": "flat",
     "fields": [("image", "镜像")]},
    {"code": "app",        "name": "应用",         "category": "application", "render_mode": "none",
     "fields": [("version", "版本")]},
]

EDGE_TYPES: list[dict] = [
    {"code": "contains",      "name": "包含",     "semantic": "contain", "exclusive_target": 1, "line_style": "solid"},
    {"code": "physical_link", "name": "物理链路", "semantic": "connect", "exclusive_target": 0, "line_style": "solid"},
    {"code": "deployed_on",   "name": "部署于",   "semantic": "connect", "exclusive_target": 0, "line_style": "dashed"},
    {"code": "depends_on",    "name": "依赖",     "semantic": "connect", "exclusive_target": 0, "line_style": "dotted"},
    {"code": "connects",      "name": "连接",     "semantic": "connect", "exclusive_target": 0, "line_style": "solid"},
]

PRESET_SETTINGS: list[tuple[str, str]] = [
    ("autosave_interval", "60"),
    ("request_log_max", "10000"),
    ("mock_path_prefix", "/mock"),
]


def _seed_node_types(conn: sqlite3.Connection) -> None:
    for nt in NODE_TYPES:
        nt_id = f"nt_{nt['code']}"
        conn.execute(
            "INSERT OR IGNORE INTO node_types (id, code, name, category, render_mode) "
            "VALUES (?, ?, ?, ?, ?)",
            (nt_id, nt["code"], nt["name"], nt["category"], nt["render_mode"]),
        )
        for order, (key, label) in enumerate(nt["fields"]):
            conn.execute(
                "INSERT OR IGNORE INTO node_type_fields "
                "(node_type_id, field_key, field_label, field_type, sort_order) "
                "VALUES (?, ?, ?, 'text', ?)",
                (nt_id, key, label, order),
            )


def _seed_edge_types(conn: sqlite3.Connection) -> None:
    for et in EDGE_TYPES:
        conn.execute(
            "INSERT OR IGNORE INTO edge_types "
            "(id, code, name, semantic, exclusive_target, line_style) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (f"et_{et['code']}", et["code"], et["name"], et["semantic"],
             et["exclusive_target"], et["line_style"]),
        )


def _seed_settings(conn: sqlite3.Connection) -> None:
    for key, value in PRESET_SETTINGS:
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


def run_seed(conn: sqlite3.Connection) -> None:
    _seed_node_types(conn)
    _seed_edge_types(conn)
    _seed_settings(conn)
