"""Набір для сліпої повторної розмітки журналів (ЛР_8, тези): вибірка 40 випадків із 192, ключ і офлайн-форма HTML.
Запуск: python -X utf8 scripts/lr8_review_kit.py
Вибірка стратифікована за категорією розмітки моделі (15 середовище, 15 невизначено, 10 твердження), не більше
2 випадків з однаковою приміткою в страті, випадковість відтворювана (SEED). Рецензент бачить лише фрагмент журналу,
проєкт і назву завдання: автоматична категорія, категорія моделі й результат повтору приховані.
Виходи:
  data/processed/lr8_review_key.csv                     — ключ (позиція → випадок, категорії); рецензенту не показувати
  labs/ЛР_8/рецензування/Сліпа_перевірка.html           — форма для рецензента (один файл, без мережі)
Результати рецензента аналізує scripts/lr8_review_analyze.py.
"""
import csv
import hashlib
import html
import json
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = "lr8-blind-review-2026-11-14"
QUOTA = {"середовище": 15, "невизначено": 15, "твердження": 10}
MAX_PER_NOTE = 2
SRC = os.path.join(ROOT, "data", "processed", "manual_review_lr7.csv")
KEY_OUT = os.path.join(ROOT, "data", "processed", "lr8_review_key.csv")
HTML_OUT = os.path.join(ROOT, "labs", "ЛР_8", "рецензування", "Сліпа_перевірка.html")

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
TS = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z \d\d[OE+]*\s?")
NOISE = re.compile(r"section_(start|end):|^Cleaning up|^Uploading artifacts|no matching files|ERROR: No files to upload|"
                   r"^Running with gitlab-runner|^\s*$", re.I)
KEYWORDS = re.compile(r"error|fail|✘|✖|●|timeout|timed out|ECONN|ETIMEDOUT|ENOTFOUND|50[0234]\b|heap|out of memory|no space|"
                      r"rate limit|expected|received|assert|unexpected|cannot|denied|refused|reset|killed|exited", re.I)


def log_path(row):
    return os.path.join(ROOT, "data", "logs", row["project"].replace("/", "__"), f"{row['failed_job_id']}.log")


def clean_lines(path):
    text = ANSI.sub("", open(path, encoding="utf-8", errors="replace").read())
    out = []
    for ln in text.splitlines():
        ln = TS.sub("", ln).rstrip()
        if NOISE.search(ln):
            continue
        if out and out[-1] == ln:
            continue
        out.append(ln[:240])
    return out


def short_fragment(lines, n_key=24, limit=3500):
    """Останні рядки журналу, що містять ключові слова про помилки (те саме, що читалося під час першої розмітки)."""
    picked = [ln for ln in lines if KEYWORDS.search(ln)][-n_key:]
    text = "\n".join(picked)
    return text[-limit:] if len(text) > limit else text


def long_fragment(lines, n=120, limit=14000):
    text = "\n".join(lines[-n:])
    return text[-limit:] if len(text) > limit else text


def pick(rows):
    chosen = []
    for cat, quota in QUOTA.items():
        pool = [r for r in rows if r["manual_category"] == cat and os.path.exists(log_path(r))]
        pool.sort(key=lambda r: hashlib.md5((SEED + r["failed_job_id"]).encode()).hexdigest())
        per_note, got = Counter(), []
        for r in pool:
            if per_note[r["note"]] >= MAX_PER_NOTE:
                continue
            per_note[r["note"]] += 1
            got.append(r)
            if len(got) == quota:
                break
        if len(got) < quota:
            raise SystemExit(f"Недостатньо випадків у страті «{cat}»: {len(got)} з {quota}")
        chosen += got
    chosen.sort(key=lambda r: hashlib.md5((SEED + "order" + r["failed_job_id"]).encode()).hexdigest())
    return chosen


PAGE = r"""<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Сліпа перевірка журналів</title>
<style>
  :root { --bg:#fbfaf8; --fg:#1b1b1a; --muted:#5d5c58; --line:#d9d8d3; --card:#ffffff; --accent:#2a78d6; --code:#f1f0ec; }
  @media (prefers-color-scheme: dark) { :root { --bg:#161615; --fg:#ecebe7; --muted:#a3a29c; --line:#3a3936; --card:#1f1f1d; --accent:#6aa7f0; --code:#262624; } }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 980px; margin: 0 auto; padding: 24px 16px 96px; }
  h1 { font-size: 1.5rem; margin: 0 0 8px; }
  .rules, .case { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px; margin:16px 0; }
  .rules h2 { margin:0 0 8px; font-size:1.1rem; }
  .rules dt { font-weight:600; margin-top:10px; }
  .rules dd { margin:2px 0 0 0; color:var(--fg); }
  .case h3 { margin:0 0 8px; font-size:1rem; }
  .meta { color:var(--muted); font-size:.9rem; }
  pre { background:var(--code); border-radius:8px; padding:10px; overflow:auto; max-height:360px; font:12.5px/1.45 ui-monospace, Consolas, monospace; white-space:pre-wrap; word-break:break-word; margin:8px 0; }
  details summary { cursor:pointer; color:var(--accent); margin:6px 0; }
  .choices { display:flex; flex-wrap:wrap; gap:8px 20px; margin-top:8px; }
  .choices label { cursor:pointer; padding:6px 10px; border:1px solid var(--line); border-radius:8px; }
  .choices input { margin-right:6px; }
  input[type=text] { width:100%; padding:8px; margin-top:8px; border:1px solid var(--line); border-radius:8px; background:var(--bg); color:var(--fg); font:inherit; }
  .bar { position:fixed; left:0; right:0; bottom:0; background:var(--card); border-top:1px solid var(--line); padding:10px 16px; display:flex; gap:12px; align-items:center; justify-content:center; flex-wrap:wrap; }
  button { font:inherit; padding:8px 14px; border-radius:8px; border:1px solid var(--accent); background:var(--accent); color:#fff; cursor:pointer; }
  button.secondary { background:transparent; color:var(--accent); }
  textarea { width:100%; height:140px; font:12px ui-monospace, Consolas, monospace; background:var(--code); color:var(--fg); border:1px solid var(--line); border-radius:8px; }
  .done { outline:2px solid var(--accent); }
</style>
</head>
<body>
<main>
  <h1>Сліпа перевірка журналів завдань</h1>
  <p class="meta">Випадків: __N__. Орієнтовно 40 хвилин. Для кожного випадку прочитайте фрагмент журналу першої невдалої спроби й оберіть категорію. Автоматична категорія, категорія моделі та результат повтору вам не показуються. Відповіді зберігаються в цьому браузері; наприкінці натисніть «Зберегти CSV».</p>

  <section class="rules">
    <h2>Правила категорій</h2>
    <p class="meta">Категорія є спостережуваною ознакою в журналі, а не першопричиною. Оцінюється причина завершення першої невдалої спроби, а не будь-який збіг слів у журналі: рядок про мережу чи пам'ять, що не призвів до збою (попередження, успішний повтор усередині завдання), не робить збій «середовищем».</p>
    <dl>
      <dt>середовище</dt>
      <dd>Збій виконавця або інфраструктури поза кодом перевірки: мережа (ECONNRESET, ETIMEDOUT, ENOTFOUND, «Could not resolve host», відповіді 502/503/504, «Connection reset by peer», обрив git fetch чи завантаження), вичерпання пам'яті або диска («JavaScript heap out of memory», «No space left on device»), реєстр образів (toomanyrequests, failed to pull image), збій завантаження зовнішніх ресурсів.</dd>
      <dt>твердження</dt>
      <dd>Перевірка запустилася й не пройшла через невідповідність очікуваного результату: Jest «●», Expected/Received, AssertionError, toBe/toEqual, «Tests: N failed», інша помилка в коді самої перевірки чи продукту.</dd>
      <dt>невизначено</dt>
      <dd>Причина не видна або може бути і в коді, і в середовищі: тайм-аут перевірки («Exceeded timeout of N ms»), Received null/undefined, перевищення часу завдання, помилка збірки чи компіляції, статус зовнішнього процесу, «N fail» без опису причини.</dd>
    </dl>
    <p class="meta">Якщо жодна з перших двох категорій не видна однозначно, обирайте «невизначено». У разі сумніву додайте коротку примітку.</p>
  </section>

  <section class="rules">
    <label>Позначка рецензента (наприклад, R1 або R2): <input type="text" id="who" placeholder="R1"></label>
  </section>

  <div id="cases"></div>

  <section class="rules" id="export">
    <h2>Готово</h2>
    <p class="meta" id="progress2"></p>
    <p>Натисніть «Зберегти CSV» і надішліть файл дослідникові. Якщо завантаження заблоковане браузером, скопіюйте текст нижче й надішліть його повідомленням.</p>
    <textarea id="csvbox" readonly></textarea>
  </section>
</main>

<div class="bar">
  <span id="progress"></span>
  <button id="save">Зберегти CSV</button>
  <button class="secondary" id="copy">Скопіювати CSV</button>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  var DATA = JSON.parse(document.getElementById('data').textContent);
  var STORE = 'lr8_blind_review_v1';
  var state = {};
  try { state = JSON.parse(localStorage.getItem(STORE) || '{}'); } catch (e) { state = {}; }
  state.answers = state.answers || {};
  state.notes = state.notes || {};
  function persist() { try { localStorage.setItem(STORE, JSON.stringify(state)); } catch (e) {} }
  var CATS = [['середовище', 'середовище'], ['твердження', 'твердження'], ['невизначено', 'невизначено']];
  var box = document.getElementById('cases');
  var who = document.getElementById('who');
  who.value = state.who || '';
  who.addEventListener('input', function () { state.who = who.value; persist(); });

  DATA.forEach(function (c) {
    var sec = document.createElement('section');
    sec.className = 'case';
    sec.id = 'case' + c.position;
    var h = document.createElement('h3');
    h.textContent = '№ ' + c.position + ' з ' + DATA.length;
    var meta = document.createElement('div');
    meta.className = 'meta';
    meta.textContent = 'Проєкт: ' + c.project + ' · завдання: ' + c.job;
    var pre = document.createElement('pre');
    pre.textContent = c.short;
    var det = document.createElement('details');
    var sum = document.createElement('summary');
    sum.textContent = 'Показати довший фрагмент журналу (останні рядки)';
    var pre2 = document.createElement('pre');
    pre2.textContent = c.long;
    det.appendChild(sum); det.appendChild(pre2);
    var choices = document.createElement('div');
    choices.className = 'choices';
    CATS.forEach(function (k) {
      var lab = document.createElement('label');
      var r = document.createElement('input');
      r.type = 'radio'; r.name = 'cat' + c.position; r.value = k[0];
      if (state.answers[c.position] === k[0]) r.checked = true;
      r.addEventListener('change', function () {
        state.answers[c.position] = k[0]; persist(); sec.classList.add('done'); refresh();
      });
      lab.appendChild(r); lab.appendChild(document.createTextNode(k[1]));
      choices.appendChild(lab);
    });
    var note = document.createElement('input');
    note.type = 'text'; note.placeholder = 'Примітка (необов\'язково)';
    note.value = state.notes[c.position] || '';
    note.addEventListener('input', function () { state.notes[c.position] = note.value; persist(); });
    if (state.answers[c.position]) sec.classList.add('done');
    [h, meta, pre, det, choices, note].forEach(function (e) { sec.appendChild(e); });
    box.appendChild(sec);
  });

  function csvCell(s) { s = String(s == null ? '' : s); return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }
  function buildCsv() {
    var rows = ['reviewer,position,category,note'];
    DATA.forEach(function (c) {
      rows.push([who.value || '', c.position, state.answers[c.position] || '', state.notes[c.position] || ''].map(csvCell).join(','));
    });
    return rows.join('\r\n') + '\r\n';
  }
  function refresh() {
    var n = Object.keys(state.answers).length;
    var t = 'Розмічено ' + n + ' із ' + DATA.length;
    document.getElementById('progress').textContent = t;
    document.getElementById('progress2').textContent = t;
    document.getElementById('csvbox').value = buildCsv();
  }
  document.getElementById('save').addEventListener('click', function () {
    var csv = '﻿' + buildCsv();
    try {
      var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'review_' + ((who.value || 'rev').replace(/[^\w-]+/g, '') || 'rev') + '.csv';
      document.body.appendChild(a); a.click(); a.remove();
    } catch (e) {
      document.getElementById('export').scrollIntoView();
    }
  });
  document.getElementById('copy').addEventListener('click', function () {
    var ta = document.getElementById('csvbox'); ta.value = buildCsv(); ta.select();
    try { document.execCommand('copy'); } catch (e) {}
  });
  who.addEventListener('input', refresh);
  refresh();
})();
</script>
</body>
</html>
"""


def main():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    chosen = pick(rows)
    os.makedirs(os.path.dirname(HTML_OUT), exist_ok=True)
    cases, key = [], []
    for pos, r in enumerate(chosen, 1):
        lines = clean_lines(log_path(r))
        cases.append({"position": pos, "project": r["project"].split("/")[-1], "job": r["job"],
                      "short": short_fragment(lines) or "(ключових рядків не знайдено)", "long": long_fragment(lines)})
        key.append({"position": pos, "failed_job_id": r["failed_job_id"], "project": r["project"], "job": r["job"],
                    "auto_category": r["auto_category"], "model_category": r["manual_category"], "model_note": r["note"]})
    with open(KEY_OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(key[0]))
        w.writeheader()
        w.writerows(key)
    data = json.dumps(cases, ensure_ascii=False).replace("<", "\\u003c")
    with open(HTML_OUT, "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__N__", str(len(cases))).replace("__DATA__", data))
    print("випадків:", len(cases), "| за категорією моделі:", dict(Counter(k["model_category"] for k in key)))
    print("за проєктом:", dict(Counter(k["project"].split("/")[-1] for k in key)))
    print("за автоматичною категорією:", dict(Counter(k["auto_category"] for k in key)))
    print("ключ:", os.path.relpath(KEY_OUT, ROOT), "| форма:", os.path.relpath(HTML_OUT, ROOT),
          f"({os.path.getsize(HTML_OUT) // 1024} КБ)")


if __name__ == "__main__":
    main()
