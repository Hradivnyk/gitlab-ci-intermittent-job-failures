"""Додаткові розрахунки для обговорення (ЛР_8) за data/processed/lr7_dataset.csv; збої без allow_failure.
Запуск: python -X utf8 scripts/lr8_extra.py > data/processed/lr8_extra.txt
Друкує: придатність `retry:when` (failure_reason у «середовище»), ціна повтору, базу для групування в часі
(випадкове розміщення збоїв у періоді проєкту), частку збоїв того самого коміту, число комітів.
"""
import csv
import math
import os
import random
import statistics as st
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = [r for r in csv.DictReader(open(os.path.join(ROOT, "data", "processed", "lr7_dataset.csv"), encoding="utf-8-sig"))
        if r["allow_failure"] == "False"]
inter = [r for r in rows if r["intermittent"] == "True"]
non = [r for r in rows if r["intermittent"] == "False"]
CATS = ("середовище", "твердження", "невизначено")
q = lambda v: (st.quantiles(v, n=4)[0], st.median(v), st.quantiles(v, n=4)[2]) if len(v) >= 4 else (None, st.median(v) if v else None, None)
f = lambda x: "—" if x is None else f"{x:.1f}"

print("1. failure_reason перемежованих збоїв за категорією (чи охопить retry:when за полем)")
for c in CATS:
    s = [r for r in inter if r["category"] == c]
    print(f"  {c} (n={len(s)}):", dict(Counter(r["failure_reason"] for r in s).most_common()))

print("\n2. Ціна повтору")
for c in CATS + ("усі",):
    s = [r for r in inter if c == "усі" or r["category"] == c]
    rt = [int(r["retries"]) for r in s]
    w = [float(r["wasted_min"]) for r in s]
    print(f"  перемежовані {c}: n={len(s)}, наступних спроб: медіана {st.median(rt)}, рівно 1 — {sum(x == 1 for x in rt)} ({100 * sum(x == 1 for x in rt) / len(s):.0f}%), "
          f"витрачений час, хв: Q1/мед/Q3 {'/'.join(f(x) for x in q(w))}, сума {sum(w) / 60:.1f} год")
for c in CATS + ("усі",):
    s = [r for r in non if c == "усі" or r["category"] == c]
    if not s:
        continue
    rt = [int(r["retries"]) for r in s]
    w = [float(r["wasted_min"]) for r in s]
    print(f"  повторені без успіху {c}: n={len(s)}, наступних спроб: медіана {st.median(rt)}, сума витраченого часу {sum(w) / 60:.1f} год (медіана {st.median(w):.1f} хв)")
rec = [float(r["recovery_min"]) for r in inter]
print(f"  сумарний час відновлення перемежованих: {sum(rec) / 60:.1f} год; без значень понад 24 год: {sum(x for x in rec if x <= 1440) / 60:.1f} год")

print("\n3. Групування в часі: спостережене і очікуване за випадкового розміщення")
def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))
period = {"gitlab-lsp": ("2026-09-01", "2026-11-01"), "design.gitlab.com": ("2026-08-01", "2026-11-01"), "gitlab-vscode-extension": ("2026-08-01", "2026-11-01")}
random.seed(11)
obs = exp_poisson = exp_perm = 0.0
n_all = 0
for name, (a, b) in period.items():
    s = [r for r in inter if r["project"].endswith(name)]
    if len(s) < 2:
        continue
    t0, t1 = (datetime.fromisoformat(x).replace(tzinfo=timezone.utc) for x in (a, b))
    span = (t1 - t0).total_seconds() / 60
    n = len(s)
    o = sum(r["cluster_30"] == "True" for r in s)
    lam = n / span
    pois = 1 - math.exp(-lam * 60)
    reps = 400
    cnt = 0
    for _ in range(reps):
        t = sorted(random.uniform(0, span) for _ in range(n))
        cnt += sum(1 for i, x in enumerate(t) if (i > 0 and x - t[i - 1] <= 30) or (i < n - 1 and t[i + 1] - x <= 30))
    perm = cnt / reps
    print(f"  {name}: n={n}, спостережено {o} ({100 * o / n:.0f}%), очікувано за Пуассоном {100 * pois:.0f}%, за випадковим розміщенням {100 * perm / n:.0f}%")
    obs += o; exp_poisson += pois * n; exp_perm += perm; n_all += n
print(f"  разом: n={n_all}, спостережено {100 * obs / n_all:.0f}%, очікувано (Пуассон) {100 * exp_poisson / n_all:.0f}%, (випадкове розміщення) {100 * exp_perm / n_all:.0f}%")
for c in CATS:
    s = [r for r in inter if r["category"] == c]
    print(f"  {c}: у вікні 30 хв {sum(r['cluster_30'] == 'True' for r in s)}/{len(s)}")

print("\n4. Збої того самого коміту")
bysha = defaultdict(list)
for r in rows:
    bysha[(r["project"], r["sha"])].append(r)
ib = defaultdict(list)
for r in inter:
    ib[(r["project"], r["sha"])].append(r)
sib = [r for r in inter if len(ib[(r["project"], r["sha"])]) > 1]
print(f"  перемежованих збоїв {len(inter)} на {len(ib)} різних комітах; із них мають інший перемежований збій того самого коміту: {len(sib)} ({100 * len(sib) / len(inter):.0f}%)")
for c in ("середовище", "твердження"):
    s = [r for r in inter if r["category"] == c]
    k = sum(len(ib[(r["project"], r["sha"])]) > 1 for r in s)
    print(f"    {c}: {k}/{len(s)}")
cl_not_sib = [r for r in inter if r["cluster_30"] == "True" and len(ib[(r["project"], r["sha"])]) == 1]
print(f"  групування в 30 хв без збою того самого коміту: {len(cl_not_sib)} із {sum(r['cluster_30'] == 'True' for r in inter)}")
size = Counter(len(v) for v in ib.values())
print("  розмір групи збоїв одного коміту:", dict(sorted(size.items())))
