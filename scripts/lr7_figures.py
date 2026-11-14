"""Рисунки ЛР_7 з data/processed/lr7_dataset.csv (лише збої без allow_failure, як в основному аналізі).
Запуск: python -X utf8 scripts/lr7_figures.py -> labs/ЛР_7/img/categories.png, effectiveness.png, recovery.png
Спершу: scripts/classify.py для проєктів, scripts/lr7_dataset.py (збирає lr7_dataset.csv з урахуванням ручної перевірки).
"""
import csv
import math
import os
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, "labs", "ЛР_7", "img")
os.makedirs(IMG, exist_ok=True)

# Палітра: перші два слоти перевіреної категоріальної палітри (синій, помаранчевий); «невизначено» — нейтральний сірий,
# бо це відсутність ознаки, а не окрема категорія з відтінком. Ідентичність дублюють підписи й штрихування.
CATS = ("середовище", "твердження", "невизначено")
COL = {"середовище": "#2a78d6", "твердження": "#eb6834", "невизначено": "#a8a7a1"}
HATCH = {"середовище": "", "твердження": "///", "невизначено": "..."}
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e3e2de", "#ffffff"

for f in ("Times New Roman", "Liberation Serif", "DejaVu Serif"):
    if any(f == x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = f
        break
plt.rcParams.update({"font.size": 10, "axes.edgecolor": MUTED, "axes.linewidth": 0.8, "text.color": INK,
                     "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED, "figure.facecolor": SURFACE,
                     "axes.facecolor": SURFACE, "hatch.linewidth": 0.6})

rows = [r for r in csv.DictReader(open(os.path.join(ROOT, "data", "processed", "lr7_dataset.csv"), encoding="utf-8-sig"))
        if r["allow_failure"] == "False"]
inter = [r for r in rows if r["intermittent"] == "True"]


def wilson(k, n, z=1.96):
    p, d = k / n, 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0, c - h), min(1, c + h)


def clean(ax, grid="x"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis=grid, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


# ---------- Рисунок 1: розподіл категорій ----------
fig, ax = plt.subplots(figsize=(6.5, 2.5), dpi=220)
bars = (("Повторені збої", rows), ("Перемежовані збої", inter))
for y, (label, data) in enumerate(bars):
    n, left = len(data), 0.0
    for c in CATS:
        k = sum(r["category"] == c for r in data)
        w = 100 * k / n
        ax.barh(y, w, left=left, height=0.55, color=COL[c], edgecolor=SURFACE, linewidth=1.5, hatch=HATCH[c])
        if w >= 6:
            ax.text(left + w / 2, y, f"{k}\n{w:.0f}%", ha="center", va="center", fontsize=9, color="white" if c == "середовище" else INK,
                    bbox=dict(facecolor=SURFACE, edgecolor="none", pad=1.2, alpha=0.85) if HATCH[c] else None)
        left += w
    ax.text(-1.5, y, f"{label}\n(n = {n})", ha="right", va="center", fontsize=9.5)
ax.set_xlim(0, 100)
ax.set_ylim(-0.6, 1.6)
ax.invert_yaxis()
ax.set_yticks([])
ax.set_xlabel("Частка збоїв, %")
clean(ax)
ax.spines["left"].set_visible(False)
handles = [plt.Rectangle((0, 0), 1, 1, facecolor=COL[c], edgecolor=SURFACE, hatch=HATCH[c]) for c in CATS]
ax.legend(handles, CATS, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.32), frameon=False, fontsize=9.5)
fig.subplots_adjust(left=0.2, right=0.98, top=0.97, bottom=0.34)
fig.savefig(os.path.join(IMG, "categories.png"))
plt.close(fig)

# ---------- Рисунок 2: результативність повторного запуску (H3) ----------
fig, ax = plt.subplots(figsize=(6.5, 2.6), dpi=220)
items = [(c, [r for r in rows if r["category"] == c]) for c in CATS] + [("усі", rows)]
ypos = [0, 1, 2, 3.4]
for y, (c, data) in zip(ypos, items):
    k, n = sum(r["intermittent"] == "True" for r in data), len(data)
    lo, hi = wilson(k, n)
    color = COL.get(c, INK)
    ax.plot([100 * lo, 100 * hi], [y, y], color=color, linewidth=2, solid_capstyle="round")
    ax.plot(100 * k / n, y, "o", markersize=8, markerfacecolor=color, markeredgecolor=SURFACE, markeredgewidth=1.5)
    ax.text(101.5, y, f"{k}/{n} = {100 * k / n:.0f}% [{100 * lo:.0f}–{100 * hi:.0f}]", va="center", fontsize=9)
ax.set_yticks(ypos)
ax.set_yticklabels(["середовище", "твердження", "невизначено", "усі збої"], fontsize=9.5)
ax.set_xlim(0, 100)
ax.set_ylim(-0.6, 4.0)
ax.invert_yaxis()
ax.axhline(2.7, color=GRID, linewidth=0.8)
ax.set_xlabel("Перемежовані / повторені, % (95% ДІ Вільсона)")
clean(ax)
ax.spines["left"].set_visible(False)
ax.tick_params(axis="y", length=0)
fig.subplots_adjust(left=0.15, right=0.69, top=0.97, bottom=0.2)
fig.savefig(os.path.join(IMG, "effectiveness.png"))
plt.close(fig)

# ---------- Рисунок 3: час відновлення ----------
fig, ax = plt.subplots(figsize=(6.5, 3.0), dpi=220)
import random
random.seed(7)  # лише для розкиду точок по вертикалі
dec = lambda x: f"{x:.1f}".replace(".", ",")
labels = []
for y, c in enumerate(CATS):
    v = sorted(float(r["recovery_min"]) for r in inter if r["category"] == c and r["recovery_min"] != "")
    v = [max(x, 0.1) for x in v]
    q1, med, q3 = st.quantiles(v, n=4)[0], st.median(v), st.quantiles(v, n=4)[2]
    for x in v:
        ax.plot(x, y + random.uniform(-0.2, 0.2), "o", markersize=3.2, markerfacecolor=COL[c], markeredgecolor=SURFACE,
                markeredgewidth=0.4, alpha=0.8)
    ax.plot([q1, q3], [y + 0.36, y + 0.36], color=INK, linewidth=2.2, solid_capstyle="butt")
    ax.plot([med, med], [y + 0.28, y + 0.44], color=INK, linewidth=2.2)
    labels.append(f"{c}\nмедіана {dec(med)} хв\nQ1–Q3 {dec(q1)}–{dec(q3)}; n = {len(v)}")
ax.set_xscale("log")
ax.set_xlim(1, 12000)
ax.set_yticks(range(3))
ax.set_yticklabels(labels, fontsize=9)
ax.set_ylim(-0.6, 2.7)
ax.invert_yaxis()
ax.set_xlabel("Час відновлення, хв (логарифмічна шкала)")
clean(ax)
ax.spines["left"].set_visible(False)
ax.tick_params(axis="y", length=0)
fig.subplots_adjust(left=0.27, right=0.98, top=0.97, bottom=0.17)
fig.savefig(os.path.join(IMG, "recovery.png"))
plt.close(fig)
print("рисунки ->", IMG)
