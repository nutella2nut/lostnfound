# Manual Smoke Test Checklist

Use this checklist to verify end-to-end functionality before a release.
Each item requires a real browser and (where noted) a real email account.

## Microsoft 365 OAuth

- [ ] Run `python manage.py microsoft_oauth_setup`; complete the browser sign-in; verify the `MicrosoftOAuthToken` row exists in the database.
- [ ] Trigger a test outbound email; verify it arrives at the target inbox.
- [ ] Force-expire the cached access token (set `cached_access_token_expires_at` to the past in admin); trigger an email; verify the helper refreshes silently and the email still sends.

## Email Submission (check_emails)

- [ ] Send a real test email from a `@tisb.ac.in` address to `LF_EMAIL_ADDRESS`; verify it appears in the approval queue with images.
- [ ] Approve it; verify approval email arrives.

## Broadcast

- [ ] Click Broadcast on an approved student lost item; verify confirmation page renders correctly with the full email preview.
- [ ] Confirm and send; verify email arrives at all recipients with images attached AND a working "View on TRACE" link.
- [ ] Verify `BroadcastLog` row was created.
- [ ] Broadcast the same item 4 times within 24 hours; verify rate limit fires on the 4th attempt.

## Claim Flow

- [ ] Submit a claim; attestation checkbox is required, confirmation modal shows, confirmation email arrives, banner updates on the item.
- [ ] Non-TISB email is rejected on the claim form.

## Magic Link (My Reports)

- [ ] Visit `/my-reports/`, enter a TISB email, request a sign-in link.
- [ ] Click the link in the email; verify you see your reports and claims.
- [ ] Verify `/my-reports/` shows the public sidebar even when signed in as a staff user.
- [ ] Try the link a second time; verify it shows "already used" message.
- [ ] Verify magic-link session does not grant access to `/staff/dashboard/` (should redirect to login).

## S3 / Media Storage

- [ ] With `MEDIA_BACKEND=s3` configured, upload an item image and verify the URL points to the bucket/custom domain.
- [ ] Run `python manage.py migrate_media_to_s3 --dry-run` and verify the planned uploads list looks correct.

## Staff User Management

- [ ] Visit `/staff/users/` as a Super User; create a new Admin user; verify they receive the welcome email.
- [ ] Sign in as the new user and verify they have Admin-only navigation (no Approval Queue, no Manage Users).
- [ ] Promote the new Admin to Super User via the UI; verify the role-change email arrives and a `UserRoleChangeLog` row was created.
- [ ] Try to demote yourself in `/staff/users/`; verify the action button is disabled.
- [ ] Create a second Super User, then attempt to demote/deactivate/delete the first one while logged in as the second; verify it works.
- [ ] Attempt the same when only one active Super User remains; verify the refusal banner appears.
- [ ] Delete a user via `/staff/users/<id>/delete/`; verify the username-typing confirmation gate works.
- [ ] Verify the `Manage users` sidebar link does not appear for an Admin (non-Super-User) account.
