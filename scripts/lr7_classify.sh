#!/usr/bin/env bash
# Класифікація ЛР_7 з журналами (послідовно, після підтвердження студента).
# Етап 1: проєкти, збір яких завершено; етап 2: gitlab-lsp після завершення збору; потім analyze.py.
# Запуск: bash scripts/lr7_classify.sh > data/raw/classify_lr7.log 2>&1
cd "$(dirname "$0")/.." || exit 1
cls() { python -X utf8 scripts/classify.py "data/raw/$1.jsonl" --max-logs 5000; }
cls gitlab-org__gitlab-web-ide
cls gitlab-org__gitlab-vscode-extension
cls gitlab-org__gitlab-services__design.gitlab.com
until grep -q "ЗБІР ЗАВЕРШЕНО" data/raw/collect_lr7.log; do
  grep -q "Traceback" data/raw/collect_lr7.log && { echo "ЗБІР ОБІРВАНО (Traceback у collect_lr7.log): gitlab-lsp не класифіковано"; exit 1; }
  sleep 60
done
cls gitlab-org__editor-extensions__gitlab-lsp
python -X utf8 scripts/analyze.py
echo "КЛАСИФІКАЦІЮ ЗАВЕРШЕНО"
