# New Project Telegram Codex Bridge

This bridge lets a Telegram bot send prompts into a Codex thread that runs against the `C:\Users\chris\Documents\New project` workspace on this Windows machine.

## What it does

- Uses the official `@openai/codex-sdk`
- Restricts control to one Telegram user ID
- Stores the attached thread ID and latest result in `bridge/state/bridge-state.json`
- Scans `C:\Users\chris\.codex\sessions` to attach to the latest matching local Codex thread for this workspace
- Runs Codex with `approvalPolicy = "never"` and `sandboxMode = "workspace-write"`
- Supports `/attach`, `/codex`, `/status`, `/last`, `/stop`, `/sessions`, `/projects`, and `/project`
- Streams useful progress into Telegram while Codex is working
- Lets you pin an active project inside the workspace for cleaner remote operation

## Setup

1. Copy `.env.example` to `.env`
2. Fill in:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_ALLOWED_USER_ID`
3. Run:

```powershell
cd C:\Users\chris\Documents\New project\safeguard360\bridge
npm run doctor
npm run start
```

## Finding your Telegram user ID

Fastest options:

- Message `@userinfobot` in Telegram
- Or, after messaging your new bot once, run:

```powershell
cd C:\Users\chris\Documents\New project\safeguard360\bridge
npm run show-updates
```

## Daily use

- `/attach`
  Attaches the bridge to the latest matching local Codex thread for `New project`
- `/attach <thread-id>`
  Attaches to a specific Codex thread ID
- `/attach <session-number>`
  Attaches to a session number shown by `/sessions`
- `/codex <prompt>`
  Queues a prompt into the attached thread, or into a new thread if nothing is attached yet
- `/status`
  Shows the active thread, queue, and last error
- `/last`
  Shows the last saved Codex reply
- `/stop`
  Aborts the active run and clears the queue
- `/sessions`
  Lists recent matching Codex sessions for the current workspace or active project
- `/projects`
  Lists top-level projects inside `New project`
- `/project <name>`
  Pins the bridge to one project so `/attach` and new threads prefer that folder
- `/project off`
  Clears the active project pin and returns to workspace-root mode

## Optional Windows startup

Install a logon task:

```powershell
cd C:\Users\chris\Documents\New project\safeguard360\bridge
npm run install-startup
```

Remove it:

```powershell
cd C:\Users\chris\Documents\New project\safeguard360\bridge
npm run uninstall-startup
```

## Notes

- The bridge uses the Codex SDK, not raw shell commands from Telegram
- The safest exact same-thread behavior is `resumeThread(threadId)` against the local Codex session store
- If both the desktop app and the bridge try to drive the same thread at the same time, results may be less predictable than serialized use
- The bridge now targets the whole `C:\Users\chris\Documents\New project` workspace, so it can work across `safeguard360`, `digigowebsite`, and other folders inside that root
