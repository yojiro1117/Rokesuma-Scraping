"""Streamlit application for scraping ロケスマ location data."""

from __future__ import annotations
import io
import os
import datetime
import logging
from typing import List, Optional
import math
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from folium.plugins import MarkerCluster
import folium
from geopy.geocoders import Nominatim
from streamlit_folium import st_folium

from selectors_def import DEFAULT_CATEGORIES
from scraper import scrape_locations, ScrapeResult, ensure_chromium


def geocode_address(query: str) -> tuple[float, float]:
    try:
        geolocator = Nominatim(user_agent="rokesuma_app")
        location = geolocator.geocode(query)
        if location:
            return (location.latitude, location.longitude)
    except Exception:
        pass
    return (33.5902, 130.4200)


def reverse_geocode(lat: float, lon: float) -> str:
    try:
        geolocator = Nominatim(user_agent="rokesuma_app")
        location = geolocator.reverse((lat, lon), exactly_one=True)
        if location and location.address:
            return location.address
    except Exception:
        pass
    return f"{lat:.5f},{lon:.5f}"


def estimate_radius_m(lat: float, zoom: int) -> float:
    base_res = 156543.03392
    meters_per_pixel = base_res * math.cos(math.radians(lat)) / (2 ** zoom)
    return meters_per_pixel * 400


def setup_logging() -> logging.Logger:
    logs_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    logfile = os.path.join(logs_dir, f"app_{timestamp}.log")

    logger = logging.getLogger("rokesuma_app")
    logger.setLevel(logging.INFO)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler = logging.FileHandler(logfile, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="data")
        worksheet = writer.sheets["data"]
        for i, col in enumerate(df.columns, start=1):
            max_len = max([len(str(x)) for x in df[col].tolist()] + [len(col)])
            worksheet.column_dimensions[chr(64 + i)].width = max_len + 2
    return output.getvalue()


def main() -> None:
    st.set_page_config(page_title="ロケスマ情報抽出ツール", layout="wide")
    st.title("ロケスマ情報抽出ツール")

    if "address" not in st.session_state:
        st.session_state.address = "福岡市博多区博多駅中央街1-1"
    if "lat" not in st.session_state or "lon" not in st.session_state:
        lat0, lon0 = geocode_address(st.session_state.address)
        st.session_state.lat = lat0
        st.session_state.lon = lon0
    if "zoom" not in st.session_state:
        st.session_state.zoom = 13

    col1, col2 = st.columns([1, 2], gap="small")

    with col1:
        st.header("設定")
        new_address = st.text_input(
            "中心住所",
            value=st.session_state.address,
            help="地図の中心となる住所を入力します。"
        )
        if new_address != st.session_state.address and new_address.strip():
            st.session_state.address = new_address
            lat_tmp, lon_tmp = geocode_address(new_address)
            st.session_state.lat, st.session_state.lon = lat_tmp, lon_tmp

        zoom_value = st.number_input(
            "ズームレベル (8〜18)",
            min_value=8, max_value=18, value=int(st.session_state.zoom),
            step=1, help="地図のズームレベルを指定します。"
        )
        if zoom_value != st.session_state.zoom:
            st.session_state.zoom = int(zoom_value)

        approx_radius = estimate_radius_m(st.session_state.lat, st.session_state.zoom)
        st.caption(f"\U0001F4CD このズームレベルの範囲: 半径約 {approx_radius:,.0f} m")

        category_options = DEFAULT_CATEGORIES
        categories: List[str] = st.multiselect(
            "カテゴリ (複数選択可)",
            options=category_options,
            default=[category_options[0]] if category_options else [],
            help="抽出したいカテゴリを選択してください。"
        )
        if "病院・診療所" in categories:
            categories = [c for c in categories if c != "病院・診療所"] + ["病院・診療所"]

        headless = st.checkbox("ヘッドレスモード", value=True)
        st.markdown(
            '<span title="ヘッドレスモードではブラウザを表示せず実行します。OFFで動作を目視確認可能。" style="cursor: help; color: #999; font-size:20px;">❓</span>',
            unsafe_allow_html=True,
        )

        max_count_input = st.text_input(
            "最大件数 (空欄または0で全件)",
            value="0", help="カテゴリ毎に処理する最大マーカー数"
        )
        try:
            max_count: Optional[int] = int(max_count_input)
            if max_count <= 0:
                max_count = None
        except ValueError:
            max_count = None

        st.caption("※ 抽出結果はExcelファイルとしてダウンロードされます。")
        execute = st.button("抽出を実行")

    with col2:
        try:
            m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=st.session_state.zoom)
            folium.Marker(
                [st.session_state.lat, st.session_state.lon], tooltip="中心", popup="中心",
            ).add_to(m)
            map_output = st_folium(m, key="folium_map", width="100%", height=400)
            if isinstance(map_output, dict):
                centre = map_output.get("center")
                new_zoom = map_output.get("zoom")
                if centre:
                    new_lat, new_lon = centre
                    if new_lat is not None and new_lon is not None:
                        if abs(new_lat - st.session_state.lat) > 1e-6 or abs(new_lon - st.session_state.lon) > 1e-6:
                            st.session_state.lat = float(new_lat)
                            st.session_state.lon = float(new_lon)
                            rev = reverse_geocode(st.session_state.lat, st.session_state.lon)
                            st.session_state.address = rev
                if new_zoom is not None and new_zoom != st.session_state.zoom:
                    st.session_state.zoom = int(new_zoom)
        except Exception:
            st.error("マップ表示に失敗しました。folium または streamlit-folium が必要です。")

        iframe_url = (
            f"https://www.locationsmart.org/"
            f"@{st.session_state.lat:.6f},{st.session_state.lon:.6f},{st.session_state.zoom}z"
        )
        components.html(
            f'<iframe src="{iframe_url}" width="100%" height="400" frameborder="0"></iframe>',
            height=400, scrolling=True,
        )

    log_placeholder = st.empty()
    data_placeholder = st.empty()
    download_placeholder = st.empty()

    if execute:
        logger = setup_logging()
        with st.spinner("Chromium 環境を確認中..."):
            ensure_chromium(logger)

        with st.spinner("抽出を実行中... お待ちください。"):
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
        log_placeholder.text_area("進捗ログ", log_text, height=200, disabled=True)

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
