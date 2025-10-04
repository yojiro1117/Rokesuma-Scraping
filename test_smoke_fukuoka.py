"""Smoke test for the Rokesuma scraper using a Fukuoka address.

These tests are intended to run quickly and simply verify that the
scraper can return at least one result for a well known address and
category.  They should not be treated as exhaustive but rather as
sanity checks that the scraping pipeline executes without raising
unexpected exceptions.
"""

import logging

from scraper import scrape_locations


def test_fukuoka_smoke() -> None:
    # Use a minimal logger to suppress console output during tests
    logger = logging.getLogger("test_fukuoka_smoke")
    result = scrape_locations(
        address="福岡市博多区博多駅中央街1-1",
        zoom=13,
        categories=["コンビニ"],
        headless=True,
        max_count=1,
        logger=logger,
    )
    assert not result.dataframe.empty, "No data returned for Fukuoka smoke test"