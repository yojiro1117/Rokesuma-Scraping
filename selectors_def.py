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
# A comprehensive list of categories supported by ロケスマ.
#
# ロケスマは非常に多くのカテゴリを提供しています。 公式の
# カテゴリリストを取得する API が公開されていないため、ここでは
# Web アプリやモバイルアプリで確認できる主要なカテゴリを
# 手作業で列挙しています。 既存のカテゴリに不足がある場合は
# ここに追加してください。 重複を避けるため、1 行に 1 件ずつ
# 記述し、アルファベット順やグループ順ではなく一般的な
# 利用順に並べています。
DEFAULT_CATEGORIES = [
    # 飲食店系
    "コンビニ",
    "カフェ",
    "レストラン",
    "ファミリーレストラン",
    "バーガー",
    "回転寿司/すし",
    "ランチ/定食",
    "ラーメン",
    "牛丼",
    "カレー",
    "ファストフード",
    "スイーツ",
    "ベーカリー",
    "サンドイッチ",
    "ハンバーガー",
    "居酒屋",
    "焼肉",
    "焼き鳥",
    "お好み焼き",
    "ステーキ",
    "しゃぶしゃぶ",
    "とんかつ",
    "そば/うどん",
    "ピザ",
    "中華料理",
    "韓国料理",
    "イタリアン",
    "フレンチ",
    "洋食",
    "和食",
    "シーフード",
    "クレープ",
    "ドーナツ",
    "チョコレート",
    "アイスクリーム",
    "パンケーキ",
    "フルーツジュース",
    "ベジタリアン/ビーガン",
    "酒屋",
    # ショッピング系
    "スーパー",
    "ドラッグストア",
    "デパート",
    "ショッピングセンター",
    "ホームセンター",
    "家電量販店",
    "家具・インテリア",
    "100円ショップ",
    "ファッション",
    "ベビー用品",
    "靴",
    "スポーツ用品",
    "書店",
    "文具",
    "楽器",
    "ペットショップ",
    "花屋",
    "メガネ",
    "宝石店",
    "雑貨",
    "リサイクルショップ",
    "アウトドア用品",
    "モール",
    "免税店",
    # 交通・車関連
    "コインパーキング",
    "駐車場",
    "駐輪場",
    "ガソリンスタンド",
    "EV充電",
    "レンタカー",
    "カーシェア",
    "タイヤショップ",
    "カー用品",
    "中古車販売",
    "洗車場",
    "自転車店",
    "バイクショップ",
    "タクシー乗り場",
    "バス停",
    "駅",
    "空港",
    # 医療・健康
    "病院・診療所",
    "調剤薬局",
    "歯科",
    "整骨院",
    "動物病院",
    "眼科",
    "産婦人科",
    "小児科",
    # 金融・公共
    "銀行",
    "銀行ATM",
    "信用金庫",
    "郵便局",
    "役所",
    "警察署",
    "消防署",
    # 教育
    "学校",
    "幼稚園",
    "保育園",
    "大学",
    "塾",
    "図書館",
    "公民館",
    "資格学校",
    # レジャー・文化
    "スポーツクラブ",
    "ゴルフ場",
    "公園",
    "博物館",
    "美術館",
    "観光スポット",
    "テーマパーク",
    "水族館",
    "動物園",
    "温泉",
    "銭湯",
    "プール",
    "ボウリング",
    "カラオケ",
    # パーソナルケア
    "美容室・理容室",
    "ネイルサロン",
    "エステサロン",
    "クリーニング",
    "コインランドリー",
    "リラクゼーション",
    "マッサージ",
    "整体",
    "まつげサロン",
    # 宿泊・旅行
    "ホテル",
    "旅館",
    "ゲストハウス",
    "カプセルホテル",
    "ホステル",
    "キャンプ場",
    "道の駅",
    "サービスエリア",
    # その他
    "ペットホテル",
    "神社/寺院",
    "教会",
    "墓地",
    "霊園",
]