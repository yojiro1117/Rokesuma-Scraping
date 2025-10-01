"""Selectors definitions for scraping the ロケスマ site.

The site structure can vary across versions and categories.  To make the
scraper robust against changes, the scraping logic iterates over lists of
candidate selectors defined in this module.  When adding or updating
selectors, keep the order from most specific to most general.  Only the
first match per field is used.
"""

# Selectors for map markers.  These selectors should return a list of
# elements corresponding to clickable markers on the map.  The list is
# ordered as they appear in the DOM; scraping logic clicks markers in this
# order.
MARKER_SELECTORS = [
    "div.leaflet-marker-icon",
    "img.leaflet-marker-icon",
    "div.gmnoprint img",        # Google Maps style markers
    "div.gmnoprint",
]

# Candidate selectors for the store name in the detail panel or popup.
# Many elements on the site display the name as a heading.  Adjust these
# selectors as necessary when the site layout evolves.
STORE_NAME_SELECTORS = [
    "div.storePanel h2",
    "div.storePanel h1",
    "div.place-name",
    ".place-name",
    "h1",
    "h2",
]

# Candidate selectors for the address field.  The address is often
# presented with a label (e.g. "住所" or "所在地").  Where CSS labels are
# unreliable this list can be extended with XPath expressions.
ADDRESS_SELECTORS = [
    "div:has-text('住所') + div",
    "div:has-text('所在地') + div",
    "span.address",
    ".address",
    ".address-wrap",
]

# Candidate selectors for the phone number.  A tel link is the preferred
# method of extraction because it provides clean digits.  If the site
# removes tel links this list can be extended with additional selectors.
PHONE_SELECTORS = [
    "a[href^='tel']",
    "a.js-phone-number",
    ".phone-number",
    "div:has-text('電話') span",
]

# Candidate selectors for opening hours.  Hours are often labelled
# explicitly but may also appear within an unstructured blob of text.  The
# scraper falls back to a regex if none of these selectors return text.
HOURS_SELECTORS = [
    "div:has-text('営業時間') + div",
    "div:has-text('時間') + div",
    ".business-hours",
    ".opening-hours",
    "span.hours",
]
