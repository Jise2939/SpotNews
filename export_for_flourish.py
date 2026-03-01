"""
生成 Flourish 专用 CSV（干净编码，列名英文，无BOM）
"""
import pandas as pd
from pathlib import Path

df = pd.read_csv("hk4tuc_all_years/csv/all_years_dnf.csv")

# 清理列名（去BOM）
df.columns = df.columns.str.replace('\ufeff', '')

# 清理姓名（去掉[Retired]前缀）
df["name"] = df["name"].str.replace(r'\[Retired\] |\[Disqualified\] ', '', regex=True).str.strip()

# 只保留Flourish需要的列，重命名为直观英文
out = pd.DataFrame({
    "Latitude":       df["gps_last_lat"],
    "Longitude":      df["gps_last_lon"],
    "Name":           df["name"],
    "Year":           df["year"].astype(str),
    "Status":         df["class"],
    "Last_CP":        df["dnf_at_cp"],
    "GPS_Stop_Time":  df["gps_last_time"],
    "Nationality":    df["nationality"].str.replace("_", " ").str.title(),
    "Bib":            df["bib"],
    "Tracking_URL":   df["tracking_url"],
})

# 去掉没有坐标的行
out = out.dropna(subset=["Latitude", "Longitude"])
out = out[out["Latitude"] != 0]

# 保存（无BOM，标准UTF-8）
out_path = Path("hk4tuc_all_years/flourish_dnf_map.csv")
out.to_csv(out_path, index=False, encoding="utf-8")

print(f"✓ 已生成: {out_path.resolve()}")
print(f"  行数: {len(out)}")
print(f"\n列名预览:")
print(out.columns.tolist())
print(f"\n前3行:")
print(out.head(3).to_string())
