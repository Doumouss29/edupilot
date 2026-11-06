"""Read-only PostgreSQL TLS diagnostics. Does not print credentials.

Usage: docker exec edupilot python /app/scripts/check_pg_tls.py
"""
import os
import sys

if os.getenv('DB_ENGINE') != 'postgresql':
    sys.exit('EduPilot is not configured for PostgreSQL')

mode=os.getenv('PGSSLMODE','require')
print('PostgreSQL TLS mode:',mode)
print('Certificate authority configured:',bool(os.getenv('PGSSLROOTCERT')))
conn=None
try:
    from postgres_rehearsal import pg_connection
    conn=pg_connection()
    row=conn.execute("""SELECT ssl, version, cipher
        FROM pg_stat_ssl WHERE pid=pg_backend_pid()""").fetchone()
    if not row or not row['ssl']:
        sys.exit('ERROR: database connection is not encrypted')
    print('Transport encrypted: yes')
    print('TLS version:',row['version'])
    print('TLS cipher:',row['cipher'])
    if mode!='verify-full':
        print('WARNING: server identity is not fully verified. Plan verify-full with a trusted CA.')
    else:
        print('Configured certificate verification: verify-full')
finally:
    if conn is not None:
        conn.close()
