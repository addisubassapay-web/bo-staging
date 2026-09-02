import asyncio, os, uuid
from dotenv import load_dotenv
os.chdir('/app/backend')
load_dotenv()
from services import mailer

async def main():
    mailer._SEND_HISTORY.clear()
    idem = f"e2e-{uuid.uuid4().hex[:8]}"
    r1 = await mailer.send_email(
        to='delivered@resend.dev',
        subject='Pro test — auth kind',
        html='<p>auth-kind test</p>', text='auth-kind test',
        email_kind='auth', tags=['pro_test','auth'],
        idempotency_key=idem,
    )
    print('send#1:', {k: r1.get(k) for k in ('ok','provider','kind','message_id')})
    r2 = await mailer.send_email(
        to='delivered@resend.dev',
        subject='Pro test — should NOT resend (idempotent)',
        html='<p>dup</p>', text='dup',
        email_kind='auth', idempotency_key=idem,
    )
    print('send#2 (idempotent):', {k: r2.get(k) for k in ('ok','provider','kind','idempotent')})
    r3 = await mailer.send_email(
        to='delivered@resend.dev',
        subject='Pro test — receipts kind',
        html='<p>receipts test</p>', text='receipts',
        email_kind='receipts', tags=['pro_test','receipts'],
    )
    print('send#3:', {k: r3.get(k) for k in ('ok','provider','kind','message_id')})

asyncio.run(main())
