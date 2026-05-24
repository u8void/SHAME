"""
browser_agent.py — Selenium Browser Automation for Iris AI
===========================================================
"""

import json
import time

def _make_driver(headless: bool = False):
    """
    Return a configured Chrome WebDriver.
    Selenium Manager (bundled since selenium 4.6) downloads ChromeDriver
    automatically — no manual setup required.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    
    import os
    profile_dir = os.path.join(os.path.dirname(__file__), "browser_profile")
    opts.add_argument(f"--user-data-dir={profile_dir}")
    opts.add_argument("--profile-directory=Default")
    
    if headless:
        opts.add_argument("--headless=new")

    # Reduce bot-detection fingerprint
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    try:
        driver = webdriver.Chrome(options=opts)
    except Exception:
        # Fallback: try webdriver-manager if installed
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=opts,
            )
        except Exception as e:
            raise RuntimeError(
                f"Could not start Chrome WebDriver: {e}\n"
                "Make sure Google Chrome is installed and run:\n"
                "  pip install selenium"
            )

    driver.implicitly_wait(6)
    return driver

def _page_snapshot(driver) -> dict:
    """
    Return a lightweight JSON snapshot of the page using JavaScript DOM traversal.
    This handles Shadow DOMs and assigns a unique 'data-iris-id' to every interactable element.
    """
    js_code = """
    window.findIrisElement = function(id) {
        function search(root) {
            let el = root.querySelector('[data-iris-id="' + id + '"]');
            if (el) return el;
            for (let child of root.querySelectorAll('*')) {
                if (child.shadowRoot) {
                    let found = search(child.shadowRoot);
                    if (found) return found;
                }
            }
            return null;
        }
        return search(document);
    };

    function extractDOM() {
        let irisIdCounter = 1;
        const items = [];
        
        function isVisible(el) {
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden';
        }
        
        const interactableSelectors = 'a, button, input, textarea, select, [role="button"], [role="link"], [tabindex]:not([tabindex="-1"])';
        
        function traverse(root) {
            const elements = root.querySelectorAll(interactableSelectors);
            for (let el of elements) {
                if (!isVisible(el)) continue;
                
                let id = el.getAttribute('data-iris-id');
                if (!id) {
                    id = irisIdCounter++;
                    el.setAttribute('data-iris-id', id);
                }
                
                const tag = el.tagName.toLowerCase();
                let text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim();
                if (text.length > 50) text = text.substring(0, 47) + '...';
                
                let obj = { id: parseInt(id), tag: tag };
                if (text) obj.text = text;
                
                const type = el.getAttribute('type');
                if (type) obj.type = type;
                
                const name = el.getAttribute('name');
                if (name) obj.name = name;
                
                if (text || tag === 'input' || tag === 'textarea' || tag === 'select') {
                    items.push(obj);
                }
            }
            
            for (let el of root.querySelectorAll('*')) {
                if (el.shadowRoot) traverse(el.shadowRoot);
            }
        }
        
        traverse(document);
        return items;
    }
    return extractDOM();
    """
    
    try:
        elements = driver.execute_script(js_code)
        return {
            "title": driver.title,
            "url": driver.current_url,
            "elements": elements
        }
    except Exception as e:
        print(f"  [Browser] Warning: JS DOM extraction failed: {e}")
        return {"title": driver.title, "url": driver.current_url, "elements": []}


_USERNAME_SELECTORS = [
    "input[autocomplete='username']",
    "input[autocomplete='email']",
    "input[type='email']",
    "input[name='email']",
    "input[name='username']",
    "input[name='login']",
    "input[name='user']",
    "input[id*='email']",
    "input[id*='user']",
    "input[placeholder*='email' i]",
    "input[placeholder*='username' i]",
    "input[type='text']",   # broad fallback
]

_PASSWORD_SELECTORS = [
    "input[type='password']",
    "input[autocomplete='current-password']",
    "input[name='password']",
    "input[name='pass']",
]

_SUBMIT_SELECTORS = [
    "button[type='submit']",
    "input[type='submit']",
    "button[id*='login' i]",
    "button[id*='signin' i]",
]


def _find_first(driver, css_list):
    """Return the first visible element matching any selector in the list."""
    from selenium.webdriver.common.by import By

    for css in css_list:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, css)
            for el in els:
                if el.is_displayed() and el.is_enabled():
                    return el
        except Exception:
            pass
    return None


def browser_login(url: str, username: str, password: str, model=None, tokenizer=None, device=None) -> str:
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver = _make_driver(headless=False)
    
    # SSO fast path delegation
    sso_providers = ["google", "apple", "github", "facebook", "microsoft"]
    if username.lower() in sso_providers and not password and model is not None:
        print(f"  [Browser] SSO Login detected ({username}). Delegating to AI task...")
        return browser_task(url, f"Log into this page using the 'Continue with {username}' button.", model, tokenizer, device, existing_driver=driver)

    try:
        print(f"  [Browser] Navigating to {url}")
        driver.get(url)
        time.sleep(2.5)

        # ── Step 1: fill username ────────────────────────────────────────────
        user_el = _find_first(driver, _USERNAME_SELECTORS)
        if not user_el:
            if model is not None:
                print("  [Browser] CSS selectors failed. Delegating to AI task...")
                return browser_task("", f"Log into this page using username '{username}' and password '{password}'.", model, tokenizer, device, existing_driver=driver)
            return (
                "⚠️ Could not find a username / email field on that page.\n"
                "The browser is open — you can log in manually."
            )
        user_el.clear()
        user_el.send_keys(username)
        print(f"  [Browser] Filled username field.")

        # ── Step 2: look for password on same page ───────────────────────────
        pass_el = _find_first(driver, _PASSWORD_SELECTORS)

        if not pass_el:
            # Two-step flow: submit username first
            print("  [Browser] Password field not visible yet — submitting username.")
            sub_el = _find_first(driver, _SUBMIT_SELECTORS)
            if sub_el:
                sub_el.click()
            else:
                user_el.send_keys(Keys.RETURN)

            # Wait up to 8 s for password field to appear
            try:
                WebDriverWait(driver, 8).until(
                    EC.visibility_of_element_located(
                        (By.CSS_SELECTOR, "input[type='password']")
                    )
                )
            except Exception:
                pass
            pass_el = _find_first(driver, _PASSWORD_SELECTORS)

        if not pass_el:
            if model is not None:
                print("  [Browser] Password selector failed. Delegating to AI task...")
                return browser_task("", f"Find the password field, fill it with '{password}' and submit.", model, tokenizer, device, existing_driver=driver)
            return (
                "⚠️ Could not find a password field after submitting your username.\n"
                "The browser is open — please complete the login manually."
            )

        # ── Step 3: fill password and submit ────────────────────────────────
        pass_el.clear()
        pass_el.send_keys(password)
        print("  [Browser] Filled password field.")

        sub_el = _find_first(driver, _SUBMIT_SELECTORS)
        if sub_el:
            sub_el.click()
        else:
            pass_el.send_keys(Keys.RETURN)

        time.sleep(3)
        new_title = driver.title
        print(f"  [Browser] After login → '{new_title}'")

        return (
            f"✅ Login submitted on **{url}**.\n"
            f"Current page: **{new_title}**\n\n"
            "The browser is open — check if you're logged in.\n"
            "If 2FA or a CAPTCHA appeared, please complete it manually."
        )

    except Exception as exc:
        try:
            driver.quit()
        except Exception:
            pass
        return f"❌ Login automation failed: {exc}"

    # Intentionally NOT calling driver.quit() — keep the browser open.


# ── Generic browser task ───────────────────────────────────────────────────────

def browser_task(url: str, task: str, model=None, tokenizer=None, device=None, existing_driver=None) -> str:
    """
    Open *url* in a visible Chrome window and execute an arbitrary *task*
    using AI-generated Selenium code.

    Flow
    ----
    1. Navigate to the URL.
    2. Take a page snapshot (inputs, buttons, links, title).
    3. Ask the Iris model to write Selenium code for the task.
    4. Execute the generated code inside the live browser session.
    5. Return a status message; browser stays open.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.keys import Keys

    driver = existing_driver if existing_driver else _make_driver(headless=False)

    try:
        if url:
            print(f"  [Browser] Navigating to {url}")
            driver.get(url)
            time.sleep(2.5)

        snapshot = _page_snapshot(driver)
        print(f"  [Browser] Page: {snapshot['title']}")

        # ── Generate Selenium code via Iris ──────────────────────────────────
        if model is not None and tokenizer is not None:
            from iris import generate_reply

            code_prompt = f"""You are a Selenium automation expert writing Python code.

The Selenium WebDriver is already running. You have access to `driver` (a Chrome instance).
Also pre-imported: By, WebDriverWait, EC, Keys, time.

We have injected a JS script that assigns a unique `data-iris-id` (an integer) to all interactable elements (including inside Shadow DOMs).
You have access to two powerful helper functions in your environment:
1. `click_element(iris_id)` - Scrolls to and clicks the element with the given ID.
2. `fill_element(iris_id, text)` - Scrolls to, clears, and types `text` into the element with the given ID.

Current page snapshot (JSON list of interactable elements):
{json.dumps(snapshot.get('elements', []), indent=2, ensure_ascii=False)}

Task to complete: {task}

Rules:
- PREFER using `click_element(id)` and `fill_element(id, text)` based on the IDs in the snapshot. This is much safer than writing CSS selectors!
- If the task requires multiple steps (like searching then clicking a result), use `time.sleep(3)` after clicking to allow the page or popup to load before interacting with the next element.
- Do NOT create a new driver or call driver.quit().
- print() a one-line summary of what happened at the very end.
- Output ONLY raw Python code. No markdown, no explanation.
"""
            raw_code = generate_reply(
                model, tokenizer, code_prompt, device, max_new_tokens=512
            )
            # Strip any accidental markdown fences
            raw_code = raw_code.strip()
            if raw_code.startswith("```"):
                raw_code = "\n".join(raw_code.split("\n")[1:])
            if raw_code.endswith("```"):
                raw_code = "\n".join(raw_code.split("\n")[:-1])
        else:
            # No model — fall back to a simple "just navigate" result
            return (
                f"Opened **{snapshot['title']}** at {url}.\n"
                "No AI model available to automate further steps — "
                "the browser is open for manual use."
            )

        # ── Execute the generated code inside the live session ───────────────
        import io
        from contextlib import redirect_stdout

        def click_element(iris_id):
            el = driver.execute_script(f"return window.findIrisElement('{iris_id}')")
            if el:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                time.sleep(0.5)
                el.click()
            else:
                raise Exception(f"Element with iris_id {iris_id} not found")

        def fill_element(iris_id, text):
            el = driver.execute_script(f"return window.findIrisElement('{iris_id}')")
            if el:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                time.sleep(0.5)
                el.clear()
                el.send_keys(text)
            else:
                raise Exception(f"Element with iris_id {iris_id} not found")

        exec_env = {
            "driver": driver,
            "By": By,
            "WebDriverWait": WebDriverWait,
            "EC": EC,
            "Keys": Keys,
            "time": time,
            "json": json,
            "click_element": click_element,
            "fill_element": fill_element,
        }

        captured = io.StringIO()
        try:
            with redirect_stdout(captured):
                exec(raw_code, exec_env)   # noqa: S102
            output = captured.getvalue().strip()
            time.sleep(1.5)
            final_title = driver.title

            result = (
                f"✅ Browser task complete on **{url}**.\n"
                f"Final page: **{final_title}**"
            )
            if output:
                result += f"\n\nAutomation log:\n```\n{output}\n```"
            result += "\n\nThe browser is open — check the result."
            return result

        except Exception as exec_err:
            time.sleep(1)
            return (
                f"⚠️ Automation partially failed: {exec_err}\n\n"
                f"Generated code that was attempted:\n```python\n{raw_code}\n```\n\n"
                "The browser is open — you can complete the task manually."
            )

    except Exception as exc:
        try:
            driver.quit()
        except Exception:
            pass
        return f"❌ Browser task failed: {exc}"

    # Intentionally NOT calling driver.quit() — keep browser open.
