"""PostgreSQL SQL helpers for future EduPilot migration."""

def placeholders(query):
    return query.replace('?', '%s')
