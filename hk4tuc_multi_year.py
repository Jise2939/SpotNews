"""
香港四径 (HK4TUC) 多年份数据收集脚本
=====================================
覆盖范围: 2021–2026 (dottrack.asia 平台覆盖年份)
注意: 2014–2020 年份在 dottrack 平台上不存在，无法通过此 API 获取。

输出目录结构:
  hk4tuc_all_years/
  ├── raw/                         原始 API 缓存
  │   ├── 21hk4tuc/
  │   │   ├── teams.json
  │   │   ├── config.json
  │   │   ├── checkpoints.json
  │   │   ├── detail_bib001.json
  │   │   └── ...
  │   └── ...
  ├── gps/                         各选手 KML 轨迹
  │   ├── 21hk4tuc/
  │   │   ├── bib001_Law.kml
  │   │   └── ...
  │   └── ...
  ├── csv/
  │   ├── all_years_athletes.csv   跨年汇总（每行一名选手）
  │   ├── all_years_dnf.csv        所有 DNF 含精确 GPS 坐标
  │   ├── all_years_splits.csv     所有检查点分段
  │   └── all_years_gps.csv        所有 GPS 轨迹点
  ├── HK4TUC_All_Years.xlsx        Excel 多 Sheet 报告
  └── DNF_All_Years_Report.md      汇总分析报告
"""

import os, time, json, requests, xml.etree.ElementTree as ET
import pandas as pd
from pathlib import Path
from datetime import datetime
from tqdm import tqdm

# ── 配置 ──────────────────────────────────────────────────────────
YEARS = [21, 22, 23, 24, 25, 26]   # dottrack 平台覆盖年份

BASE_LIVE    = "https://live.dottrack.asia"
EDITOR_API   = "https://editor.opentracking.com/event"

OUTPUT_DIR   = Path("hk4tuc_all_years")
RAW_DIR      = OUTPUT_DIR / "raw"
GPS_DIR      = OUTPUT_DIR / "gps"
CSV_DIR      = OUTPUT_DIR / "csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

REQUEST_DELAY = 0.8  # 秒
# ─────────────────────────────────────────────────────────────────


def setup_dirs():
    for yr in YEARS:
        (RAW_DIR / f"{yr}hk4tuc").mkdir(parents=True, exist_ok=True)
        (GPS_DIR / f"{yr}hk4tuc").mkdir(parents=True, exist_ok=True)
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[✓] 输出目录: {OUTPUT_DIR.resolve()}")


def fetch_json(url: str, params: dict = None, referer: str = "") -> dict | None:
    hdrs = {**HEADERS, "Referer": referer}
    for attempt in range(3):
        try:
            r = requests.get(url, headers=hdrs, params=params, timeout=20)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            return None
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                return None


def fetch_kml(event_code: str, bib: int) -> str | None:
    url = f"{EDITOR_API}/{event_code}/trace"
    referer = f"{BASE_LIVE}/{event_code}/?b={bib}"
    for attempt in range(3):
        try:
            r = requests.get(url, headers={**HEADERS, "Referer": referer},
                             params={"id": bib}, timeout=30)
            r.raise_for_status()
            if r.text.strip().startswith("<?xml"):
                return r.text
            return None
        except Exception:
            if attempt < 2:
                time.sleep(2)
    return None


def parse_kml_points(kml_text: str) -> list[dict]:
    """返回按时间排序的 GPS 点列表 [{timestamp, lat, lon}, ...]"""
    ns = "{http://www.opengis.net/kml/2.2}"
    try:
        root = ET.fromstring(kml_text)
    except ET.ParseError:
        return []
    points = []
    for pm in root.iter(f"{ns}Placemark"):
        name_el = pm.find(f"{ns}name")
        name = name_el.text.strip() if name_el is not None else ""
        pt_el = pm.find(f"{ns}Point")
        if pt_el is not None:
            ct = pt_el.find(f"{ns}coordinates")
            if ct is not None:
                parts = ct.text.strip().split(",")
                if len(parts) >= 2:
                    try:
                        points.append({
                            "timestamp": name,
                            "lat": float(parts[1]),
                            "lon": float(parts[0]),
                        })
                    except ValueError:
                        pass
    points.sort(key=lambda x: x["timestamp"])
    return points


# ── 单年份数据收集 ────────────────────────────────────────────────

def collect_year(year: int, fetch_gps: bool = True) -> dict:
    """
    收集单年份全量数据，返回:
    {
      "year": int,
      "event_code": str,
      "athletes": [...],   # 含 gps_last_lat/lon
      "splits": [...],
      "gps_points": [...],
    }
    """
    event_code = f"{year}hk4tuc"
    raw_dir    = RAW_DIR / event_code
    gps_dir    = GPS_DIR / event_code
    referer    = f"{BASE_LIVE}/{event_code}/"

    print(f"\n{'─'*55}")
    print(f"  [{year+2000}] {event_code}")
    print(f"{'─'*55}")

    # ── config ──────────────────────────────────────────────────
    cfg = fetch_json(f"{BASE_LIVE}/{event_code}/data/config.json", referer=referer)
    if cfg:
        with open(raw_dir / "config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        ev_start = cfg.get("data", {}).get("eventstart", "")
        print(f"  赛事开始: {ev_start}")

    # ── checkpoints ─────────────────────────────────────────────
    chk = fetch_json(f"{BASE_LIVE}/{event_code}/data/checkpoints.json", referer=referer)
    if chk:
        with open(raw_dir / "checkpoints.json", "w", encoding="utf-8") as f:
            json.dump(chk, f, ensure_ascii=False, indent=2)

    # ── teams ───────────────────────────────────────────────────
    teams_data = fetch_json(f"{BASE_LIVE}/{event_code}/data/teams.json", referer=referer)
    if not teams_data:
        print(f"  [!] 无法获取 teams.json")
        return {"year": year, "event_code": event_code,
                "athletes": [], "splits": [], "gps_points": []}
    with open(raw_dir / "teams.json", "w", encoding="utf-8") as f:
        json.dump(teams_data, f, ensure_ascii=False, indent=2)

    # 解析选手列表
    raw_athletes = []
    for cls in teams_data["data"]:
        class_name = cls["classname"]
        for t in cls["teams"]:
            bib      = t.get("r")
            finished = bool(t.get("fin"))
            dnf_type = "N/A"
            if not finished:
                if "Retired" in class_name:
                    dnf_type = "Retired"
                elif "Disqualified" in class_name:
                    dnf_type = "Disqualified"
                else:
                    dnf_type = "Unknown"
            raw_athletes.append({
                "year":        year + 2000,
                "event_code":  event_code,
                "bib":         bib,
                "name":        t.get("n", ""),
                "class":       class_name,
                "finished":    finished,
                "dnf_type":    dnf_type,
                "finish_time": t.get("t", "") if finished else "",
                "dnf_at_cp":   t.get("lc", "") if not finished else "",
                "last_cp":     t.get("lc", ""),
                "last_time":   t.get("dt", ""),
                "nationality": (t.get("f") or "").replace(".gif", ""),
                "tracking_url": f"{BASE_LIVE}/{event_code}/?b={bib}",
                "gps_last_lat":  None,
                "gps_last_lon":  None,
                "gps_last_time": None,
                "gps_point_count": 0,
            })

    fin_count = sum(1 for a in raw_athletes if a["finished"])
    dnf_count = sum(1 for a in raw_athletes if not a["finished"])
    print(f"  选手: {len(raw_athletes)} 人  完赛={fin_count}  DNF={dnf_count}")

    # ── details (splits) ────────────────────────────────────────
    all_splits = []
    all_details = {a["bib"]: a for a in raw_athletes}

    print(f"  [details] 获取检查点分段...")
    for athlete in tqdm(raw_athletes, desc=f"  {event_code} details", leave=False):
        bib = athlete["bib"]
        time.sleep(REQUEST_DELAY)
        detail = fetch_json(
            f"{EDITOR_API}/{event_code}/details",
            params={"id": bib},
            referer=f"{BASE_LIVE}/{event_code}/?b={bib}"
        )
        if not detail or not detail.get("success"):
            continue
        d = detail["data"]
        with open(raw_dir / f"detail_bib{bib:03d}.json", "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

        # 更新详情
        det_info = d.get("details", {})
        all_details[bib]["total_time"]     = det_info.get("Time Taken", "")
        all_details[bib]["total_dwell"]    = d.get("totaldwell", "")
        all_details[bib]["splits_count"]   = len(d.get("splits", []))

        for sp in d.get("splits", []):
            all_splits.append({
                "year":         year + 2000,
                "event_code":   event_code,
                "bib":          bib,
                "name":         athlete["name"],
                "finished":     athlete["finished"],
                "dnf_type":     athlete["dnf_type"],
                "cp_id":        sp.get("i"),
                "cp_name":      sp.get("n"),
                "cp_type":      sp.get("ct"),
                "arrival_time": sp.get("v"),
                "split_label":  sp.get("s"),
                "split_secs":   sp.get("ss"),
                "elapsed_str":  sp.get("sss"),
                "dwell_secs":   sp.get("ds"),
            })

    # ── GPS traces ───────────────────────────────────────────────
    all_gps_points = []
    if fetch_gps:
        print(f"  [GPS] 下载轨迹...")
        for athlete in tqdm(raw_athletes, desc=f"  {event_code} GPS", leave=False):
            bib  = athlete["bib"]
            name = athlete["name"]
            time.sleep(REQUEST_DELAY)
            kml_text = fetch_kml(event_code, bib)
            if not kml_text:
                tqdm.write(f"    bib={bib} 无GPS数据")
                continue

            # 保存 KML
            safe = name.replace("[Retired] ","").replace("[Disqualified] ","").split()[0].replace("/","_")
            kml_path = gps_dir / f"bib{bib:03d}_{safe}.kml"
            with open(kml_path, "w", encoding="utf-8") as f:
                f.write(kml_text)

            pts = parse_kml_points(kml_text)
            last_pt = pts[-1] if pts else None

            # ★ 更新精确停止坐标
            if last_pt:
                all_details[bib]["gps_last_lat"]  = last_pt["lat"]
                all_details[bib]["gps_last_lon"]  = last_pt["lon"]
                all_details[bib]["gps_last_time"] = last_pt["timestamp"]
                all_details[bib]["gps_point_count"] = len(pts)

            for p in pts:
                all_gps_points.append({
                    "year":      year + 2000,
                    "event_code": event_code,
                    "bib":       bib,
                    "name":      name,
                    "finished":  athlete["finished"],
                    "dnf_type":  athlete["dnf_type"],
                    "timestamp": p["timestamp"],
                    "lat":       p["lat"],
                    "lon":       p["lon"],
                })
            tqdm.write(
                f"    bib={bib:3d} {'[DNF]' if not athlete['finished'] else '[FIN]'} "
                f"{name[:22]:22s}: {len(pts):3d} 点"
                + (f"  最后: {last_pt['lat']:.5f},{last_pt['lon']:.5f}" if last_pt else "")
            )

    athletes_list = list(all_details.values())
    print(f"  [✓] splits={len(all_splits)}  gps_pts={len(all_gps_points)}")
    return {
        "year": year,
        "event_code": event_code,
        "athletes": athletes_list,
        "splits": all_splits,
        "gps_points": all_gps_points,
    }


# ── 多年汇总输出 ──────────────────────────────────────────────────

def save_all(all_results: list[dict]):
    print(f"\n{'='*55}")
    print("  生成汇总输出...")
    print(f"{'='*55}")

    all_athletes  = []
    all_splits    = []
    all_gps       = []

    for res in all_results:
        all_athletes.extend(res["athletes"])
        all_splits.extend(res["splits"])
        all_gps.extend(res["gps_points"])

    df_all   = pd.DataFrame(all_athletes)
    df_splits = pd.DataFrame(all_splits)
    df_gps    = pd.DataFrame(all_gps)
    df_dnf    = df_all[df_all["finished"] == False].copy()

    # DNF 列顺序
    dnf_cols = ["year","event_code","bib","name","class","nationality",
                "dnf_at_cp","last_time",
                "gps_last_lat","gps_last_lon","gps_last_time",
                "gps_point_count","finish_time","total_time","tracking_url"]
    dnf_cols = [c for c in dnf_cols if c in df_dnf.columns]

    # ── CSV ─────────────────────────────────────────────────────
    df_all.to_csv(CSV_DIR / "all_years_athletes.csv",  index=False, encoding="utf-8-sig")
    df_dnf[dnf_cols].to_csv(CSV_DIR / "all_years_dnf.csv", index=False, encoding="utf-8-sig")
    if not df_splits.empty:
        df_splits.to_csv(CSV_DIR / "all_years_splits.csv", index=False, encoding="utf-8-sig")
    if not df_gps.empty:
        df_gps.to_csv(CSV_DIR / "all_years_gps.csv", index=False, encoding="utf-8-sig")

    print(f"  [✓] CSV → {CSV_DIR}/")

    # ── Excel ────────────────────────────────────────────────────
    xlsx_path = OUTPUT_DIR / "HK4TUC_All_Years.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df_all.to_excel(writer, sheet_name="所有选手", index=False)
        df_dnf[dnf_cols].to_excel(writer, sheet_name="DNF精确坐标", index=False)
        df_all[df_all["finished"] == True].to_excel(writer, sheet_name="完赛选手", index=False)
        if not df_splits.empty:
            df_splits.to_excel(writer, sheet_name="检查点分段", index=False)

        # 各年份单独 Sheet
        for yr in YEARS:
            df_yr = df_all[df_all["year"] == yr + 2000]
            if not df_yr.empty:
                df_yr.to_excel(writer, sheet_name=f"{yr+2000}年", index=False)

    print(f"  [✓] Excel → {xlsx_path}")

    # ── Markdown 报告 ────────────────────────────────────────────
    generate_report(df_all, df_dnf, df_splits, dnf_cols)

    # ── 地图 ─────────────────────────────────────────────────────
    generate_map(df_all, all_gps)

    print(f"\n{'='*55}")
    print(f"  完成！全部文件已保存至: {OUTPUT_DIR.resolve()}")
    print(f"{'='*55}")


def generate_report(df_all, df_dnf, df_splits, dnf_cols):
    lines = []
    lines.append("# HK4TUC 多年份 DNF 分析报告 (2021–2026)\n")
    lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"> 注: 2021年前数据在 dottrack.asia 平台无记录\n\n")

    # 跨年统计表
    lines.append("## 各年份总览\n\n")
    lines.append("| 年份 | 总参赛 | 完赛 | DNF | 完赛率 | 冠军 | 冠军时间 |\n")
    lines.append("|------|-------|------|-----|--------|------|----------|\n")
    for yr in YEARS:
        df_yr = df_all[df_all["year"] == yr + 2000]
        if df_yr.empty:
            continue
        total    = len(df_yr)
        fin      = int(df_yr["finished"].sum())
        dnf      = total - fin
        rate     = fin / total * 100
        fin_rows = df_yr[df_yr["finished"] == True]
        if not fin_rows.empty:
            # 用finish_time，按字符串排序近似（格式 HH:MM:SS）
            best = fin_rows.sort_values("finish_time").iloc[0]
            champ = best["name"].replace("[Retired] ", "").replace("[Disqualified] ", "")
            champ_t = best.get("finish_time") or best.get("total_time", "")
        else:
            champ = "—"; champ_t = "—"
        lines.append(f"| {yr+2000} | {total} | {fin} | {dnf} | {rate:.0f}% | {champ} | {champ_t} |\n")

    # 各年DNF精确坐标
    lines.append("\n## 各年份 DNF 选手精确停止坐标\n\n")
    lines.append("> GPS纬/经度 = KML轨迹最后一个 ping 点（真实停止位置）\n\n")

    for yr in YEARS:
        df_yr_dnf = df_dnf[df_dnf["year"] == yr + 2000]
        if df_yr_dnf.empty:
            continue
        lines.append(f"### {yr+2000} 年 ({len(df_yr_dnf)} 人 DNF)\n\n")
        lines.append("| Bib | 姓名 | 分类 | 最后计时CP | GPS停止时间 | GPS纬度 | GPS经度 | 地图 |\n")
        lines.append("|-----|------|------|------------|------------|---------|---------|------|\n")
        for _, row in df_yr_dnf.sort_values("bib").iterrows():
            name = str(row["name"]).replace("[Retired] ","").replace("[Disqualified] ","")
            lat  = row.get("gps_last_lat")
            lon  = row.get("gps_last_lon")
            gps_t = row.get("gps_last_time", "")
            if pd.notna(lat) and lat:
                maps = f"[📍](https://maps.google.com/?q={lat},{lon})"
                lat_s = f"{lat:.5f}"; lon_s = f"{lon:.5f}"
            else:
                maps = "N/A"; lat_s = "N/A"; lon_s = "N/A"
            lines.append(
                f"| {row['bib']} | {name} | {row.get('class','')} | "
                f"{row.get('dnf_at_cp','')} | {gps_t} | {lat_s} | {lon_s} | {maps} |\n"
            )
        lines.append("\n")

    # DNF 最常见放弃点（跨年）
    if not df_splits.empty:
        lines.append("## 跨年 DNF 最常见放弃区间\n\n")
        dnf_bibs_per_year = df_dnf.groupby(["year","event_code","bib"]).size().reset_index()[["year","event_code","bib"]]
        df_s_dnf_all = df_splits.merge(dnf_bibs_per_year, on=["year","event_code","bib"])
        df_s_dnf_valid = df_s_dnf_all[df_s_dnf_all["arrival_time"].notna()]
        if not df_s_dnf_valid.empty:
            last_cp = df_s_dnf_valid.sort_values("elapsed_str").groupby(["year","event_code","bib"]).last().reset_index()
            cp_cnt = last_cp.groupby("cp_name").size().sort_values(ascending=False)
            lines.append("| 最后抵达检查点 | DNF总人次 |\n|--------------|----------|\n")
            for cp, cnt in cp_cnt.items():
                lines.append(f"| {cp} | {cnt} |\n")

    report_path = OUTPUT_DIR / "DNF_All_Years_Report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"  [✓] 报告 → {report_path}")


def generate_map(df_all: pd.DataFrame, all_gps: list[dict]):
    try:
        import folium
        from collections import defaultdict

        m = folium.Map(location=[22.35, 114.15], zoom_start=11, tiles="CartoDB positron")

        year_colors = {
            2021: "#e74c3c", 2022: "#e67e22", 2023: "#f1c40f",
            2024: "#2ecc71", 2025: "#3498db", 2026: "#9b59b6",
        }

        # 轨迹线（仅DNF，按年份着色）
        tracks = defaultdict(list)
        for p in all_gps:
            key = (p["year"], p["bib"])
            tracks[key].append((p["lat"], p["lon"]))

        for (yr, bib), coords in tracks.items():
            row = df_all[(df_all["year"] == yr) & (df_all["bib"] == bib)]
            if row.empty or row.iloc[0]["finished"]:
                continue
            color = year_colors.get(yr, "#999")
            folium.PolyLine(coords, color=color, weight=2, opacity=0.6,
                            tooltip=f"{yr} #{bib}").add_to(m)

        # DNF 精确停止标记
        for _, row in df_all[df_all["finished"] == False].iterrows():
            lat = row.get("gps_last_lat"); lon = row.get("gps_last_lon")
            if not pd.notna(lat) or not lat:
                continue
            yr = int(row["year"])
            color = year_colors.get(yr, "red")
            name = str(row["name"]).replace("[Retired] ","").replace("[Disqualified] ","")
            popup = (
                f"<b>{yr} #{row['bib']} {name}</b><br>"
                f"状态: {row.get('dnf_type','DNF')}<br>"
                f"末位CP: {row.get('dnf_at_cp','')}<br>"
                f"GPS停止: {row.get('gps_last_time','')}<br>"
                f"坐标: {lat:.5f}, {lon:.5f}<br>"
                f"<a href='{row.get('tracking_url','')}' target='_blank'>轨迹 ↗</a>"
            )
            folium.CircleMarker(
                [lat, lon], radius=6,
                color=color, fill=True, fill_opacity=0.85,
                popup=folium.Popup(popup, max_width=280),
                tooltip=f"{yr} #{row['bib']} {name}"
            ).add_to(m)

        # 图例
        legend = "<div style='position:fixed;bottom:30px;left:30px;z-index:1000;" \
                 "background:white;padding:12px 18px;border-radius:8px;" \
                 "box-shadow:0 2px 8px rgba(0,0,0,0.3);font-size:13px;'>" \
                 "<b>HK4TUC DNF 停止点</b><br>"
        for yr, clr in year_colors.items():
            legend += f"<span style='color:{clr}'>●</span> {yr}<br>"
        legend += "</div>"
        m.get_root().html.add_child(folium.Element(legend))

        map_path = OUTPUT_DIR / "HK4TUC_DNF_Map.html"
        m.save(str(map_path))
        print(f"  [✓] 地图 → {map_path}")
    except Exception as e:
        print(f"  [!] 地图生成失败: {e}")


# ── 主入口 ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="HK4TUC 多年份数据收集")
    parser.add_argument("--no-gps", action="store_true", help="跳过 GPS 轨迹下载")
    parser.add_argument("--year", type=int, help="只收集指定年份（如 --year 2023）")
    parser.add_argument("--resume", action="store_true",
                        help="跳过已有 raw JSON 的年份（断点续传）")
    args = parser.parse_args()

    setup_dirs()

    years_to_run = YEARS
    if args.year:
        yr2 = args.year % 100
        if yr2 not in YEARS:
            print(f"[!] {args.year} 不在支持范围内，可用: {[y+2000 for y in YEARS]}")
            exit(1)
        years_to_run = [yr2]

    all_results = []
    for yr in years_to_run:
        event_code = f"{yr}hk4tuc"
        # 断点续传：如果 teams.json 已存在则加载缓存
        teams_cache = RAW_DIR / event_code / "teams.json"
        if args.resume and teams_cache.exists() and not args.no_gps is False:
            print(f"\n[跳过 {yr+2000}] 缓存已存在: {teams_cache}")
            # 仍然加载已有数据到 all_results
            with open(teams_cache) as f:
                td = json.load(f)
            athletes = []
            for cls in td["data"]:
                for t in cls["teams"]:
                    bib = t["r"]
                    finished = bool(t.get("fin"))
                    dnf_type = "Retired" if "Retired" in cls["classname"] else \
                               "Disqualified" if "Disqualified" in cls["classname"] else "N/A"
                    a = {
                        "year": yr+2000, "event_code": event_code,
                        "bib": bib, "name": t["n"], "class": cls["classname"],
                        "finished": finished, "dnf_type": dnf_type if not finished else "N/A",
                        "finish_time": t.get("t","") if finished else "",
                        "dnf_at_cp": t.get("lc","") if not finished else "",
                        "last_cp": t.get("lc",""), "last_time": t.get("dt",""),
                        "nationality": (t.get("f") or "").replace(".gif",""),
                        "tracking_url": f"{BASE_LIVE}/{event_code}/?b={bib}",
                        "gps_last_lat": None, "gps_last_lon": None,
                        "gps_last_time": None, "gps_point_count": 0,
                    }
                    # 尝试读取缓存 GPS 坐标
                    kml_files = list((GPS_DIR / event_code).glob(f"bib{bib:03d}_*.kml"))
                    if kml_files:
                        with open(kml_files[0]) as f:
                            pts = parse_kml_points(f.read())
                        if pts:
                            a["gps_last_lat"]  = pts[-1]["lat"]
                            a["gps_last_lon"]  = pts[-1]["lon"]
                            a["gps_last_time"] = pts[-1]["timestamp"]
                            a["gps_point_count"] = len(pts)
                    athletes.append(a)
            all_results.append({"year": yr, "event_code": event_code,
                                 "athletes": athletes, "splits": [], "gps_points": []})
            continue

        result = collect_year(yr, fetch_gps=not args.no_gps)
        all_results.append(result)
        time.sleep(1)

    save_all(all_results)
