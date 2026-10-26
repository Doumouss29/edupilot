"""Create indexes supporting heavily consulted EduPilot read endpoints.

Run once from the VPS inside the app container, during a low-traffic window:
  docker exec edupilot python /app/scripts/optimize_planning_indexes.py
Non-destructive; indexes are added only when missing.
"""
import os
if os.getenv("DB_ENGINE", "sqlite").lower() != "postgresql":
    raise SystemExit("Index maintenance script is only for PostgreSQL.")

from app import db

INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_lessons_school_start ON lessons (school_id,starts_at)",
    "CREATE INDEX IF NOT EXISTS idx_lessons_school_teacher_start ON lessons (school_id,teacher_id,starts_at)",
    "CREATE INDEX IF NOT EXISTS idx_lessons_school_visible_start ON lessons (school_id,hidden_from_planning,starts_at)",
    "CREATE INDEX IF NOT EXISTS idx_enrollments_student_class ON enrollments (student_id,class_id)",
    "CREATE INDEX IF NOT EXISTS idx_parent_links_parent_student ON parent_links (parent_id,student_id)",
    "CREATE INDEX IF NOT EXISTS idx_courses_school_class ON courses (school_id,class_id)",
)
if __name__ == "__main__":
    with db() as connection:
        for sql in INDEXES:
            connection.execute(sql)
    print("EduPilot: index planning verified.")
