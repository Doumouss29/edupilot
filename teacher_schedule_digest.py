"""Legacy weekly scheduler disabled.

EduPilot planning email is now sent only on explicit administrator action
from /planning. Retaining this no-op entry point prevents an old VPS cron
from continuing to send unwanted Sunday 20:00 planning email.
Remove the obsolete cron entry when deploying.
"""

if __name__=='__main__':
    print('Weekly schedule email disabled. Use the manual share action in EduPilot.')
