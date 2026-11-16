#!/usr/bin/env bash
# สำรองฐานข้อมูล + ไฟล์ (รูปเมนู, สลิป, รูปส่งของ) เก็บ 14 วันล่าสุด
# รันจากโฟลเดอร์โปรเจกต์:  bash deploy/backup.sh
# ตั้งให้รันทุกคืนตี 3:     crontab -e  แล้วเพิ่มบรรทัด
#   0 3 * * * cd /root/kitchen && bash deploy/backup.sh >> /root/kitchen-backups/backup.log 2>&1
set -euo pipefail

COMPOSE="docker compose -f deploy/docker-compose.prod.yml --env-file .env"
DEST="${BACKUP_DIR:-$HOME/kitchen-backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
KEEP_DAYS=14
mkdir -p "$DEST"

# อ่านชื่อฐานข้อมูล/ผู้ใช้จาก .env
set -a; . ./.env; set +a

echo "[$STAMP] dump database"
$COMPOSE exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom > "$DEST/db-$STAMP.dump"

echo "[$STAMP] archive media"
$COMPOSE exec -T web tar -czf - -C /app media private_media > "$DEST/files-$STAMP.tar.gz"

# ลบไฟล์เก่ากว่า KEEP_DAYS วัน
find "$DEST" -name 'db-*.dump' -mtime +"$KEEP_DAYS" -delete
find "$DEST" -name 'files-*.tar.gz' -mtime +"$KEEP_DAYS" -delete

echo "[$STAMP] done: $(du -sh "$DEST" | cut -f1) in $DEST"
