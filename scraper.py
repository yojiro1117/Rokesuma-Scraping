"""Scraping logic for the ロケスマ Streamlit application.

This module encapsulates all browser automation using Playwright.  It exposes
a single entry point `scrape_locations` which accepts search parameters,
launches a Chromium instance (honouring the headless flag) and
programmatically interacts with the ロケスマ web application.  The scraper
clicks markers on the map one by one and collects structured information
from the detail panel or popups.  Where a value cannot be extracted
directly from a specific DOM element the implementation falls back to
regular expressions applied to the full visible text.

Because the structure of the ロケスマ site may evolve, selectors are
centralised in the selectors.py module.  The scraper iterates over lists
of candidate selectors until it finds a match for each field.  When new
elements are introduced on the site updating selectors.py is usually
sufficient without touching the scraping logic.

Errors and progress information are logged via the provided logger.  The
calling code is responsible for configuring logging handlers.
"""

import re
import time
import datetime
import os
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

import pandas as pd
import numpy as np
from tenacity import retry, stop_after_attempt, wait_fixed

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError

from selectors import (
    MARKER_SELECTORS,
    STORE_NAME_SELECTORS,
    ADDRESS_SELECTORS,
    PHONE_SELECTORS,
    HOURS_SELECTORS,
)
from utils import (
    extract_phone,
    extract_address,
    extract_hours,
    haversine_distance,
    normalize_key,
)


@dataclass
class ScrapeResult:
    """Container for the result of a scrape.

    Attributes
    ----------
    dataframe : pandme
        The DataFrame of extracted location information.
    log_lines : List[str]
        The list of log messages captured during the scrape.
    """

    dataframe: pd.DataFrame
    log_lines: List[str]


def append_log(logs: List[str], message: str) -> None:
    """Append a message to the in-memory log list with timestamp."""
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    logs.append(f"{ts} {message}")


def safe_get_text(page: Page, selectors: List[str], logger, logs: List[str]) -> Optional[str]:
    """Try a series of selectors and return the first non-empty text.

    Parameters
    ----------
    page : playwright.sync_api.Page
        The current page.
    selectors : List[str]
        Candidate selectors to try.
    logger : logging.Logger
        Logger for debug messages.
    logs : List[str]
        In-memory log lines to update.

    Returns
    -------
    Optional[str]
        The text content if found, otherwise None.
    """
    for sel in selectors:
        try:
            element = page.query_selector(sel)
            if element:
                text = element.inner_text().strip()
                if text:
                    logger.info(f"Found text for selector '{sel}': {text}")
                    append_log(logs, f"selector '{sel}' -> '{text}'")
                    return text
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue
    return None


def parse_detail_panel(page: Page, logger, logs: List[str], origin_lat: float, origin_lng: float) -> Dict[str, object]:
    """Extract store information from the detail panel or popup.

    This method reads visible text and attributes from the page to build a
    dictionary of values.  It uses multiple selectors for robustness and
    fas.DataFra
alls back to regular expression based extraction where necessary.

    Parameters
    ----------
    page : playwright.sync_api.Page
        The page instance.
    logger : logging.Logger
        Logger to record progress.
    logs : List[str]
        In-memory log lines.
    origin_lat : float
        Latitude of the search centre for distance calculations.
    origin_lng : float
        Longitude of the search centre for distance calculations.

    Returns
    -------
    Dict[str, object]
        A dictionary containing extracted fields.
    """
    data: Dict[str, object] = {}

    # Obtain the full visible text from the detail panel for regex fallback
    full_text = ""
    try:
        full_text = page.inner_text("body")  # fallback to whole page
    except Exception:
        full_text = ""

    # Store name
    name = safe_get_text(page, STORE_NAME_SELECTORS, logger, logs)
    if not name:
        # fallback: first line of full_text
        first_line = full_text.strip().split("\n")[0] if full_text else ""
        name = first_line[:100] if first_line else ""
        logger.warning(f"Store name fallback used: {name}")
        append_log(logs, f"Name fallback used: {name}")
    data["店舗名"] = name

    # Phone number
    phone = safe_get_text(page, PHONE_SELECTORS, logger, logs)
    if not phone and full_text:
        phone = extract_phone(full_text)
        if phone:
            logger.info(f"Phone extracted via regex: {phone}")
            append_log(logs, f"Phone via regex: {phone}")
    data["電話番号"] = phone if phone else ""

    # Address
    address = safe_get_text(page, ADDRESS_SELECTORS, logger, logs)
    if not address and full_text:
        address = extract_address(full_text)
        if address:
            logger.info(f"Adess}")
            append_log(logs, f"Address via regex: {address}")
    data["住所"] = address if address else ""

    # Opening hours
    hours = safe_get_text(page, HOURS_SELECTORS, logger, logs)
    if not hours and full_text:
        hours = extract_hours(full_text)
        if hours:
            logger.info(f"Hours extracted via regex: {hours}")
            append_log(logs, f"Hours via regex: {hours}")
    data["営業時間"] = hours if hours else ""

    # Coordinates: attempt to pull from marker attributes or URL
    lat, lng = None, None
    # Try reading attributes from visible elements
    for attr_selector in [
        "div.leaflet-marker-icon",  # Leaflet default icon
        "img.leaflet-marker-icon",
        "div.gm-style-iw-d > a[href*=\\@]",  # Google style info window links containing @lat,lng
    ]:
        try:
            elem = page.query_selector(attr_selector)
            if elem:
                data_lat = elem.get_attribute("data-lat")
                data_lng = elem.get_attribute("data-lng")
                if data_lat and data_lng:
                    lat = float(data_lat)
                    lng = float(data_lng)
                    logger.info(f"Coordinates from marker attributes: {lat}, {lng}")
                    append_log(logs, f"Coords from attrs: {lat}, {lng}")
                    break
        except Exception:
            continue
    # If still not found, attempt to parse from URL (@lat,lng,zoom)
    if lat is None or lng is None:
        url = page.url
        match = re.search(r"@([-\d\.]+),([-\d\.]+)", url)
        if match:
            lat = float(match.group(1))
            lng = float(match.group(2))
            logger.info(f"Coordinates from URL: {lat}, {lng}")
            append_log(logs, f"Coords from URL: {lat}, {lng}")
    # If stdress extractedill not found, use page.evaluate to ask map centre
    if lat is None or lng is None:
        try:
            lat = page.evaluate("window.map && map.getCenter ? map.getCenter().lat : null")
            lng = page.evaluate("window.map && map.getCenter ? map.getCenter().lng : null")
            if lat is not None and lng is not None:
                lat, lng = float(lat), float(lng)
                logger.info(f"Coordinates from map centre: {lat}, {lng}")
                append_log(logs, f"Coords from centre: {lat}, {lng}")
        except Exception:
            lat = None
            lng = None

    data["緯度"] = lat if lat is not None else np.nan
    data["経度"] = lng if lng is not None else np.nan

    # Distance calculation (if coordinates are available)
    if lat is not None and lng is not None and origin_lat is not None and origin_lng is not None:
        dist_m, dist_km = haversine_distance(origin_lat, origin_lng, lat, lng)
        data["距離_m"] = dist_m
        data["距離_km"] = dist_km
    else:
        data["距離_m"] = np.nan
        data["距離_km"] = np.nan

    return data


def extract_origin_coords(page: Page, logger, logs: List[str]) -> Tuple[Optional[float], Optional[float]]:
    """Attempt to determine the latitude and longitude of the map centre.

    The centre coordinates are used as the baseline for distance calculations.

    Returns
    -------
    Tuple[Optional[float], Optional[float]]
        (latitude, longitude) or (None, None) if unavailable.
    """
    # Try from URL first
    url = page.url
    match = re.search(r"@([-\d\.]+),([-\d\.]+)", url)
    if match:
        try:
            return float(match.group(1)), float(match.group(2))
        except Exception:
            pass
    # Fallback to map centre via JS
    try:
        lat = page.evaluate(" via regwindow.map && map.getCenter ? map.getCenter().lat : null")
        lng = page.evaluate("window.map && map.getCenter ? map.getCenter().lng : null")
        if lat is not None and lng is not None:
            return float(lat), float(lng)
    except Exception:
        return None, None
    return None, None


def locate_and_click_marker(page: Page, idx: int, logger, logs: List[str]) -> bool:
    """Locate the marker by index and click it.

    Returns True if the click appears to succeed, False otherwise.  The
    function iterates through MARKER_SELECTORS from selectors.py and
    attempts to fetch the list of marker elements.  If the requested
    index does not exist it returns False.
    """
    for sel in MARKER_SELECTORS:
        try:
            markers = page.query_selector_all(sel)
            if markers and len(markers) > idx:
                logger.info(f"Clicking marker #{idx} using selector {sel}")
                append_log(logs, f"Click marker {idx} using {sel}")
                markers[idx].click()
                return True
        except Exception:
            continue
    return False


def scrape_locations(
    address: str,
    zoom: int,
    categories: List[str],
    headless: bool,
    max_items: int,
    logger,
) -> ScrapeResult:
    """High level scraping function.

    Parameters
    ----------
    address : str
        The central address to search around.
    zoom : int
        Zoom level for the map (8‑18).
    categories : List[str]
        Categories of stores to search.  The special category "病院・診療所" is
        handled via the search bar because it may not appear in the panel.
    headless : bool
        If True, launch the browser in headless mode.
    max_items : int
        Maximum number of items tomit).
    logger : logging.Logger
        A logger configured by the caller.

    Returns
    -------
    ScrapeResult
        Contains the resulting DataFrame and a list of log lines.
    """
    # Accumulate logs in memory for display in the UI
    logs: List[str] = []

    append_log(logs, "Playwright session starting")
    # Set browser path environment variable to ensure bundled browsers are used
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.path.join(os.path.dirname(__file__), "ms-playwright"))

    data_records: List[Dict[str, object]] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless, args=["--disable-infobars", "--start-maximized"])
            context = browser.new_context()
            page = context.new_page()
            base_url = "https://www.locationsmart.org"  # Web version of ロケスマ
            logger.info(f"Navigating to {base_url}")
            append_log(logs, f"Navigate to {base_url}")
            page.goto(base_url, wait_until="domcontentloaded")

            # Accept any cookie or terms dialogs if present
            try:
                page.click("text=同意", timeout=3000)
                append_log(logs, "Clicked consent button")
            except Exception:
                pass

            # Input the address in the search box
            try:
                search_box = page.wait_for_selector("input[type=text]", timeout=10000)
                search_box.click()
                search_box.fill(address)
                search_box.press("Enter")
                append_log(logs, f"Search for address: {address}")
            except PlaywrightTimeoutError:
                append_log(logs, "Search box not found; cannot proceed")
                logger.error("Search box not f
                return ScrapeResult(pd.DataFrame(), logs)

            # Wait for map to load results
            page.wait_for_timeout(5000)

            # Adjust zoom if necessary by interacting with the map controls
            try:
                current_zoom = page.evaluate("window.map && map.getZoom ? map.getZoom() : null")
                if current_zoom is not None:
                    while int(current_zoom) < zoom:
                        page.click("button[aria-label='Zoom in']", timeout=2000)
                        current_zoom = page.evaluate("map.getZoom()")
                        page.wait_for_timeout(500)
                    while int(current_zoom) > zoom:
                        page.click("button[aria-label='Zoom out']", timeout=2000)
                        current_zoom = page.evaluate("map.getZoom()")
                        page.wait_for_timeout(500)
                append_log(logs, f"Adjusted zoom to {zoom}")
            except Exception:
                logger.info("Zoom controls not found; skipping zoom adjustment")
                append_log(logs, "Zoom adjustment skipped")

            # Determine centre coordinates for distance calculations
            origin_lat, origin_lng = extract_origin_coords(page, logger, logs)

            # For each selected category, apply filters or search
            for cat in categories:
                append_log(logs, f"Processing category: {cat}")
                logger.info(f"Processing category: {cat}")

                # Special handling for 病院・診療所
                if cat == "病院・診療所":
                    # Use search bar for this category
                    try:
                        search_box = page.query_selector("input[type=text]")
                        if search_box:
                           ound") extract (0 or negativ search_box.click()
                            search_box.fill(cat)
                            search_box.press("Enter")
                            append_log(logs, f"Searched for special category: {cat}")
                            page.wait_for_timeout(3000)
                    except Exception:
                        logger.warning(f"Failed to perform search for special category: {cat}")
                        append_log(logs, f"Search failed for {cat}")
                else:
                    # Try clicking category button in panel; fallback to search bar
                    clicked = False
                    for sel in [f"text='{cat}'", f"button:has-text('{cat}')", f"[role=button]:has-text('{cat}')"]:
                        try:
                            element = page.query_selector(sel)
                            if element:
                                element.click()
                                clicked = True
                                append_log(logs, f"Clicked category button {cat}")
                                page.wait_for_timeout(2000)
                                break
                        except Exception:
                            continue
                    if not clicked:
                        # fallback to search bar
                        try:
                            search_box = page.query_selector("input[type=text]")
                            if search_box:
                                search_box.click()
                                search_box.fill(cat)
                                search_box.press("Enter")
                                append_log(logs, f"Searched for category via search: {cat}")
                                page.wait_for_timeout(3000)
                        ption:
                            append_log(logs, f"Failed to search for category {cat}")

                # Wait briefly for markers to refresh
                page.wait_for_timeout(2000)

                # Get markers count to iterate through
                marker_count = 0
                for sel in MARKER_SELECTORS:
                    try:
                        markers = page.query_selector_all(sel)
                        if markers:
                            marker_count = len(markers)
                            break
                    except Exception:
                        continue
                append_log(logs, f"Found {marker_count} markers for category {cat}")
                logger.info(f"Found {marker_count} markers for category {cat}")
                # If no markers found, try to scroll or zoom slightly to provoke loading
                if marker_count == 0:
                    page.mouse.wheel(0, 200)  # Scroll down
                    page.wait_for_timeout(2000)
                    for sel in MARKER_SELECTORS:
                        markers = page.query_selector_all(sel)
                        if markers:
                            marker_count = len(markers)
                            append_log(logs, f"After scrolling, markers = {marker_count}")
                            break

                # Iterate over markers
                for idx in range(marker_count):
                    # Respect maximum items
                    if max_items and len(data_records) >= max_items:
                        append_log(logs, f"Reached maximum of {max_items} items, stopping.")
                        break
                    success = locate_and_click_marker(page, idx, logger, logs)
                    if not success:
except E  append_log(logs, f"Failed to click marker {idx} for category {cat}")
                        continue
                    # Wait for detail panel to appear
                    page.wait_for_timeout(1000)
                    try:
                        record = parse_detail_panel(page, logger, logs, origin_lat, origin_lng)
                        record["カテゴリ"] = cat
                        record["取得時刻"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        data_records.append(record)
                        append_log(logs, f"Extracted record for marker {idx}: {record['店舗名']}")
                    except Exception as e:
                        logger.warning(f"Error parsing marker {idx}: {e}")
                        append_log(logs, f"Error parsing marker {idx}: {e}")
                        continue

                # If maximum reached, break outer loop
                if max_items and len(data_records) >= max_items:
                    break

        # End of Playwright context
    except Exception as exc:
        logger.exception("Scraping failed with exception")
        append_log(logs, f"Scraping failed: {exc}")
        return ScrapeResult(pd.DataFrame(), logs)

    # Construct DataFrame
    if data_records:
        df = pd.DataFrame(data_records)
    else:
        df = pd.DataFrame(columns=["店舗名", "電話番号", "住所", "営業時間", "緯度", "経度", "距離_m", "距離_km", "カテゴリ", "取得時刻"])

    # Deduplicate on key (店舗名＋住所)
    if not df.empty:
        df["_key"] = df["店舗名"].fillna("").astype(str) + df["住所"].fillna("").astype(str)
        df["_key_norm"] = df["_key"].apply(normalize_key)
        df = df.drop_duplicates(subset="_key_norm")
        df = df.drop(columns=["_key", "_key_norm"])

    return ScrapeResult(df, logs)
xcee means no liex: {addr
