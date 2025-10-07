"""Streamlit application for scraping ロケスマ location data.

Users choose an area and categories, then run a Playwright-based scraper.
The app shows a clear status panel, progress logs, result preview, and
download buttons for Excel and CSV. Defensive casting is used to avoid
type issues with st_folium return values.
"""

from __future__ import annotations

import io
import os
import datetime
import logging
from typing import List, Optional, Tuple, Union

import math
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

from selectors_def import DEFAULT_CATEGORIES
from scraper import scrape_locations, ScrapeResult


# ----------------------------- helpers --------------------------------------
def _as_float(x: Union[str, float, int, None]) -> Optional[float]:
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def geocode_address(query: str) -> Tuple[float, float]:
    try:
        geo = Nominatim(user_agent="rokesuma_app")
        loc = geo.geocode(query)
        if loc:
            return float(loc.latitude), float(loc.longitude)
    except Exception:
        pass
    # fallback: Fukuoka Station
    return 33.5902, 130.4200


def reverse_geocode(lat: float, lon: float) -> str:
    try:
        geo = Nominatim(user_agent="rokesuma_app")
        loc = geo.reverse((lat, lon), exactly_one=True)
        if loc and loc.address:
            return loc.address
    except Exception:
        pass
    return f"{lat:.5f},{lon:.5f}"


def estimate_radius_m(lat: float, zoom: int) -> float:
    base_res = 156543.03392  # m/px at z0
    mpp = base_res * math.cos(math.radians(lat)) / (2 ** zoom)
    return mpp * 400  # ~800px viewport half-width


def setup_logging() -> logging.Logger:
    logs_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    logfile = os.path.join(logs_dir, f"app_{ts}.log")

    logger = logging.getLogger("rokesuma_app")
    logger.setLevel(logging.INFO)
    for h in list(logger.handlers):
        logger.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="data")
        ws = writer.sheets["data"]
        for i, col in enumerate(df.columns, start=1):
            max_len = max([len(str(x)) for x in df[col].tolist()] + [len(col)])
            ws.column_dimensions[chr(64 + i)].width = max_len + 2
    return output.getvalue()


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


# ----------------------------------- UI -------------------------------------
def main() -> None:
    st.set_page_config(page_title="ロケスマ情報抽出ツール", layout="wide")
    st.title("ロケスマ情報抽出ツール")

    # Session defaults (force types)
    if "address" not in st.session_state:
        st.session_state.address = "福岡市博多区博多駅中央街1-1"
    if "lat" not in st.session_state or "lon" not in st.session_state:
        lat0, lon0 = geocode_address(st.session_state.address)
        st.session_state.lat = float(lat0)
        st.session_state.lon = float(lon0)
    else:
        st.session_state.lat = float(st.session_state.lat)
        st.session_state.lon = float(st.session_state.lon)
    if "zoom" not in st.session_state:
        st.session_state.zoom = 13
    else:
        st.session_state.zoom = int(st.session_state.zoom)

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
            st.session_state.lat, st.session_state.lon = float(lat_tmp), float(lon_tmp)

        zoom_val = st.number_input(
            "ズームレベル (8〜18)", min_value=8, max_value=18,
            value=int(st.session_state.zoom), step=1,
            help="地図のズームレベルを指定します。"
        )
        if zoom_val != st.session_state.zoom:
            st.session_state.zoom = int(zoom_val)

        approx_radius = estimate_radius_m(float(st.session_state.lat), int(st.session_state.zoom))
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

        execute = st.button("抽出を実行", type="primary")

    with col2:
        # Map
        try:
            m = folium.Map(
                location=[float(st.session_state.lat), float(st.session_state.lon)],
                zoom_start=int(st.session_state.zoom),
            )
            folium.Marker(
                [float(st.session_state.lat), float(st.session_state.lon)],
                tooltip="中心", popup="中心",
            ).add_to(m)

            map_output = st_folium(m, key="folium_map", width="100%", height=400)

            if isinstance(map_output, dict):
                centre = map_output.get("center")
                new_zoom = map_output.get("zoom")

                new_lat = new_lon = None
                if isinstance(centre, dict):
                    new_lat = _as_float(centre.get("lat") or centre.get("latitude"))
                    new_lon = _as_float(centre.get("lng") or centre.get("lon") or centre.get("longitude"))
                elif isinstance(centre, (list, tuple)) and len(centre) == 2:
                    new_lat = _as_float(centre[0])
                    new_lon = _as_float(centre[1])

                prev_lat = _as_float(st.session_state.lat)
                prev_lon = _as_float(st.session_state.lon)

                if (
                    new_lat is not None and new_lon is not None
                    and prev_lat is not None and prev_lon is not None
                ):
                    if abs(new_lat - prev_lat) > 1e-6 or abs(new_lon - prev_lon) > 1e-6:
                        st.session_state.lat = float(new_lat)
                        st.session_state.lon = float(new_lon)
                        st.session_state.address = reverse_geocode(float(new_lat), float(new_lon))

                if new_zoom is not None:
                    try:
                        new_zoom_int = int(new_zoom)
                        if new_zoom_int != int(st.session_state.zoom):
                            st.session_state.zoom = new_zoom_int
                    except Exception:
                        pass

        except Exception as e:
            st.error("マップの表示に失敗しました。folium / streamlit-folium を確認してください。")
            st.exception(e)

    # placeholders
    status_placeholder = st.empty()
    log_placeholder = st.empty()
    table_placeholder = st.empty()
    dl_col = st.columns(2)

    if execute:
        logger = setup_logging()
        with st.status("準備中…", expanded=True) as s:
            try:
                s.update(label="抽出を実行中…", state="running")
                coord_address = f"{float(st.session_state.lat)},{float(st.session_state.lon)}"
                result: ScrapeResult = scrape_locations(
                    address=coord_address,
                    zoom=int(st.session_state.zoom),
                    categories=categories,
                    headless=headless,
                    max_count=max_count,
                    logger=logger,
                )
                log_text = "\n".join(result.log_lines) if result.log_lines else "(ログなし)"
                log_placeholder.text_area("進捗ログ", log_text, height=220)

                if not result.dataframe.empty:
                    s.update(label="完了しました", state="complete")
                    st.success(f"{len(result.dataframe)} 件のデータを取得しました。")
                    table_placeholder.dataframe(result.dataframe, use_container_width=True)

                    excel_bytes = dataframe_to_excel_bytes(result.dataframe)
                    csv_bytes = dataframe_to_csv_bytes(result.dataframe)
                    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    base = f"ロケスマ抽出_{ts}"

                    with dl_col[0]:
                        st.download_button(
                            "Excel ダウンロード",
                            data=excel_bytes,
                            file_name=f"{base}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                    with dl_col[1]:
                        st.download_button(
                            "CSV ダウンロード",
                            data=csv_bytes,
                            file_name=f"{base}.csv",
                            mime="text/csv",
                        )
                else:
                    s.update(label="完了（データなし）", state="complete")
                    st.warning("データが取得できませんでした。条件を変えてお試しください。")

            except Exception as e:
                s.update(label="失敗しました", state="error")
                st.error("抽出中にエラーが発生しました。以下をご確認ください。")
                st.exception(e)


if __name__ == "__main__":
    main()
