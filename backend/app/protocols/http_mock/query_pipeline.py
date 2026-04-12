"""Query pipeline: SQL mode and Static mode data processing."""

import json
import re
import uuid
import random
import string
from datetime import datetime

from loguru import logger

from app.dal.memory_store import MemoryStore


class QueryPipeline:
    """Executes data queries based on API config data source settings."""

    def __init__(self, memory: MemoryStore):
        self._memory = memory

    async def execute(self, config: dict, params: dict) -> dict:
        """Execute query based on config and request params. Returns query result dict."""
        ds = config.get("data_source", "{}")
        if isinstance(ds, str):
            ds = json.loads(ds)

        ds_type = ds.get("type", "sql")
        if ds_type == "static":
            return self._execute_static(ds)
        else:
            return await self._execute_sql(config, params)

    @staticmethod
    def _execute_static(data_source: dict) -> dict:
        """Static mode: return body with placeholder replacement."""
        body = data_source.get("body", {})
        body_str = json.dumps(body, ensure_ascii=False)

        # Replace placeholders
        body_str = re.sub(r'\{\{uuid\}\}', lambda _: uuid.uuid4().hex, body_str)
        body_str = re.sub(r'\{\{random\}\}', lambda _: ''.join(random.choices(string.ascii_letters + string.digits, k=16)), body_str)
        body_str = re.sub(r'\{\{timestamp\}\}', lambda _: str(int(datetime.now().timestamp())), body_str)
        body_str = re.sub(r'\{\{date\}\}', lambda _: datetime.now().strftime('%Y-%m-%d'), body_str)

        try:
            rendered = json.loads(body_str)
        except json.JSONDecodeError:
            rendered = body_str

        return {"renderedResponse": rendered}

    async def _execute_sql(self, config: dict, params: dict) -> dict:
        """SQL mode: bind params, paginate, execute."""
        ds = config.get("data_source", "{}")
        if isinstance(ds, str):
            ds = json.loads(ds)
        sql = ds.get("sql", "")

        query_cfg = config.get("query", "{}")
        if isinstance(query_cfg, str):
            query_cfg = json.loads(query_cfg)

        param_defs = query_cfg.get("params", [])
        pagination = query_cfg.get("pagination", {})
        pagination_enabled = pagination.get("enabled", False)

        # Build SQL params from request params + param definitions
        sql_params = {}
        for pd in param_defs:
            url_param = pd.get("param", "")
            sql_param = pd.get("sqlParam", f":{url_param}").lstrip(":")
            value = params.get(url_param, pd.get("default"))
            sql_params[sql_param] = value

        total = None
        page_no = None
        page_size = None

        if pagination_enabled:
            page_no_param = pagination.get("pageNoParam", "pageNo")
            page_size_param = pagination.get("pageSizeParam", "pageSize")
            default_page_size = pagination.get("defaultPageSize", 100)

            page_no = int(params.get(page_no_param, 1))
            page_size = int(params.get(page_size_param, default_page_size))
            offset = (page_no - 1) * page_size

            # Count query
            count_sql = f"SELECT COUNT(*) as cnt FROM ({sql})"
            try:
                total = await self._memory.execute_count(count_sql, sql_params)
            except Exception as e:
                logger.warning(f"QueryPipeline: count query failed: {e}")
                total = 0

            # Paginated query
            paginated_sql = f"{sql} LIMIT :__pageSize OFFSET :__offset"
            sql_params["__pageSize"] = page_size
            sql_params["__offset"] = offset
            executed_sql = paginated_sql
        else:
            executed_sql = sql

        # Execute
        try:
            columns, rows = await self._memory.execute_sql(executed_sql, sql_params)
            # Convert rows to dicts
            items = [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"QueryPipeline: SQL execution failed: {e}")
            return {"error": str(e), "executedSql": executed_sql}

        query_result = {"items": items}
        if total is not None:
            query_result["total"] = total
        if page_no is not None:
            query_result["pageNo"] = page_no
        if page_size is not None:
            query_result["pageSize"] = page_size

        return {"executedSql": executed_sql, "queryResult": query_result}
