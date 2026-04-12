"""Playwright test for Phase 7-8 frontend pages."""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:3002"

def test_pages():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        errors = []

        # 1. Dashboard
        print("Testing Dashboard...")
        page.goto(f"{BASE}/dashboard")
        page.wait_for_load_state("networkidle")
        page.screenshot(path="/tmp/dashboard.png", full_page=True)
        if page.locator("text=仪表盘").count() == 0:
            errors.append("Dashboard: title not found")
        else:
            print("  OK - Dashboard loaded")

        # 2. API Config page
        print("Testing API Config...")
        page.goto(f"{BASE}/api-config")
        page.wait_for_load_state("networkidle")
        page.screenshot(path="/tmp/api_config.png", full_page=True)
        if page.locator("text=HTTP 接口配置").count() == 0:
            errors.append("ApiConfig: title not found")
        else:
            print("  OK - API Config loaded")

        # Check for table
        if page.locator("table").count() > 0:
            print("  OK - Table present")

        # Check new button
        if page.locator("text=新建").count() > 0:
            print("  OK - New button present")

        # 3. Click new button to open drawer
        print("Testing Create Config drawer...")
        page.locator("text=新建").first.click()
        page.wait_for_timeout(500)
        page.screenshot(path="/tmp/api_config_new.png", full_page=True)
        if page.locator("text=基本信息").count() > 0:
            print("  OK - Config form opened with tabs")

        # Close drawer
        page.locator(".ant-drawer-close").first.click()
        page.wait_for_timeout(300)

        # 4. Data Viewer
        print("Testing Data Viewer...")
        page.goto(f"{BASE}/data")
        page.wait_for_load_state("networkidle")
        page.screenshot(path="/tmp/data_viewer.png", full_page=True)
        if page.locator("text=数据查看").count() == 0:
            errors.append("DataViewer: title not found")
        else:
            print("  OK - Data Viewer loaded")

        # Check tabs
        tabs = ["设备", "告警", "指标"]
        for tab in tabs:
            if page.locator(f"text={tab}").count() > 0:
                print(f"  OK - Tab '{tab}' present")

        # 5. Log Viewer
        print("Testing Log Viewer...")
        page.goto(f"{BASE}/logs")
        page.wait_for_load_state("networkidle")
        page.screenshot(path="/tmp/log_viewer.png", full_page=True)
        if page.locator("text=请求日志").count() == 0:
            errors.append("LogViewer: title not found")
        else:
            print("  OK - Log Viewer loaded")

        # 6. Settings page
        print("Testing Settings...")
        page.goto(f"{BASE}/settings")
        page.wait_for_load_state("networkidle")
        page.screenshot(path="/tmp/settings.png", full_page=True)
        if page.locator("text=系统设置").count() == 0:
            errors.append("Settings: title not found")
        else:
            print("  OK - Settings loaded")

        # Check settings tabs
        settings_tabs = ["协议管理", "Token 管理"]
        for tab in settings_tabs:
            if page.locator(f"text={tab}").count() > 0:
                print(f"  OK - Tab '{tab}' present")

        # Click Protocol Management tab
        print("Testing Protocol Management tab...")
        page.locator("text=协议管理").first.click()
        page.wait_for_timeout(500)
        page.screenshot(path="/tmp/settings_protocols.png", full_page=True)
        if page.locator("text=HTTP Mock").count() > 0 or page.locator("text=http-mock").count() > 0:
            print("  OK - Protocol cards loaded")

        # Click Token Management tab
        print("Testing Token Management tab...")
        page.locator("text=Token 管理").first.click()
        page.wait_for_timeout(500)
        page.screenshot(path="/tmp/settings_tokens.png", full_page=True)
        if page.locator("text=认证配置").count() > 0:
            print("  OK - Token management loaded")

        # 7. Navigation test - sidebar
        print("Testing sidebar navigation...")
        nav_items = {
            "/dashboard": "仪表盘",
            "/api-config": "HTTP 接口配置",
            "/data": "数据查看",
            "/logs": "日志查看",
            "/settings": "系统设置",
        }
        for path, label in nav_items.items():
            page.goto(f"{BASE}{path}")
            page.wait_for_load_state("networkidle")
            # Just verify no crash
            print(f"  OK - {label} ({path}) navigable")

        browser.close()

        if errors:
            print(f"\nFAILED with {len(errors)} errors:")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        else:
            print("\nAll Phase 7-8 tests passed!")

if __name__ == "__main__":
    test_pages()
