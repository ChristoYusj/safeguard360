# Authentication and Email Delivery

This document explains how the authentication and password-reset subsystem
works, and why it is designed the way it is.

## What This Subsystem Covers

SafeGuard 360 includes:

- operator sign-in
- session refresh and logout
- operator registration approval
- two-factor setup and verification
- authenticated password change
- password reset by emailed link

Primary files:

- `backend/app/api/auth.py`
- `backend/app/services/auth.py`
- `backend/app/services/email.py`
- `backend/app/config/settings.py`
- `frontend/src/pages/Portal.jsx`
- `frontend/src/pages/ResetPassword.jsx`

## Why Authentication Matters Here

The dashboard is not meant to be a public viewer. It controls gate decisions,
shows workforce history, exposes review decisions, and can affect live site
operations. That is why the project includes a full auth path instead of a
simple demo login.

## Password Reset: Internal Flow

Password reset is a two-phase process.

### Phase 1: Request

1. The operator submits an email in the portal reset form.
2. The backend normalizes the email and checks whether the account is eligible
   for reset.
3. If the account is valid, the backend creates a signed, time-limited reset
   token.
4. The backend builds the frontend reset URL.
5. The backend sends the email through the configured mail transport.

The public API still responds with a generic success message when an account is
missing, so the UI does not expose account existence directly.

### Phase 2: Confirmation

1. The operator opens the reset link.
2. The frontend sends the token and new password to the backend.
3. The backend validates the token.
4. The password hash is updated.
5. The password-reset token version is advanced so old reset links become
   invalid.
6. Old refresh sessions are cleared.

This design ensures that password reset is not just a UI gesture. It is a real
security state transition.

## How Frontend and Backend Work Together

The frontend and backend divide responsibility clearly.

### Frontend

- collects credentials or reset form input
- sends explicit REST requests
- displays success or failure messages
- renders the reset-password page after the email link is opened

### Backend

- validates identity-related inputs
- creates or verifies signed tokens
- controls whether the reset request is valid
- chooses the delivery transport
- updates the stored password and session state

This split is important because the browser should never be trusted to own the
security logic. The frontend collects intent. The backend performs the
security-sensitive work.

## Mail Transport Modes

The project supports two mail behaviors.

### Resend verified-domain mode

Use this for real email delivery:

- `MAIL_TRANSPORT=resend`
- `RESEND_API_KEY=<your resend key>`
- `RESEND_FROM_EMAIL=no-reply@yourdomain.com`
- `FRONTEND_APP_URL=http://your-frontend-origin`

What this means operationally:

- the domain must be verified in Resend
- the sender address must belong to that verified domain
- reset links are delivered as actual email

This is the production-style path because it behaves like a real operator
system, not a dev tool.

### Local capture mode

Use this when you want local-first testing without relying on a live provider:

- `MAIL_TRANSPORT=local`
- `MAIL_LOCAL_OUTBOX_DIR=./backend/data/mail`

Behavior:

- emails are written to a local outbox directory
- the project can still exercise the reset flow without third-party delivery

This exists because the project is local-first and should still be testable
when provider setup is incomplete or internet access is unreliable.

## Why Direct Reset-Link Exposure Is Dangerous By Default

There is a convenience feature:

- `MAIL_EXPOSE_LOCAL_RESET_LINKS=true`

When enabled in local mode, the browser can expose the direct reset link on the
same machine. This is useful for solo development, but dangerous on a shared
operator terminal because someone could request a reset for a valid account and
immediately use the local link.

That is why direct link exposure is opt-in, not the default.

## Security Design Notes

- reset tokens are signed and time-limited
- old reset links become invalid after a successful reset
- prior refresh sessions are cleared on reset
- provider-specific raw errors are not shown directly to the operator UI
- direct browser exposure of local reset links is disabled by default

These choices make the subsystem safer while still keeping it practical to
develop locally.

## Operational Notes

- if real password-reset email fails, first verify the sender domain and sender
  address
- `FRONTEND_APP_URL` should be configured so reset links point to the correct
  frontend origin
- local captured emails under `backend/data/mail/` are runtime data, not
  source-controlled project assets
