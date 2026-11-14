"""Збирання історії конвеєрів GitLab CI (відкриті проєкти, без автентифікації).
Запуск: python -X utf8 scripts/collect.py <шлях проєкту> --since 2026-04-01 --max-pipelines 200 [--mr --max-mr 300] [--mr-only]
Результат: data/raw/<проєкт>.jsonl — одна спроба завдання на рядок, без персональних даних.
З --mr: data/raw/mr/<проєкт>.jsonl — злиті запити на злиття (iid, created_at, merged_at, id їхніх конвеєрів).
Для gitlab-org/gitlab потрібен токен read_api у змінній середовища GITLAB_TOKEN (без нього API повертає 500).
"""
import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://gitlab.com/api/v4"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEEP = ("id", "name", "stage", "status", "failure_reason", "allow_failure", "created_at", "started_at",
        "finished_at", "duration", "queued_duration", "retried", "tag_list")


def _token():
    """GITLAB_TOKEN зі змінних середовища процесу або користувача Windows (без перезапуску терміналу)."""
    t = os.environ.get("GITLAB_TOKEN")
    if not t and os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                t = winreg.QueryValueEx(k, "GITLAB_TOKEN")[0]
        except OSError:
            t = None
    return t


TOKEN = _token()


def get(url, tries=30):
    for k in range(tries):
        try:
            headers = {"User-Agent": "flaky-study (student research)"}
            if TOKEN:  # токен read_api — лише зі змінної середовища, не в коді
                headers["PRIVATE-TOKEN"] = TOKEN
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r), r.headers
            time.sleep(0.15)  # ~6 запитів/с на всі процеси — менше ліміту 500/хв без автентифікації
            return data
        except urllib.error.HTTPError as e:
            if e.code == 429:  # обмеження частоти: чекаємо (не довше 2 хв) і пробуємо знову
                wait = min(int(e.headers.get("Retry-After") or 60), 120) + 1
                print(f"  429, чекаю {wait} с", flush=True)
                time.sleep(wait)
                continue
            if e.code in (500, 502, 503) and k < tries - 1:
                time.sleep(5 * (k + 1))
                continue
            raise
        except Exception:  # тайм-аут, обрив з'єднання, неповна відповідь
            if k == tries - 1:
                raise
            time.sleep(5 * (k + 1))


def pages(url):
    page = 1
    while True:
        data, h = get(f"{url}&page={page}")
        yield from data
        nxt = h.get("X-Next-Page")
        if not nxt:
            return
        page = int(nxt)


def collect_mr(pid, project, since, until, limit):
    """Злиті запити на злиття періоду з id їхніх конвеєрів. Конвеєри запиту мають різні sha
    (гілка, результат злиття, черга злиття), тому зв'язок «збій — запит» будується за id конвеєра."""
    os.makedirs(os.path.join(ROOT, "data", "raw", "mr"), exist_ok=True)
    out = os.path.join(ROOT, "data", "raw", "mr", project.replace("/", "__") + ".jsonl")
    q = f"{API}/projects/{pid}/merge_requests?state=merged&per_page=100&order_by=updated_at&sort=desc&updated_after={since}"
    n = 0
    with open(out, "w", encoding="utf-8") as f:
        for m in pages(q):
            if n >= limit:
                break
            merged = m.get("merged_at") or ""
            if merged[:10] < since or (until and merged[:10] > until):
                continue
            ids = [p["id"] for p in pages(f"{API}/projects/{pid}/merge_requests/{m['iid']}/pipelines?per_page=100")]
            f.write(json.dumps({"project": project, "iid": m["iid"], "created_at": m["created_at"],
                                "merged_at": m["merged_at"], "pipeline_ids": ids}) + "\n")  # без авторів і текстів
            n += 1
    print(f"{project}: merge_requests={n} -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--since", required=True)
    ap.add_argument("--until")
    ap.add_argument("--max-pipelines", type=int, default=200)
    ap.add_argument("--resume", action="store_true", help="продовжити перерваний збір: пропустити вже записані конвеєри")
    ap.add_argument("--mr", action="store_true", help="додатково зібрати злиті запити на злиття")
    ap.add_argument("--mr-only", action="store_true", help="лише злиті запити на злиття (конвеєри вже зібрано)")
    ap.add_argument("--max-mr", type=int, default=300)
    a = ap.parse_args()

    pid = urllib.parse.quote(a.project, safe="")
    if a.mr_only:
        collect_mr(pid, a.project, a.since, a.until, a.max_mr)
        return
    q = f"{API}/projects/{pid}/pipelines?per_page=100&order_by=id&sort=desc&updated_after={a.since}"
    if a.until:
        q += f"&updated_before={a.until}"
    os.makedirs(os.path.join(ROOT, "data", "raw"), exist_ok=True)
    out = os.path.join(ROOT, "data", "raw", a.project.replace("/", "__") + ".jsonl")
    n_pipe = n_job = 0
    t0 = time.time()
    done, mode = set(), "w"
    if a.resume and os.path.exists(out):
        keep = []
        for line in open(out, encoding="utf-8"):
            try:
                keep.append((json.loads(line)["pipeline_id"], line))
            except ValueError:  # обірвана остання лінія
                break
        if keep:  # останній записаний конвеєр міг бути неповним -> збираємо його знову
            last = keep[-1][0]
            keep = [(i, l) for i, l in keep if i != last]
        with open(out, "w", encoding="utf-8") as f:
            f.writelines(l for _, l in keep)
        done, mode = {i for i, _ in keep}, "a"
        n_job = len(keep)
        print(f"  відновлення: {len(done)} конвеєрів уже зібрано", flush=True)
    with open(out, mode, encoding="utf-8") as f:
        seen = set()
        for p in pages(q):
            if n_pipe >= a.max_pipelines:
                break
            if p["id"] in seen:  # нові конвеєри під час збору зсувають сторінки списку -> той самий конвеєр на межі сторінок
                continue
            seen.add(p["id"])
            n_pipe += 1
            if p["id"] in done:
                continue
            for j in pages(f"{API}/projects/{pid}/pipelines/{p['id']}/jobs?per_page=100&include_retried=true"):
                rec = {k: j.get(k) for k in KEEP}
                rec.update(project=a.project, pipeline_id=p["id"], pipeline_source=p.get("source"),
                           pipeline_ref=p.get("ref"), ref_is_default=p.get("ref") in ("main", "master"), sha=p.get("sha"))
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_job += 1
            f.flush()
            if n_pipe % 100 == 0:
                print(f"  {n_pipe} конвеєрів, {p['created_at'][:10]}", flush=True)
    print(f"{a.project}: pipelines={n_pipe} job_attempts={n_job} time={time.time() - t0:.0f}s -> {out}")
    if a.mr:
        collect_mr(pid, a.project, a.since, a.until, a.max_mr)


if __name__ == "__main__":
    main()
