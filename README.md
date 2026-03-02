# HK4TUC 退賽數據圖譜

**互動式數據新聞專頁** — 呈現 2021–2026 年香港四徑超級挑戰（HK4TUC）退賽選手的分佈、路段特徵與退賽規律。

🔗 **線上閱讀**：[https://jise2939.github.io/SpotNews/](https://jise2939.github.io/SpotNews/)

---

## 專題簡介

HK4TUC（Hong Kong Four Trails Ultra Challenge）是每年農曆新年舉行的自主超級馬拉松，選手須依序完成香港四大法定遠足徑：

| 路段 | 全長 |
|------|------|
| 麥理浩徑 | 100 km | 
| 衛奕信徑 | 78 km |
| 港島徑 | 50 km |
| 鳳凰徑 | 70 km | 

全程 **298 公里**，累積爬升 **14,500 米**，無官方補給站、無醫療支援，選手全程自負。

本專題聚焦 **2021–2026 年間 119 名參賽者中的 50 名退賽選手**，透過 GPS 最後定位、計時點記錄及路段特徵分析，呈現退賽的時空分佈。

---

## 數據來源

| 來源 | 內容 | 獲取方式 |
|------|------|----------|
| [dottrack.asia](https://dottrack.asia) | 選手 GPS 即時追蹤、最後定位座標、計時點記錄（2021–2026） | 公開賽事追蹤平台，人工逐年存取 |
| [HK4TUC 官方網站](https://hk4trailschallenge.com) | 官方賽事規則、歷年完賽名單、時限規定 | 公開資料 |
| [Lands Department Hong Kong](https://www.landsd.gov.hk) | 四條官方遠足徑 KML 路線數據 | 公開地理數據 |

> ⚠️ **注意**：2021 年以前的賽次在 dottrack.asia 平台無完整追蹤記錄，故本專題數據範圍為 2021–2026 年。

---

## 資料處理方法

- GPS 座標取自 dottrack.asia 每位退賽選手的**最後一個追蹤 ping 點**，作為退賽位置的近似值
- 退賽路段分類依據選手最後通過的**官方計時點**（CP）判斷
- 所有座標經人工核對，排除 GPS 漂移異常值
- 資料整理工具：Python（pandas）、手動核查

---

## 專頁技術

- 純 HTML/CSS/JavaScript，無後端框架
- 地圖：[Leaflet.js](https://leafletjs.com/) v1.9.4，底圖 CARTO Dark Matter
- 路線數據：官方 KML 轉換為 GeoJSON
- 圖表：純 SVG + CSS 動畫
- 部署：GitHub Pages（`docs/` 目錄）

---

## 目錄結構

```
docs/          # GitHub Pages 發佈目錄
  index.html   # 主專頁
  postbox.jpg  # 終點郵筒照片
  comic.JPG    # 規則漫畫（來源：耐力學社）
  hk4tuc-logo.png
data/
  csv/         # 整理後的退賽數據 CSV
  raw/         # 原始數據備份
  gps/         # GPS 追蹤原始檔
scripts/       # 數據處理 Python 腳本
  scraper.py        # 抓取單年份 dottrack.asia API 數據（以 2026 為例）
  multi_year.py     # 批次抓取 2021–2026 多年份選手數據
  make_map.py       # 生成 DNF 精確停止點地圖（按年份著色）
```

---

## 免責聲明

本專題為獨立新聞數據報導作品，與 HK4TUC 主辦方無關聯。所有數據均來自公開渠道，選手姓名已按 dottrack.asia 公開顯示方式呈現。如有數據錯誤，歡迎提交 Issue。

---

*製作：Jise2939 ｜ 2026 年 3 月*
