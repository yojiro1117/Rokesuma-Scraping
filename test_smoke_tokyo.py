"""Smoke test for the Rokesuma scraper using a Tokyo address."""

import logging

from scraper import scrape_locations


def test_tokyo_smoke() -> None:
    logger = logging.getLogger("test_tokyo_smoke")
    result = scrape_locations(
        address="東京都千代田区丸の内1-9-1",
        zoom=13,
        categories=["カフェ"],
        headless=True,
        max_count=1,
        logger=logger,
    )
    assert not result.dataframe.empty, "No data returned for Tokyo smoke test"