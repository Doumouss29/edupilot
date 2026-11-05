"""Deliver queued EduPilot push/email without slowing planning form submissions.

Install on the VPS (host cron, every minute):
* * * * * /usr/bin/docker exec edupilot python /app/notification_delivery_worker.py >> /tmp/edupilot-notifications.log 2>&1
"""
import json
import os
import time

from app import app, db, allrows, execute, one, send_brevo_email


def send_push(uid, message, href):
    if not all(os.getenv(k) for k in ('VAPID_PRIVATE_KEY','VAPID_PUBLIC_KEY','VAPID_SUBJECT')):
        return True  # Push not configured; the in-app alert is already stored.
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        app.logger.warning('Notifications push : pywebpush non disponible')
        return True
    subscriptions=allrows('SELECT id,subscription_json FROM push_subscriptions WHERE user_id=?',(uid,))
    for subscription in subscriptions:
        try:
            webpush(
                subscription_info=json.loads(subscription['subscription_json']),
                data=json.dumps({'title':'EduPilot','body':message[:350],
                                 'url':href if href.startswith('/') and not href.startswith('//') else '/'}),
                vapid_private_key=os.getenv('VAPID_PRIVATE_KEY'),
                vapid_claims={'sub':os.getenv('VAPID_SUBJECT')},timeout=3)
        except WebPushException as exc:
            if getattr(getattr(exc,'response',None),'status_code',None) in (404,410):
                execute('DELETE FROM push_subscriptions WHERE id=?',(subscription['id'],))
            else:
                app.logger.warning('Échec push uid=%s: %s',uid,type(exc).__name__)
        except Exception as exc:
            app.logger.warning('Échec push uid=%s: %s',uid,type(exc).__name__)
    return True


def deliver(limit=50):
    now=int(time.time())
    candidates=allrows("""SELECT id FROM notification_delivery_queue
        WHERE attempts<3 AND (status='pending' OR
        (status='processing' AND claimed_at<?))
        ORDER BY id LIMIT ?""",(now-600,limit))
    delivered=0
    for candidate in candidates:
        jid=candidate['id']
        with db() as conn:
            claimed=conn.execute("""UPDATE notification_delivery_queue
                SET status='processing',claimed_at=?,attempts=attempts+1
                WHERE id=? AND attempts<3 AND (status='pending'
                   OR (status='processing' AND claimed_at<?))""",
                (int(time.time()),jid,int(time.time())-600))
            if claimed.rowcount!=1:continue
        job=one('SELECT * FROM notification_delivery_queue WHERE id=?',(jid,))
        try:
            account=one('SELECT id,active,school_id FROM users WHERE id=?',(job['user_id'],))
            if not account or not account['active'] or account['school_id']!=job['school_id']:
                ok=True  # Deleted/inactive account: do not contact.
            elif job['channel']=='email':
                ok=bool(send_brevo_email(job['address'],job['subject'],job['message'],
                                         job['school_id'],job['user_id']))
            elif job['channel']=='push':
                ok=send_push(job['user_id'],job['message'],job['href'])
            else:
                ok=True
        except Exception:
            app.logger.exception('Erreur de livraison notification id=%s',jid)
            ok=False
        with db() as conn:
            conn.execute("""UPDATE notification_delivery_queue
                SET status=? WHERE id=? AND status='processing'""",
                ('sent' if ok else ('failed' if job['attempts']>=3 else 'pending'),jid))
        if ok:delivered+=1
    return len(candidates),delivered


if __name__=='__main__':
    with app.app_context():
        pending,delivered=deliver()
        print(f'Notifications traitées : {pending}; livraisons acceptées : {delivered}')
