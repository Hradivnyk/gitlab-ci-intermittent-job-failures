"""Аналіз сліпої повторної розмітки журналів (ЛР_8, тези): збіг рецензента з розміткою моделі, κ Коена, розбіжності.
Запуск: python -X utf8 scripts/lr8_review_analyze.py <review_R1.csv> [<review_R2.csv>]
        python -X utf8 scripts/lr8_review_analyze.py --self-test       (перевірка формул на синтетичних даних)
Вхід: CSV із форми (reviewer, position, category, note); ключ data/processed/lr8_review_key.csv.
Вибірка стратифікована за категорією моделі (15 / 15 / 10), тому частки відносяться до цієї вибірки, а не до всіх 192.
"""
import csv
import os
import random
import sys
from collections import Counter
from math import sqrt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = os.path.join(ROOT, "data", "processed", "lr8_review_key.csv")
CATS = ["середовище", "твердження", "невизначено"]


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def kappa(pairs):
    """Cohen's κ для списку пар (оцінка A, оцінка B)."""
    n = len(pairs)
    if n == 0:
        return float("nan")
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[c] * cb[c] for c in set(ca) | set(cb)) / (n * n)
    if pe == 1:
        return 1.0 if po == 1 else 0.0
    return (po - pe) / (1 - pe)


def read_key():
    return {int(r["position"]): r for r in csv.DictReader(open(KEY, encoding="utf-8-sig"))}


def read_review(path):
    out, name = {}, None
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        name = name or (r.get("reviewer") or "").strip()
        cat = (r.get("category") or "").strip()
        if cat in CATS:
            out[int(r["position"])] = (cat, (r.get("note") or "").strip())
        elif cat:
            print(f"  УВАГА: невідома категорія «{cat}» у позиції {r['position']} пропущена")
    return name or os.path.basename(path), out


def pct(x):
    return f"{100 * x:.0f}%"


def report_vs(label, answers, key, ref_field):
    pairs = [(key[p][ref_field], a[0]) for p, a in sorted(answers.items()) if p in key]
    n = len(pairs)
    k = sum(x == y for x, y in pairs)
    lo, hi = wilson(k, n)
    kap = kappa(pairs)
    print(f"  {label}: збіг {k} із {n} ({pct(k / n)}, 95% ДІ {pct(lo)}–{pct(hi)}), κ Коена {kap:.2f}")
    return n, k, lo, hi, kap


def confusion(answers, key, ref_field):
    m = {c: Counter() for c in CATS}
    for p, a in answers.items():
        m[key[p][ref_field]][a[0]] += 1
    print(f"    {'':<14}" + "".join(f"{c:>14}" for c in CATS) + "   (рядки: категорія моделі; стовпці: рецензент)")
    for c in CATS:
        print(f"    {c:<14}" + "".join(f"{m[c][d]:>14}" for d in CATS))


def analyze(reviews, key):
    stats = {}
    for name, answers in reviews:
        print(f"\nРецензент {name}: розмічено {len(answers)} із {len(key)}")
        n, k, lo, hi, kap = report_vs("з розміткою моделі", answers, key, "model_category")
        stats[name] = (n, k, lo, hi, kap)
        report_vs("з автоматичними правилами", answers, key, "auto_category")
        confusion(answers, key, "model_category")
        print("    за стратою моделі: " + "; ".join(
            f"{c} {sum(1 for p, a in answers.items() if key[p]['model_category'] == c and a[0] == c)} із "
            f"{sum(1 for p in answers if key[p]['model_category'] == c)}" for c in CATS))
        diff = [(p, a) for p, a in sorted(answers.items()) if a[0] != key[p]["model_category"]]
        if diff:
            print(f"  Розбіжності ({len(diff)}):")
            for p, a in diff:
                print(f"    №{p} {key[p]['project'].split('/')[-1]} / {key[p]['job']}: модель «{key[p]['model_category']}» "
                      f"({key[p]['model_note'][:70]}), рецензент «{a[0]}»" + (f" ({a[1][:60]})" if a[1] else ""))
    if len(reviews) >= 2:
        (n1, a1), (n2, a2) = reviews[0], reviews[1]
        common = sorted(set(a1) & set(a2))
        pairs = [(a1[p][0], a2[p][0]) for p in common]
        k = sum(x == y for x, y in pairs)
        lo, hi = wilson(k, len(pairs))
        print(f"\nМіж рецензентами {n1} і {n2}: збіг {k} із {len(pairs)} ({pct(k / len(pairs))}, 95% ДІ {pct(lo)}–{pct(hi)}), "
              f"κ Коена {kappa(pairs):.2f}")
    print("\nЧернетка речення для тез (числа з цього запуску; вибірка стратифікована, не відтворює склад усіх 192):")
    for name, (n, k, lo, hi, kap) in stats.items():
        print(f"  Повторну розмітку {n} випадків наосліп виконав рецензент {name}: збіг із розміткою моделі {k} із {n} "
              f"({pct(k / n)}, 95% ДІ {pct(lo)}–{pct(hi)}), κ Коена {kap:.2f}.")


def self_test():
    # 1. κ на відомому прикладі: [[20, 5], [10, 15]] → po 0,7, pe 0,5, κ 0,4
    pairs = [("a", "a")] * 20 + [("a", "b")] * 5 + [("b", "a")] * 10 + [("b", "b")] * 15
    assert abs(kappa(pairs) - 0.4) < 1e-9, kappa(pairs)
    # 2. повний збіг → κ 1; повна розбіжність у двох категоріях → від'ємний
    assert kappa([("a", "a"), ("b", "b")]) == 1.0
    assert kappa([("a", "b"), ("b", "a")]) < 0
    # 3. інтервали Вільсона збігаються з опублікованими в ЛР_7 (H3: 49 із 50 → 90–100%, 103 із 146 → 63–77%)
    for k, n, a, b in ((49, 50, 90, 100), (103, 146, 63, 77)):
        lo, hi = wilson(k, n)
        assert (round(100 * lo), round(100 * hi)) == (a, b), (k, n, lo, hi)
    # 4. синтетичний рецензент: збігається з моделлю в ~85% випадків
    key = read_key()
    rnd = random.Random(1)
    syn = {p: (r["model_category"] if rnd.random() < 0.85 else rnd.choice([c for c in CATS if c != r["model_category"]]), "")
           for p, r in key.items()}
    print("Формули перевірено. Нижче синтетичний запуск (не результат дослідження):")
    analyze([("СИНТЕТИКА", syn)], key)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--self-test" in sys.argv:
        self_test()
        return
    if not args:
        raise SystemExit(__doc__)
    key = read_key()
    analyze([read_review(p) for p in args], key)


if __name__ == "__main__":
    main()
