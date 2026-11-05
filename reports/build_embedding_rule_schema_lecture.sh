#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
pandoc embedding_rule_schema_lecture_2026-10-16.md \
  --from markdown --to html5 --standalone --toc \
  --metadata title='3분커리: 임베딩 입력 정제와 근거 중심 규칙 스키마' \
  --css embedding_rule_schema_lecture.css \
  -o embedding_rule_schema_lecture_2026-10-16.html
wkhtmltopdf --enable-local-file-access --print-media-type \
  --margin-top 18mm --margin-bottom 18mm --margin-left 17mm --margin-right 17mm \
  --footer-center '[page] / [topage]' --footer-font-size 8 \
  embedding_rule_schema_lecture_2026-10-16.html \
  embedding_rule_schema_lecture_2026-10-16.pdf
