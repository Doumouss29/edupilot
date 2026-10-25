"""Send consolidated schedule emails once per teacher per week.

Run inside the production container via cron:
docker exec edupilot python teacher_schedule_digest.py
"""
from app import app, send_all_teacher_weekly_schedules

if __name__ == '__main__':
    with app.app_context():
        count = send_all_teacher_weekly_schedules()
        print(f'Teacher weekly schedules emailed: {count}')
