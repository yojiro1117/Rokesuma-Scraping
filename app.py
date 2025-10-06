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

from selectors_def import DEFAULT_CATEGORIES
from scraper import scrape_locations, ScrapeResult

import math
import folium  # for map rendering
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
import streamlit.components.v1 as components


def geocode_address(query: str) -> tuple[float, float]:
    """Geocode a free‑form address into latitude and longitude.

    Parameters
    ----------
    query : str
        Address to geocode.

    Returns
    -------
    tuple[float, float]
        Tuple of (latitude, longitude).  If geocoding fails a
        reasonable default centred on Fukuoka is returned.
    """
    try:
        geolocator = Nominatim(user_agent="rokesuma_app")
        location = geolocator.geocode(query)
        if location:
            return (location.latitude, location.longitude)
    except Exception:
        pass
    # Fallback to Fukuoka Station area if geocoding fails
    return (33.5902, 130.4200)


def reverse_geocode(lat: float, lon: float) -> str:
    """Reverse geocode coordinates into an address.

    Parameters
    ----------
    lat : float
        Latitude.
    lon : float
        Longitude.

    Returns
    -------
    str
        Human‑readable address or a lat/lon string if reverse geocoding fails.
    """
    try:
        geolocator = Nominatim(user_agent="rokesuma_app")
        location = geolocator.reverse((lat, lon), exactly_one=True)
        if location and location.address:
            return location.address
    except Exception:
        pass
    return f"{lat:.5f},{lon:.5f}"


def estimate_radius_m(lat: float, zoom: int) -> float:
    """Estimate the map radius in metres for a given latitude and zoom.

    This calculation approximates the visible half‑width of the map at
    the current zoom level.  It assumes a map viewport around 800
    pixels wide.  The formula derives from the Web Mercator projection.
    """
    # metres per pixel at equator for zoom level 0
    base_res = 156543.03392
    # adjust for latitude and zoom
    meters_per_pixel = base_res * math.cos(math.radians(lat)) / (2 ** zoom)
    # radius is half the viewport width in pixels (800px/2)
    return meters_per_pixel * 400


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

    # Initialize persistent session state values
    if "address" not in st.session_state:
        st.session_state.address = "福岡市博多区博多駅中央街1-1"
    if "lat" not in st.session_state or "lon" not in st.session_state:
        lat0, lon0 = geocode_address(st.session_state.address)
        st.session_state.lat = lat0
        st.session_state.lon = lon0
    if "zoom" not in st.session_state:
        st.session_state.zoom = 13

    # Layout: use two columns for controls and map.  The left column
    # contains all input controls; the right column shows both an
    # interactive map (for centre/zoom selection) and an embedded
    # ロケスマWEB iframe so users can visually verify the scraping
    # progress.  Using a two‑column layout keeps the interface tidy
    # and allows the map to occupy more horizontal space.
    col1, col2 = st.columns([1, 2], gap="small")

    with col1:
        st.header("設定")
        # Address input; update coordinates when changed
        new_address = st.text_input(
            "中心住所",
            value=st.session_state.address,
            help="地図の中心となる住所を入力します。"
        )
        if new_address != st.session_state.address and new_address.strip():
            st.session_state.address = new_address
            lat_tmp, lon_tmp = geocode_address(new_address)
            st.session_state.lat, st.session_state.lon = lat_tmp, lon_tmp

        # Zoom input (number input) and update state
        zoom_value = st.number_input(
            "ズームレベル (8〜18)",
            min_value=8,
            max_value=18,
            value=int(st.session_state.zoom),
            step=1,
            help="地図のズームレベルを指定します。"
        )
        if zoom_value != st.session_state.zoom:
            st.session_state.zoom = int(zoom_value)

        # Approximate radius display next to zoom control
        approx_radius = estimate_radius_m(st.session_state.lat, st.session_state.zoom)
        st.caption(f"\U0001F4CD このズームレベルの範囲: 半径約 {approx_radius:,.0f} m")

        # Category selection from default categories
        category_options = DEFAULT_CATEGORIES
        categories: List[str] = st.multiselect(
            "カテゴリ (複数選択可)",
            options=category_options,
            default=[category_options[0]] if category_options else [],
            help="抽出したいカテゴリを選択してください。"
        )
        # Ensure "病院・診療所" stays at end to act as a fallback
        if "病院・診療所" in categories:
            categories = [c for c in categories if c != "病院・診療所"] + ["病院・診療所"]

        # Headless mode checkbox with tooltip icon
        headless = st.checkbox("ヘッドレスモード", value=True)
        # Provide a question‑mark icon with a tooltip explaining headless mode.
        st.markdown(
            '<span title="ヘッドレスモードではブラウザのウィンドウを表示せずにバックグラウンドで実行します。\n通常はONのままで問題ありませんが、実行状況を目視したい場合はOFFにしてください。" style="cursor: help; color: #999; font-size:20px;">❓</span>',
            unsafe_allow_html=True,
        )

        # Maximum count per category
        max_count_input = st.text_input(
            "最大件数 (空欄または0で全件)",
            value="0",
            help="カテゴリ毎に処理する最大マーカー数"
        )
        try:
            max_count: Optional[int] = int(max_count_input)
            if max_count <= 0:
                max_count = None
        except ValueError:
            max_count = None

        # Note about Excel output location
        st.caption("※ 抽出結果はExcelファイルとしてダウンロードされ、ブラウザのダウンロードフォルダに保存されます。")

        execute = st.button("抽出を実行")

    with col2:
        # Show an interactive map using folium to allow the user to adjust
        # the centre coordinates and zoom.  When the map is dragged or
        # zoomed, the session state is updated and the address is
        # reverse‑geocoded automatically.  This map is used solely for
        # selecting the search area; data scraping is performed via
        # Playwright.
        try:
            m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=st.session_state.zoom)
            folium.Marker(
                [st.session_state.lat, st.session_state.lon],
                tooltip="中心",
                popup="中心",
            ).add_to(m)
            map_output = st_folium(m, key="folium_map", width="100%", height=400)
            if isinstance(map_output, dict):
                centre = map_output.get("center")
                new_zoom = map_output.get("zoom")
                if centre:
                    new_lat, new_lon = centre
                    if new_lat is not None and new_lon is not None:
                        # Update state if changed
                        if abs(new_lat - st.session_state.lat) > 1e-6 or abs(new_lon - st.session_state.lon) > 1e-6:
                            st.session_state.lat = float(new_lat)
                            st.session_state.lon = float(new_lon)
                            # Attempt to update address
                            rev = reverse_geocode(st.session_state.lat, st.session_state.lon)
                            st.session_state.address = rev
                if new_zoom is not None and new_zoom != st.session_state.zoom:
                    st.session_state.zoom = int(new_zoom)
        except Exception:
            st.error("マップの表示に失敗しました。folium または streamlit‑folium がインストールされていることを確認してください。")

        # Embed the official ロケスマWEB site alongside the interactive map.
        # A simple iframe is used for display purposes; note that we
        # cannot programmatically control or extract data from this
        # embedded page due to browser sandboxing, so it serves only
        # as a visual reference for users during scraping.
        # We avoid passing query parameters as they are not officially
        # documented; instead we show the default landing page.
        components.html(
            '<iframe src="https://www.locationsmart.org/" width="100%" height="400" frameborder="0"></iframe>',
            height=400,
            scrolling=True,
        )

    # Placeholders for logs, data table and download button
    log_placeholder = st.empty()
    data_placeholder = st.empty()
    download_placeholder = st.empty()

    if execute:
        logger = setup_logging()
        with st.spinner("抽出を実行中... お待ちください。"):
            # Use the current latitude and longitude as the address string
            coord_address = f"{st.session_state.lat},{st.session_state.lon}"
            result: ScrapeResult = scrape_locations(
                address=coord_address,
                zoom=st.session_state.zoom,
                categories=categories,
                headless=headless,
                max_count=max_count,
                logger=logger,
            )
        log_text = "\n".join(result.log_lines)
        log_placeholder.text_area(
            "進捗ログ", log_text, height=200, max_chars=None, disabled=True
        )
        if not result.dataframe.empty:
            st.success(f"{len(result.dataframe)} 件のデータを取得しました。")
            data_placeholder.dataframe(result.dataframe, use_container_width=True)
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