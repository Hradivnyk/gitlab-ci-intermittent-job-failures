"""Підготовка даних ЛР_7: підсумки очищення з data/raw/*.jsonl і зведений набір даних.
Запуск: python -X utf8 scripts/lr7_dataset.py
Вихід: таблиця очищення в консолі; data/processed/lr7_dataset.csv — по одному рядку на повторений збій з остаточною категорією.
Остаточна категорія: ручна (data/processed/manual_review_lr7.csv), якщо випадок перевірено, інакше автоматична.
"""
import csv
import glob
import json
import os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, PROC = os.path.join(ROOT, "data", "raw"), os.path.join(ROOT, "data", "processed")
sys_path = os.path.join(ROOT, "scripts")
import importlib.util
spec = importlib.util.spec_from_file_location("classify", os.path.join(sys_path, "classify.py"))
cl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cl)  # правила відбору завдань перевірок беремо з classify.py

print("Очищення за проєктами")
total = Counter()
for f in sorted(glob.glob(os.path.join(RAW, "*.jsonl"))):
    rows = [json.loads(l) for l in open(f, encoding="utf-8")]
    name = rows[0]["project"].split("/")[-1]
    st = Counter(r["status"] for r in rows)
    is_test = lambda r: cl.TEST_JOB.search(r["name"] or "") and not cl.NOT_JS_JOB.search(r["name"] or "")
    tests = [r for r in rows if is_test(r)]
    usable = [r for r in tests if r["status"] in ("failed", "success")]
    created = [r["created_at"][:10] for r in rows]
    ids = [r["id"] for r in rows]
    stats = {"спроб завдань": len(rows), "конвеєрів із завданнями": len({r["pipeline_id"] for r in rows}),
             "дублікатів id завдань": len(ids) - len(set(ids)), "створено від": min(created), "створено до": max(created),
             "завдань за назвою перевірок": len(tests), "з них failed/success": len(usable),
             "вилучено (не перевірки)": len(rows) - len(tests), "вилучено (canceled, skipped, manual, created)": len(tests) - len(usable),
             "статуси": dict(st.most_common())}
    print(f"\n{name}"); [print(f"  {k}: {v}") for k, v in stats.items()]
    total.update({"attempts": len(rows), "tests": len(tests), "usable": len(usable)})
print("\nРазом:", dict(total))

manual = {}
mp = os.path.join(PROC, "manual_review_lr7.csv")
if os.path.exists(mp):
    manual = {r["failed_job_id"]: r["manual_category"] for r in csv.DictReader(open(mp, encoding="utf-8-sig"))}
COLS = ["project", "sha", "job", "failed_job_id", "kind", "intermittent", "retries", "failure_reason", "category", "category_auto",
        "category_manual", "basis_level", "allow_failure", "ref_kind", "started_at", "recovery_min", "wasted_min",
        "mr_iid", "mr_after_fail_min", "cluster_15", "cluster_30", "cluster_60"]
out = []
for f in sorted(glob.glob(os.path.join(PROC, "*_failures.csv"))):
    if not os.path.exists(f.replace("_failures.csv", "_summary.json")):
        continue
    for r in csv.DictReader(open(f, encoding="utf-8-sig")):
        if "failed_job_id" not in r:
            continue
        r["category_auto"], r["category_manual"] = r["category"], manual.get(r["failed_job_id"], "")
        if r["category_manual"]:
            r["category"], r["basis_level"] = r["category_manual"], "ручна перевірка"
        out.append({c: r[c] for c in COLS})
with open(os.path.join(PROC, "lr7_dataset.csv"), "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=COLS)
    w.writeheader()
    w.writerows(out)
print(f"\nНабір даних: {len(out)} повторених збоїв -> data/processed/lr7_dataset.csv")
