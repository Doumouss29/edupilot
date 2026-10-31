"""Weekly EduPilot planning digest for teachers and students.

Schedule once every Sunday at 20:00 UTC (GMT), for example:
0 20 * * 0 docker exec edupilot python /app/teacher_schedule_digest.py
"""
from app import app, send_all_teacher_weekly_schedules, send_all_student_weekly_schedules

if __name__ == '__main__':
    from datetime import datetime, timezone
    now=datetime.now(timezone.utc)
    if now.weekday()!=6 or now.hour!=20:
        raise SystemExit('Weekly digest only runs on Sunday at 20:00 UTC.')
    with app.app_context():
        teachers=send_all_teacher_weekly_schedules()
        students=send_all_student_weekly_schedules()
        print(f'Weekly planning sent: teachers={teachers}, students={students}')
