# image เดียวใช้ทั้ง web (gunicorn), celery worker และ celery beat
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

# GDAL/GEOS/PROJ สำหรับ GeoDjango (PostGIS) แล้วลบ cache ของ apt ให้ image เล็กลง
RUN apt-get update \
    && apt-get install -y --no-install-recommends gdal-bin libgdal32 libgeos-c1v5 libproj25 curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements/ requirements/
RUN pip install -r requirements/production.txt

COPY . .

# ไม่รันด้วย root · สร้างโฟลเดอร์ไฟล์ไว้ก่อน ให้ volume ที่ mount ทับได้สิทธิ์ของ app (เขียน static/รูปได้)
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/staticfiles /app/media /app/private_media \
    && chown -R app:app /app
USER app

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
