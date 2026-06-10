"""TC3-6 Browser Test: Directory Delete (Clear Directory)"""
import asyncio
from playwright.async_api import async_playwright

BASE = "http://localhost:5173"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})

        # Navigate to API management page
        print("[Step 0] Navigate to API management page...")
        await page.goto(f"{BASE}/apis")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # Take screenshot of initial state
        await page.screenshot(path="tc36_step0_initial.png")
        print("[Step 0] Screenshot saved: tc36_step0_initial.png")

        # Step 1: Verify "ManageOne" directory exists with 3 APIs
        print("[Step 1] Looking for ManageOne directory...")
        # Find the directory header containing "ManageOne"
        manage_header = page.locator(".domain-group-header", has_text="ManageOne")
        header_count = await manage_header.count()
        print(f"  Found {header_count} ManageOne directory header(s)")

        if header_count > 0:
            header_text = await manage_header.first.inner_text()
            print(f"  Header text: {header_text}")

            # Verify buttons: [ExportOutlined], [+], [DeleteOutlined]
            buttons = manage_header.first.locator("button")
            btn_count = await buttons.count()
            print(f"  Button count in header: {btn_count}")
        else:
            print("  [WARN] ManageOne directory not found, checking all groups...")
            all_headers = page.locator(".domain-group-header")
            for i in range(await all_headers.count()):
                txt = await all_headers.nth(i).inner_text()
                print(f"    Group {i}: {txt}")

        await page.screenshot(path="tc36_step1_directory.png")
        print("[Step 1] Screenshot saved: tc36_step1_directory.png")

        # Step 2: Expand the directory first (click header to toggle)
        print("[Step 2] Expanding ManageOne directory...")
        if header_count > 0:
            arrow = manage_header.first.locator(".group-arrow")
            arrow_text = await arrow.inner_text()
            print(f"  Arrow state: {arrow_text}")
            if arrow_text == "▶":
                await manage_header.first.click()
                await asyncio.sleep(0.5)
                print("  Clicked to expand")

        await page.screenshot(path="tc36_step2_expanded.png")
        print("[Step 2] Screenshot saved: tc36_step2_expanded.png")

        # Step 3: Click the trash button to show Popconfirm
        print("[Step 3] Clicking trash button...")
        if header_count > 0:
            # The trash button is the last button in the header (DeleteOutlined)
            trash_btn = manage_header.first.locator("button").last
            await trash_btn.click()
            await asyncio.sleep(1)

            await page.screenshot(path="tc36_step3_popconfirm.png")
            print("[Step 3] Screenshot saved: tc36_step3_popconfirm.png")

            # Check if Popconfirm appeared
            popconfirm = page.locator(".ant-popover")
            pop_count = await popconfirm.count()
            print(f"  Popconfirm visible: {pop_count > 0}")

            if pop_count > 0:
                pop_text = await popconfirm.first.inner_text()
                print(f"  Popconfirm text: {pop_text[:100]}")

            # Step 4: Click cancel first
            print("[Step 4] Clicking cancel...")
            cancel_btn = page.locator(".ant-popover .ant-btn:not(.ant-btn-primary)")
            if await cancel_btn.count() > 0:
                await cancel_btn.first.click()
                await asyncio.sleep(0.5)
                print("  Cancel clicked")

            await page.screenshot(path="tc36_step4_after_cancel.png")
            print("[Step 4] Screenshot saved: tc36_step4_after_cancel.png")

            # Verify directory still has APIs (header should still show count)
            header_text_after = await manage_header.first.inner_text()
            print(f"  Header after cancel: {header_text_after}")

            # Step 5: Click trash again, then confirm
            print("[Step 5] Clicking trash button again...")
            await trash_btn.click()
            await asyncio.sleep(1)

            print("  Clicking confirm...")
            confirm_btn = page.locator(".ant-popover .ant-btn-primary")
            if await confirm_btn.count() > 0:
                await confirm_btn.first.click()
                await asyncio.sleep(2)  # Wait for API call + refresh

            await page.screenshot(path="tc36_step5_after_confirm.png")
            print("[Step 5] Screenshot saved: tc36_step5_after_confirm.png")

            # Check success message
            msg = page.locator(".ant-message-success")
            if await msg.count() > 0:
                msg_text = await msg.first.inner_text()
                print(f"  Success message: {msg_text}")

            # Verify ManageOne directory now shows 0
            header_text_final = await manage_header.first.inner_text()
            print(f"  ManageOne header after clear: {header_text_final}")

            # Step 6: Check "未归类" directory has the APIs and no trash button
            print("[Step 6] Checking '未归类' directory...")
            unclassified = page.locator(".domain-group-header", has_text="未归类")
            if await unclassified.count() > 0:
                unclass_text = await unclassified.first.inner_text()
                print(f"  未归类 header: {unclass_text}")

                # Check buttons in 未归类 - should have no trash
                unclass_buttons = unclassified.first.locator("button")
                unclass_btn_count = await unclass_buttons.count()
                print(f"  Button count in 未归类: {unclass_btn_count}")

                # Expand to see the APIs
                unclass_arrow = unclassified.first.locator(".group-arrow")
                if await unclass_arrow.count() > 0:
                    arrow_txt = await unclass_arrow.inner_text()
                    if arrow_txt == "▶":
                        await unclassified.first.click()
                        await asyncio.sleep(0.5)

            await page.screenshot(path="tc36_step6_unclassified.png")
            print("[Step 6] Screenshot saved: tc36_step6_unclassified.png")

        # Final full page screenshot
        await page.screenshot(path="tc36_final.png", full_page=True)
        print("\n[Done] Final screenshot saved: tc36_final.png")

        await browser.close()


asyncio.run(main())
