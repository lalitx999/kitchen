#!/usr/bin/env bash
# ดาวน์โหลดไลบรารีหน้าเว็บมาเก็บในเครื่อง (ไม่โหลดจาก CDN ตอนใช้งานจริง)
# รันครั้งเดียวจากโฟลเดอร์โปรเจกต์:  bash scripts/fetch_vendor.sh
# เวอร์ชันล็อกไว้ทุกตัว ถ้าจะอัปเดตให้แก้ตัวเลขด้านล่างแล้วรันใหม่
set -euo pipefail

HTMX_VERSION=2.0.4
ALPINE_VERSION=3.14.8
BI_VERSION=1.11.3
NOTO_THAI_VERSION=5.1.0
JAKARTA_VERSION=5.1.0

CDN=https://cdn.jsdelivr.net/npm
VENDOR=static/vendor

fetch() {  # fetch <url> <ไฟล์ปลายทาง>
  mkdir -p "$(dirname "$2")"
  curl -fsSL "$1" -o "$2"
  echo "  ok  $2"
}

echo "HTMX ${HTMX_VERSION}"
fetch "$CDN/htmx.org@${HTMX_VERSION}/dist/htmx.min.js" "$VENDOR/htmx/htmx.min.js"

echo "Alpine.js ${ALPINE_VERSION}"
fetch "$CDN/alpinejs@${ALPINE_VERSION}/dist/cdn.min.js" "$VENDOR/alpine/alpine.min.js"

echo "Bootstrap Icons ${BI_VERSION}"
fetch "$CDN/bootstrap-icons@${BI_VERSION}/font/bootstrap-icons.min.css" "$VENDOR/bootstrap-icons/bootstrap-icons.min.css"
fetch "$CDN/bootstrap-icons@${BI_VERSION}/font/fonts/bootstrap-icons.woff2" "$VENDOR/bootstrap-icons/fonts/bootstrap-icons.woff2"
fetch "$CDN/bootstrap-icons@${BI_VERSION}/font/fonts/bootstrap-icons.woff" "$VENDOR/bootstrap-icons/fonts/bootstrap-icons.woff"

echo "Fonts: Noto Sans Thai ${NOTO_THAI_VERSION}, Plus Jakarta Sans ${JAKARTA_VERSION}"
for w in 400 500 600 700 800; do
  fetch "$CDN/@fontsource/noto-sans-thai@${NOTO_THAI_VERSION}/files/noto-sans-thai-thai-${w}-normal.woff2" \
        "$VENDOR/fonts/noto-sans-thai-${w}.woff2"
  fetch "$CDN/@fontsource/plus-jakarta-sans@${JAKARTA_VERSION}/files/plus-jakarta-sans-latin-${w}-normal.woff2" \
        "$VENDOR/fonts/plus-jakarta-sans-${w}.woff2"
done

echo "เสร็จแล้ว"
