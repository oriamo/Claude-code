#!/usr/bin/env python3
"""
Tesla Model 3 Browser Scanner

Opens a real visible Chrome window, navigates Tesla's inventory like a human,
scrapes the DOM for all listings, stores them to the database, then runs the
filter/rank/alert pipeline from tesla_alert.py.

Usage:
    python browse_tesla.py               # scan with config.json
    python browse_tesla.py --config path/to/config.json
"""

import argparse
import datetime
import json
import logging
import random
import smtplib
import sys
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("browse_tesla")

SCRIPT_DIR = Path(__file__).parent
DEFAULT_CONFIG = SCRIPT_DIR / "config.json"
DB_PATH = SCRIPT_DIR / "tesla_tracker.db"


def load_config(path=None):
    p = Path(path) if path else DEFAULT_CONFIG
    if not p.exists():
        log.error("Config not found: %s", p)
        sys.exit(1)
    with open(p) as f:
        return json.load(f)


def send_notification(subject: str, body: str, config: dict):
    """Send to every recipient in notification_recipients, each with 3-attempt retry."""
    email_cfg = config.get("email_notifications", {})
    if not email_cfg.get("enabled"):
        return
    sender = email_cfg.get("sender_email", "")
    password = email_cfg.get("sender_app_password", "").replace(" ", "")
    if not sender or not password:
        return

    recipients = email_cfg.get("notification_recipients") or []
    if not recipients:
        # Fall back to legacy single recipient field
        r = email_cfg.get("recipient_email", "")
        if r:
            recipients = [r]
    if not recipients:
        return

    for recipient in recipients:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient
        msg.attach(MIMEText(body, "plain"))
        sent = False
        for attempt in range(3):
            try:
                with smtplib.SMTP(email_cfg["smtp_server"], email_cfg["smtp_port"]) as server:
                    server.starttls()
                    server.login(sender, password)
                    server.sendmail(sender, recipient, msg.as_string())
                log.info("Notification sent to %s", recipient)
                sent = True
                break
            except Exception as e:
                if attempt < 2:
                    log.warning("Notification attempt %d failed for %s: %s — retrying in 5s",
                                attempt + 1, recipient, e)
                    time.sleep(5)
                else:
                    log.error("All 3 notification attempts failed for %s: %s", recipient, e)
        if not sent:
            log.error("Could not deliver notification to %s", recipient)


def browse_and_capture(config: dict) -> list[dict]:
    try:
        import undetected_chromedriver as uc
    except ImportError:
        log.error("Run: pip install undetected-chromedriver")
        sys.exit(1)

    zip_code = config["zip_code"]
    inventory_url = (
        f"https://www.tesla.com/inventory/used/m3"
        f"?arrangeby=plh&zip={zip_code}&range=0"
    )

    opts = uc.ChromeOptions()
    opts.add_argument("--window-size=1440,900")
    opts.add_argument("--lang=en-US,en;q=0.9")
    opts.add_argument("--disable-features=IsolateOrigins,site-per-process")

    # Required on Linux servers running under Xvfb
    import platform
    if platform.system() == "Linux":
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-setuid-sandbox")
        # Persistent profile so cookies/fingerprints survive across cron runs
        profile_dir = SCRIPT_DIR / "chrome_profile"
        profile_dir.mkdir(exist_ok=True)
        opts.add_argument(f"--user-data-dir={profile_dir}")

    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    log.info("Opening Chrome (undetected mode)...")
    driver = uc.Chrome(options=opts, headless=False, version_main=149)

    def pause(lo=0.8, hi=2.0):
        """Random human-like pause between lo and hi seconds."""
        time.sleep(random.uniform(lo, hi))

    def human_click(element):
        """Scroll element into view, small pause, then click."""
        driver.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'})", element)
        pause(0.4, 0.9)
        element.click()
        pause(0.3, 0.7)

    def human_type(element, text):
        """Type text character by character with random inter-key delays."""
        element.clear()
        pause(0.2, 0.5)
        for ch in text:
            element.send_keys(ch)
            time.sleep(random.uniform(0.05, 0.18))
        pause(0.3, 0.6)

    def popup_gone(selector, timeout=6):
        """Wait up to timeout seconds for an element to disappear from view."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            els = driver.find_elements("css selector", selector)
            if not els or not any(e.is_displayed() for e in els):
                return True
            time.sleep(0.4)
        return False

    captured = []

    try:
        # Warm up on the homepage first so Akamai builds session trust
        # before we hit the inventory page (cold direct nav often gets blocked).
        log.info("Warming up on tesla.com homepage...")
        driver.get("https://www.tesla.com")
        pause(4, 7)
        # Scroll a bit to simulate reading the page
        for _ in range(random.randint(2, 4)):
            driver.execute_script(f"window.scrollBy(0, {random.randint(200, 500)})")
            pause(0.8, 1.8)
        driver.execute_script("window.scrollTo(0, 0)")
        pause(2, 4)

        log.info("Navigating to: %s", inventory_url)
        driver.get(inventory_url)

        log.info("Waiting for page to load...")
        pause(5, 7)

        # ── 1. Dismiss cookie / consent popup ────────────────────────────────
        dismiss_selectors = [
            "button[class*='accept']",
            "button[class*='cookie']",
            "button[class*='consent']",
            "[aria-label*='close' i]",
            "[aria-label*='accept' i]",
            "[data-id='modal-close-button']",
            "button.tds-btn--primary",
        ]
        for sel in dismiss_selectors:
            try:
                for btn in driver.find_elements("css selector", sel):
                    if btn.is_displayed():
                        log.info("Dismissing cookie popup: %s", btn.text.strip() or sel)
                        human_click(btn)
                        break
            except Exception:
                continue

        pause(1, 2)

        # ── 2. Set delivery ZIP + range, then wait for popup to close ─────────
        delivery_zip = config.get("delivery_zip", config["zip_code"])
        log.info("Opening delivery popup (ZIP=%s, range=All Deliverable)...", delivery_zip)
        try:
            zip_btn = None
            for candidate in driver.find_elements("css selector",
                    ".postal-code-results-cta button.tds-link, button.tds-link"):
                if candidate.is_displayed() and candidate.text.strip().isdigit():
                    zip_btn = candidate
                    break

            if zip_btn:
                human_click(zip_btn)
                pause(1.5, 2.5)  # wait for popup animation

                # Type ZIP character by character into the input
                zip_input = None
                for sel in [
                    "input[data-id='registration-postal-code-textbox']",
                    "input[name='zip']",
                ]:
                    els = driver.find_elements("css selector", sel)
                    visible = [e for e in els if e.is_displayed()]
                    if visible:
                        zip_input = visible[0]
                        break

                if zip_input:
                    zip_input.click()
                    pause(0.3, 0.6)
                    # Select-all then type new ZIP (clears existing value naturally)
                    zip_input.send_keys(u'' + 'a')  # Ctrl+A
                    pause(0.1, 0.3)
                    human_type(zip_input, delivery_zip)
                    log.info("Typed delivery ZIP = %s", delivery_zip)
                else:
                    log.warning("ZIP input not found in popup")

                pause(0.5, 1.0)

                # Set range dropdown to 0 = All Deliverable
                found_range = driver.execute_script("""
                    const sel = document.querySelector(
                        "select#search-radius-dropdown, select[name='range']"
                    );
                    if (sel) {
                        sel.value = '0';
                        sel.dispatchEvent(new Event('change', {bubbles:true}));
                    }
                    return !!sel;
                """)
                log.info("Set range = All Deliverable (found: %s)", found_range)
                pause(0.5, 1.0)

                # Click confirm button, or fall back to Enter
                from selenium.webdriver.common.keys import Keys
                confirmed = False
                confirm_texts = {"update", "apply", "search", "done", "confirm"}
                for btn in driver.find_elements("css selector", "button"):
                    if btn.is_displayed() and btn.text.strip().lower() in confirm_texts:
                        log.info("Clicking popup confirm: %r", btn.text.strip())
                        human_click(btn)
                        confirmed = True
                        break
                if not confirmed and zip_input:
                    zip_input.send_keys(Keys.RETURN)
                    log.info("Submitted popup via Enter")

                # Tesla keeps popup inputs in DOM (display:none) after close, so always
                # press Escape to guarantee the popup is dismissed before continuing.
                pause(1.5, 2.5)
                driver.find_element("css selector", "body").send_keys(Keys.ESCAPE)
                log.info("Delivery popup dismissed")
                pause(2, 4)  # let inventory reload with new delivery filter

            else:
                log.warning("Delivery popup button not found — skipping")

        except Exception as e:
            log.warning("Could not set delivery ZIP/range: %s", e)

        # ── 3. Apply year filter ──────────────────────────────────────────────
        log.info("Applying year filter (%d–%d)...", config["min_year"], config["max_year"])
        set_input_js = """
            const nativeSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            const el = document.querySelector("input[name='" + arguments[0] + "']");
            if (el) {
                el.scrollIntoView({behavior:'smooth', block:'center'});
                nativeSetter.call(el, arguments[1]);
                el.dispatchEvent(new Event('input',  {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
                el.dispatchEvent(new KeyboardEvent('keydown',
                    {key:'Enter', keyCode:13, bubbles:true}));
                el.dispatchEvent(new KeyboardEvent('keyup',
                    {key:'Enter', keyCode:13, bubbles:true}));
            }
            return !!el;
        """
        for name, value in [
            ("inputMin-Year", str(config["min_year"])),
            ("inputMax-Year", str(config["max_year"])),
        ]:
            try:
                found = driver.execute_script(set_input_js, name, value)
                log.info("Set %s = %s (found: %s)", name, value, found)
                pause(2.5, 4.0)
            except Exception as e:
                log.warning("Could not set %s: %s", name, e)

        log.info("Waiting for filtered results to load...")
        pause(4, 6)

        # ── 4. Scroll to load all paginated cards ─────────────────────────────
        # Tesla lazy-loads cards only when the page bottom is reached.
        # Approach: a few human-like partial scrolls, then a final snap to the
        # absolute bottom each iteration. Track card count — stop when it stops growing.
        log.info("Scrolling to load all paginated results...")
        prev_count = 0
        for i in range(25):
            current_count = driver.execute_script(
                "return document.querySelectorAll('article.result.card.vehicle-card').length"
            )
            if i > 0:
                log.info("  scroll %d: %d cards loaded", i, current_count)

            # 2–4 gradual steps towards the bottom (looks human)
            for _ in range(random.randint(2, 4)):
                driver.execute_script(
                    f"window.scrollBy(0, {random.randint(300, 700)})"
                )
                time.sleep(random.uniform(0.15, 0.4))

            # Final snap to the very bottom so Tesla's observer fires
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            pause(2.5, 4.0)

            new_count = driver.execute_script(
                "return document.querySelectorAll('article.result.card.vehicle-card').length"
            )
            if new_count == prev_count and i > 0:
                log.info("No new cards after scroll %d — end of results (%d total)", i, new_count)
                break
            prev_count = new_count

        pause(1.5, 2.5)
        log.info("Page title: %r", driver.title)

        log.info("Scraping vehicle cards from page DOM...")
        captured = driver.execute_script(r"""
            const cards = document.querySelectorAll('article.result.card.vehicle-card');
            return Array.from(cards).map(card => {
                const vin = (card.dataset.id || '').replace(/-search-result-container$/, '');

                const trim = card.querySelector('.trim-name')?.textContent?.trim() || '';

                // Price: "Est $265 /mo financing • $18,400" — sale price is the last $ amount
                const priceText = card.querySelector('.tds-text--contrast-high span')?.textContent || '';
                const priceMatches = [...priceText.matchAll(/\$([\d,]+)/g)];
                const price = priceMatches.length > 0
                    ? parseInt(priceMatches[priceMatches.length - 1][1].replace(/,/g, ''))
                    : 0;

                // "2022 Pre-Owned Vehicle with 45,000 mi"
                const contrastEls = Array.from(card.querySelectorAll('.tds-text--contrast-low'));
                const yearMiEl = contrastEls.find(el => el.textContent.includes('Pre-Owned'));
                const yearMiText = yearMiEl ? yearMiEl.textContent : '';
                const yearMatch = yearMiText.match(/(\d{4})/);
                const year = yearMatch ? parseInt(yearMatch[1]) : 0;
                const miMatch = yearMiText.match(/([\d,]+)\s*mi/);
                const mileage = miMatch ? parseInt(miMatch[1].replace(/,/g, '')) : 0;

                // "Located in Vienna, VA"
                const locEl = contrastEls.find(el => el.textContent.includes('Located in'));
                const locText = locEl ? locEl.textContent.replace('Located in', '').trim() : '';
                const locParts = locText.split(',');
                const city = locParts[0]?.trim() || '';
                const state = locParts[1]?.trim() || '';

                // All tooltip feature items (paint, roof, interior, options…)
                const allItems = Array.from(
                    card.querySelectorAll(
                        '.feature-list-tooltip .feature-list-item .option-description'
                    )
                ).map(el => el.textContent.trim()).filter(Boolean);

                // Extra option tags that sometimes appear on the card
                const optionTags = Array.from(
                    card.querySelectorAll(
                        '.vehicle-card-key-value-list li, .vehicle-options-list li'
                    )
                ).map(el => el.textContent.trim()).filter(Boolean);

                const allOptions = [...new Set([...allItems, ...optionTags])];

                const findOption = (keywords) =>
                    allOptions.find(o => keywords.some(k => o.toLowerCase().includes(k))) || '';

                return {
                    VIN:           vin,
                    Year:          year,
                    TrimName:      trim,
                    Price:         price,
                    Odometer:      mileage,
                    City:          city,
                    StateProvince: state,
                    PAINT:         [allItems[0] || ''],
                    INTERIOR:      [allItems[2] || ''],
                    OPTIONS_RAW:   allOptions,
                    SUPERCHARGING: findOption(['supercharging', 'supercharge']),
                    FSD:           findOption(['full self-driving', 'fsd']),
                    AUTOPILOT:     findOption(['autopilot', 'enhanced autopilot']),
                    WHEEL_TYPE:    findOption(['wheel', 'rim', '18"', '19"', '20"']),
                };
            });
        """)

        if captured:
            log.info("Scraped %d vehicle cards from page", len(captured))
            years = sorted({v.get("Year", 0) for v in captured if v.get("Year")})
            prices = sorted([v["Price"] for v in captured if v.get("Price")])
            log.info(
                "Years: %s | Price range: $%s – $%s",
                years,
                f"{prices[0]:,}" if prices else "?",
                f"{prices[-1]:,}" if prices else "?",
            )
        else:
            log.warning("No vehicle cards found in DOM — page title: %r", driver.title)

    finally:
        driver.quit()

    return captured


def main():
    parser = argparse.ArgumentParser(description="Tesla Model 3 Browser Scanner")
    parser.add_argument("--config", default=None)
    parser.add_argument("--no-delay", action="store_true",
                        help="Skip random start delay (used by web dashboard)")
    args = parser.parse_args()

    # Add variance so scheduled runs don't hit Tesla at the exact same second daily.
    # Skip automatically when running in a terminal, or when --no-delay is passed.
    if not args.no_delay and not sys.stdin.isatty():
        delay_secs = random.randint(0, 55 * 60)
        log.info("Scheduled run — waiting %d min %d sec before scan",
                 delay_secs // 60, delay_secs % 60)
        time.sleep(delay_secs)

    config = load_config(args.config)

    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        from tesla_alert import (
            GeoLocator,
            apply_filters,
            detect_new_listings,
            enrich_with_shipping,
            format_results,
            parse_vehicle,
            rank_vehicles,
            save_results,
            send_email,
        )
    except ImportError as e:
        log.error("Could not import tesla_alert.py: %s", e)
        sys.exit(1)

    import database

    criteria_summary = (
        f"{config['min_year']}-{config['max_year']} Model 3 | "
        f"< {config['max_mileage'] // 1000}k mi | "
        f"<= ${config['max_price']:,} | "
        f"ZIP {config['zip_code']}"
    )
    log.info("Criteria: %s", criteria_summary)

    try:
        raw_vehicles = browse_and_capture(config)

        if not raw_vehicles:
            log.warning("No vehicles captured — page may have been blocked. No notification sent.")
            print("\nNo vehicles captured from Tesla's inventory page.")
            return

        scan_date = datetime.date.today().isoformat()
        conn = database.init_db(DB_PATH)

        # Store ALL vehicles to DB before filtering so trends cover full market
        database.insert_daily_summary(conn, scan_date, raw_vehicles)
        parsed_all = [parse_vehicle(v) for v in raw_vehicles]
        for v in parsed_all:
            database.upsert_vehicle(conn, v, scan_date)
            database.insert_price_snapshot(conn, v["vin"], scan_date, v)
        conn.commit()
        log.info("Stored %d vehicles to database (scan_date=%s)", len(parsed_all), scan_date)

        # Run the alert pipeline on filtered subset
        filtered = apply_filters(parsed_all, config)

        if not filtered:
            log.info("Scan complete. No matches yet — %d vehicles checked.", len(parsed_all))
            conn.close()
            return

        geo = GeoLocator(config["lat"], config["lng"])
        with_shipping = enrich_with_shipping(filtered, geo, config)

        if not with_shipping:
            log.info("Scan complete. Matches found but all exceed total cost limit with shipping.")
            conn.close()
            return

        ranked = rank_vehicles(with_shipping, config)

        # Back-fill shipping/score into price_history rows
        for v in ranked:
            database.update_price_snapshot_enriched(conn, v["vin"], scan_date, v)
        conn.commit()
        conn.close()

        new_listings = detect_new_listings(ranked)
        print(format_results(ranked))
        save_results(ranked)

        if new_listings:
            log.info("%d new listing(s) since last scan", len(new_listings))
            if config["email_notifications"].get("enabled"):
                send_email(
                    subject=f"Tesla Model 3 Alert: {len(new_listings)} new deal(s)!",
                    body=format_results(new_listings, title="NEW LISTINGS"),
                    config=config,
                )

        log.info("Done. %d matching vehicles found.", len(ranked))

    except Exception as e:
        log.error("Script error: %s", e, exc_info=True)
        send_notification(
            "Tesla Alert: ERROR",
            f"The Tesla alert script failed with an error:\n\n{type(e).__name__}: {e}",
            config,
        )
        raise


if __name__ == "__main__":
    main()
