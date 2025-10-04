"""Smoke test for the Rokesuma scraper using an Osaka address."""

import logging

from scraper import scrape_locations


def test_osaka_smoke() -> None:
    logger = logging.getLogger("test_osaka_smoke")
    result = scrape_locations(
        address="大阪市北区梅田3-1-1",
        zoom=13,
        categories=["スーパー"],
        headless=True,
        max_count=1,
        logger=logger,
    )
    assert not result.dataframe.empty, "No data returned for Osaka smoke test"