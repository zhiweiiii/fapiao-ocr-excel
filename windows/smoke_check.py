"""Windows 发布包冒烟测试：校验 /fapiao/ocr_excel 导出的 Excel 主表字段与真值一致。

用法：python smoke_check.py <程序目录> <导出的xlsx> <真值json>
"""
import json
import sys
from pathlib import Path

import pandas as pd

app_dir, xlsx_path, truth_path = sys.argv[1:4]
sys.path.insert(0, app_dir)
import main  # noqa: E402

df = pd.read_excel(xlsx_path, sheet_name=0, dtype=str).fillna("")
truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
row = df.iloc[0]

mismatches = []
for key, expected in truth.items():
    if key == "items":
        continue
    got = str(row.get(main.MAIN_FIELD_MAP[key], "")).strip()
    if got != str(expected).strip():
        mismatches.append(f"{key}: got={got!r} expected={expected!r}")

total = len(truth) - 1
print(f"main fields matched: {total - len(mismatches)}/{total}")
for m in mismatches:
    print("  MISMATCH", m)
sys.exit(1 if mismatches else 0)
