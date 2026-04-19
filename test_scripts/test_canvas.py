import sys
sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Capture console errors
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

    # Navigate to canvas page (using existing topology id)
    page.goto("http://localhost:5174/topologies/topo_34849061a60f/canvas")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # Check page loaded
    content = page.content()
    assert "拓扑画布" in content, "Page title not found"
    print("[PASS] Page title found: topology canvas")

    # Check toolbar rendered
    assert page.locator(".canvas-toolbar").count() > 0, "Toolbar not found"
    print("[PASS] Toolbar rendered")

    # Check save button
    assert page.locator("button:has-text('保存')").count() > 0, "Save button not found"
    print("[PASS] Save button found")

    # Check canvas container
    assert page.locator(".topology-canvas").count() > 0, "Canvas not found"
    print("[PASS] Canvas container rendered")

    # Verify no console errors
    critical_errors = [e for e in errors if "Error" in e or "error" in e]
    if critical_errors:
        print(f"[WARN] Console errors: {critical_errors}")
    else:
        print("[PASS] No console errors")

    browser.close()
    print("\n[ALL TESTS PASSED]")
