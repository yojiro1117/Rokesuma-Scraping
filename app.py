"""Streamlit application for scraping ロケスマ location data.

This module defines the UI and orchestrates execution of the scraping logic.
Users select a centre address, zoom level, one or more categories, whether
the browser should run headless and optionally cap the number of items to
collect.  The application calls into the scraper to perform the
Playwright‑driven scraping and displays the results.  It also writes an
Excel file to a fixed location on the user's desktop and exposes a
download button within the app.

The UI reflects the design described in the project brief: a sidebar with
controls and a main area that displays progress logs, the result
DataFrame and a download button.  Logs are streamed back to the UI to
aid debugging and transparency during long running operations.
"""

from __future__ import annotations

import io
import os
import datetime
import logging
from typing import List, Optional

import pandas as pd
import streamlit as st

from selectors import DEFAULT_CATEGORIES
from scraper import scrape_locations, ScrapeResult


def setup_logging() -> logging.Logger:
    """Configure a logger that writes to both a file and an in‑memory list.

    The file provides persistent logs for later inspection.  Each run of
    the application creates a new log file with a timestamp in the logs
    directory.

    Returns
    -------
    logging.Logger
        A logger instance ready for use by the scraping routines.
    """
    logs_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    logfile = os.path.join(logs_dir, f"app_{timestamp}.log")

    logger = logging.getLogger("rokesuma_app")
    logger.setLevel(logging.INFO)
    # Remove existing handlers to avoid duplicate messages if the user
    # re-runs the app
    for h in list(logger.handlers):
        logger.removeHandler(h)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler = logging.FileHandler(logfile, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Convert a DataFrame into an Excel file stored in memory.

    The result is returned as raw bytes suitable for feeding into
    Streamlit's `download_button`.  Column widths are automatically
    adjusted to fit their contents.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to convert.

    Returns
    -------
    bytes
        Excel file contents.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="data")
        worksheet = writer.sheets["data"]
        # Adjust column widths based on the maximum length in each column
        for i, col in enumerate(df.columns, start=1):
            max_len = max(
                [len(str(x)) for x in df[col].tolist()] + [len(col)]
            )
            worksheet.column_dimensions[chr(64 + i)].width = max_len + 2
    return output.getvalue()


def main() -> None:
    """Render the Streamlit UI and handle user interactions."""
    st.set_page_config(page_title="ロケスマ情報抽出ツール", layout="wide")
    st.title("ロケスマ情報抽出ツール")

    # Sidebar inputs
    with st.sidebar:
        st.header("設定")
        address = st.text_input(
            "中心住所",
            value="福岡市博多区博多駅中央街1-1",
            help="地図の中心となる住所を入力します。",
        )
        zoom = st.number_input(
            "ズームレベル (8〜18)",
            min_value=8,
            max_value=18,
            value=13,
            step=1,
            help="地図のズームレベルを指定します。",
        )
        # Category selection.  Use the default list defined in selectors.
        category_options = DEFAULT_CATEGORIES
        categories: List[str] = st.multiselect(
            "カテゴリ (複数選択可)",
            options=category_options,
            default=[category_options[0]],
            help="抽出したいカテゴリを選択してください。",
        )
        # Special handling for hospital/clinic.  If selected we also
        # automatically include the search term in the categories list to
        # search via the search bar when no matching entry exists in the
        # left panel of ロケスマ.
        if "病院・診療所" in categories:
            # This ensures the search term is typed explicitly even if not
            # present in the category list on the site
            categories = [c for c in categories if c != "病院・診療所"] + ["病院・診療所"]

        headless = st.checkbox(
            "ヘッドレスモード", value=True, help="ブラウザを画面に表示せずに実行します。"
        )
        max_count_input = st.text_input(
            "最大件数 (空欄または0で全件)", value="0", help="カテゴリ毎に処理する最大マーカー数"
        )
        # Convert to integer if possible
        try:
            max_count: Optional[int] = int(max_count_input)
            if max_count <= 0:
                max_count = None
        except ValueError:
            max_count = None

        execute = st.button("抽出を実行")

    # Main area
    log_placeholder = st.empty()
    data_placeholder = st.empty()
    download_placeholder = st.empty()

    if execute:
        logger = setup_logging()
        log_lines_ui: List[str] = []
        # Stream logs to the UI by polling the returned log list
        with st.spinner("抽出を実行中... お待ちください。"):
            result: ScrapeResult = scrape_locations(
                address=address,
                zoom=zoom,
                categories=categories,
                headless=headless,
                max_count=max_count,
                logger=logger,
            )
        # Display logs
        log_text = "\n".join(result.log_lines)
        log_placeholder.text_area(
            "進捗ログ", log_text, height=200, max_chars=None, disabled=True
        )
        # Display results
        if not result.dataframe.empty:
            st.success(f"{len(result.dataframe)} 件のデータを取得しました。")
            data_placeholder.dataframe(result.dataframe, use_container_width=True)
            # Create Excel for download
            excel_bytes = dataframe_to_excel_bytes(result.dataframe)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ロケスマ抽出_{timestamp}.xlsx"
            download_placeholder.download_button(
                label="Excel ダウンロード",
                data=excel_bytes,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.warning("データが取得できませんでした。条件を変えてお試しください。")


if __name__ == "__main__":
    main()