"""
香港四径 (HK4TUC) 2026 数据收集工具
====================================
数据来源: https://live.dottrack.asia/26hk4tuc/
API 基础: https://live.dottrack.asia/26hk4tuc/data/
个人详情: https://editor.opentracking.com/event/26hk4tuc/details?id=BIB
GPS轨迹: https://editor.opentracking.com/event/26hk4tuc/trace?id=BIB

收集内容:
- 所有选手基本信息（完赛/退赛/被取消资格）
- 检查点分段时间
- GPS 轨迹（KML → CSV）
- DNF 最后已知位置
- 汇总 Excel 报告
- 可视化地图（HTML）
"""

import os
import time
import json
import csv
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from pathlib import Path
from tqdm import tqdm
from datetime import datetime

# ── 配置 ──────────────────────────────────────────────────────────────────────
EVENT_CODE   = "26hk4tuc"
BASE_API     = f"https://live.dottrack.asia/{EVENT_CODE}/data"
EDITOR_API   = f"https://editor.opentracking.com/event/{EVENT_CODE}"
LIVE_BASE    = f"https://live.dottrack.asia/{EVENT_CODE}"

OUTPUT_DIR   = Path("hk4tuc_2026_data")
GPS_DIR      = OUTPUT_DIR / "gps_traces"
RAW_DIR      = OUTPUT_DIR / "raw_json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Referer": f"{LIVE_BASE}/",
    "Accept": "application/json, text/plain, */*",
}

REQUEST_DELAY = 0.8   # 请求间隔（秒），避免被限速
# ─────────────────────────────────────────────────────────────────────────────


def setup_dirs():
    """创建输出目录"""
    for d in [OUTPUT_DIR, GPS_DIR, RAW_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    print(f"[✓] 输出目录: {OUTPUT_DIR.resolve()}")


def fetch_json(url: str, params: dict = None) -> dict | None:
    """通用 JSON 请求，含重试"""
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=20)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            print(f"  [!] HTTP {e.response.status_code}: {url}")
            return None
        except Exception as e:
            if attempt < 2:
                print(f"  [!] 请求失败 (尝试 {attempt+1}/3): {e}")
                time.sleep(2)
            else:
                print(f"  [✗] 放弃: {url} -> {e}")
                return None


def fetch_kml(bib: int) -> str | None:
    """获取选手 GPS 轨迹 KML"""
    url = f"{EDITOR_API}/trace"
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, params={"id": bib}, timeout=30)
            r.raise_for_status()
            if r.text.startswith("<?xml"):
                return r.text
            return None
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                print(f"  [✗] 获取 KML 失败 bib={bib}: {e}")
                return None


def parse_kml_to_points(kml_text: str) -> list[dict]:
    """
    解析 KML，返回时间戳坐标点列表
    格式: [{timestamp, lat, lon, ele}, ...]
    仅提取带时间戳的 Point Placemark（即实际 GPS ping 点）
    """
    ns = "{http://www.opengis.net/kml/2.2}"
    try:
        root = ET.fromstring(kml_text)
    except ET.ParseError:
        return []

    points = []
    for pm in root.iter(f"{ns}Placemark"):
        name_el = pm.find(f"{ns}name")
        name = name_el.text.strip() if name_el is not None else ""

        # Point 类型（带时间戳的单点，name 格式: "2026-02-19 12:14:02"）
        pt_el = pm.find(f"{ns}Point")
        if pt_el is not None:
            coord_text = pt_el.find(f"{ns}coordinates")
            if coord_text is not None:
                parts = coord_text.text.strip().split(",")
                if len(parts) >= 2:
                    lon = float(parts[0])
                    lat = float(parts[1])
                    ele = float(parts[2]) if len(parts) > 2 else 0.0
                    points.append({
                        "timestamp": name,
                        "lat": lat,
                        "lon": lon,
                        "ele": ele,
                        "type": "track_point"
                    })

    # 按时间排序
    points.sort(key=lambda x: x["timestamp"])
    return points


def get_last_gps_point(points: list[dict]) -> dict | None:
    """
    从已排序的轨迹点列表中取最后一个真实 GPS 点。
    这是选手最后被追踪到的实际坐标，
    与 teams.json 的 `ll` 字段（始终为赛事中心坐标）完全不同。
    """
    return points[-1] if points else None


def get_all_bibs() -> list[dict]:
    """
    获取所有参赛者列表（含 bib 号、姓名、完赛状态）
    """
    print("\n[1] 获取参赛者列表...")
    data = fetch_json(f"{BASE_API}/teams.json")
    if not data or not data.get("success"):
        print("[✗] 无法获取参赛者列表")
        return []

    # 保存原始数据
    with open(RAW_DIR / "teams.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    athletes = []
    for cls in data["data"]:
        class_name = cls["classname"]
        for t in cls["teams"]:
            # 解析关键字段
            bib       = t.get("r")          # bib 号
            name      = t.get("n", "")      # 姓名
            finished  = bool(t.get("fin"))  # 是否完赛
            status    = t.get("st")         # 状态标记（如 "bed"=退赛）
            last_cp   = t.get("lc", "")     # 最后检查点
            last_ll   = t.get("ll", "")     # 最后位置 "lat,lon"
            last_time = t.get("dt", "")     # 最后更新时间
            finish_t  = t.get("t", "")      # 完赛/当前用时
            nationality = t.get("f", "")    # 国旗文件名
            
            # 解析最后位置
            last_lat, last_lon = None, None
            if last_ll and "," in last_ll:
                try:
                    last_lat, last_lon = map(float, last_ll.split(","))
                except ValueError:
                    pass

            # 判断 DNF 类型
            dnf_type = "N/A"
            if not finished:
                if "Retired" in class_name or "Disqualified" in class_name:
                    dnf_type = class_name
                elif status == "bed":
                    dnf_type = "Retired"
                else:
                    dnf_type = "Unknown"

            athletes.append({
                "bib":          bib,
                "name":         name,
                "class":        class_name,
                "finished":     finished,
                "dnf_type":     dnf_type,
                "finish_time":  finish_t if finished else "",
                "dnf_at_cp":    last_cp if not finished else "",
                "last_cp":      last_cp,
                "last_time":    last_time,
                "last_lat":     last_lat,
                "last_lon":     last_lon,
                "nationality":  nationality.replace(".gif", "") if nationality else "",
                "status_code":  status or "",
            })

    print(f"  [✓] 共 {len(athletes)} 名选手")
    print(f"      完赛: {sum(1 for a in athletes if a['finished'])}")
    print(f"      DNF:  {sum(1 for a in athletes if not a['finished'])}")
    return athletes


def get_athlete_details(bib: int) -> dict | None:
    """获取选手详细检查点分段数据"""
    data = fetch_json(f"{EDITOR_API}/details", params={"id": bib})
    if not data or not data.get("success"):
        return None
    return data.get("data")


def get_athlete_gps(bib: int, name: str, finished: bool) -> list[dict]:
    """
    获取选手 GPS 轨迹点（已排序）。
    同时保存原始 KML 文件。
    返回按时间升序排列的坐标点列表。
    """
    kml_text = fetch_kml(bib)
    if not kml_text:
        return []

    # 保存原始 KML
    safe_name = name.split()[0].replace("/", "_")
    kml_path = GPS_DIR / f"bib{bib:03d}_{safe_name}.kml"
    with open(kml_path, "w", encoding="utf-8") as f:
        f.write(kml_text)

    points = parse_kml_to_points(kml_text)   # 内部已排序
    return points


def collect_all_data(fetch_gps: bool = True):
    """主流程：收集所有数据"""
    setup_dirs()

    # ── Step 1: 获取参赛者列表 ─────────────────────────────────
    athletes = get_all_bibs()
    if not athletes:
        return

    # ── Step 2: 获取检查点配置 ──────────────────────────────────
    print("\n[2] 获取检查点信息...")
    cp_data = fetch_json(f"{BASE_API}/checkpoints.json")
    if cp_data:
        with open(RAW_DIR / "checkpoints.json", "w", encoding="utf-8") as f:
            json.dump(cp_data, f, ensure_ascii=False, indent=2)
        print(f"  [✓] 检查点数据已保存")

    # ── Step 3: 逐一获取选手详细数据 ────────────────────────────
    print(f"\n[3] 获取各选手详细数据...")
    all_splits = []    # 检查点分段记录
    all_details = []   # 完整选手详情

    for athlete in tqdm(athletes, desc="获取详情"):
        bib  = athlete["bib"]
        name = athlete["name"]

        time.sleep(REQUEST_DELAY)
        detail = get_athlete_details(bib)
        if not detail:
            tqdm.write(f"  [!] bib={bib} {name} 无详情")
            continue

        # 保存原始数据
        with open(RAW_DIR / f"detail_bib{bib:03d}.json", "w", encoding="utf-8") as f:
            json.dump(detail, f, ensure_ascii=False, indent=2)

        # 提取 splits（检查点分段）
        splits = detail.get("splits", [])
        for sp in splits:
            all_splits.append({
                "bib":          bib,
                "name":         name,
                "finished":     athlete["finished"],
                "dnf_type":     athlete["dnf_type"],
                "cp_id":        sp.get("i"),
                "cp_name":      sp.get("n"),
                "cp_type":      sp.get("ct"),   # start/control/finish
                "arrival_time": sp.get("v"),     # 到达时间 (UTC)
                "split_label":  sp.get("s"),     # 分段时间字符串
                "split_secs":   sp.get("ss"),    # 分段秒数
                "elapsed_str":  sp.get("sss"),   # 累计用时字符串
                "dwell_mins":   sp.get("ds"),    # 驻留秒数
            })

        # 汇总详情
        details_info = detail.get("details", {})
        all_details.append({
            **athlete,
            "total_time":        details_info.get("Time Taken", ""),
            "last_timed_loc":    details_info.get("Last Timed Location", ""),
            "last_tracked":      details_info.get("Last Tracked", ""),
            "total_dwell":       detail.get("totaldwell", ""),
            "splits_count":      len(splits),
            "tracking_url":      f"{LIVE_BASE}/?b={bib}",
        })

    # ── Step 4: 获取 GPS 轨迹 ────────────────────────────────────
    all_gps_points = []
    if fetch_gps:
        print(f"\n[4] 下载 GPS 轨迹（并提取 DNF 精确停止坐标）...")
        for athlete in tqdm(athletes, desc="下载GPS"):
            bib      = athlete["bib"]
            name     = athlete["name"]
            finished = athlete["finished"]

            time.sleep(REQUEST_DELAY)
            pts = get_athlete_gps(bib, name, finished)

            # ★ 用 GPS 最后一点覆盖 DNF 坐标（比 teams.json 的 ll 字段精确得多）
            last_pt = get_last_gps_point(pts)
            if last_pt:
                # 找到对应的 all_details 记录并更新
                for rec in all_details:
                    if rec["bib"] == bib:
                        rec["gps_last_lat"]  = last_pt["lat"]
                        rec["gps_last_lon"]  = last_pt["lon"]
                        rec["gps_last_time"] = last_pt["timestamp"]
                        rec["gps_point_count"] = len(pts)
                        break

            for p in pts:
                p["bib"]      = bib
                p["name"]     = name
                p["finished"] = finished
                p["dnf_type"] = athlete["dnf_type"]
            all_gps_points.extend(pts)
            tqdm.write(
                f"  bib={bib:3d} {'[DNF]' if not finished else '[FIN]'} "
                f"{name[:22]:22s}: {len(pts):3d} 点"
                + (f"  最后坐标: {last_pt['lat']:.5f},{last_pt['lon']:.5f}" if last_pt else "")
            )
    else:
        print("\n[4] 跳过 GPS 轨迹下载（fetch_gps=False）")

    # ── Step 5: 输出结果 ─────────────────────────────────────────
    print("\n[5] 生成输出文件...")
    save_results(athletes, all_details, all_splits, all_gps_points)


def save_results(athletes, all_details, all_splits, all_gps_points):
    """保存所有结果到 CSV + Excel + 可视化地图"""

    # ── 5-1: 选手汇总 CSV ─────────────────────────────────────
    df_athletes = pd.DataFrame(all_details if all_details else athletes)
    csv_path = OUTPUT_DIR / "athletes_summary.csv"
    df_athletes.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"  [✓] 选手汇总: {csv_path}")

    # ── 5-2: DNF 专项 CSV ────────────────────────────────────
    df_dnf = df_athletes[df_athletes["finished"] == False].copy()

    # 整理 DNF 专项列顺序，优先展示精确 GPS 坐标
    dnf_cols_priority = [
        "bib", "name", "class", "nationality",
        "dnf_at_cp",             # 最后通过的检查点（计时系统）
        "last_time",             # 最后计时时间
        "gps_last_lat",          # ★ GPS 最后精确纬度
        "gps_last_lon",          # ★ GPS 最后精确经度
        "gps_last_time",         # ★ GPS 最后ping时间
        "gps_point_count",       # GPS 点数
        "total_time",            # 运动总时长
        "tracking_url",
    ]
    dnf_cols = [c for c in dnf_cols_priority if c in df_dnf.columns] + \
               [c for c in df_dnf.columns if c not in dnf_cols_priority]
    df_dnf = df_dnf[dnf_cols]

    dnf_csv = OUTPUT_DIR / "dnf_athletes.csv"
    df_dnf.to_csv(dnf_csv, index=False, encoding="utf-8-sig")
    print(f"  [✓] DNF 选手（含精确GPS坐标）: {dnf_csv}  ({len(df_dnf)} 人)")

    # ── 5-3: 检查点分段 CSV ───────────────────────────────────
    if all_splits:
        df_splits = pd.DataFrame(all_splits)
        splits_csv = OUTPUT_DIR / "checkpoint_splits.csv"
        df_splits.to_csv(splits_csv, index=False, encoding="utf-8-sig")
        print(f"  [✓] 检查点分段: {splits_csv}  ({len(df_splits)} 条记录)")

    # ── 5-4: GPS 轨迹 CSV ────────────────────────────────────
    if all_gps_points:
        df_gps = pd.DataFrame(all_gps_points)
        gps_csv = OUTPUT_DIR / "all_gps_tracks.csv"
        df_gps.to_csv(gps_csv, index=False, encoding="utf-8-sig")
        print(f"  [✓] GPS 轨迹: {gps_csv}  ({len(df_gps)} 个点)")

    # ── 5-5: Excel 综合报告 ───────────────────────────────────
    excel_path = OUTPUT_DIR / "HK4TUC_2026_Report.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        # 总览
        df_athletes.to_excel(writer, sheet_name="选手总览", index=False)
        # DNF
        df_dnf.to_excel(writer, sheet_name="DNF详情", index=False)
        # 完赛
        df_fin = df_athletes[df_athletes["finished"] == True]
        df_fin.to_excel(writer, sheet_name="完赛选手", index=False)
        # 检查点分段
        if all_splits:
            pd.DataFrame(all_splits).to_excel(writer, sheet_name="检查点分段", index=False)
        # GPS汇总（前50000行）
        if all_gps_points:
            pd.DataFrame(all_gps_points[:50000]).to_excel(
                writer, sheet_name="GPS轨迹(前5万)", index=False)
    print(f"  [✓] Excel 报告: {excel_path}")

    # ── 5-6: 可视化地图（HTML）────────────────────────────────
    generate_map(df_athletes, all_gps_points)

    # ── 5-7: DNF 分析报告 ─────────────────────────────────────
    generate_dnf_report(df_athletes, all_splits)

    print(f"\n{'='*50}")
    print(f"[完成] 所有数据已保存至: {OUTPUT_DIR.resolve()}")


def generate_map(df_athletes: pd.DataFrame, all_gps_points: list[dict]):
    """生成交互式 HTML 地图"""
    try:
        import folium
        from folium import plugins

        m = folium.Map(
            location=[22.35, 114.15],
            zoom_start=11,
            tiles="CartoDB positron"
        )

        # 颜色映射
        color_map = {
            True:  "#2094f3",   # 完赛 - 蓝色
            False: "#f44034",   # DNF  - 红色
        }

        # 绘制 GPS 轨迹线
        if all_gps_points:
            from collections import defaultdict
            tracks = defaultdict(list)
            for pt in all_gps_points:
                tracks[pt["bib"]].append((pt["lat"], pt["lon"]))

            for bib, coords in tracks.items():
                athlete_info = df_athletes[df_athletes["bib"] == bib]
                if athlete_info.empty:
                    continue
                row = athlete_info.iloc[0]
                color = color_map.get(row["finished"], "#999")
                folium.PolyLine(
                    coords,
                    color=color,
                    weight=1.5,
                    opacity=0.5,
                    tooltip=f"#{bib} {row['name']}"
                ).add_to(m)

        # 标记最后位置
        # DNF 选手：优先用 gps_last_lat/lon（精确GPS停止坐标），完赛者用 last_lat/lon
        for _, row in df_athletes.iterrows():
            # 取坐标：DNF 用精确GPS点，完赛用最后计时点
            if not row["finished"] and pd.notna(row.get("gps_last_lat")):
                pin_lat = row["gps_last_lat"]
                pin_lon = row["gps_last_lon"]
                pin_time = row.get("gps_last_time", row.get("last_time", ""))
            elif pd.notna(row.get("last_lat")):
                pin_lat = row["last_lat"]
                pin_lon = row["last_lon"]
                pin_time = row.get("last_time", "")
            else:
                continue

            if not row["finished"]:
                icon_color = "red"
                icon_name = "times"
            else:
                icon_color = "blue"
                icon_name = "flag"

            popup_html = f"""
            <b>#{row['bib']} {row['name'].replace('[Retired] ','').replace('[Disqualified] ','')}</b><br>
            状态: {'完赛 ✓' if row['finished'] else f"❌ {row.get('dnf_type','DNF')}"}<br>
            末位CP: {row.get('last_cp','')}<br>
            {'GPS停止时间: ' + str(row.get('gps_last_time','')) + '<br>' if not row['finished'] else ''}
            {'GPS坐标: ' + str(round(pin_lat,5)) + ', ' + str(round(pin_lon,5)) + '<br>' if not row['finished'] else ''}
            用时: {row.get('finish_time', row.get('total_time',''))}<br>
            <a href="{row.get('tracking_url','')}" target="_blank">查看轨迹 ↗</a>
            """
            folium.Marker(
                [pin_lat, pin_lon],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"#{row['bib']} {row['name'].replace('[Retired] ','').replace('[Disqualified] ','')}",
                icon=folium.Icon(color=icon_color, icon=icon_name, prefix="fa")
            ).add_to(m)

        # 图例
        legend_html = """
        <div style="position:fixed; bottom:30px; left:30px; z-index:1000;
                    background:white; padding:12px 18px; border-radius:8px;
                    box-shadow:0 2px 8px rgba(0,0,0,0.3); font-size:13px;">
          <b>2026 HK4TUC</b><br>
          <span style="color:#2094f3">●</span> 完赛选手<br>
          <span style="color:#f44034">●</span> DNF / 退赛
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

        map_path = OUTPUT_DIR / "HK4TUC_2026_Map.html"
        m.save(str(map_path))
        print(f"  [✓] 可视化地图: {map_path}")

    except ImportError:
        print("  [!] folium 未安装，跳过地图生成")
    except Exception as e:
        print(f"  [!] 地图生成失败: {e}")


def generate_dnf_report(df_athletes: pd.DataFrame, all_splits: list[dict]):
    """生成 DNF 分析 Markdown 报告（含精确 GPS 停止坐标）"""
    lines = []
    lines.append("# 2026 HK4TUC DNF 分析报告\n")
    lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    # 总体统计
    total    = len(df_athletes)
    finished = int(df_athletes["finished"].sum())
    dnf_count = total - finished
    finish_rate = finished / total * 100 if total > 0 else 0

    lines.append("## 总体统计\n")
    lines.append("| 项目 | 数量 |\n|---|---|\n")
    lines.append(f"| 总参赛人数 | {total} |\n")
    lines.append(f"| 完赛人数 | {finished} |\n")
    lines.append(f"| DNF人数 | {dnf_count} |\n")
    lines.append(f"| 完赛率 | {finish_rate:.1f}% |\n\n")

    # DNF 精确停止坐标表
    lines.append("## DNF 选手精确停止坐标\n\n")
    lines.append("> `gps_last_lat/lon` = GPS轨迹最后一个ping点（真实位置）\n")
    lines.append("> `dnf_at_cp` = 计时系统记录的最后检查点（可能早于实际停止）\n\n")
    lines.append("| Bib | 姓名 | 分类 | 最后计时检查点 | GPS停止时间 | GPS纬度 | GPS经度 | Google Maps |\n")
    lines.append("|-----|------|------|--------------|------------|---------|---------|-------------|\n")

    df_dnf = df_athletes[df_athletes["finished"] == False].sort_values("bib")
    for _, row in df_dnf.iterrows():
        name = str(row["name"]).replace("[Retired] ", "").replace("[Disqualified] ", "")
        lat  = row.get("gps_last_lat")
        lon  = row.get("gps_last_lon")
        gps_time = row.get("gps_last_time", "")
        maps_link = f"[📍]({f'https://maps.google.com/?q={lat},{lon}'})" if pd.notna(lat) and lat else "N/A"
        lat_str = f"{lat:.5f}" if pd.notna(lat) and lat else "N/A"
        lon_str = f"{lon:.5f}" if pd.notna(lon) and lon else "N/A"
        lines.append(
            f"| {row['bib']} | {name} | {row.get('class','')} | "
            f"{row.get('dnf_at_cp', row.get('last_cp',''))} | "
            f"{gps_time} | {lat_str} | {lon_str} | {maps_link} |\n"
        )

    # DNF 按分类分组详情
    lines.append("\n## DNF 分类详情\n")
    df_dnf2 = df_athletes[df_athletes["finished"] == False]
    for cls, grp in df_dnf2.groupby("class"):
        lines.append(f"\n### {cls} ({len(grp)} 人)\n\n")
        lines.append("| Bib | 姓名 | 国籍 | 最后计时CP | 计时时间 | GPS时间 | GPS坐标 |\n")
        lines.append("|-----|------|------|-----------|---------|---------|--------|\n")
        for _, row in grp.iterrows():
            name = str(row["name"]).replace("[Retired] ", "").replace("[Disqualified] ", "")
            lat  = row.get("gps_last_lat")
            lon  = row.get("gps_last_lon")
            coord_str = f"{lat:.5f}, {lon:.5f}" if pd.notna(lat) and lat else "N/A"
            lines.append(
                f"| {row['bib']} | {name} | {row.get('nationality','')} | "
                f"{row.get('dnf_at_cp', row.get('last_cp',''))} | "
                f"{row.get('last_time','')} | "
                f"{row.get('gps_last_time','')} | "
                f"{coord_str} |\n"
            )

    # 检查点 DNF 分布
    if all_splits:
        lines.append("\n## DNF 选手最后抵达检查点统计\n\n")
        dnf_bibs = set(df_dnf2["bib"].tolist())
        df_s     = pd.DataFrame(all_splits)
        df_s_dnf = df_s[df_s["bib"].isin(dnf_bibs) & df_s["arrival_time"].notna()]
        if not df_s_dnf.empty:
            last_cp = df_s_dnf.sort_values("elapsed_str").groupby("bib").last().reset_index()
            cp_cnt  = last_cp.groupby("cp_name").size().sort_values(ascending=False)
            lines.append("| 最后抵达检查点 | DNF 人数 |\n|--------------|----------|\n")
            for cp, cnt in cp_cnt.items():
                lines.append(f"| {cp} | {cnt} |\n")

    # 完赛时间分布
    lines.append("\n## 完赛选手成绩\n\n")
    df_fin = df_athletes[df_athletes["finished"] == True].copy()
    if not df_fin.empty:
        lines.append("| Rank | Bib | 姓名 | 国籍 | 完赛时间 |\n")
        lines.append("|------|-----|------|------|----------|\n")
        for rank, (_, row) in enumerate(df_fin.iterrows(), 1):
            lines.append(
                f"| {rank} | {row['bib']} | {row['name']} | "
                f"{row.get('nationality','')} | "
                f"{row.get('finish_time', row.get('total_time',''))} |\n"
            )

    report_path = OUTPUT_DIR / "DNF_Analysis_Report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"  [✓] DNF 分析报告: {report_path}")


# ── 命令行入口 ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="HK4TUC 2026 数据收集工具"
    )
    parser.add_argument(
        "--no-gps",
        action="store_true",
        help="跳过 GPS 轨迹下载（节省时间和带宽）"
    )
    parser.add_argument(
        "--bib",
        type=int,
        help="只收集指定 bib 号选手的数据（测试用）"
    )
    args = parser.parse_args()

    if args.bib:
        # 单选手测试模式
        print(f"[测试] 收集 bib={args.bib} 的数据...")
        setup_dirs()
        detail = get_athlete_details(args.bib)
        if detail:
            print(json.dumps(detail, ensure_ascii=False, indent=2))
            pts = get_athlete_gps(args.bib, f"bib{args.bib}", True)
            print(f"GPS 轨迹点数: {len(pts)}")
            if pts:
                print("前3点:", pts[:3])
    else:
        collect_all_data(fetch_gps=not args.no_gps)
