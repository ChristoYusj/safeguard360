# Authentication and Email Delivery

This document describes the current authentication and password-reset
configuration in SafeGuard 360.

## Auth Responsibilities

The auth layer covers:

- operator sign-in
- session refresh and logout
- two-factor setup and verification
- operator registration approval
- password changes for authenticated users
- password reset requests and reset-token confirmation

Primary files:

- `backend/app/api/auth.py`
- `backend/app/services/auth.py`
- `backend/app/services/email.py`
- `backend/app/config/settings.py`
- `frontend/src/pages/Portal.jsx`
- `frontend/src/pages/ResetPassword.jsx`

## Password Reset Flow

### Request phase

1. Operator submits an email from the portal reset form.
2. Backend normalizes the email and looks up an active or restricted account.
3. If the account is eligible, backend creates a signed password-reset token.
4. Backend builds the frontend reset URL.
5. Backend sends the email through the configured mail transport.

The public API still responds with a generic success message for missing
accounts so the reset form does not leak account existence.

### Confirm phase

1. Operator opens the reset link.
2. Frontend sends the token and new password to
   `/api/auth/password-reset/confirm`.
3. Backend validates the token, updates the password hash, increments the
   reset-token version, and clears old refresh sessions.

## Mail Transport Modes

### Resend mode

Use this in real deployments:

- `MAIL_TRANSPORT=resend`
- `RESEND_API_KEY=<your resend key>`
- `RESEND_FROM_EMAIL=no-reply@yourdomain.com`
- `FRONTEND_APP_URL=http://your-frontend-origin`

Requirements:

- Resend domain is verified
- sender address belongs to that verified domain

### Local capture mode

Use this for local-first development when you do not want to depend on a live
provider:

- `MAIL_TRANSPORT=local`
- `MAIL_LOCAL_OUTBOX_DIR=./backend/data/mail`

Behavior:

- emails are written to the local outbox directory
- reset requests do not require a third-party provider
- browser-side direct reset-link exposure is disabled by default

### Dev-only reset-link exposure

Optional:

- `MAIL_EXPOSE_LOCAL_RESET_LINKS=true`

Use this only when you explicitly want the browser to show the direct local
reset link on the machine running the app.

This is convenient for solo development, but it should not be the default for
shared operator terminals.

## Security Notes

- reset tokens are signed and time-limited
- password-reset confirmation invalidates prior reset versions
- old refresh sessions are cleared on reset
- local reset-link exposure is opt-in
- provider-specific raw errors are not shown directly to the operator UI

## Operational Notes

- if real password-reset emails fail, verify the sending domain and sender
  address first
- `FRONTEND_APP_URL` should be set in environments where the backend origin
  differs from the frontend origin
- local captured emails live under `backend/data/mail/` and are runtime data,
  not source-controlled assets
