from playwright.sync_api import sync_playwright

MENU_ITEMS = ["仪表盘", "拓扑", "类型管理", "接口", "Token", "请求日志", "系统设置"]


def main():
    errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Capture console errors
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # 1. Load index
        page.goto("http://localhost:5173/")
        page.wait_for_load_state("networkidle")

        # 2. Check sidebar brand
        brand = page.locator(".brand")
        if not brand.is_visible():
            errors.append("❌ Brand '网管接口模拟' not visible")
        elif "网管" not in brand.text_content():
            errors.append(f"❌ Brand text unexpected: {brand.text_content()}")
        else:
            print("✅ Brand visible")

        # 3. Check all 7 menu items
        menu = page.locator(".ant-menu")
        if not menu.is_visible():
            errors.append("❌ Sidebar menu not visible")
        else:
            for item in MENU_ITEMS:
                mi = page.locator(f"span:text('{item}')")
                if mi.count() == 0:
                    errors.append(f"❌ Menu item '{item}' not found")
                else:
                    print(f"✅ Menu item: {item}")

        # 4. Click each menu item and verify navigation
        for item in MENU_ITEMS:
            mi = page.locator(f".ant-menu-item:has-text('{item}')")
            if mi.count() > 0:
                mi.first.click()
                page.wait_for_load_state("networkidle")
                # Check page title in header
                title = page.locator(".page-title")
                if title.count() > 0:
                    print(f"✅ Navigated to {item}, header: {title.text_content()}")

        # 5. Proxy health check (via Vite dev server)
        resp = page.request.get("http://localhost:5173/admin/api/health")
        body = resp.json()
        if resp.status != 200:
            errors.append(f"❌ Proxy health status {resp.status}")
        elif body.get("code") != 0:
            errors.append(f"❌ Proxy health code {body.get('code')}, expected 0")
        else:
            print(f"✅ Proxy /admin/api/health → {body}")

        # 6. Report console errors
        if console_errors:
            errors.append(f"❌ Console errors: {console_errors}")
        else:
            print("✅ No console errors")

        browser.close()

    if errors:
        print("\n--- FAILURES ---")
        for e in errors:
            print(e)
        raise SystemExit(1)
    else:
        print("\n✅ All checks passed")


if __name__ == "__main__":
    main()
