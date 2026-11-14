#!/usr/bin/env bash
# Збір даних ЛР_7: 90 діб (01.08.2026–31.10.2026), проєкти послідовно одним процесом (ліміт 500 запитів/хв).
# Запуск:      bash scripts/lr7_collect.sh > data/raw/collect_lr7.log 2>&1
# Продовження: bash scripts/lr7_collect.sh --resume >> data/raw/collect_lr7.log 2>&1   (після обриву)
cd "$(dirname "$0")/.." || exit 1
for P in gitlab-org/gitlab-web-ide gitlab-org/gitlab-vscode-extension \
         gitlab-org/gitlab-services/design.gitlab.com gitlab-org/editor-extensions/gitlab-lsp; do
  python -X utf8 scripts/collect.py "$P" --since 2026-08-01 --until 2026-11-01 \
    --max-pipelines 100000 --mr --max-mr 5000 "$@"
done
echo "ЗБІР ЗАВЕРШЕНО"
