"""
HK4TUC 新闻报道图表组合
========================
图1: 散点地图 — DNF精确停止位置（无轨迹线，点大清晰）
图2: 横向条形图 — 哪个路段放弃人最多
图3: 完赛率年份趋势 — 折线+柱状组合
"""
import json, folium, pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.font_manager as fm
from pathlib import Path

HK_JSON  = Path("/Users/yumok/Desktop/hk.json")
DNF_CSV  = Path("hk4tuc_all_years/csv/all_years_dnf.csv")
ALL_CSV  = Path("hk4tuc_all_years/csv/all_years_athletes.csv")
OUT_DIR  = Path("hk4tuc_all_years/charts")
OUT_DIR.mkdir(exist_ok=True)

YEAR_COLORS = {
    "2021": "#e74c3c",
    "2022": "#e67e22",
    "2023": "#f1c40f",
    "2024": "#27ae60",
    "2025": "#2980b9",
    "2026": "#8e44ad",
}

# 尝试加载中文字体
zh_font = None
for fp in ["/System/Library/Fonts/STHeiti Medium.ttc",
           "/System/Library/Fonts/PingFang.ttc",
           "/Library/Fonts/Arial Unicode MS.ttf"]:
    if Path(fp).exists():
        zh_font = fm.FontProperties(fname=fp)
        plt.rcParams["font.family"] = zh_font.get_name()
        break

# ── 读取数据 ──────────────────────────────────────────────────────
df_dnf = pd.read_csv(DNF_CSV)
df_dnf.columns = df_dnf.columns.str.replace('\ufeff','')
df_dnf["name"] = df_dnf["name"].str.replace(r'\[Retired\] |\[Disqualified\] ','',regex=True).str.strip()
df_dnf["year"] = df_dnf["year"].astype(str)

df_all = pd.read_csv(ALL_CSV)
df_all.columns = df_all.columns.str.replace('\ufeff','')
df_all["year"] = df_all["year"].astype(str)

# ══════════════════════════════════════════════════════════════════
# 图1：DNF 停止位置地图（无轨迹线，大点）
# ══════════════════════════════════════════════════════════════════
print("生成图1：DNF停止位置地图...")

m = folium.Map(
    location=[22.37, 114.13],
    zoom_start=11,
    tiles="CartoDB positron",
    prefer_canvas=True,
)

# 香港边界
with open(HK_JSON, encoding="utf-8") as f:
    hk_geo = json.load(f)
folium.GeoJson(
    hk_geo,
    style_function=lambda x: {
        "fillColor": "#e8f4f8",
        "color": "#2c3e50",
        "weight": 2,
        "fillOpacity": 0.15,
    },
).add_to(m)

# 按年份分组图层
for yr in sorted(YEAR_COLORS.keys()):
    fg = folium.FeatureGroup(name=f"{yr}", show=True)
    df_yr = df_dnf[df_dnf["year"] == yr]
    for _, row in df_yr.iterrows():
        lat, lon = row.get("gps_last_lat"), row.get("gps_last_lon")
        if pd.isna(lat) or pd.isna(lon):
            continue
        color = YEAR_COLORS[yr]
        nat = str(row.get("nationality","")).replace("_"," ").title()
        popup_html = f"""
        <div style='font-family:sans-serif;min-width:190px;font-size:13px'>
          <b>{row['name']}</b><br>
          <span style='color:{color}'>■</span> {yr}年 &nbsp;#{row['bib']}<br>
          <hr style='margin:4px 0;border-color:#eee'>
          <b>最后CP：</b>{row.get('dnf_at_cp','')}<br>
          <b>停止时间：</b>{str(row.get('gps_last_time',''))[:16]}<br>
          <b>国籍：</b>{nat}<br>
          <a href='{row.get('tracking_url','')}' target='_blank'
             style='color:#3498db;font-size:12px'>查看轨迹 ↗</a>
        </div>"""
        folium.CircleMarker(
            location=[lat, lon],
            radius=10,
            color="white",
            weight=2,
            fill=True,
            fill_color=color,
            fill_opacity=0.92,
            popup=folium.Popup(popup_html, max_width=240),
            tooltip=f"{yr} #{row['bib']} {row['name']}",
        ).add_to(fg)
    fg.add_to(m)

# 图例
dnf_counts = df_dnf.groupby("year").size()
legend = """<div style='position:fixed;bottom:35px;left:35px;z-index:1000;
background:white;padding:14px 18px;border-radius:10px;
box-shadow:0 2px 14px rgba(0,0,0,0.2);font-family:sans-serif;
font-size:13px;line-height:2'>
<b style='font-size:14px'>香港四径 DNF 停止位置</b><br>
<span style='color:#888;font-size:11px'>2021–2026 · 共50人次放弃</span>
<hr style='margin:6px 0;border-color:#eee'>"""
for yr, clr in sorted(YEAR_COLORS.items()):
    cnt = dnf_counts.get(yr, 0)
    legend += f"<span style='color:{clr};font-size:18px'>●</span> {yr}年 <span style='color:#aaa;font-size:12px'>({cnt}人)</span><br>"
legend += "</div>"
m.get_root().html.add_child(folium.Element(legend))
folium.LayerControl(collapsed=False, position="topright").add_to(m)

map_path = OUT_DIR / "chart1_dnf_map.html"
m.save(str(map_path))
print(f"  ✓ {map_path}")

# ══════════════════════════════════════════════════════════════════
# 图2：放弃路段分布（横向条形图）
# ══════════════════════════════════════════════════════════════════
print("生成图2：放弃路段分布...")

# CP名称映射（更易读）
cp_labels = {
    "Start":                  "起点（赛前/起跑阶段）",
    "Start Wilson Trail":     "麦理浩径→卫奕信径",
    "Start HK Trail":         "卫奕信径→港岛径",
    "End Wilson Trail":       "卫奕信径终点",
    "End Maclehose Trail":    "麦理浩径终点",
    "End HK Trail":           "港岛径终点",
    "Start Lantau Trail":     "大屿山径起点",
    "Lantau Trail Mid Way":   "大屿山径中段",
}

cp_order = [
    "Start",
    "Start Wilson Trail",
    "End Wilson Trail",
    "Start HK Trail",
    "End Maclehose Trail",
    "End HK Trail",
    "Start Lantau Trail",
    "Lantau Trail Mid Way",
]

# 统计各CP各年DNF人数
pivot = df_dnf.groupby(["dnf_at_cp","year"]).size().unstack(fill_value=0)
pivot = pivot.reindex([c for c in cp_order if c in pivot.index])
pivot.index = [cp_labels.get(c, c) for c in pivot.index]

fig, ax = plt.subplots(figsize=(10, 5))
colors = [YEAR_COLORS[yr] for yr in pivot.columns if yr in YEAR_COLORS]
pivot.plot(kind="barh", stacked=True, ax=ax,
           color=colors, edgecolor="white", linewidth=0.5)

ax.set_xlabel("DNF 人次", fontsize=12)
ax.set_title("香港四径各路段放弃人次（2021–2026）", fontsize=14, fontweight="bold", pad=15)
ax.set_ylabel("")
ax.invert_yaxis()
ax.spines[["top","right","left"]].set_visible(False)
ax.tick_params(left=False)
ax.grid(axis="x", alpha=0.3, linestyle="--")

# 在每条bar右侧显示总数
for i, (idx, row) in enumerate(pivot.iterrows()):
    total = row.sum()
    ax.text(total + 0.1, i, f" {int(total)}人", va="center", fontsize=11, color="#555")

legend_patches = [mpatches.Patch(color=YEAR_COLORS[yr], label=f"{yr}年")
                  for yr in sorted(pivot.columns) if yr in YEAR_COLORS]
ax.legend(handles=legend_patches, loc="lower right", framealpha=0.9,
          fontsize=10, title="年份", title_fontsize=10)

plt.tight_layout()
chart2_path = OUT_DIR / "chart2_dnf_by_cp.png"
plt.savefig(chart2_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"  ✓ {chart2_path}")

# ══════════════════════════════════════════════════════════════════
# 图3：完赛率年份趋势
# ══════════════════════════════════════════════════════════════════
print("生成图3：完赛率趋势...")

years  = sorted(df_all["year"].unique())
totals = [len(df_all[df_all["year"]==y]) for y in years]
fins   = [int(df_all[df_all["year"]==y]["finished"].sum()) for y in years]
dnfs   = [t - f for t, f in zip(totals, fins)]
rates  = [f/t*100 for f, t in zip(fins, totals)]

fig, ax1 = plt.subplots(figsize=(9, 5))
ax2 = ax1.twinx()

x = range(len(years))
bar_w = 0.38

b1 = ax1.bar([i - bar_w/2 for i in x], fins, bar_w,
             label="完赛", color="#27ae60", alpha=0.85, zorder=3)
b2 = ax1.bar([i + bar_w/2 for i in x], dnfs, bar_w,
             label="DNF", color="#e74c3c", alpha=0.85, zorder=3)

ax2.plot(x, rates, "o-", color="#2c3e50", linewidth=2.5,
         markersize=8, zorder=4, label="完赛率")
for i, (xi, r) in enumerate(zip(x, rates)):
    ax2.annotate(f"{r:.0f}%", (xi, r),
                 textcoords="offset points", xytext=(0, 10),
                 ha="center", fontsize=11, fontweight="bold", color="#2c3e50")

ax1.set_xticks(list(x))
ax1.set_xticklabels([f"{y}年" for y in years], fontsize=11)
ax1.set_ylabel("参赛人数", fontsize=11)
ax2.set_ylabel("完赛率 %", fontsize=11)
ax2.set_ylim(0, 100)
ax1.set_ylim(0, max(totals) * 1.3)
ax1.spines[["top","right"]].set_visible(False)
ax2.spines[["top","left"]].set_visible(False)
ax1.grid(axis="y", alpha=0.3, linestyle="--", zorder=0)

lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2,
           loc="upper left", fontsize=10, framealpha=0.9)

ax1.set_title("香港四径历年完赛率（2021–2026）", fontsize=14, fontweight="bold", pad=15)
plt.tight_layout()
chart3_path = OUT_DIR / "chart3_finish_rate.png"
plt.savefig(chart3_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"  ✓ {chart3_path}")

print(f"\n✓ 全部图表已保存至: {OUT_DIR.resolve()}")
print("  图1（地图）: chart1_dnf_map.html  → 浏览器打开")
print("  图2（条形）: chart2_dnf_by_cp.png → 可直接插入报道")
print("  图3（趋势）: chart3_finish_rate.png → 可直接插入报道")
