"""Utility functions for the ロケスマ scraping application.

This module contains helper routines for extracting information
using regular expressions, computing distances and deduplicating
rows.  Isolating these concerns outside of the scraper simplifies
testing and keeps the scraping code focused on browser automation.
"""

from __future__ import annotations

import re
import math
import urllib.parse
from typing import Iterable, List, Dict, Optional, Tuple, Any


# Regular expression patterns for phone numbers, addresses and hours.
_PHONE_RE = re.compile(r"\d{2,4}-\d{2,4}-\d{3,4}")
_POSTCODE_RE = re.compile(r"〒?\d{3}-\d{4}")


def extract_phone(text: str) -> str:
    """Extract a phone number from the given text.

    The pattern matches Japanese phone numbers in the form
    `xxx-xxxx-xxxx` or `xx-xxxx-xxxx`.  If no phone number is found
    an empty string is returned.
    """
    if not text:
        return ""
    match = _PHONE_RE.search(text)
    return match.group(0) if match else ""


def extract_address(text: str) -> str:
    """Attempt to extract an address from arbitrary text.

    This function splits the text into lines and returns the first line
    containing common Japanese address components such as '県', '府',
    '市', '区', '町' or '村'.  If none of these tokens are present
    the function returns an empty string.
    """
    if not text:
        return ""
    lines = text.splitlines()
    for line in lines:
        stripped = line.strip()
        if any(tok in stripped for tok in ["県", "府", "市", "区", "町", "村"]):
            return stripped
    return ""


def extract_hours(text: str) -> str:
    """Attempt to extract opening hours from text.

    The function looks for lines containing the character '時' which is
    often present in Japanese time ranges.  If multiple lines match
    the first is returned.
    """
    if not text:
        return ""
    for line in text.splitlines():
        if "時" in line or "AM" in line.upper() or "PM" in line.upper():
            return line.strip()
    return ""


def parse_coords_from_url(url: str) -> Optional[Tuple[float, float]]:
    """Parse latitude and longitude from a URL.

    Many mapping services encode the map centre or selected location
    coordinates in the URL as `@lat,lng` or `ll=lat,lng`.  This
    function decodes percent‑encoded characters and searches for
    patterns matching these formats.  If no coordinates are found
    `None` is returned.
    """
    if not url:
        return None
    # Unquote percent encoded parts and normalise the separator
    decoded = urllib.parse.unquote(url)
    # Normalise stray spaces around the @ symbol
    decoded = decoded.replace("@ ", "@").replace(" @", "@")
    # Pattern 1: @lat,lng
    m = re.search(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", decoded)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except ValueError:
            pass
    # Pattern 2: ll=lat,lng or q=lat,lng
    m = re.search(r"(?:ll|q)=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", decoded)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except ValueError:
            pass
    return None


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[float, float]:
    """Compute the great circle distance between two points.

    The haversine formula is used to calculate the distance on the
    Earth's surface given two latitude/longitude pairs.  The function
    returns the distance in metres and kilometres.  If any of the
    inputs are NaN a distance of 0 is returned.
    """
    # Convert degrees to radians
    try:
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = phi2 - phi1
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance_m = 6371000.0 * c
        distance_km = distance_m / 1000.0
        return distance_m, distance_km
    except Exception:
        return 0.0, 0.0


def unique_by_name_address(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate a list of result dictionaries by store name and address.

    Because ロケスマ can display the same facility multiple times when
    searching different categories or when markers overlap, the key
    `(店舗名, 住所)` is used to identify duplicates.  The first
    occurrence of a given key is kept.
    """
    seen: set[Tuple[str, str]] = set()
    unique_rows: List[Dict[str, Any]] = []
    for row in rows:
        key = (row.get("店舗名", ""), row.get("住所", ""))
        if key not in seen:
            seen.add(key)
            unique_rows.append(row)
    return unique_rows