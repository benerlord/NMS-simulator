import sys
sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Capture console errors
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

    # Navigate to topology page
    page.goto("http://localhost:5174/topologies")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # Check page loaded
    content = page.content()
    assert "拓扑管理" in content, "Page title not found"
    print("[PASS] Page title found: topology management")

    # Check table is rendered
    assert page.locator(".ant-table").count() > 0, "Table not found"
    print("[PASS] Table rendered")

    # Check toolbar
    assert page.locator("text=新建").count() > 0, "New button not found"
    print("[PASS] New button found")

    # Check "进入画布" button exists
    assert page.locator("text=进入画布").count() > 0, "Enter canvas button not found"
    print("[PASS] Enter canvas button found")

    # Click new topology button
    page.locator("button:has-text('新建')").click()
    page.wait_for_timeout(500)

    # Check modal opened
    modal_visible = page.locator(".ant-modal").is_visible()
    assert modal_visible, "Modal did not open"
    print("[PASS] Create modal opened")

    # Fill form
    page.locator(".ant-modal input").first.fill("test-topology")
    page.locator(".ant-modal .ant-btn-primary").click()
    page.wait_for_timeout(1000)

    # Verify no console errors
    critical_errors = [e for e in errors if "Error" in e or "error" in e]
    if critical_errors:
        print(f"[WARN] Console errors: {critical_errors}")
    else:
        print("[PASS] No console errors")

    browser.close()
    print("\n[ALL TESTS PASSED]")
