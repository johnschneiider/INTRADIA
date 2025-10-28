#!/usr/bin/env bash
set -euo pipefail

export DJANGO_SETTINGS_MODULE=config.settings

python manage.py migrate
celery -A engine worker -l info &
celery -A engine beat -l info &
python manage.py runserver 0.0.0.0:8000

