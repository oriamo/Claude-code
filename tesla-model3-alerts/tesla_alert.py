#!/usr/bin/env python3
"""
Tesla Model 3 Price Alert Bot

Scrapes Tesla's used inventory for Model 3 vehicles matching criteria
and ranks them using a composite score based on year, mileage, price,
shipping cost, and repair history.

Usage:
    python tesla_alert.py                       # Run once (API mode)
    python tesla_alert.py --selenium            # Run once (browser mode)
    python tesla_alert.py --daemon              # Run on daily schedule
    python tesla_alert.py --test                # Run with sample data
    python tesla_alert.py --config config.json  # Custom config file
"""

import argparse
import json
import logging
import math
import os
import smtplib
import sys
import time
import urllib.parse
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import requests
from tabulate import tabulate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("tesla_alert")

SCRIPT_DIR = Path(__file__).parent
DEFAULT_CONFIG = SCRIPT_DIR / "config.json"
RESULTS_CACHE = SCRIPT_DIR / "last_results.json"

# v1 is the most widely verified working endpoint (used by multiple open-source scrapers).
# v4 is used by teslahunt/inventory but less documented.
# We try v1 first, then fall back to v4.
TESLA_API_ENDPOINTS = [
    "https://www.tesla.com/inventory/api/v1/inventory-results",
    "https://www.tesla.com/inventory/api/v4/inventory-results",
]

# Shipping cost lookup: (min_miles, max_miles, estimated_cost)
SHIPPING_TABLE = [
    (0, 30, 0),
    (31, 100, 300),
    (101, 250, 500),
    (251, 500, 700),
    (501, 750, 900),
    (751, 1000, 1100),
    (1001, 1500, 1500),
    (1501, 2000, 1800),
    (2001, float("inf"), 2000),
]

STATE_COORDS = {
    "AL": (32.806671, -86.791130), "AK": (61.370716, -152.404419),
    "AZ": (33.729759, -111.431221), "AR": (34.969704, -92.373123),
    "CA": (36.116203, -119.681564), "CO": (39.059811, -105.311104),
    "CT": (41.597782, -72.755371), "DE": (39.318523, -75.507141),
    "FL": (27.766279, -81.686783), "GA": (33.040619, -83.643074),
    "HI": (21.094318, -157.498337), "ID": (44.240459, -114.478828),
    "IL": (40.349457, -88.986137), "IN": (39.849426, -86.258278),
    "IA": (42.011539, -93.210526), "KS": (38.526600, -96.726486),
    "KY": (37.668140, -84.670067), "LA": (31.169546, -91.867805),
    "ME": (44.693947, -69.381927), "MD": (39.063946, -76.802101),
    "MA": (42.230171, -71.530106), "MI": (43.326618, -84.536095),
    "MN": (45.694454, -93.900192), "MS": (32.741646, -89.678696),
    "MO": (38.456085, -92.288368), "MT": (46.921925, -110.454353),
    "NE": (41.125370, -98.268082), "NV": (38.313515, -117.055374),
    "NH": (43.452492, -71.563896), "NJ": (40.298904, -74.521011),
    "NM": (34.840515, -106.248482), "NY": (42.165726, -74.948051),
    "NC": (35.630066, -79.806419), "ND": (47.528912, -99.784012),
    "OH": (40.388783, -82.764915), "OK": (35.565342, -96.928917),
    "OR": (44.572021, -122.070938), "PA": (40.590752, -77.209755),
    "RI": (41.680893, -71.511780), "SC": (33.856892, -80.945007),
    "SD": (44.299782, -99.438828), "TN": (35.747845, -86.692345),
    "TX": (31.054487, -97.563461), "UT": (40.150032, -111.862434),
    "VT": (44.045876, -72.710686), "VA": (37.769337, -78.169968),
    "WA": (47.400902, -121.490494), "WV": (38.491226, -80.954453),
    "WI": (44.268543, -89.616508), "WY": (42.755966, -107.302490),
    "DC": (38.897438, -77.026817),
}

SAMPLE_VEHICLES = [
    {
        "VIN": "5YJ3E1EA1NF000001", "Year": 2022, "TrimName": "Standard Range+",
        "Price": 19500, "Odometer": 35000, "City": "Richmond", "StateProvince": "VA",
        "PAINT": ["Pearl White"], "INTERIOR": ["Black"], "PostalCode": "23220",
        "VehicleHistory": "", "TitleStatus": "Clean", "DamageDisclosure": "",
        "TransportationFee": 300, "Latitude": 37.5407, "Longitude": -77.4360,
    },
    {
        "VIN": "5YJ3E1EA3PF000002", "Year": 2023, "TrimName": "Long Range AWD",
        "Price": 21800, "Odometer": 22000, "City": "Charlotte", "StateProvince": "NC",
        "PAINT": ["Midnight Silver"], "INTERIOR": ["Black"], "PostalCode": "28202",
        "VehicleHistory": "", "TitleStatus": "Clean", "DamageDisclosure": "",
        "TransportationFee": 500, "Latitude": 35.2271, "Longitude": -80.8431,
    },
    {
        "VIN": "5YJ3E1EB5PF000003", "Year": 2023, "TrimName": "Performance",
        "Price": 22000, "Odometer": 58000, "City": "Atlanta", "StateProvince": "GA",
        "PAINT": ["Red Multi-Coat"], "INTERIOR": ["White"], "PostalCode": "30301",
        "VehicleHistory": "Previously Repaired to Tesla Specifications",
        "TitleStatus": "Clean", "DamageDisclosure": "Repaired",
        "TransportationFee": 700, "Latitude": 33.7490, "Longitude": -84.3880,
    },
    {
        "VIN": "5YJ3E1EA7NF000004", "Year": 2022, "TrimName": "Long Range AWD",
        "Price": 20000, "Odometer": 18000, "City": "Baltimore", "StateProvince": "MD",
        "PAINT": ["Solid Black"], "INTERIOR": ["Black"], "PostalCode": "21201",
        "VehicleHistory": "", "TitleStatus": "Clean", "DamageDisclosure": "",
        "TransportationFee": 0, "Latitude": 39.2904, "Longitude": -76.6122,
    },
    {
        "VIN": "5YJ3E1EA2PF000005", "Year": 2023, "TrimName": "Standard Range+",
        "Price": 18500, "Odometer": 28000, "City": "Philadelphia", "StateProvince": "PA",
        "PAINT": ["Deep Blue"], "INTERIOR": ["Black"], "PostalCode": "19101",
        "VehicleHistory": "", "TitleStatus": "Clean", "DamageDisclosure": "",
        "TransportationFee": 300, "Latitude": 39.9526, "Longitude": -75.1652,
    },
    {
        "VIN": "5YJ3E1EA9NF000006", "Year": 2022, "TrimName": "Standard Range+",
        "Price": 22000, "Odometer": 59000, "City": "Los Angeles", "StateProvince": "CA",
        "PAINT": ["Pearl White"], "INTERIOR": ["Black"], "PostalCode": "90001",
        "VehicleHistory": "", "TitleStatus": "Clean", "DamageDisclosure": "",
        "TransportationFee": 2000, "Latitude": 33.9425, "Longitude": -118.2551,
    },
    {
        "VIN": "5YJ3E1EA1PF000007", "Year": 2023, "TrimName": "Standard Range+",
        "Price": 20500, "Odometer": 40000, "City": "Norfolk", "StateProvince": "VA",
        "PAINT": ["Midnight Silver"], "INTERIOR": ["Black"], "PostalCode": "23510",
        "VehicleHistory": "", "TitleStatus": "Clean", "DamageDisclosure": "",
        "TransportationFee": 300, "Latitude": 36.8508, "Longitude": -76.2859,
    },
]


def load_config(config_path: str = None) -> dict:
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    if not path.exists():
        log.error("Config file not found: %s", path)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in miles between two lat/lon points."""
    R = 3959
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def estimate_shipping(distance_miles: float) -> int:
    """Estimate Tesla transport fee from distance using lookup table."""
    for min_d, max_d, cost in SHIPPING_TABLE:
        if min_d <= distance_miles <= max_d:
            return cost
    return 2000


class GeoLocator:
    """Resolves locations to coordinates for distance calculation."""

    def __init__(self, home_lat: float, home_lng: float):
        self.home_lat = home_lat
        self.home_lng = home_lng
        try:
            import pgeocode
            self._nomi = pgeocode.Nominatim("us")
        except Exception:
            self._nomi = None
        self._cache: dict[str, tuple[float, float]] = {}

    def distance_to(
        self,
        city: str = None,
        state: str = None,
        zip_code: str = None,
        lat: float = None,
        lng: float = None,
    ) -> Optional[float]:
        if lat is not None and lng is not None:
            return haversine(self.home_lat, self.home_lng, lat, lng)

        if zip_code and self._nomi is not None:
            key = f"zip:{zip_code}"
            if key not in self._cache:
                try:
                    result = self._nomi.query_postal_code(zip_code)
                    if result is not None and not math.isnan(result.latitude):
                        self._cache[key] = (result.latitude, result.longitude)
                except Exception:
                    pass
            if key in self._cache:
                clat, clng = self._cache[key]
                return haversine(self.home_lat, self.home_lng, clat, clng)

        if state and state.upper() in STATE_COORDS:
            slat, slng = STATE_COORDS[state.upper()]
            return haversine(self.home_lat, self.home_lng, slat, slng)

        return None


# ─── Fetching: API Mode ─────────────────────────────────────────────────────


def _build_query_json(config: dict, offset: int, count: int, outside: bool) -> str:
    """Build the JSON query string matching Tesla's expected format."""
    query_obj = {
        "query": {
            "model": "m3",
            "condition": "used",
            "options": {},
            "arrangeby": "Price",
            "order": "asc",
            "market": "US",
            "language": "en",
            "super_region": "north america",
            "lng": config["lng"],
            "lat": config["lat"],
            "zip": config["zip_code"],
            "range": config.get("search_radius_miles", 0),
        },
        "offset": offset,
        "count": count,
        "outsideOffset": offset,
        "outsideSearch": outside,
    }
    return json.dumps(query_obj)


def fetch_inventory_api(config: dict) -> list[dict]:
    """
    Fetch used Model 3 inventory via Tesla's JSON API.

    Uses direct URL construction with urllib.parse.quote (matching verified
    working open-source scrapers) rather than requests' params= encoding,
    which can double-encode the JSON query string.

    Verified against:
    - github.com/kaedenbrinkman/tesla-inventory (Python, v1)
    - github.com/stephenlindauer/tesla-used-inventory-monitor (JS, v1)
    - github.com/teslahunt/inventory (JS, v4)
    """
    all_results = []
    page_size = 50
    max_pages = 20

    for endpoint in TESLA_API_ENDPOINTS:
        log.info("Trying endpoint: %s", endpoint)
        all_results = []

        for page in range(max_pages):
            query_json = _build_query_json(
                config, offset=page * page_size, count=page_size, outside=True
            )
            full_url = endpoint + "?query=" + urllib.parse.quote(query_json)

            try:
                resp = requests.get(full_url, timeout=30)
                if resp.status_code == 403:
                    log.warning("403 Forbidden on %s — trying next endpoint", endpoint)
                    all_results = []
                    break
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as e:
                log.error("Request failed (page %d): %s", page, e)
                all_results = []
                break
            except json.JSONDecodeError:
                log.error("Invalid JSON response")
                all_results = []
                break

            results = data.get("results", [])
            if not results:
                break

            all_results.extend(results)

            total_raw = data.get("total_matches_found", len(all_results))
            total = int(total_raw) if isinstance(total_raw, str) else total_raw

            if (page + 1) * page_size >= total:
                break

            time.sleep(1.5)

        if all_results:
            log.info("Fetched %d vehicles via %s", len(all_results), endpoint)
            return all_results

    log.warning("All API endpoints returned 0 results")
    return []


# ─── Fetching: Selenium Mode ────────────────────────────────────────────────


def fetch_inventory_selenium(config: dict) -> list[dict]:
    """Fetch inventory using Selenium to render the Tesla page and capture API calls."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError:
        log.error(
            "Selenium not installed. Install with: pip install selenium\n"
            "Also install ChromeDriver: https://chromedriver.chromium.org/downloads"
        )
        return []

    zip_code = config["zip_code"]
    url = (
        f"https://www.tesla.com/inventory/used/m3"
        f"?arrangeby=plh&zip={zip_code}&range=0"
    )

    log.info("Launching headless Chrome for %s", url)

    chrome_opts = Options()
    chrome_opts.add_argument("--headless=new")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--disable-dev-shm-usage")
    chrome_opts.add_argument("--disable-gpu")
    chrome_opts.add_argument("--window-size=1920,1080")
    chrome_opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    chrome_opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_opts)
        driver.get(url)

        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='result'], [class*='inventory'], [class*='card']"))
        )
        time.sleep(5)

        logs = driver.get_log("performance")
        api_results = []

        for entry in logs:
            try:
                msg = json.loads(entry["message"])["message"]
                if msg["method"] != "Network.responseReceived":
                    continue
                resp_url = msg["params"]["response"]["url"]
                if "inventory-results" not in resp_url and "inventory/api" not in resp_url:
                    continue

                request_id = msg["params"]["requestId"]
                body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
                data = json.loads(body.get("body", "{}"))
                results = data.get("results", [])
                api_results.extend(results)
                log.info("Captured %d vehicles from network log", len(results))
            except Exception:
                continue

        if api_results:
            return api_results

        log.info("No API calls captured, falling back to DOM scraping")
        cards = driver.find_elements(By.CSS_SELECTOR, "[class*='result-card'], [class*='inventory-card'], article")

        vehicles = []
        for card in cards:
            try:
                text = card.text
                lines = text.strip().split("\n")
                vehicle = _parse_card_text(lines)
                if vehicle:
                    vehicles.append(vehicle)
            except Exception:
                continue

        log.info("Scraped %d vehicles from page DOM", len(vehicles))
        return vehicles

    except Exception as e:
        log.error("Selenium fetch failed: %s", e)
        return []
    finally:
        if driver:
            driver.quit()


def _parse_card_text(lines: list[str]) -> Optional[dict]:
    """Best-effort parse of a vehicle card's visible text into a dict."""
    vehicle = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("$") or line.startswith("$"):
            price_str = line.replace("$", "").replace(",", "").strip()
            try:
                vehicle["Price"] = int(float(price_str))
            except ValueError:
                pass

        if "mi" in line.lower() and any(c.isdigit() for c in line):
            parts = line.replace(",", "").split()
            for p in parts:
                try:
                    val = int(p)
                    if 100 < val < 200000:
                        vehicle["Odometer"] = val
                        break
                except ValueError:
                    continue

        for year in range(2020, 2026):
            if str(year) in line:
                vehicle["Year"] = year
                if "Model 3" in line or "Model3" in line:
                    remaining = line.split(str(year))[-1].strip()
                    remaining = remaining.replace("Model 3", "").replace("Tesla", "").strip()
                    vehicle["TrimName"] = remaining or "Standard"
                break

    if "Price" in vehicle and "Year" in vehicle:
        vehicle.setdefault("VIN", f"SCRAPED-{vehicle.get('Year', 0)}-{vehicle.get('Price', 0)}")
        vehicle.setdefault("TrimName", "Unknown")
        vehicle.setdefault("Odometer", 0)
        vehicle.setdefault("City", "")
        vehicle.setdefault("StateProvince", "")
        vehicle.setdefault("PAINT", ["Unknown"])
        vehicle.setdefault("INTERIOR", ["Unknown"])
        return vehicle

    return None


# ─── Vehicle Parsing & Processing ───────────────────────────────────────────


def parse_vehicle(raw: dict) -> dict:
    """
    Normalize a raw Tesla API vehicle record.

    Field names verified against real API response (123+ fields per vehicle):
      github.com/kaedenbrinkman/tesla-inventory - Price, VIN, Model, TrimName, Odometer, MetroName
      gist.github.com/myhalici/2241ae06ca4f8069290cd63c3b114542 - full field inventory
    """
    odometer = raw.get("Odometer") or raw.get("Mileage") or 0
    price = raw.get("Price") or raw.get("PurchasePrice") or raw.get("TotalPrice") or 0
    year = raw.get("Year") or 0
    vin = raw.get("VIN") or "Unknown"

    trim = raw.get("TrimName") or "Unknown"
    if isinstance(trim, list):
        trim = trim[0] if trim else "Unknown"
    raw_trim = raw.get("TRIM")
    if trim == "Unknown" and isinstance(raw_trim, list) and raw_trim:
        trim = raw_trim[0]

    city = raw.get("City") or ""
    state = raw.get("StateProvince") or ""
    metro = raw.get("MetroName") or ""
    zip_code = raw.get("PostalCode") or ""

    color = raw.get("PAINT", ["Unknown"])
    if isinstance(color, list):
        color = color[0] if color else "Unknown"

    interior = raw.get("INTERIOR", ["Unknown"])
    if isinstance(interior, list):
        interior = interior[0] if interior else "Unknown"

    # Repair detection: verified fields from real API responses
    vehicle_history = raw.get("VehicleHistory") or ""
    title_status = raw.get("TitleStatus") or ""
    title_subtype = raw.get("TitleSubtype") or ""
    damage_disclosure = raw.get("DamageDisclosure") or ""
    damage_status = raw.get("DamageDisclosureStatus") or ""
    cpo_status = raw.get("CPORefurbishmentStatus") or ""
    has_damage_photos = raw.get("HasDamagePhotos", False)

    is_repaired = bool(has_damage_photos)
    repair_indicators = [
        "previously repaired", "repaired", "damage", "accident",
        "rebuilt", "salvage", "refurbish",
    ]
    for field_val in [vehicle_history, title_status, title_subtype,
                      damage_disclosure, damage_status, cpo_status]:
        if isinstance(field_val, str) and any(
            ind in field_val.lower() for ind in repair_indicators
        ):
            is_repaired = True
            break

    # Transport fee: verified field name from real API response
    transport_fee = raw.get("TransportationFee")
    if transport_fee is None:
        transport_fees = raw.get("TransportFees")
        if isinstance(transport_fees, dict):
            transport_fee = transport_fees.get("total") or transport_fees.get("amount")

    # Location: use geoPoints if lat/lng not available directly
    car_lat = raw.get("Latitude")
    car_lng = raw.get("Longitude")
    if car_lat is None:
        geo_points = raw.get("geoPoints")
        if isinstance(geo_points, list) and geo_points:
            pt = geo_points[0] if isinstance(geo_points[0], dict) else {}
            car_lat = pt.get("lat") or pt.get("latitude")
            car_lng = pt.get("lng") or pt.get("longitude")

    location_str = metro or (f"{city}, {state}" if city else state)

    return {
        "vin": vin,
        "year": int(year),
        "trim": trim,
        "price": int(price),
        "mileage": int(odometer),
        "color": color,
        "interior": interior,
        "city": city,
        "state": state,
        "metro": metro,
        "location_str": location_str,
        "zip_code": zip_code,
        "lat": float(car_lat) if car_lat else None,
        "lng": float(car_lng) if car_lng else None,
        "is_repaired": is_repaired,
        "vehicle_history": str(vehicle_history),
        "title_status": str(title_status),
        "transport_fee_api": int(transport_fee) if transport_fee else None,
        "url": f"https://www.tesla.com/m3/order/{vin}",
        "raw_data": raw,
    }


def apply_filters(vehicles: list[dict], config: dict) -> list[dict]:
    """Filter vehicles by year, price, and mileage criteria."""
    filtered = []
    for v in vehicles:
        if v["year"] < config["min_year"] or v["year"] > config["max_year"]:
            continue
        if v["price"] <= 0 or v["price"] > config["max_price"]:
            continue
        if v["mileage"] <= 0 or v["mileage"] >= config["max_mileage"]:
            continue
        filtered.append(v)

    log.info(
        "Filtered to %d vehicles (year %d-%d, price <= $%s, mileage < %sk)",
        len(filtered),
        config["min_year"],
        config["max_year"],
        f"{config['max_price']:,}",
        config["max_mileage"] // 1000,
    )
    return filtered


def enrich_with_shipping(vehicles: list[dict], geo: GeoLocator, config: dict) -> list[dict]:
    """Add shipping estimates and filter by total cost."""
    enriched = []
    for v in vehicles:
        distance = geo.distance_to(
            city=v["city"],
            state=v["state"],
            zip_code=v["zip_code"],
            lat=v["lat"],
            lng=v["lng"],
        )

        if v["transport_fee_api"] is not None:
            shipping = v["transport_fee_api"]
            shipping_source = "tesla"
        elif distance is not None:
            shipping = estimate_shipping(distance)
            shipping_source = f"est. ({int(distance)} mi)"
        else:
            shipping = 1000
            shipping_source = "default est."

        total = v["price"] + shipping

        if total > config["max_total_with_shipping"]:
            continue

        v["shipping_cost"] = shipping
        v["shipping_source"] = shipping_source
        v["total_cost"] = total
        v["distance"] = int(distance) if distance else 0
        enriched.append(v)

    log.info(
        "After shipping filter: %d vehicles (total <= $%s)",
        len(enriched),
        f"{config['max_total_with_shipping']:,}",
    )
    return enriched


# ─── Scoring System ─────────────────────────────────────────────────────────


def score_vehicle(v: dict, config: dict) -> float:
    """
    Composite score 0-100 (higher = better deal).

    - Year:     newer is better    (2022→0.0 ... 2024→1.0)
    - Mileage:  lower is better    (60k→0.0  ... 0→1.0)
    - Price:    lower is better    (22k→0.0  ... 0→1.0)
    - Shipping: lower is better    ($2k→0.0  ... $0→1.0)
    - Repair:   no history→1.0, repaired→0.0
    """
    w = config["scoring_weights"]

    year_range = config["max_year"] - config["min_year"]
    year_score = (v["year"] - config["min_year"]) / year_range if year_range > 0 else 0.5

    mileage_score = max(0.0, 1.0 - (v["mileage"] / config["max_mileage"]))
    price_score = max(0.0, 1.0 - (v["price"] / config["max_price"]))
    shipping_score = max(0.0, 1.0 - (v["shipping_cost"] / 2000))
    repair_score = 0.0 if v["is_repaired"] else 1.0

    composite = (
        w["year"] * year_score
        + w["mileage"] * mileage_score
        + w["price"] * price_score
        + w["shipping"] * shipping_score
        + w["repair_history"] * repair_score
    )
    return round(composite * 100, 1)


def rank_vehicles(vehicles: list[dict], config: dict) -> list[dict]:
    """Score and sort vehicles, best deals first."""
    for v in vehicles:
        v["score"] = score_vehicle(v, config)
    vehicles.sort(key=lambda v: v["score"], reverse=True)
    for i, v in enumerate(vehicles, 1):
        v["rank"] = i
    return vehicles


# ─── Output ─────────────────────────────────────────────────────────────────


def format_results(vehicles: list[dict], title: str = None) -> str:
    """Format ranked results as a readable table + detailed listings."""
    if not vehicles:
        return "No vehicles found matching your criteria.\n"

    header = title or f"Tesla Model 3 Alert — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    output = (
        f"\n{header}\n"
        f"Found {len(vehicles)} vehicle(s) matching criteria\n"
        f"{'=' * 90}\n\n"
    )

    rows = []
    for v in vehicles:
        repair_flag = " *" if v["is_repaired"] else ""
        rows.append([
            v["rank"],
            f"{v['score']:.1f}",
            v["year"],
            v["trim"][:18],
            f"${v['price']:,}",
            f"{v['mileage']:,}",
            f"${v['shipping_cost']:,}",
            f"${v['total_cost']:,}",
            f"{v['location_str']}{repair_flag}",
        ])

    output += tabulate(
        rows,
        headers=["#", "Score", "Year", "Trim", "Price", "Miles", "Ship", "Total", "Location"],
        tablefmt="simple",
        numalign="right",
        stralign="left",
    )

    output += "\n\n* = Previously repaired\n"
    output += "\n" + "-" * 90 + "\nDetailed Listings:\n" + "-" * 90 + "\n"

    for v in vehicles:
        output += (
            f"\n  #{v['rank']}  Score: {v['score']:.1f}/100\n"
            f"  {v['year']} Tesla Model 3 {v['trim']}\n"
            f"  Price: ${v['price']:,}  |  Mileage: {v['mileage']:,} mi\n"
            f"  Shipping: ${v['shipping_cost']:,} ({v['shipping_source']})\n"
            f"  Total Cost: ${v['total_cost']:,}\n"
            f"  Color: {v['color']}  |  Interior: {v['interior']}\n"
            f"  Location: {v['location_str']}  |  Distance: {v['distance']} mi\n"
            f"  Repaired: {'YES' if v['is_repaired'] else 'No'}"
            f"{'  (' + v['vehicle_history'] + ')' if v['is_repaired'] and v['vehicle_history'] else ''}\n"
            f"  VIN: {v['vin']}\n"
            f"  Link: {v['url']}\n"
        )

    return output


# ─── Notifications ──────────────────────────────────────────────────────────


def send_email(subject: str, body: str, config: dict):
    """Send email notification."""
    email_cfg = config["email_notifications"]
    if not email_cfg.get("enabled"):
        return

    if not email_cfg.get("sender_email") or not email_cfg.get("recipient_email"):
        log.warning("Email enabled but sender/recipient not configured")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_cfg["sender_email"]
    msg["To"] = email_cfg["recipient_email"]
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(email_cfg["smtp_server"], email_cfg["smtp_port"]) as server:
            server.starttls()
            server.login(email_cfg["sender_email"], email_cfg["sender_app_password"])
            server.sendmail(
                email_cfg["sender_email"],
                email_cfg["recipient_email"],
                msg.as_string(),
            )
        log.info("Email sent to %s", email_cfg["recipient_email"])
    except Exception as e:
        log.error("Failed to send email: %s", e)


# ─── Results Cache ──────────────────────────────────────────────────────────


def save_results(vehicles: list[dict]):
    """Cache results to JSON for new-listing detection."""
    serializable = []
    for v in vehicles:
        serializable.append({k: val for k, val in v.items() if k != "raw_data"})

    with open(RESULTS_CACHE, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "count": len(serializable),
            "vehicles": serializable,
        }, f, indent=2)
    log.info("Results cached to %s", RESULTS_CACHE)


def detect_new_listings(vehicles: list[dict]) -> list[dict]:
    """Find vehicles not in the previous cached scan."""
    if not RESULTS_CACHE.exists():
        return vehicles
    try:
        with open(RESULTS_CACHE) as f:
            cached = json.load(f)
        old_vins = {v["vin"] for v in cached.get("vehicles", [])}
        return [v for v in vehicles if v["vin"] not in old_vins]
    except (json.JSONDecodeError, KeyError):
        return vehicles


# ─── Main Scan Logic ────────────────────────────────────────────────────────


def run_scan(config: dict, use_selenium: bool = False, test_mode: bool = False):
    """Execute one full scan cycle."""
    log.info("Starting Tesla Model 3 inventory scan...")
    log.info(
        "Criteria: %d-%d, < %dk mi, <= $%s, total <= $%s (ZIP: %s)",
        config["min_year"], config["max_year"],
        config["max_mileage"] // 1000,
        f"{config['max_price']:,}",
        f"{config['max_total_with_shipping']:,}",
        config["zip_code"],
    )

    if test_mode:
        log.info("TEST MODE — using sample vehicle data")
        raw_vehicles = SAMPLE_VEHICLES
    elif use_selenium:
        raw_vehicles = fetch_inventory_selenium(config)
    else:
        raw_vehicles = fetch_inventory_api(config)

    if not raw_vehicles:
        msg = (
            "\nNo vehicles returned from Tesla API.\n"
            "Possible causes:\n"
            "  1. Tesla blocks datacenter/VPN IPs — run from your home network\n"
            "  2. API endpoint changed — try --selenium mode\n"
            "  3. Rate limited — wait a few minutes and try again\n"
            "  4. Use --test to verify scoring logic with sample data\n"
        )
        print(msg)
        return

    parsed = [parse_vehicle(v) for v in raw_vehicles]
    filtered = apply_filters(parsed, config)

    if not filtered:
        print("\nNo vehicles matched your year/price/mileage criteria after filtering.")
        return

    geo = GeoLocator(config["lat"], config["lng"])
    with_shipping = enrich_with_shipping(filtered, geo, config)

    if not with_shipping:
        print("\nVehicles found but all exceed $22,500 total cost with shipping.")
        return

    ranked = rank_vehicles(with_shipping, config)
    new_listings = detect_new_listings(ranked)

    output = format_results(ranked)
    print(output)

    if ranked:
        save_results(ranked)

    if new_listings:
        log.info("%d new listing(s) since last scan", len(new_listings))
        if config["email_notifications"].get("enabled"):
            send_email(
                subject=f"Tesla Model 3 Alert: {len(new_listings)} new deal(s)!",
                body=format_results(new_listings, title="NEW LISTINGS"),
                config=config,
            )
        else:
            log.info("Enable email in config.json to get notified of new listings")

    log.info("Scan complete. %d matching vehicles found.", len(ranked))


def run_daemon(config: dict, use_selenium: bool = False):
    """Run the scanner on a schedule."""
    import schedule as sched

    run_at = config.get("schedule", {}).get("run_at_time", "09:00")
    interval = config.get("schedule", {}).get("interval_hours", 24)

    log.info("Daemon mode — scanning every %dh, daily at %s", interval, run_at)
    run_scan(config, use_selenium=use_selenium)

    if interval == 24:
        sched.every().day.at(run_at).do(run_scan, config, use_selenium)
    else:
        sched.every(interval).hours.do(run_scan, config, use_selenium)

    while True:
        sched.run_pending()
        time.sleep(60)


def main():
    parser = argparse.ArgumentParser(
        description="Tesla Model 3 Price Alert Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python tesla_alert.py              # Single scan via API\n"
            "  python tesla_alert.py --selenium   # Single scan via browser\n"
            "  python tesla_alert.py --daemon     # Daily scheduled scans\n"
            "  python tesla_alert.py --test       # Test with sample data\n"
        ),
    )
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--daemon", action="store_true", help="Run on daily schedule")
    parser.add_argument("--selenium", action="store_true", help="Use headless Chrome instead of API")
    parser.add_argument("--test", action="store_true", help="Run with sample data to verify scoring")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.daemon:
        run_daemon(config, use_selenium=args.selenium)
    else:
        run_scan(config, use_selenium=args.selenium, test_mode=args.test)


if __name__ == "__main__":
    main()
