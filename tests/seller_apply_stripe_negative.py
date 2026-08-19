#!/usr/bin/env python3
"""Negative API check: removed Stripe payout option should not be accepted."""
import json
import time

from stripe_removal_verification import auth, request

ts = int(time.time())
email = f"e2e_stripe_removed_{ts}@example.com"
password = "pass1234"
reg = request("POST", "/auth/register", json={"email": email, "username": f"stripegone{ts}", "password": password})
reg.raise_for_status()
token = reg.json()["token"]

send_email = request("POST", "/verify/email/send", headers=auth(token), json={})
send_email.raise_for_status()
email_token = send_email.json().get("token")
confirm_email = request("POST", "/verify/email/confirm", headers=auth(token), json={"token": email_token})
confirm_email.raise_for_status()

phone = f"+1555{str(ts)[-7:]}"
send_phone = request("POST", "/verify/phone/send", headers=auth(token), json={"phone": phone})
send_phone.raise_for_status()
code = send_phone.json().get("code")
confirm_phone = request("POST", "/verify/phone/confirm", headers=auth(token), json={"phone": phone, "code": code})
confirm_phone.raise_for_status()

payload = {
    "legal_name": "Stripe Removed QA",
    "business_name": "",
    "business_type": "individual",
    "tax_id": "1234",
    "country": "US",
    "address_line1": "1 Test St",
    "address_line2": "",
    "city": "Testville",
    "state": "CA",
    "postal_code": "94105",
    "phone": phone,
    "payout_method": "stripe_connect",
    "id_document_note": "negative test",
}
apply = request("POST", "/seller/apply", headers=auth(token), json=payload)
print(json.dumps({"email": email, "status": apply.status_code, "body": apply.text[:500]}))
raise SystemExit(0 if apply.status_code >= 400 else 1)