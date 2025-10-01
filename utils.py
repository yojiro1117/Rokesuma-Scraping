"""Utility functions for the ロケスマ scraping project.

This module groups together a variety of helper functions used across the
application.  They include regular expression helpers for extracting
phone numbers, addresses and opening hours from unstructured text,
distance calculations using the haversine formula and text normalisation
for deduplication.
"""

import re
import math
import unicodedata
from typing import List, Tuple, Optional

import numpy as np


def get_categories_list() -> List[str]:
    """Return a static list of categories supported by the application.

    The list is derived from the ロケスマ service and covers typical
    chain store categories.  If the web UI exposes categories dynamically
    it may be desirable to fetch them at runtime, however for reliability
    a static list is provided here.

    Returns
    -------
    List[str]
        Names of categories in Japanese.
    """
    return [
        "コンビニ",
        "ドラッグストア",
        "調剤薬局",
        "スーパー",
        "飲食",
        "カフェ",
        "銀行",
        "ATM",
        "郵便局",
        "公共施設",
        "学校",
        "ガソリンスタンド",
        "コインランドリー",
        "家電量販店",
        "書店",
        "百貨店",
        "病院・診療所",
    ]


def normalize_text(text: str) -> str:
    """Normalise Japanese text by converting full/half width characters and trimming spaces."""
    if not isinstance(text, str):
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("\u3000", " ")  # full width space to normal space
    normalized = normalized.strip()
    return normalized


def normalize_key(key: str) -> str:
    """Return a normalised key used for deduplication (店舗名+住所)."""
    return normalize_text(key).lower()


def extract_phone(text: str) -> Optional[str]:
    """Extract a Japanese phone number from the given text using regex.

    Matches patterns such as 03-1234-5678, 090-1234-5678, 0120-123-456 etc.
    Returns only the first match.
    """
    phone_regex = re.compile(r"(0\d{1,4}-\d{1,4}-\d{3,4})")
    match = phone_regex.search(text)
    return match.group(1) if match else None


def extract_address(text: str) -> Optional[str]:
    """Attempt to extract an address from free text.

    The implementation looks for typical Japanese prefecture/city markers
    followed by two or more characters.  This is heuristic and may need
    tuning depending on the input.
    """
    # Prefecture names (partial list) for simple heuristics
    prefectures = [
        "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県", "茨城県", "栃木県", "群馬県",
        "埼玉県", "千葉県", "東京都", "神奈川県", "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
        "岐阜県", "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
        "鳥取県", "島根県", "岡山県", "広島県", "山口県", "徳島県", "香川県", "愛媛県", "高知県", "福岡県",
        "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
    ]
    for pref in prefectures:
        idx = text.find(pref)
        if idx != -1:
            # Return substring starting at prefecture and spanning until line break
            remaining = text[idx:]
            lines = remaining.split("\n")
            if lines:
                line = lines[0].strip()
                # Basic sanity check: ensure it contains a number
                if re.search(r"\d", line):
                    return line
    return None


def extract_hours(text: str) -> Optional[str]:
    """Extract opening hours from free text.

    Looks for patterns like '10:00〜22:00', '9:00-19:30', etc.  Returns the
    first occurrence.
    """
    hours_regex = re.compile(r"(\d{1,2}:\d{2}\s*[〜\-]\s*\d{1,2}:\d{2})")
    match = hours_regex.search(text)
    return match.group(1) if match else None


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[float, float]:
    """Calculate the great circle distance between two points on Earth (haversine).

    Parameters
    ----------
    lat1, lon1 : float
        Latitude and longitude of the first point in decimal degrees.
    lat2, lon2 : float
        Latitude and longitude of the second point in decimal degrees.

    Returns
    -------
    Tuple[float, float]
        Distance in metres and kilometres.
    """
    # Radius of the Earth in metres
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance_m = R * c
    distance_km = distance_m / 1000.0
    return round(distance_m, 3), round(distance_km, 3)
