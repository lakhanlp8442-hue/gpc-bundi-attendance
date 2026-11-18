#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

python manage.py shell -c "
from core.models import User
if not User.objects.filter(username='hod_cse').exists():
    User.objects.create_superuser(
        username='hod_cse',
        email='hod@gpcbundi.ac.in',
        password='Admin@GPC2026',
        first_name='HOD',
        last_name='CSE',
        role='HOD',
        branch='CSE'
    )
    print('Superuser & HOD account created!')
"