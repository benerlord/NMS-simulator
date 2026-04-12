"""Response template renderer."""

import json
import re


class ResponseRenderer:
    """Renders query results into response templates."""

    def render(self, config: dict, query_result: dict) -> tuple[dict | str, str]:
        """Render query result into response template.

        Returns (rendered_body, content_type).
        """
        resp_cfg = config.get("response", "{}")
        if isinstance(resp_cfg, str):
            resp_cfg = json.loads(resp_cfg)

        content_type = resp_cfg.get("contentType", "application/json")
        template = resp_cfg.get("template", {})

        if not template:
            # No template, return query result directly
            qr = query_result.get("queryResult", query_result)
            return qr, content_type

        items = query_result.get("queryResult", {}).get("items", [])
        total = query_result.get("queryResult", {}).get("total", len(items))
        page_no = query_result.get("queryResult", {}).get("pageNo", 1)
        page_size = query_result.get("queryResult", {}).get("pageSize", len(items))

        # Serialize template to string for placeholder replacement
        tmpl_str = json.dumps(template, ensure_ascii=False)

        # Replace placeholders: "{{items}}" -> actual array, "{{total}}" -> number, etc.
        # We use a two-pass approach: first replace quoted placeholders with actual JSON values
        tmpl_str = re.sub(r'"?\{\{items\}\}"?', json.dumps(items, ensure_ascii=False), tmpl_str)
        tmpl_str = re.sub(r'"?\{\{total\}\}"?', str(total), tmpl_str)
        tmpl_str = re.sub(r'"?\{\{pageNo\}\}"?', str(page_no), tmpl_str)
        tmpl_str = re.sub(r'"?\{\{pageSize\}\}"?', str(page_size), tmpl_str)

        try:
            rendered = json.loads(tmpl_str)
        except json.JSONDecodeError:
            rendered = tmpl_str

        return rendered, content_type
