"""Scraping logic for the ロケスマ Streamlit application.

This module encapsulates all browser automation using Playwright.  It
exposes a single entry point `scrape_locations` which accepts search
parameters, launches a Chromium instance (honouring the headless flag)
and programmatically interacts with the ロケスマ web app.  For each
selected category the scraper clicks markers on the map one by one and
extracts structured information from the detail panel or popup.  Where
a value cannot be extracted directly from a specific DOM element the
implementation falls back to regular expressions applied to the full
visible text or URL based heuristics.

Errors and progress information are logged via the provided logger.  The
calling code is responsible for configuring logging handlers and
presenting log messages to the user.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import sys
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Any

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_fixed
from playwright.async_api import async_playwright

# Import selectors and default categories from selectors_def to avoid
# clashing with Python's built-in selectors module.  This module
# contains lists of CSS selectors and a fallback category list for
# situations where categories cannot be retrieved dynamically from
# ロケスマWEB.
from selectors_def import (
    MARKER_SELECTORS,
    STORE_NAME_SELECTORS,
    ADDRESS_SELECTORS,
    PHONE_SELECTORS,
    HOURS_SELECTORS,
    DEFAULT_CATEGORIES,
)

from utils import (
    extract_phone,
    extract_address,
    extract_hours,
    parse_coords_from_url,
    haversine_distance,
    unique_by_name_address,
)

# ---------------------------------------------------------------------------
# Runtime bootstrap (robust Chromium provisioning for Streamlit Cloud)
#
# On Streamlit Cloud the post-install script may not be executed
# automatically after dependency installation. As a result Playwright may
# not have downloaded a Chromium build. The helpers below perform a one-off
# installation of Chromium into a repo-local directory on first call and
# reuse it on subsequent runs to avoid cold starts / failures.

BASE_DIR = Path(__file__).resolve().parent
PLAYWRIGHT_DIR = BASE_DIR / "ms-playwright"
# Persist browsers under the repository so they survive app restarts
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(PLAYWRIGHT_DIR))


def _run(cmd: List[str]) -> None:
    """Run a subprocess, raising on non-zero exit for clear failures."""
    subprocess.run(cmd, check=True)


def ensure_chromium(logger: Optional[logging.Logger] = None) -> None:
    """Ensure that a Chromium browser is available for Playwright.

    - Installs Chromium into ./ms-playwright if not present.
    - Uses the *current* Python interpreter to invoke Playwright so that
      venv/path issues cannot cause 'command not found'.
    """
    try:
        PLAYWRIGHT_DIR.mkdir(parents=True, exist_ok=True)
        # Quick presence check: any chromium-* folder under PLAYWRIGHT_DIR
        if any(PLAYWRIGHT_DIR.glob("chromium-*")):
            if logger:
                logger.info("[setup] Chromium already present in ms-playwright.")
            return

        if logger:
            logger.info("[setup] Installing Chromium via Playwright...")
        _run([sys.executable, "-m", "playwright", "install", "chromium"])
        if logger:
            logger.info("[setup] Chromium install completed.")
    except Exception as e:
        if logger:
            logger.error(f"[setup] Chromium install failed: {e}")
        # Re-raise to make the failure explicit at launch time
        raise


@dataclass
class ScrapeResult:
    """Container for the result of a scrape.

    Attributes
    ----------
    dataframe : pd.DataFrame
        The DataFrame of extracted location information.
    log_lines : List[str]
        The list of log messages captured during the scrape.  Each
        message is prefixed with a timestamp to aid debugging.
    """

    dataframe: pd.DataFrame
    log_lines: List[str]


async def _scrape_async(
    address: str,
    zoom: int,
    categories: Optional[List[str]],
    headless: bool,
    max_count: Optional[int],
    logger: logging.Logger,
) -> ScrapeResult:
    """Asynchronous core scraping routine.

    This function is intended to be executed inside an asyncio event
    loop.  It performs all browser automation using Playwright's
    asynchronous API.  A synchronous wrapper is provided by
    `scrape_locations` which invokes this coroutine via
    `asyncio.run()`.
    """
    logs: List[str] = []

    def append_log(message: str) -> None:
        """Helper to record a log line with timestamp."""
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {message}"
        logs.append(entry)
        if logger:
            logger.info(message)

    # Use provided categories or fall back to default
    category_list = categories or []
    if not category_list:
        category_list = DEFAULT_CATEGORIES

    # Ensure Chromium is available before launching Playwright
    ensure_chromium(logger)

    # Keep track of the origin coordinates after searching the centre
    origin_lat: Optional[float] = None
    origin_lng: Optional[float] = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()

        # Visit ロケスマ（※実運用では正しい公式URLに合わせて修正してください）
        await page.goto("https://www.locationsmart.org/", timeout=60000)
        append_log("Loaded ロケスマWEB")

        # Locate the map search input. We try a handful of selectors to
        # improve resilience against UI changes.
        search_selectors = [
            "input[placeholder*='住所']",
            "input[aria-label*='検索']",
            "input[type='search']",
            "input[type='text']",
        ]
        search_input = None
        for sel in search_selectors:
            try:
                element = await page.query_selector(sel)
                if element:
                    search_input = element
                    break
            except Exception:
                continue

        # Enter the centre address to reposition the map (best-effort).
        if search_input:
            try:
                await search_input.fill(address)
                await search_input.press("Enter")
                append_log(f"Searched for centre address: {address}")
                # Give the map a moment to update
                await page.wait_for_timeout(2000)
                origin_coords = parse_coords_from_url(page.url)
                if origin_coords:
                    origin_lat, origin_lng = origin_coords
                    append_log(
                        f"Origin coordinates resolved from URL: {origin_lat}, {origin_lng}"
                    )
            except Exception as e:
                append_log(f"Failed to search centre address: {e}")
        else:
            append_log("Search input not found; proceeding without setting centre address")

        all_rows: List[Dict[str, Any]] = []

        # Iterate through the selected categories.  The ロケスマ search
        # input accepts both chain names and broader categories; after
        # entering the value and confirming we expect the map to
        # populate with markers corresponding to the selected category.
        for cat in category_list:
            # Clear the search input before typing a new category
            if search_input:
                try:
                    await search_input.fill("")
                    await search_input.type(cat)
                    await search_input.press("Enter")
                    append_log(f"Selected category: {cat}")
                    # Allow time for markers to load
                    await page.wait_for_timeout(2000)
                except Exception as e:
                    append_log(f"Failed to search category '{cat}': {e}")

            # Locate markers on the map.  Try each selector until we
            # find at least one candidate.  If none are found we log
            # and continue with the next category.
            marker_elements: List[Any] = []
            for msel in MARKER_SELECTORS:
                try:
                    elements = await page.query_selector_all(msel)
                    if elements:
                        marker_elements = elements
                        break
                except Exception:
                    continue
            if not marker_elements:
                append_log(f"No markers found for category '{cat}'")
                continue

            # Iterate over the markers.  For each marker click it,
            # extract details and append to the result list.  Respect
            # the max_count limit if provided.
            processed = 0
            for marker in marker_elements:
                if max_count and processed >= max_count:
                    break
                try:
                    await marker.click()
                    # Wait a short while for the detail panel or popup
                    await page.wait_for_timeout(800)

                    # Grab the entire visible text as a fallback
                    try:
                        full_text = await page.inner_text("body")
                    except Exception:
                        full_text = ""

                    # Extract store name
                    name: str = ""
                    for sel in STORE_NAME_SELECTORS:
                        try:
                            elem = await page.query_selector(sel)
                            if elem:
                                text = (await elem.inner_text()).strip()
                                if text:
                                    name = text
                                    break
                        except Exception:
                            continue

                    # Extract address
                    address_text: str = ""
                    for sel in ADDRESS_SELECTORS:
                        try:
                            elem = await page.query_selector(sel)
                            if elem:
                                text = (await elem.inner_text()).strip()
                                if text:
                                    address_text = text
                                    break
                        except Exception:
                            continue
                    if not address_text:
                        address_text = extract_address(full_text)

                    # Extract phone
                    phone_text: str = ""
                    for sel in PHONE_SELECTORS:
                        try:
                            elem = await page.query_selector(sel)
                            if elem:
                                text = (await elem.inner_text()).strip()
                                if text:
                                    phone_text = text
                                    break
                        except Exception:
                            continue
                    phone = extract_phone(phone_text or full_text)

                    # Extract hours
                    hours_text: str = ""
                    for sel in HOURS_SELECTORS:
                        try:
                            elem = await page.query_selector(sel)
                            if elem:
                                text = (await elem.inner_text()).strip()
                                if text:
                                    hours_text = text
                                    break
                        except Exception:
                            continue
                    hours = extract_hours(hours_text or full_text)

                    # Attempt to resolve coordinates.
                    lat: Optional[float] = None
                    lng: Optional[float] = None
                    try:
                        attr_lat = await marker.get_attribute("data-lat")
                        attr_lng = await marker.get_attribute("data-lng") or await marker.get_attribute("data-lon")
                        if attr_lat and attr_lng:
                            lat = float(attr_lat)
                            lng = float(attr_lng)
                    except Exception:
                        pass
                    # Fallback 1: parse from the URL
                    if lat is None or lng is None:
                        coords = parse_coords_from_url(page.url)
                        if coords:
                            lat, lng = coords
                            append_log("[URL→coords] Coordinates resolved from URL")
                    # Fallback 2: use map centre via JS API if available
                    if lat is None or lng is None:
                        try:
                            centre = await page.evaluate(
                                "(window.map && window.map.getCenter) ? [map.getCenter().lat, map.getCenter().lng] : null"
                            )
                            if centre:
                                lat, lng = float(centre[0]), float(centre[1])
                                append_log("Using map centre as coordinate fallback")
                        except Exception:
                            pass

                    # Compute distance from origin if possible
                    dist_m: Optional[float] = None
                    dist_km: Optional[float] = None
                    if (
                        lat is not None
                        and lng is not None
                        and origin_lat is not None
                        and origin_lng is not None
                    ):
                        dm, dk = haversine_distance(origin_lat, origin_lng, lat, lng)
                        dist_m = round(dm, 2)
                        dist_km = round(dk, 3)

                    row = {
                        "店舗名": name,
                        "電話番号": phone,
                        "住所": address_text,
                        "営業時間": hours,
                        "緯度": lat,
                        "経度": lng,
                        "距離_m": dist_m,
                        "距離_km": dist_km,
                        "カテゴリ": cat,
                        "取得時刻": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    all_rows.append(row)
                    processed += 1
                except Exception as e:
                    append_log(f"Error processing marker: {e}")
            append_log(f"Processed {processed} markers for category '{cat}'")

        # Close browser
        await browser.close()

    # Deduplicate results by name and address
    unique_rows = unique_by_name_address(all_rows)
    df = pd.DataFrame(unique_rows)
    return ScrapeResult(dataframe=df, log_lines=logs)


def scrape_locations(
    address: str,
    zoom: int = 13,
    categories: Optional[List[str]] = None,
    headless: bool = True,
    max_count: Optional[int] = None,
    logger: Optional[logging.Logger] = None,
) -> ScrapeResult:
    """Synchronously scrape locations from ロケスマ.

    Parameters
    ----------
    address : str
        Centre address used to focus the map before extracting data.
    zoom : int, optional
        Initial zoom level (currently unused but reserved for future
        enhancements), by default 13.
    categories : list of str, optional
        One or more category names to search.  If omitted the default
        category list from ``selectors.DEFAULT_CATEGORIES`` is used.
    headless : bool, optional
        Whether to run the browser in headless mode, by default True.
    max_count : int, optional
        Maximum number of markers to process per category.  Use 0 or
        ``None`` to process all markers.
    logger : logging.Logger, optional
        Logger instance for recording progress messages.  If None
        messages are stored in the returned log lines but not emitted
        elsewhere.

    Returns
    -------
    ScrapeResult
        Object containing a pandas DataFrame with the extracted data
        and a list of log lines.
    """
    # Normalise max_count: treat 0 or negative as unlimited
    max_count_norm: Optional[int] = None
    if max_count:
        try:
            mc = int(max_count)
            if mc > 0:
                max_count_norm = mc
        except Exception:
            pass

    return asyncio.run(
        _scrape_async(
            address=address,
            zoom=zoom,
            categories=categories,
            headless=headless,
            max_count=max_count_norm,
            logger=logger or logging.getLogger(__name__),
        )
    )
