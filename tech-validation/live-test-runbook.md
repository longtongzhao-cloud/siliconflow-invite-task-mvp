# Supervised Live Test Runbook

This runbook covers validation that cannot be completed from public, read-only
evidence. It MUST NOT be executed until SiliconFlow has provided written
permission or formal third-party API documentation covering proxy login,
session storage, and the required status reads. Use test accounts and phone
numbers owned by the participants. Do not use a customer's account.

## Preconditions

- Written SiliconFlow permission or a formal third-party API agreement.
- A test inviter account that has enabled the SiliconFlow referral program.
- One never-registered test phone for invite registration.
- The inviter and test worker are present and explicitly consent.
- Browser developer tools and server logging are configured to redact `code`,
  `token`, `cookie`, `authorization`, and phone fields.
- The test environment is isolated from production and contains no payout code.

## Test A: inviter login and invite code

1. Open a single-use order link.
2. Enter the inviter phone.
3. Complete the slider manually.
4. Confirm that the SMS sender and message context are expected.
5. Enter the OTP directly into the test page. Never send the OTP in chat.
6. Confirm that an 8-character invite code or canonical invite URL is returned.
7. Confirm that the stored session is encrypted at rest, has a 24-hour TTL, and
   cannot be read from application logs, analytics, error traces, or admin pages.
8. Revoke/delete the session and confirm subsequent status reads fail closed.

Pass criteria: code returned; no OTP persistence; encrypted token with enforced
TTL; explicit logout/revocation works.

## Test B: new worker registration attribution

1. Claim a test task with the never-registered phone.
2. Register through the canonical SiliconFlow invite flow using the assigned
   invite code.
3. Verify the platform returns a stable user ID and a registration timestamp.
4. Verify the inviter's record or equivalent proxied state associates the new
   user with the intended invite code.

Pass criteria: stable user ID, correct attribution, and no access to unrelated
inviter data.

## Test C: authentication state

1. Before authentication, confirm status is `unverified`.
2. Complete SiliconFlow authentication on its official flow.
3. Poll at a conservative interval with backoff.
4. Confirm transition to `verified` and `effective=true`.
5. A separate, consenting test identity previously used for authentication may
   be used to verify that duplicate authentication produces `effective=false`.

Pass criteria: all three states can be distinguished without storing name,
identity number, document image, or biometric data.

## Stop conditions

Stop and mark the feature No-Go if any of the following occurs:

- The flow requires bypassing CAPTCHA or anti-bot controls.
- The server must impersonate the user outside the explicitly consented login.
- Attribution cannot be proven deterministically.
- Authentication status is inferred from coupon balance instead of an explicit
  status field.
- Tokens cannot be revoked or reliably expire.
- SiliconFlow blocks the test or indicates the integration is unauthorized.
