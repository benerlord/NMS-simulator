import sys
sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

    # Navigate to topology page
    page.goto("http://localhost:5174/topologies")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # Click first "进入画布" button
    page.locator("text=进入画布").first.click()
    page.wait_for_timeout(3000)  # longer wait to check for auto-shrink

    # Verify navigated to canvas page
    assert "/canvas" in page.url, f"Expected /canvas in URL, got {page.url}"
    print(f"[PASS] Navigated to canvas: {page.url}")

    # Check canvas page elements
    content = page.content()
    assert "拓扑画布" in content, "Page title not found"
    print("[PASS] Canvas page title found")

    assert page.locator(".canvas-toolbar").count() > 0, "Toolbar not found"
    print("[PASS] Canvas toolbar found")

    # Check canvas SVG has non-zero dimensions (auto-shrink bug would cause collapse)
    svg = page.locator(".topology-canvas svg")
    assert svg.count() > 0, "Canvas SVG not found"
    bbox = svg.first.bounding_box()
    assert bbox and bbox['width'] > 0 and bbox['height'] > 0, f"Canvas SVG has zero dimensions: {bbox}"
    print(f"[PASS] Canvas SVG rendered with size {bbox['width']:.0f}x{bbox['height']:.0f}")

    critical_errors = [e for e in errors if "Error" in e or "error" in e]
    if critical_errors:
        print(f"[WARN] Console errors: {critical_errors}")
    else:
        print("[PASS] No console errors")

    browser.close()
    print("\n[ALL TESTS PASSED]")
