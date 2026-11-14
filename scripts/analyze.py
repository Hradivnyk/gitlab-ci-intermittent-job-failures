"""Аналіз ЛР_7 (протокол ЛР_6): повторені й перемежовані збої завдань перевірок за data/processed/*_failures.csv.
Запуск: python -X utf8 scripts/analyze.py [шлях до ручної перевірки, типово data/processed/manual_review_lr7.csv]
Вхід:  data/processed/*_failures.csv і *_summary.json (classify.py); ручні рішення — failed_job_id, manual_category.
Вихід: друк таблиць у консоль + data/processed/lr7_results.json (для рисунків і звіту).
Менше 30 перемежованих збоїв без allow_failure разом -> лише описова статистика (інтервали Вільсона), критерії H1–H3
не проводяться (рішення студента, 2026-10-31). Лише стандартна бібліотека Python.
"""
import csv
import glob
import json
import math
import os
import statistics as st
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "data", "processed")
CATS = ("середовище", "твердження", "невизначено")
MIN_N = 30  # мінімум перемежованих збоїв для критеріїв H1–H3
ALPHA = 0.05


# ---------- статистика ----------
def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"),) * 2
    p, d = k / n, 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0, c - h), min(1, c + h)


def pct(k, n):
    if not n:
        return "—"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {100 * k / n:.0f}% [{100 * lo:.0f}–{100 * hi:.0f}]"


def fisher_greater(a, b, c, d):
    """Точний однобічний критерій Фішера: P(X >= a), де a — «успіхи» групи 1 (a+b), c — групи 2 (c+d)."""
    n1, n2, k = a + b, c + d, a + c
    tot = math.comb(n1 + n2, k)
    return sum(math.comb(n1, x) * math.comb(n2, k - x) for x in range(a, min(n1, k) + 1)) / tot


def fisher_two_sided(a, b, c, d):
    n1, n2, k = a + b, c + d, a + c
    tot = math.comb(n1 + n2, k)
    pr = lambda x: math.comb(n1, x) * math.comb(n2, k - x) / tot
    p0 = pr(a)
    return min(1.0, sum(pr(x) for x in range(max(0, k - n2), min(n1, k) + 1) if pr(x) <= p0 * (1 + 1e-9)))


def mann_whitney(x, y):
    """Двобічний критерій Манна–Вітні (нормальне наближення з поправкою на однакові значення)."""
    n1, n2 = len(x), len(y)
    allv = sorted([(v, 0) for v in x] + [(v, 1) for v in y])
    ranks, i = {}, 0
    ties = 0.0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1][0] == allv[i][0]:
            j += 1
        for t in range(i, j + 1):
            ranks[t] = (i + j) / 2 + 1
        ties += (j - i + 1) ** 3 - (j - i + 1)
        i = j + 1
    r1 = sum(ranks[t] for t, (_, g) in enumerate(allv) if g == 0)
    u = r1 - n1 * (n1 + 1) / 2
    n = n1 + n2
    sd = math.sqrt(n1 * n2 / 12 * ((n + 1) - ties / (n * (n - 1)))) if n > 1 else 0
    if sd == 0:
        return u, 1.0
    z = (abs(u - n1 * n2 / 2) - 0.5) / sd
    return u, math.erfc(max(z, 0) / math.sqrt(2))


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, run = [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = run
    return adj


def num(r, k):
    return float(r[k]) if r[k] != "" else None


def med(v):
    return f"{st.median(v):.1f}" if v else "—"


def iqr(v):
    if len(v) < 4:
        return "—"
    q = st.quantiles(v, n=4)
    return f"{q[0]:.1f}–{q[2]:.1f}"


# ---------- дані ----------
manual_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(P, "manual_review_lr7.csv")
manual = {}
if os.path.exists(manual_path):
    manual = {r["failed_job_id"]: r["manual_category"] for r in csv.DictReader(open(manual_path, encoding="utf-8-sig"))}
projects, summaries = {}, {}
for f in sorted(glob.glob(os.path.join(P, "*_failures.csv"))):
    sf = f.replace("_failures.csv", "_summary.json")
    if not os.path.exists(sf):  # застарілі файли без підсумків (наприклад, пробні) пропускаємо
        continue
    summ = json.load(open(sf, encoding="utf-8"))
    rows = [r for r in csv.DictReader(open(f, encoding="utf-8-sig")) if "failed_job_id" in r]  # проєкт без повторених збоїв: лише заголовок
    for r in rows:
        r["auto_category"] = r["category"]
        if r["failed_job_id"] in manual:
            r["category"], r["basis_level"] = manual[r["failed_job_id"]], "ручна перевірка"
    projects[summ["project"]] = rows
    summaries[summ["project"]] = summ
if not projects:
    sys.exit("Немає data/processed/*_failures.csv з *_summary.json: спершу запустити classify.py")


def report(name, rows, summ, results):
    """Описова статистика одного набору (проєкт або разом) для двох зрізів: усі збої / без allow_failure."""
    print("=" * 100, f"\n{name}")
    print(f" конвеєрів {summ['pipelines']}, спроб завдань {summ['attempts']}, спроб перевірок {summ['test_attempts']} "
          f"(невдалих {summ['test_failed']}), пар «коміт — завдання» з невдалою спробою {summ['failed_pairs']}")
    res = {"summary": summ}
    for label, sub in (("усі", rows), ("без allow_failure", [r for r in rows if r["allow_failure"] == "False"])):
        inter = [r for r in sub if r["intermittent"] == "True"]
        print(f" --- {label}: повторених {len(sub)} (W {sum(r['kind'] == 'W' for r in sub)}, P {sum(r['kind'] == 'P' for r in sub)}), перемежованих {len(inter)}")
        if label == "усі":
            print(f"   повторені серед пар із невдалою спробою: {pct(len(sub), summ['failed_pairs'])}")
        print(f"   результативність повторного запуску (перемежовані / повторені): {pct(len(inter), len(sub))}")
        r_ = {"repeated": len(sub), "intermittent": len(inter)}
        for scope, s in (("повторені", sub), ("перемежовані", inter)):
            c = Counter(r["category"] for r in s)
            n = len(s)
            low, up = c["середовище"], c["середовище"] + c["невизначено"]
            print(f"   категорії ({scope}): " + ", ".join(f"{k} {c[k]}" for k in CATS)
                  + (f" | середовище: нижня межа {pct(low, n)}, верхня {pct(up, n)}" if n else ""))
            r_[f"cat_{scope}"] = dict(c)
        print("   результативність за категоріями (перемежовані / повторені):")
        for k in CATS:
            s = [r for r in sub if r["category"] == k]
            print(f"     {k}: {pct(sum(r['intermittent'] == 'True' for r in s), len(s))}")
        print("   час відновлення, хв (медіана; Q1–Q3; n) і групування у вікні 30 хв (15 / 60):")
        for k in CATS + ("усі",):
            s = inter if k == "усі" else [r for r in inter if r["category"] == k]
            rec = [num(r, "recovery_min") for r in s if num(r, "recovery_min") is not None]
            cl = [sum(r[f"cluster_{w}"] == "True" for r in s) for w in (30, 15, 60)]
            print(f"     {k}: {med(rec)}; {iqr(rec)}; n={len(rec)} | групування {pct(cl[0], len(s))} (15: {cl[1]}, 60: {cl[2]})")
        wasted = [num(r, "wasted_min") for r in inter if num(r, "wasted_min") is not None]
        print(f"   витрачений час, хв: медіана {med(wasted)}, Q1–Q3 {iqr(wasted)}")
        mr = [r for r in inter if r["mr_iid"] != ""]
        after = [num(r, "recovery_min") / num(r, "mr_after_fail_min") for r in mr if num(r, "mr_after_fail_min")]
        if after:
            print(f"   зв'язок з MR: {len(mr)}/{len(inter)}; частка часу відновлення в часі від збою до злиття: "
                  f"медіана {100 * st.median(after):.1f}%, макс {100 * max(after):.1f}%")
        jobs = Counter(r["job"] for r in inter).most_common(6)
        print("   завдання з перемежованими збоями:", dict(jobs) if jobs else "—")
        r_["recovery_min"] = [num(r, "recovery_min") for r in inter if num(r, "recovery_min") is not None]
        results.setdefault(name, {})[label] = r_
    results[name]["summary"] = summ


def compute(rows, win=30, max_rec=None, skip_h1=False):
    """H1–H3 для збоїв без allow_failure -> (перемежованих, рядок-опис, {гіпотеза: p}); p=None, якщо <MIN_N перемежованих."""
    sub = [r for r in rows if r["allow_failure"] == "False"]
    inter = [r for r in sub if r["intermittent"] == "True"]
    if len(inter) < MIN_N:
        return len(inter), {}, None
    env_all = [r for r in sub if r["category"] == "середовище"]
    ass_all = [r for r in sub if r["category"] == "твердження"]
    env_i = [r for r in env_all if r["intermittent"] == "True"]
    ass_i = [r for r in ass_all if r["intermittent"] == "True"]
    out, desc = {}, {}
    if env_all and ass_all:  # H3: результативність повторного запуску вища для «середовище» (однобічний)
        out["H3"] = fisher_greater(len(env_i), len(env_all) - len(env_i), len(ass_i), len(ass_all) - len(ass_i))
        desc["H3"] = f"середовище {pct(len(env_i), len(env_all))} проти твердження {pct(len(ass_i), len(ass_all))}"
    if env_i and ass_i:
        if not skip_h1:  # H1: частка збоїв у часових групах вища для «середовище» (однобічний)
            ce = sum(r[f"cluster_{win}"] == "True" for r in env_i)
            ca = sum(r[f"cluster_{win}"] == "True" for r in ass_i)
            out["H1"] = fisher_greater(ce, len(env_i) - ce, ca, len(ass_i) - ca)
            desc["H1"] = f"середовище {pct(ce, len(env_i))} проти твердження {pct(ca, len(ass_i))}"
        # H2: час відновлення відрізняється між категоріями (двобічний)
        x = [num(r, "recovery_min") for r in env_i if num(r, "recovery_min") is not None]
        y = [num(r, "recovery_min") for r in ass_i if num(r, "recovery_min") is not None]
        if max_rec:
            x, y = [v for v in x if v <= max_rec], [v for v in y if v <= max_rec]
        if x and y:
            out["H2"] = mann_whitney(x, y)[1]
            desc["H2"] = f"медіана {st.median(x):.1f} хв (n={len(x)}) проти {st.median(y):.1f} хв (n={len(y)})"
    return len(inter), desc, out


def fp(x):
    return "< 0,0001" if x < 1e-4 else f"= {x:.4f}".replace(".", ",")


def tests(rows, label="Критерії H1–H3 (разом, без allow_failure)", win=30, max_rec=None, quiet=False, skip_h1=False):
    n, desc, out = compute(rows, win, max_rec, skip_h1)
    if not quiet:
        print("=" * 100, f"\n{label}: перемежованих {n}")
    if out is None:
        if not quiet:
            print(f" менше {MIN_N} -> критерії не проводяться, лише описова статистика з інтервалами Вільсона")
        return None
    keys = list(out)
    adj = holm([out[k] for k in keys])
    for k, pv, pa in zip(keys, [out[k] for k in keys], adj):
        print(f" {k}: p {fp(pv)}, p (Холм) {fp(pa)} -> {'відхилено H0' if pa < ALPHA else 'H0 не відхилено'} при α = {ALPHA} | {desc[k]}")
    return dict(zip(keys, adj))


def events(rows, gap=30):
    """Збої одного проєкту, що починаються не пізніше ніж за gap хв від попереднього, — одна подія; представник — найраніший."""
    from datetime import datetime
    reps = []
    byp = {}
    for r in rows:
        byp.setdefault(r["project"], []).append(r)
    for rs in byp.values():
        rs = sorted(rs, key=lambda r: r["started_at"])
        last = None
        for r in rs:
            t = datetime.fromisoformat(r["started_at"].replace("Z", "+00:00"))
            if last is None or (t - last).total_seconds() > gap * 60:
                reps.append(r)
            last = t
    return reps


def robust(rows):
    """Перевірки стійкості: інша категорія, інше вікно, лише gitlab-lsp, без тривалих відновлень, невизначено в обидва боки, події, лише вид W."""
    sub = lambda f: [dict(r) for r in rows if f(r)]
    auto = [dict(r, category=r["auto_category"]) for r in rows]
    out_all = {}
    variants = [
        ("V0 основний аналіз (категорії після ручної перевірки, вікно 30 хв)", rows, {}),
        ("V1 лише автоматичні категорії (без ручних)", auto, {}),
        ("V2 вікно групування 15 хв", rows, {"win": 15}),
        ("V3 вікно групування 60 хв", rows, {"win": 60}),
        ("V4 лише gitlab-lsp", sub(lambda r: "gitlab-lsp" in r["project"]), {}),
        ("V5 без часів відновлення понад 24 год (H2)", rows, {"max_rec": 24 * 60}),
        ("V6 «невизначено» віднесено до «твердження»", [dict(r, category="твердження" if r["category"] == "невизначено" else r["category"]) for r in rows], {}),
        ("V7 «невизначено» віднесено до «середовище»", [dict(r, category="середовище" if r["category"] == "невизначено" else r["category"]) for r in rows], {}),
        ("V8 лише вид повтору W", sub(lambda r: r["kind"] == "W"), {}),
        ("V9 подія замість збою (збої в межах 30 хв — одна подія)", events([r for r in rows if r["allow_failure"] == "False"]), {"skip_h1": True}),
    ]
    print("=" * 100, "\nПеревірки стійкості (H1–H3, без allow_failure)")
    for name, data, kw in variants:
        print(f"\n {name}")
        res = tests(data, label="  ", quiet=True, **kw)
        n = compute(data, **{k: v for k, v in kw.items()})[0]
        print(f"  перемежованих {n}" + ("" if res is not None else " -> менше 30, критерії не проводяться"))
        out_all[name] = res
    return out_all


results = {}
allrows = [r for rows in projects.values() for r in rows]
tot = {k: sum(s[k] for s in summaries.values()) for k in ("pipelines", "attempts", "test_attempts", "test_failed", "failed_pairs")}
for pname, rows in projects.items():
    report(pname, rows, summaries[pname], results)
report("РАЗОМ", allrows, tot, results)
results["tests"] = tests(allrows)
results["robust"] = robust(allrows)
if manual:
    rev = [r for r in allrows if r["failed_job_id"] in manual]
    agree = sum(r["auto_category"] == r["category"] for r in rev)
    print("=" * 100, f"\nРучна перевірка (файл {os.path.basename(manual_path)}): {len(rev)} випадків, збіг з автоматикою {pct(agree, len(rev))}")
    print(" розбіжності (авто -> ручна):", dict(Counter((r["auto_category"], r["category"]) for r in rev if r["auto_category"] != r["category"])))
json.dump(results, open(os.path.join(P, "lr7_results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\nрезультати -> data/processed/lr7_results.json")
