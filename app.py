"""Streamlit application for scraping location information from the ロケスマ web site.

This module defines the UI and orchestrates execution of the scraping logic.  Users
select a centre address, zoom level, one or more categories, whether the
browser should run headless and optionally cap the number of items to
collect.  The application calls into the scraper module to perform the
playwright driven scraping and displays the results.  It also writes an
Excel file to a fixed location on the user's desktop and exposes a
download button within the app.

The UI reflects the design described in the project brief: a sidebar with
controls and a main area that displays progress, logs and the result
DataFrame.  Logs are streamed back to the UI to aid debugging and
transparency during long running operations.
"""

import io
import os
import datetime
import logging
from typing import List, Tuple

import streamlit as st
import pandas as pd

from utils import get_categories_list
from scraper import scrape_locations, ScrapeResult


def setup_logging() -> logging.Logger:
    """Configure a logger that writes to both a file and an in-memory list.

    The in-memory list allows streaming logs back to the Streamlit UI while
    the file provides persistent logs for later inspection.  Each run of the
    application creates a new log file with a timestamp in the logs
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

    logger = logging.getLogger("lokesma_app")
    logger.setLevel(logging.INFO)
    # Remove any pre‑existing handlers so we don't duplicate messages
    for h in list(logger.handlers):
        logger.removeHandler(h)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler = logging.FileHandler(logfile, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def save_excel(df: pd.DataFrame, timestamp: str) -> str:
    """Save the provided DataFrame to an Excel file on the user's desktop.

    A fixed naming convention is used: ロケスマ抽出_YYYYMMDD_HHMMSS.xlsx.  The
    Desktop path is hard coded to C:\\Users\\user\\Desktop as specified in the
    requirements.  Any existing file with the same name will be overwritten.

    Parameters
    ----------
    df : pandas.DataFrame
        The result DataFrame to write.
    timestamp : str
        Timestamp string to include in the filename.

    Returns
    -------
    str
        The absolute path of the written file.
    """
    # Compose the filename and ensure the directory exists
    desktop_path = os.path.join("C:", "Users", "user", "Desktop")
    os.makedirs(desktop_path, exist_ok=True)
    file_name = f"ロケスマ抽出_{timestamp}.xlsx"
    file_path = os.path.join(desktop_path, file_name)
    # Write the Excel file using openpyxl engine for UTF‑µ৺µ°Bßñº»µ¡ safety
    df.to_excel(file_path, index=False, engine="openpyxl")
    return file_path


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Convert a DataFrame into an Excel binary for download via Streamlit.

    Streamlit's `download_button` requires the data to be provided as a
    bytes-like object.  Writing to an in-memory BytesIO allows the same
    DataFrame to be both saved to disk and offered for download.

    Parameters
    ----------
    df : pandas.DataFrame
        The DataFrame to convert.

    Returns
    -------
    bytes
        The binary Excel representation.
    """
    with io.BytesIO() as buffer:
        df.to_excel(buffer, index=False, engine="openpyxl")
        return buffer.getvalue()


def main() -> None:
    """Main entrypoint for the Streamlit app."""
    st.set_page_config(page_title="ロケスマ情報抽出ツール", layout="wide")
    st.title("ロケスマ情報抽出ツール")
    st.write(
        "中心住所とカテゴリを指定して、ロケスマの地図上にあるチェーン店情報を自動収集します。"
    )

    # Initialise logger
    logger = setup_logging()

    # Sidebar inputs
    with st.sidebar:
        st.header("検索条件")
        default_address = "福岡市南区地中大桥 3 丁目"
        address = st.text_input("住所", value=default_address, help="中心となる住所を入力します。")
        zoom = st.slider("ズームレベル", min_value=8, max_value=18, value=13, step=1,
                         help="初期表示時のズームを指定します。")
        categories_list = get_categories_list()
        default_categories = [categories_list[0]] if categories_list else []
        selected_categories = st.multiselect(
            "カテゴリ (複数選択可)", options=categories_list, default=default_categories,
            help="抽出対象とするカテゴリを選択してください。"
        )
        headless = st.checkbox("ヘッドレスモード", value=True,
                               help="オフにするとブラウザが表示されます。")
        max_items = st.number_input(
            "最大件数", min_value=0, value=0, step=1,
            help="0または空欄は全件抽出します。"
        )
        run_button = st.button("抽出を実行")

    # Placeholder areas for dynamic content
    status_placeholder = st.empty()
    log_placeholder = st.empty()
    result_placeholder = st.empty()
    download_placeholder = st.empty()

    # Execute scraping when button pressed
    if run_button:
        if not address:
            st.warning("住所を入力してください。")
            return
        if not selected_categories:
            st.warning("少なくとも1つカテゴリを選択してください。")
            return

        # Capture start time and inform user
        start_time = datetime.datetime.now()
        timestamp = start_time.strftime("%Y%m%d_%H%M%S")
        status_placeholder.info("処理を開始しました。ブラウザ操作中です…")
        logger.info(
            f"Starting scrape: address='{address}', zoom={zoom}, categories={selected_categories}, headless={headless}, max_items={max_items}"
        )

        # Perform scraping
        try:
            result: ScrapeResult = scrape_locations(
                address=address,
                zoom=zoom,
                categories=selected_categories,
                headless=headless,
                max_items=int(max_items) if max_items else 0,
                logger=logger,
            )
        except Exception as exc:
            logger.exception("An unhandled exception occurred during scraping.")
            status_placeholder.error("抽出中にエラーが発生しました。ログファイルを確認してください。")
            return

        # DataFrame and logs from scraping
        df = result.dataframe
        scrape_logs = result.log_lines

        # Deduplicate and sort by distance
        if not df.empty:
            df = df.sort_values(by=["距離_m"]).reset_index(drop=True)

        # Save Excel to desktop
        file_path = save_excel(df, timestamp)

        # Update UI with results
        if df.empty:
            status_placeholder.warning("該当する店舗が見つかりませんでした。条件を変更して再試行してください。")
        else:
            status_placeholder.success(
                f"{len(df)} 件の店舗を抽出しました。Excelファイルを {file_path} に保存しました。"
            )

        # Show DataFrame in UI
        result_placeholder.subheader("抽出結果")
        result_placeholder.dataframe(df)

        # Provide download button in the app
        excel_bytes = dataframe_to_excel_bytes(df)
        download_placeholder.download_button(
            label="結果をダウンロード (Excel)",
            data=excel_bytes,
            file_name=os.path.basename(file_path),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # Display logs: show last 100 lines for brevity
        log_placeholder.subheader("ログ")
        display_lines = scrape_logs[-100:] if scrape_logs else []
        log_placeholder.text("\n".join(display_lines))


if __name__ == "__main__":
    main()
