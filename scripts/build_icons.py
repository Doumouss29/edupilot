"""Legacy icon generator retired. The official EduPilot PNGs are supplied as assets.
Never overwrite official branding with generated placeholders.
"""
from pathlib import Path

static=Path(__file__).resolve().parent.parent / 'static'
required=('edupilot-180.png','edupilot-192.png','edupilot-512.png',
          'edupilot-maskable-512.png','edupilot-logo-header.png')
missing=[name for name in required if not (static/name).is_file()]
if missing:
    raise SystemExit('Missing official EduPilot assets: '+', '.join(missing))
print('Official EduPilot assets present; no regeneration performed.')
