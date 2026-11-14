"""Виявлення повторених і перемежованих збоїв завдань та класифікація за спостережуваними ознаками (ЛР_6).
Запуск: python -X utf8 scripts/classify.py <data/raw/проєкт.jsonl> [--no-logs] [--max-logs 400]
Вхід:  data/raw/<проєкт>.jsonl; за наявності data/raw/mr/<проєкт>.jsonl — зв'язок із запитами на злиття.
Вихід: data/processed/<проєкт>_failures.csv — один рядок на повторений збій; підсумок у консолі.

Повторений збій — перша невдала спроба завдання перевірок для коміту (sha), за якою були наступні спроби
того самого завдання для цього коміту. Вид: W — перша наступна спроба в тому самому конвеєрі, P — в іншому.
Перемежований збій — повторений збій, після якого є успішна спроба (intermittent = True).
Категорія збою — спостережувана ознака, а не першопричина: середовище / твердження / невизначено.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOWS = (15, 30, 60)  # вікна групування в часі, хв (основне — 30; решта — перевірка чутливості)
# Поле failure_reason, що позначає збій виконавця або системи GitLab. Тайм-аути (stuck_or_timeout_failure,
# job_execution_timeout) сюди не входять: завдання могла зависнути перевірка, тому вони -> «невизначено».
ENV_REASONS = {"runner_system_failure", "scheduler_failure", "api_failure", "data_integrity_failure"}
# Ознаки середовища в журналі: мережа, пам'ять і диск, реєстр образів
ENV_LOG = re.compile(
    r"ECONNRESET|ETIMEDOUT|ENOTFOUND|EAI_AGAIN|ECONNREFUSED|socket hang up|Could not resolve host|"
    r"\b50[234]\b.*(Bad Gateway|Service Unavailable|Gateway Time-?out)|npm ERR! network|ERR_SOCKET_TIMEOUT|"
    r"TLS handshake timeout|Connection reset by peer|No space left on device|JavaScript heap out of memory|"
    r"toomanyrequests|failed to pull image|Cannot connect to the Docker daemon|rate limit exceeded|"
    r"Failed to download|net::ERR_|getaddrinfo|Response code 5\d\d|unexpected disconnect while reading sideband|"
    r"remote command exited without exit status", re.I)  # останні 3 — уточнення за пробною перевіркою
# Тайм-аут перевірки або відсутній результат процесу: причина може бути і в коді, і в середовищі
AMBIG_LOG = re.compile(
    r"Exceeded timeout of \d+ ?ms|Test timeout of \d+ms exceeded|Timeout of \d+ms exceeded|Received:\s+null|"
    r"Received has value: undefined|ERROR: Job failed: execution took longer|"
    r"Workflow \d+ finished with status: failed", re.I)  # статус зовнішнього процесу (уточнення за пробною перевіркою)
ASSERT_LOG = re.compile(
    r"Tests:\s+\d+ failed|●\s|expect\(.*\)\.|Expected:|Received:|AssertionError|\d+ failed\b|✘|"
    r"Error: expect|toHaveBeenCalled|toBe\(|toEqual\(", re.I)
# Лише завдання, що виконують перевірки (за назвою); службові (lint, danger, build) — поза вибіркою
TEST_JOB = re.compile(r"test|jest|vitest|e2e|playwright|cypress|spec|unit|integration|karma", re.I)
NOT_JS_JOB = re.compile(r"rspec|ruby|rubocop|golang|go-test|qa", re.I)  # серверні перевірки (gitlab-org/gitlab)


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def minutes(a, b):
    return round((b - a).total_seconds() / 60, 1) if a and b else ""


def fetch_log(project, job_id, cache):
    path = os.path.join(cache, f"{job_id}.log")
    if os.path.exists(path):
        return open(path, encoding="utf-8", errors="replace").read()
    url = f"https://gitlab.com/{project}/-/jobs/{job_id}/raw"
    k = 0
    while k < 4:
        try:
            t = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
            text = t.decode("utf-8", "replace")
            open(path, "w", encoding="utf-8").write(text)
            time.sleep(0.2)  # не навантажувати разом зі збором (ліміт 500 запитів/хв з однієї адреси)
            return text
        except urllib.error.HTTPError as e:
            if e.code == 429:  # обмеження частоти: чекаємо і повторюємо, не рахуючи спробою
                time.sleep(min(int(e.headers.get("Retry-After") or 60), 120) + 1)
                continue
            if e.code in (403, 404):  # журнал видалено або недоступний — повтори марні
                return None
        except Exception:
            pass
        k += 1
        time.sleep(3 * k)
    return None


def classify(att, project, log_budget, cache):
    """-> (категорія, підстава, рівень підстави). Порядок правил — як у табл. 3 звіту ЛР_6."""
    r = att["failure_reason"]
    if r in ENV_REASONS:
        return "середовище", f"failure_reason={r}", "поле"
    if r != "script_failure":
        return "невизначено", f"failure_reason={r}", "поле"
    if log_budget[0] <= 0 and not os.path.exists(os.path.join(cache, f"{att['id']}.log")):
        return "невизначено", "журнал не запитувався", "—"
    log = fetch_log(project, att["id"], cache)
    log_budget[0] -= 1
    if log is None:
        return "невизначено", "журнал недоступний", "—"
    tail = log[-20000:]
    for pat, cat in ((ENV_LOG, "середовище"), (AMBIG_LOG, "невизначено"), (ASSERT_LOG, "твердження")):
        m = pat.search(tail)
        if m:
            return cat, "журнал: " + m.group(0)[:40], "журнал"
    return "невизначено", "журнал: шаблон не знайдено", "журнал"


REVIEW_UNDET_MAX = 50  # «невизначено»: не більше 50 випадків на проєкт (повна перевірка нездійсненна в масштабі)


def in_review_sample(job_id):
    """Детермінована вибірка 20% для ручної перевірки (відтворювана за id завдання)."""
    return int(hashlib.md5(str(job_id).encode()).hexdigest(), 16) % 5 == 0


def mark_review(out):
    """Правило ручної перевірки: усі «середовище» за журналом; 20% «твердження»; до 50 «невизначено» (за хешем id)."""
    und = sorted((o for o in out if o["category"] == "невизначено"), key=lambda o: hashlib.md5(str(o["failed_job_id"]).encode()).hexdigest())
    chosen = {o["failed_job_id"] for o in und[:REVIEW_UNDET_MAX]}
    for o in out:
        env_log = o["category"] == "середовище" and o["basis_level"] == "журнал"
        o["review"] = "так" if env_log or o["failed_job_id"] in chosen or (o["category"] == "твердження" and in_review_sample(o["failed_job_id"])) else ""


def ref_kind(ref):
    ref = ref or ""
    return "черга злиття" if ref.endswith("/train") else "результат злиття" if ref.endswith("/merge") else "гілка"


def load_mr(project):
    path = os.path.join(ROOT, "data", "raw", "mr", project.replace("/", "__") + ".jsonl")
    by_pipeline = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            m = json.loads(line)
            for pid in m["pipeline_ids"]:
                by_pipeline[pid] = m
    return by_pipeline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("--no-logs", action="store_true")
    ap.add_argument("--max-logs", type=int, default=400, help="ліміт завантажень журналів за запуск")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.raw, encoding="utf-8")]
    project = rows[0]["project"]
    cache = os.path.join(ROOT, "data", "logs", project.replace("/", "__"))
    os.makedirs(cache, exist_ok=True)
    mr = load_mr(project)
    budget = [0 if a.no_logs else a.max_logs]

    by_key = defaultdict(list)  # (sha, назва завдання) -> усі спроби
    for r in rows:
        is_test = TEST_JOB.search(r["name"] or "") and not NOT_JS_JOB.search(r["name"] or "")  # стадія «test» часто містить і службові завдання
        if r["status"] in ("failed", "success") and is_test:
            by_key[(r["sha"], r["name"])].append(r)

    out = []
    for (sha, name), atts in by_key.items():
        atts.sort(key=lambda r: (r["created_at"] or "", r["id"]))
        first = next((i for i, x in enumerate(atts) if x["status"] == "failed"), None)
        if first is None or first == len(atts) - 1:
            continue  # немає невдалої спроби або після неї не було повторів
        att, later = atts[first], atts[first + 1:]
        ok = next((b for b in later if b["status"] == "success"), None)
        chain = [x for x in atts[first:] if x["status"] == "failed" and (ok is None or x["created_at"] < ok["created_at"] or x is att)]
        cat, basis, level = classify(att, project, budget, cache)
        m = mr.get(att["pipeline_id"])
        rec = {
            "project": project, "sha": sha[:10], "job": name, "failed_job_id": att["id"],
            "kind": "W" if later[0]["pipeline_id"] == att["pipeline_id"] else "P",
            "intermittent": ok is not None, "retries": len(later),
            "failure_reason": att["failure_reason"], "category": cat, "basis": basis, "basis_level": level,
            "review": "",
            "started_at": att["started_at"], "recovery_min": minutes(ts(att["finished_at"]), ts(ok["finished_at"])) if ok else "",
            "wasted_min": round(sum(x["duration"] or 0 for x in chain) / 60, 1),
            "allow_failure": bool(att["allow_failure"]), "ref_kind": ref_kind(att.get("pipeline_ref")),
            "failed_finished_at": att["finished_at"],
            "mr_iid": m["iid"] if m else "", "mr_life_min": minutes(ts(m["created_at"]), ts(m["merged_at"])) if m else "",
            # час від кінця першої невдалої спроби до злиття MR: знаменник частки часу відновлення
            "mr_after_fail_min": minutes(ts(att["finished_at"]), ts(m["merged_at"])) if m else "",
        }
        out.append(rec)

    mark_review(out)
    # Групування в часі (H1): початок іншого перемежованого збою цього проєкту не далі ніж за вікно
    inter = [o for o in out if o["intermittent"]]
    for o in out:
        for w in WINDOWS:
            o[f"cluster_{w}"] = ""
    for o in inter:
        t0 = ts(o["started_at"])
        for w in WINDOWS:
            o[f"cluster_{w}"] = any(p is not o and abs((ts(p["started_at"]) - t0).total_seconds()) <= w * 60 for p in inter)

    os.makedirs(os.path.join(ROOT, "data", "processed"), exist_ok=True)
    dst = os.path.join(ROOT, "data", "processed", project.replace("/", "__") + "_failures.csv")
    with open(dst, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]) if out else ["project"])
        w.writeheader()
        w.writerows(out)

    n_test = sum(len(v) for v in by_key.values())
    n_fail = sum(1 for v in by_key.values() for r in v if r["status"] == "failed")
    n_pairs = sum(1 for v in by_key.values() if any(r["status"] == "failed" for r in v))  # пар «коміт — завдання» з невдалою спробою
    kinds = Counter(r.get("pipeline_ref") and ref_kind(r["pipeline_ref"]) for v in by_key.values() for r in v)
    with open(dst.replace("_failures.csv", "_summary.json"), "w", encoding="utf-8") as f:  # знаменники для analyze.py
        json.dump({"project": project, "pipelines": len({r["pipeline_id"] for r in rows}), "attempts": len(rows),
                   "test_attempts": n_test, "test_failed": n_fail, "failed_pairs": n_pairs, "repeated": len(out),
                   "intermittent": len(inter), "attempts_by_ref_kind": dict(kinds), "logs": not a.no_logs}, f, ensure_ascii=False, indent=1)
    print(f"{project}: pipelines={len({r['pipeline_id'] for r in rows})} attempts={len(rows)} test_attempts={n_test} "
          f"test_failed={n_fail} failed_pairs={n_pairs} repeated={len(out)} intermittent={len(inter)} -> {dst}")
    print("  вид повтору (повторені):", dict(Counter(o["kind"] for o in out)), "| (перемежовані):", dict(Counter(o["kind"] for o in inter)))
    print("  категорія (повторені):", dict(Counter(o["category"] for o in out)), "| (перемежовані):", dict(Counter(o["category"] for o in inter)))
    print("  рівень підстави (перемежовані):", dict(Counter(o["basis_level"] for o in inter)),
          "| до ручної перевірки (усі повторені):", sum(1 for o in out if o["review"]))
    print("  allow_failure (перемежовані):", sum(o["allow_failure"] for o in inter),
          "| прив'язано до MR:", sum(1 for o in inter if o["mr_iid"] != ""))
    print("  спроби перевірок за видом конвеєра:", dict(kinds))
    print("  failure_reason (повторені):", dict(Counter(o["failure_reason"] for o in out)))
    print("  журнал недоступний (позначено «невизначено»):", sum(1 for o in out if o["basis"] == "журнал недоступний"),
          "| не запитувався:", sum(1 for o in out if o["basis"] == "журнал не запитувався"))
    if inter:
        print("  групування (перемежовані):", {f"{w} хв": sum(1 for o in inter if o[f"cluster_{w}"]) for w in WINDOWS})
    if budget[0] <= 0 and not a.no_logs:
        print(f"  УВАГА: ліміт --max-logs {a.max_logs} вичерпано; решта script_failure без журналу -> «невизначено»")


if __name__ == "__main__":
    main()
