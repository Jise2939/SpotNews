"""
HK4TUC 退赛热力图（按赛段）
- 四条径按退赛总人数加粗/加深颜色
- 每条径中段标注退赛人数气泡
- 不显示任何个人GPS坐标，避免误导
"""
import json, folium, pandas as pd
import xml.etree.ElementTree as ET
from pathlib import Path

HK_JSON   = Path("/Users/yumok/Desktop/hk.json")
DNF_CSV   = Path("hk4tuc_all_years/csv/all_years_dnf.csv")
ROUTE_KML = Path("hk4tuc_route_official.kml")
OUTPUT    = Path("hk4tuc_all_years/HK4TUC_Trail_DNF_Map.html")

# ── 精确分类 ───────────────────────────────────────────────────────
df = pd.read_csv(DNF_CSV)
df.columns = df.columns.str.replace('\ufeff', '')
df['name'] = df['name'].str.replace(r'\[Retired\] |\[Disqualified\] ', '', regex=True).str.strip()

# CP含义：dnf_at_cp = 最后打卡的CP，之后退赛
# Start              → 麦理浩径途中退赛（未打到任何中间CP）
# End Maclehose Trail → 麦理浩径完成后退赛（转场区放弃）
# Start Wilson Trail  → 卫奕信径途中退赛
# End Wilson Trail    → 卫奕信径完成后退赛
# Start HK Trail      → 港岛径途中退赛
# End HK Trail        → 港岛径完成后退赛
# Start Lantau Trail  → 大屿山径途中退赛
# Lantau Trail Mid Way→ 大屿山径途中退赛
CP_MAP = {
    'Start':                ('麦理浩径', '途中退赛'),
    'End Maclehose Trail':  ('麦理浩径', '完成后退赛'),
    'Start Wilson Trail':   ('卫奕信径', '途中退赛'),
    'End Wilson Trail':     ('卫奕信径', '完成后退赛'),
    'Start HK Trail':       ('港岛径',   '途中退赛'),
    'End HK Trail':         ('港岛径',   '完成后退赛'),
    'Start Lantau Trail':   ('大屿山径', '途中退赛'),
    'Lantau Trail Mid Way': ('大屿山径', '途中退赛'),
}

df['trail']  = df['dnf_at_cp'].map({k: v[0] for k, v in CP_MAP.items()})
df['detail'] = df['dnf_at_cp'].map({k: v[1] for k, v in CP_MAP.items()})

# 各径合计（用于线宽）
trail_counts = df.dropna(subset=['trail']).groupby('trail').size()

# 各径细分（途中 / 完成后）
trail_detail = df.dropna(subset=['trail']).groupby(['trail', 'detail']).size().unstack(fill_value=0)

print("各径退赛统计（含细分）:")
print(trail_detail)
print("\n合计:", trail_counts.sort_values(ascending=False).to_dict())

max_count = trail_counts.max()

# ── KML段 → 赛段映射 ──────────────────────────────────────────────
SEG_TO_TRAIL = {
    "The Mac":                       "麦理浩径",
    "Wilson to Lam Tim MTR":         "卫奕信径",
    "Wilson from Tai Too MTR":       "卫奕信径",
    "HK Trail":                      "港岛径",
    "Lantau Trail":                  "大屿山径",
    "Peak to Pier":                  None,  # 跳过，仅2个点
    "The Maclehose Trail (reverse)": "麦理浩径",
    "HK Trail + Shek O (reverse)":   "港岛径",
    "Lantau Trail (reverse)":        "大屿山径",
    "#1 Maclehose trail":            "麦理浩径",
    "#2 Wilson trail (part one)":    "卫奕信径",
    "#2 Wilson trail (part two)":    "卫奕信径",
    "#3 Hong Kong trail":            "港岛径",
    "#4 Lantau trail":               "大屿山径",
}

TRAIL_BASE_COLOR = {
    "麦理浩径": "#e74c3c",
    "卫奕信径": "#2980b9",
    "港岛径":   "#27ae60",
    "大屿山径": "#f39c12",
}

def trail_color(trail_name):
    count = trail_counts.get(trail_name, 0)
    base  = TRAIL_BASE_COLOR.get(trail_name, "#999999")
    # 退赛越多颜色越深（opacity通过weight体现）
    return base

def trail_weight(trail_name):
    count = trail_counts.get(trail_name, 0)
    # 基础线宽4，最多到12
    return 4 + int((count / max_count) * 8)

def trail_opacity(trail_name):
    count = trail_counts.get(trail_name, 0)
    return 0.35 + (count / max_count) * 0.55

# ── 创建地图 ───────────────────────────────────────────────────────
m = folium.Map(
    location=[22.38, 114.10],
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
        "fillColor": "#f5f5f5",
        "color": "#aaaaaa",
        "weight": 1,
        "fillOpacity": 0.15,
    },
).add_to(m)

# ── 绘制四径路线（线宽/透明度按退赛人数缩放）─────────────────────
print("\n绘制路线...")
ns = "{http://www.opengis.net/kml/2.2}"
with open(ROUTE_KML, encoding="utf-8") as f:
    kml_root = ET.fromstring(f.read())

trail_midpoints = {}  # 记录各径中点坐标用于标注

# 每条径建一个 FeatureGroup，方便JS按组控制
TRAIL_ORDER = ['麦理浩径', '卫奕信径', '港岛径', '大屿山径']
trail_groups = {}
for t in TRAIL_ORDER:
    fg = folium.FeatureGroup(name=t, show=False)
    fg.add_to(m)
    trail_groups[t] = fg

for pm in kml_root.iter(f"{ns}Placemark"):
    name_el  = pm.find(f"{ns}name")
    seg_name = name_el.text.strip() if name_el is not None else ""
    trail    = SEG_TO_TRAIL.get(seg_name)
    if trail is None:
        continue  # 跳过 Peak to Pier 及未知段
    ls = pm.find(f".//{ns}LineString")
    if ls is None:
        continue
    pts = []
    for tok in ls.find(f"{ns}coordinates").text.strip().split():
        p = tok.split(",")
        if len(p) >= 2:
            try:
                pts.append((float(p[1]), float(p[0])))
            except ValueError:
                pass
    if not pts:
        continue

    count = trail_counts.get(trail, 0)
    folium.PolyLine(
        pts,
        color=trail_color(trail),
        weight=trail_weight(trail),
        opacity=trail_opacity(trail),
        tooltip=f"{trail}：{count} 人退赛",
    ).add_to(trail_groups[trail])

    # 取中点坐标（最长段优先用于标注）
    if trail not in trail_midpoints or len(pts) > trail_midpoints[trail][2]:
        mid = pts[len(pts) // 2]
        trail_midpoints[trail] = (mid[0], mid[1], len(pts))

# ── 各径中段标注退赛人数气泡（按赛程顺序编号）──────────────────────
print("添加标注气泡...")
TRAIL_ORDER_MAP = {t: i for i, t in enumerate(TRAIL_ORDER, 1)}

for trail, (lat, lon, _) in trail_midpoints.items():
    count   = trail_counts.get(trail, 0)
    color   = TRAIL_BASE_COLOR.get(trail, "#999")
    detail  = trail_detail.loc[trail] if trail in trail_detail.index else {}
    mid_cnt = int(detail.get('途中退赛', 0))
    aft_cnt = int(detail.get('完成后退赛', 0))
    order_n = TRAIL_ORDER_MAP.get(trail, '')

    detail_lines = ""
    if mid_cnt:
        detail_lines += f'<div style="font-size:10px;opacity:0.9">途中 {mid_cnt} 人</div>'
    if aft_cnt:
        detail_lines += f'<div style="font-size:10px;opacity:0.9">完成后 {aft_cnt} 人</div>'

    bubble_html = f"""
    <div style="
        background:{color};
        color:white;
        border-radius:12px;
        padding:6px 10px;
        font-family:'Arial',sans-serif;
        font-weight:bold;
        box-shadow:0 2px 8px rgba(0,0,0,0.4);
        border:2px solid white;
        text-align:center;
        white-space:nowrap;
    ">
        <div style="font-size:9px;opacity:0.8;margin-bottom:1px">第{order_n}段</div>
        <div style="font-size:20px;line-height:1.1">{count} 人</div>
        {detail_lines}
    </div>
    """
    tooltip_txt = f"第{order_n}段 {trail}：共 {count} 人退赛"
    if mid_cnt: tooltip_txt += f"｜途中退赛 {mid_cnt} 人"
    if aft_cnt: tooltip_txt += f"｜完成后退赛 {aft_cnt} 人"

    folium.Marker(
        location=[lat, lon],
        icon=folium.DivIcon(
            html=bubble_html,
            icon_size=(100, 60),
            icon_anchor=(50, 30),
        ),
        tooltip=tooltip_txt,
    ).add_to(trail_groups[trail])

# ── 图例 ──────────────────────────────────────────────────────────
# 按赛程顺序排列（TRAIL_ORDER 已在上面定义）
legend_rows = ""
for i, trail in enumerate(TRAIL_ORDER, 1):
    count   = trail_counts.get(trail, 0)
    color   = TRAIL_BASE_COLOR.get(trail, "#999")
    bar_w   = int((count / max_count) * 80)
    detail  = trail_detail.loc[trail] if trail in trail_detail.index else {}
    mid_cnt = int(detail.get('途中退赛', 0))
    aft_cnt = int(detail.get('完成后退赛', 0))
    sub = []
    if mid_cnt: sub.append(f"途中 {mid_cnt} 人")
    if aft_cnt: sub.append(f"完成后 {aft_cnt} 人")
    sub_txt = " / ".join(sub)
    legend_rows += f"""
    <div style="margin:6px 0;">
        <div style="display:flex;align-items:center;gap:8px;">
            <div style="width:16px;height:16px;border-radius:50%;background:{color};
                        color:white;font-size:10px;font-weight:bold;display:flex;
                        align-items:center;justify-content:center;flex-shrink:0">{i}</div>
            <div style="width:72px;font-size:12px;font-weight:bold;color:{color}">{trail}</div>
            <div style="background:{color};width:{bar_w}px;height:8px;border-radius:3px;opacity:0.8;"></div>
            <div style="font-size:13px;font-weight:bold;color:{color}">{count}</div>
        </div>
        <div style="font-size:10px;color:#888;padding-left:96px;margin-top:1px">{sub_txt}</div>
    </div>
    """

# 赛前退赛单独说明
pre_count = int(df[df['trail'].isna()].shape[0])
legend_html = f"""
<div style="
  position:fixed; bottom:30px; left:30px; z-index:1000;
  background:white; padding:14px 18px; border-radius:12px;
  box-shadow:0 2px 14px rgba(0,0,0,0.2); font-family:'Arial',sans-serif;
  min-width:220px;
">
  <div style="font-size:14px; font-weight:bold; margin-bottom:8px;">
    🏃 各径退赛人数（2021–2026）
  </div>
  <div style="font-size:11px; color:#888; margin-bottom:10px;">
    线条越粗 = 退赛人数越多
  </div>
  {legend_rows}
  <div style="margin-top:8px; font-size:11px; color:#999; border-top:1px solid #eee; padding-top:6px;">
    另有 {pre_count} 人赛前/未出发退赛（不显示在图上）
  </div>
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))

# ── 保存 ──────────────────────────────────────────────────────────
m.save(str(OUTPUT))

# ── 注入动画控制器 JS ─────────────────────────────────────────────
# 读取已生成的 HTML，在 </body> 前插入动画脚本
html_txt = OUTPUT.read_text(encoding="utf-8")

# 构建赛段信息 JSON 供 JS 使用
import json as _json
trail_info_js = _json.dumps({
    t: {
        "color": TRAIL_BASE_COLOR[t],
        "order": i,
        "count": int(trail_counts.get(t, 0)),
        "label": t
    }
    for i, t in enumerate(TRAIL_ORDER, 1)
}, ensure_ascii=False)

anim_script = f"""
<style>
#trail-animator {{
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 9999;
  background: white;
  border-radius: 14px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.18);
  padding: 14px 18px;
  font-family: -apple-system, BlinkMacSystemFont, 'Arial', sans-serif;
  min-width: 200px;
  user-select: none;
}}
#trail-animator h3 {{
  font-size: 13px;
  font-weight: 700;
  color: #333;
  margin: 0 0 10px 0;
  letter-spacing: 0.3px;
}}
.ta-trail-btn {{
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
  margin-bottom: 3px;
}}
.ta-trail-btn:hover {{ background: #f5f5f5; }}
.ta-trail-btn.active {{ background: #f0f0f0; }}
.ta-dot {{
  width: 12px; height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
  opacity: 0.3;
  transition: opacity 0.3s, transform 0.3s;
  transform: scale(0.8);
}}
.ta-dot.on {{
  opacity: 1;
  transform: scale(1);
}}
.ta-label {{
  font-size: 12px;
  font-weight: 600;
  color: #555;
  transition: color 0.3s;
}}
.ta-label.on {{ color: #111; }}
.ta-count {{
  font-size: 11px;
  color: #aaa;
  margin-left: auto;
  transition: color 0.3s;
}}
.ta-count.on {{ color: #666; font-weight: bold; }}
#ta-controls {{
  display: flex;
  gap: 6px;
  margin-top: 10px;
  border-top: 1px solid #eee;
  padding-top: 10px;
}}
#ta-controls button {{
  flex: 1;
  padding: 6px 0;
  border: none;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}}
#ta-play-btn {{ background: #e74c3c; color: white; }}
#ta-play-btn:hover {{ background: #c0392b; }}
#ta-reset-btn {{ background: #ecf0f1; color: #555; }}
#ta-reset-btn:hover {{ background: #dfe6e9; }}
#ta-progress {{
  font-size: 11px;
  color: #aaa;
  text-align: center;
  margin-top: 7px;
  min-height: 14px;
}}
</style>

<div id="trail-animator">
  <h3>🏃 賽段動畫播放</h3>
  <div id="ta-trail-list"></div>
  <div id="ta-controls">
    <button id="ta-play-btn">▶ 播放</button>
    <button id="ta-reset-btn">↺ 重置</button>
  </div>
  <div id="ta-progress"></div>
</div>

<script>
(function() {{
  var TRAIL_INFO = {trail_info_js};
  var TRAIL_ORDER = {_json.dumps(TRAIL_ORDER, ensure_ascii=False)};
  var DELAY_PER_TRAIL = 1800;   // 每段停留 ms
  var INTRO_DELAY    = 600;    // 首段出现前延迟 ms
  var animTimer = null;
  var isPlaying = false;
  var currentStep = -1;  // -1=全隐, 0~3=显示第0~3段, 4=全显示

  // ── 构建侧边栏列表 ──
  var listEl = document.getElementById('ta-trail-list');
  TRAIL_ORDER.forEach(function(t) {{
    var info = TRAIL_INFO[t];
    var row = document.createElement('div');
    row.className = 'ta-trail-btn';
    row.id = 'ta-row-' + info.order;
    row.innerHTML =
      '<div class="ta-dot" id="ta-dot-'+info.order+'" style="background:'+info.color+'"></div>' +
      '<div class="ta-label" id="ta-lbl-'+info.order+'">'+t+'</div>' +
      '<div class="ta-count" id="ta-cnt-'+info.order+'">'+info.count+' 人</div>';
    row.addEventListener('click', (function(order) {{
      return function() {{ manualToggle(order); }};
    }})(info.order));
    listEl.appendChild(row);
  }});

  // ── 找到 Leaflet 图层（FeatureGroup）──
  function getLayersByName(name) {{
    var results = [];
    if (!window._map) return results;
    _map.eachLayer(function(layer) {{
      if (layer.options && layer.options.name === name) {{
        results.push(layer);
      }}
    }});
    return results;
  }}

  // 等待地图初始化
  function waitForMap(cb) {{
    var t = setInterval(function() {{
      // folium 生成的地图变量名不固定，扫描全局
      if (!window._map) {{
        for (var k in window) {{
          if (window[k] && window[k].eachLayer && window[k]._container) {{
            window._map = window[k];
            break;
          }}
        }}
      }}
      if (window._map) {{ clearInterval(t); cb(); }}
    }}, 100);
  }}

  function setTrailVisible(trailName, visible) {{
    var layers = getLayersByName(trailName);
    layers.forEach(function(l) {{
      if (visible) {{ _map.addLayer(l); }} else {{ _map.removeLayer(l); }}
    }});
    // 更新 UI
    var info = TRAIL_INFO[trailName];
    var dot = document.getElementById('ta-dot-' + info.order);
    var lbl = document.getElementById('ta-lbl-' + info.order);
    var cnt = document.getElementById('ta-cnt-' + info.order);
    if (dot) {{ dot.classList.toggle('on', visible); }}
    if (lbl) {{ lbl.classList.toggle('on', visible); }}
    if (cnt) {{ cnt.classList.toggle('on', visible); }}
  }}

  function hideAll() {{
    TRAIL_ORDER.forEach(function(t) {{ setTrailVisible(t, false); }});
    currentStep = -1;
    document.getElementById('ta-progress').textContent = '';
  }}

  function showUpTo(step) {{
    // step: 0~3，显示第0到step段
    TRAIL_ORDER.forEach(function(t, i) {{
      setTrailVisible(t, i <= step);
    }});
    currentStep = step;
    var names = TRAIL_ORDER.slice(0, step+1).join('、');
    if (step === TRAIL_ORDER.length - 1) {{
      document.getElementById('ta-progress').textContent = '✅ 四條徑全部展示';
    }} else {{
      document.getElementById('ta-progress').textContent =
        '第 ' + (step+1) + ' 段：' + TRAIL_ORDER[step];
    }}
  }}

  function playAnimation() {{
    if (isPlaying) return;
    isPlaying = true;
    document.getElementById('ta-play-btn').textContent = '⏸ 播放中';
    document.getElementById('ta-play-btn').style.background = '#95a5a6';
    hideAll();
    var step = 0;
    function nextStep() {{
      if (step < TRAIL_ORDER.length) {{
        showUpTo(step);
        step++;
        // 最后一步停更久
        var delay = step === TRAIL_ORDER.length ? DELAY_PER_TRAIL * 1.5 : DELAY_PER_TRAIL;
        animTimer = setTimeout(nextStep, delay);
      }} else {{
        // 动画结束
        isPlaying = false;
        document.getElementById('ta-play-btn').textContent = '▶ 重播';
        document.getElementById('ta-play-btn').style.background = '#27ae60';
        document.getElementById('ta-progress').textContent = '✅ 動畫完成，可點擊各段切換';
      }}
    }}
    animTimer = setTimeout(nextStep, INTRO_DELAY);
  }}

  function stopAnimation() {{
    if (animTimer) {{ clearTimeout(animTimer); animTimer = null; }}
    isPlaying = false;
    document.getElementById('ta-play-btn').textContent = '▶ 播放';
    document.getElementById('ta-play-btn').style.background = '#e74c3c';
  }}

  function manualToggle(order) {{
    stopAnimation();
    // 手动点击：显示到该段（累积）
    showUpTo(order - 1);
  }}

  document.getElementById('ta-play-btn').addEventListener('click', function() {{
    if (isPlaying) {{
      stopAnimation();
    }} else {{
      playAnimation();
    }}
  }});

  document.getElementById('ta-reset-btn').addEventListener('click', function() {{
    stopAnimation();
    hideAll();
    document.getElementById('ta-play-btn').textContent = '▶ 播放';
    document.getElementById('ta-play-btn').style.background = '#e74c3c';
  }});

  // 初始化：等地图加载后隐藏所有图层，然后自动播放
  waitForMap(function() {{
    hideAll();
    setTimeout(playAnimation, 800);
  }});
}})();
</script>
"""

html_txt = html_txt.replace("</body>", anim_script + "\n</body>")
OUTPUT.write_text(html_txt, encoding="utf-8")

# 同步到 docs/
import shutil
docs_out = Path("docs/map_trails.html")
shutil.copy(str(OUTPUT), str(docs_out))

print(f"\n✓ 地图已保存: {OUTPUT.resolve()}")
print(f"✓ 已同步到: {docs_out.resolve()}")
