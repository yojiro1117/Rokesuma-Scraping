"""CSS selector definitions for scraping the ロケスマ web application.

The ロケスマ site is built with a combination of the Leaflet and
Google Maps libraries.  Markers and detail panels are constructed
dynamically which means their structure can differ depending on the
selected map type and view.  To make the scraper resilient the
selectors defined here specify multiple candidates for each piece
of information.  The scraping logic iterates through the lists in
order until it finds a match.

Should the site change in the future you can update these lists
without modifying the main scraping code.  When adding selectors
remember to put more specific selectors earlier in the list.
"""

# Markers on the map.  These selectors should return a list of
# elements corresponding to clickable markers.  Some maps use
# Leaflet markers (`div.leaflet-marker-icon`), others use Google
# Maps markers (`div.gmoprint img`).
MARKER_SELECTORS = [
    "div.leaflet-marker-icon",
    "img.leaflet-marker-icon",
    "div.gmnoprint",
    "div.gmoprint img",
    "div.gm-style-iw div[role='button']"
]

# Candidate selectors for the store name displayed in the detail panel
# or popup.  These selectors are tried in order.
STORE_NAME_SELECTORS = [
    "div#storePanel h2",
    "div#storePanel h1",
    "div.storePanel h2",
    "div.storePanel h1",
    "div#detailPanel h2",
    "div#detailPanel h1",
    "div.leaflet-popup-content h2",
    "div.leaflet-popup-content h1"
]

# Candidate selectors for the address field.
ADDRESS_SELECTORS = [
    "div#storePanel .addr",
    "div.storePanel .addr",
    "div#storePanel p",
    "div.storePanel p",
    "div#detailPanel .addr",
    "div.leaflet-popup-content p"
]

# Candidate selectors for the phone number.
PHONE_SELECTORS = [
    "div#storePanel .tel",
    "div.storePanel .tel",
    "div#detailPanel .tel",
    "div#storePanel p:contains('電話')",
    "div.storePanel p:contains('電話')"
]

# Candidate selectors for the opening hours.
HOURS_SELECTORS = [
    "div#storePanel .hour",
    "div.storePanel .hour",
    "div#detailPanel .hour",
    "div.leaflet-popup-content .hour",
    "div#storePanel p:contains('時間')",
    "div.storePanel p:contains('時間')"
]


# A default list of categories to display in the Streamlit UI when
# automatic retrieval of categories from the site fails.  These
# represent common types of facilities users may wish to search for.
DEFAULT_CATEGORIES = [
    "コンビニ",
    "カフェ",
    "レストラン",
    "バーガー",
    "回転寿司/すし",
    "ラーメン",
    "牛丼",
    "ファミレス",
    "カレー",
    "ファストフード",
    "スイーツ",
    "ベーカリー",
    "居酒屋",
    "焼肉",
    "カラオケ",
    "コインパーキング",
    "ガソリンスタンド",
    "銀行ATM",
    "ドラッグストア",
    "スーパー",
    "ホームセンター",
    "電気店",
    "100円ショップ",
    "ファッション",
    "ホテル",
    "病院・診療所",
    "郵便局",
    "図書館",
    "スポーツクラブ"
]