"""
HK4TUC DNF 精确地图
- 香港边界 GeoJSON 底图
- 2021-2026 所有 DNF 停止点
- 按年份着色 + 弹窗详情
- 四径官方路线（来自 dottrack 22hk4tuc.kml）
"""
import json, folium, pandas as pd
import xml.etree.ElementTree as ET
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────────────────
HK_JSON   = Path("/Users/yumok/Desktop/hk.json")
DNF_CSV   = Path("hk4tuc_all_years/csv/all_years_dnf.csv")
# ROUTE_KML = Path("hk4tuc_route_official.kml")
# Resolve hk4tuc_route_official.kml from common locations so README/目录调整不会导致脚本找不到文件
_possible_route_paths = [
    Path("hk4tuc_route_official.kml"),
    Path("data/hk4tuc_route_official.kml"),
    Path(__file__).resolve().parent.parent / "hk4tuc_route_official.kml",
]
ROUTE_KML = next((p for p in _possible_route_paths if p.exists()), _possible_route_paths[0])
if not ROUTE_KML.exists():
    raise FileNotFoundError(
        "hk4tuc_route_official.kml not found. Checked: " + ", ".join(str(p) for p in _possible_route_paths)
    )
OUTPUT    = Path("hk4tuc_all_years/HK4TUC_DNF_Map_v2.html")

YEAR_COLORS = {
    "2021": "#e74c3c",
    "2022": "#e67e22",
    "2023": "#f39c12",
    "2024": "#27ae60",
    "2025": "#2980b9",
    "2026": "#8e44ad",
}

# 注意：2022年KML中 "Wilson to Lam Tim MTR" 实为卫奕信径主体（2690点）
SEGMENT_STYLE = {
    "The Mac":                       ("#e74c3c", "麦理浩径"),
    "Wilson to Lam Tim MTR":         ("#3498db", "卫奕信径"),
    "Wilson from Tai Too MTR":       ("#3498db", "卫奕信径 (南段)"),
    "HK Trail":                      ("#27ae60", "港岛径"),
    "Lantau Trail":                  ("#f39c12", "大屿山径"),
    "Peak to Pier":                  None,  # 仅2个点，跳过不画
    "The Maclehose Trail (reverse)": ("#e74c3c", "麦理浩径"),
    "HK Trail + Shek O (reverse)":   ("#27ae60", "港岛径"),
    "Lantau Trail (reverse)":        ("#f39c12", "大屿山径"),
    "#1 Maclehose trail":            ("#e74c3c", "麦理浩径"),
    "#2 Wilson trail (part one)":    ("#3498db", "卫奕信径"),
    "#2 Wilson trail (part two)":    ("#3498db", "卫奕信径 (南段)"),
    "#3 Hong Kong trail":            ("#27ae60", "港岛径"),
    "#4 Lantau trail":               ("#f39c12", "大屿山径"),
}

# ── 读取数据 ───────────────────────────────────────────────────────
df_dnf = pd.read_csv(DNF_CSV)
df_dnf.columns = df_dnf.columns.str.replace('\ufeff', '')
df_dnf["name"] = df_dnf["name"].str.replace(r'\[Retired\] |\[Disqualified\] ', '', regex=True).str.strip()
df_dnf["year"] = df_dnf["year"].astype(str)

# ── 创建地图 ───────────────────────────────────────────────────────
m = folium.Map(
    location=[22.38, 114.12],
    zoom_start=11,
    tiles="CartoDB positron",
    prefer_canvas=True,
)

# ── 香港边界 ───────────────────────────────────────────────────────
with open(HK_JSON, encoding="utf-8") as f:
    hk_geo = json.load(f)

folium.GeoJson(
    hk_geo,
    name="香港边界",
    style_function=lambda x: {
        "fillColor": "#f0f0f0",
        "color": "#666666",
        "weight": 1.5,
        "fillOpacity": 0.1,
    },
).add_to(m)

# ── 四径官方路线 ───────────────────────────────────────────────────
print("绘制官方四径路线...")
ns = "{http://www.opengis.net/kml/2.2}"

route_group = folium.FeatureGroup(name="四径官方路线", show=True)
m.add_child(route_group)

with open(ROUTE_KML, encoding="utf-8") as f:
    kml_root = ET.fromstring(f.read())

for pm in kml_root.iter(f"{ns}Placemark"):
    name_el = pm.find(f"{ns}name")
    seg_name = name_el.text.strip() if name_el is not None else ""
    ls = pm.find(f".//{ns}LineString")
    if ls is None:
        continue
    coord_el = ls.find(f"{ns}coordinates")
    if coord_el is None:
        continue
    pts = []
    for token in coord_el.text.strip().split():
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                pts.append((float(parts[1]), float(parts[0])))
            except ValueError:
                pass

    style = SEGMENT_STYLE.get(seg_name, ("#666666", seg_name))
    if style is None:
        continue  # 跳过 Peak to Pier 等无需显示的段
    color, label = style
    folium.PolyLine(
        pts,
        color=color,
        weight=4,
        opacity=0.7,
        tooltip=label,
    ).add_to(route_group)
    print(f"  {label}: {len(pts)} 点")

# ── 各年份图层组 ──────────────────────────────────────────────────
year_groups = {}
for yr in sorted(YEAR_COLORS.keys()):
    fg = folium.FeatureGroup(name=f"{yr}年 DNF", show=True)
    year_groups[yr] = fg
    m.add_child(fg)

# ── DNF 停止点标记 ────────────────────────────────────────────────
print("绘制停止点...")
for _, row in df_dnf.iterrows():
    lat = row.get("gps_last_lat")
    lon = row.get("gps_last_lon")
    if pd.isna(lat) or pd.isna(lon):
        continue
    yr    = str(row["year"])
    color = YEAR_COLORS.get(yr, "#999")

    popup_html = f"""
    <div style="font-family:sans-serif;min-width:200px">
      <b style="font-size:14px">{row['name']}</b><br>
      <span style="color:{color}">● {yr}年</span> &nbsp; #{row['bib']}<br>
      <hr style="margin:4px 0">
      <b>状态：</b>{row.get('class','')}<br>
      <b>最后CP：</b>{row.get('dnf_at_cp','')}<br>
      <b>停止时间：</b>{row.get('gps_last_time','')}<br>
      <b>国籍：</b>{str(row.get('nationality','')).replace('_',' ').title()}<br>
      <b>坐标：</b>{lat:.5f}, {lon:.5f}<br>
      <a href="{row.get('tracking_url','')}" target="_blank"
         style="color:#3498db">📍 查看完整轨迹 ↗</a>
    </div>
    """

    folium.CircleMarker(
        location=[lat, lon],
        radius=8,
        color="white",
        weight=1.5,
        fill=True,
        fill_color=color,
        fill_opacity=0.9,
        popup=folium.Popup(popup_html, max_width=260),
        tooltip=f"{yr} #{row['bib']} {row['name']}",
    ).add_to(year_groups.get(yr, m))

# ── 图例 ──────────────────────────────────────────────────────────
legend_html = """
<div style="
  position:fixed; bottom:40px; left:40px; z-index:1000;
  background:white; padding:14px 18px; border-radius:10px;
  box-shadow:0 2px 12px rgba(0,0,0,0.25); font-family:sans-serif;
  font-size:13px; line-height:1.8;
">
  <b style="font-size:14px">HK4TUC DNF 停止点</b><br>
  <span style="font-size:11px;color:#888">2021–2026 · 共50人次</span><br>
  <hr style="margin:6px 0">
"""
dnf_counts = df_dnf.groupby("year").size()
for yr, clr in sorted(YEAR_COLORS.items()):
    cnt = dnf_counts.get(yr, 0)
    legend_html += f'<span style="color:{clr};font-size:16px">●</span> {yr}年 <span style="color:#888">({cnt}人)</span><br>'
legend_html += "</div>"
m.get_root().html.add_child(folium.Element(legend_html))

# ── 图层控制 ──────────────────────────────────────────────────────
folium.LayerControl(collapsed=False).add_to(m)

# ── 保存 ──────────────────────────────────────────────────────────
m.save(str(OUTPUT))
print(f"\n✓ 地图已保存: {OUTPUT.resolve()}")
