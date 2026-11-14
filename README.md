# Betting Assistant

A Windows desktop record-keeping application built with Python's Tkinter GUI and SQLite.

## Run

Open PowerShell in this folder and run:

```powershell
.\.venv\Scripts\python.exe app.py
```

If you use another Python installation, run `python app.py` instead. The app creates `betting_assistant.db` in this folder the first time it starts. Keep a backup of this file to preserve records.

## Main screens

- **Matches** — create matches and enter two or more comma-separated team names (up to 12).
- **Users & references** — keep contact information, commission references, limits, patti rates, and permission flags.
- **Entry panel** — save and edit match, session, or meter entries linked to a match and user.
- **Results** — declare or undeclare a match result.
- **Reports & accounts** — review gross transaction totals or an individual entry list, then export the visible report to CSV.

The reference screenshots do not define settlement, commission, or team-liability formulas. Reports therefore show recorded gross entry amounts and do not infer those calculations.

## Login

The app checks the shared username and password against a salted PBKDF2 hash bundled in `shared_login_credentials.py`. The current shared username is `main`; clones that include this file will require the same password. Use **Log out** in the sidebar to return to sign-in.

To set a new shared username/password, run `.\.venv\Scripts\python.exe create_shared_login.py`, then commit and distribute the generated `shared_login_credentials.py`. The password itself is entered without being echoed and is not written to the file.

**Important:** this is a deterrent, not owner-only access control. Anyone who can edit a clone can replace the hash or bypass the login; a committed hash can also be attacked offline. Keep the repository private if the shared password is sensitive. Local application data remains in `betting_assistant.db`.

## Test

```powershell
.\.venv\Scripts\python.exe -m unittest
```
