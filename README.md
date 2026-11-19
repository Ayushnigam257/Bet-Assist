# Betting Assistant

A Windows desktop record-keeping application built with Python's Tkinter GUI and SQLite.

## Run

Open PowerShell in this folder and run:

```powershell
.\.venv\Scripts\python.exe app.py
```

If you use another Python installation, run `python app.py` instead. The app creates `betting_assistant.db` in this folder the first time it starts. Keep a backup of this file to preserve records.

## Main screens

- **Matches** — create matches and enter two or more comma-separated team names (up to 12); view history, delete multiple matches, and inspect change logs.
- **Users & references** — search a full-width user table; add or edit contact information, commission references, limits, patti rates, and permission flags in the user form, and inspect change logs. **Entry → State/Ref** manages reusable State/Ref choices; values typed on a user record are added to that list, while deleting or clearing choices leaves saved user records unchanged.
- **Entry panel** — save and edit match, session, or meter entries; view one book at a time; save Mundi, Mundi Rate, Cutting/Dibba Book, and per-book F8 settings; add/select named sessions; prepare Runs, Fancy, and Meter entries; toggle K/L or Back/Lay with `+/-`; and view/print transactions and logs.
- **Results** — open Declaration with F5, double-click a match to choose its winner, or select a declared match and choose Undeclare. F6 opens Connect Report; Shift+F6 opens Connect Report Cup with a user filter.
- **Settling** — re-enter the shared app password from Settings to unlock Settling Transaction, Settling Report, and Commission Report. Settlement records support NAAM/JAMA entries, manual balances, opening balances, CH, codes, third-party names, Monday Final tagging, last-week filtering, and tallied status. Commission Report shows configured rates only.
- **Reports** — Individual Report filters a user's Match entries by match and date. Session Individual Report filters session entries by user, match, and named session, with a 1–25 run breakdown and selectable entry details. User Account filters users by match and State/Ref, shows manually recorded CH, and leaves A/B uncalculated. Each report supports printing and CSV export. Connect Report remains available from the Result menu and F6.
- **Tools** — each tool asks for the shared password again. Refresh (F1) reloads the current screen; Add (F12) opens the Match/User/Entry chooser. Blank Data first saves a SQLite backup, then clears application records while retaining login settings. Import Old Data merges a compatible Betting Assistant SQLite database and prevents importing the same source twice. Export Match saves the selected match and its entries as CSV. Unregister explains that this build has no separate registration record and makes no changes.

The reference screenshots do not define settlement, commission, or team-liability formulas. Settlement balances are therefore manually entered; reports show NAAM/JAMA totals separately and leave combined totals uncalculated. Reports and the entry panel show recorded gross amounts and manually entered CH; X/Z, team totals, Avg K/L, commission, patti settlement, and final combined totals are explicitly left uncalculated. Session run summaries include exact run values from 1 through 25.

## Login

The app checks the shared username and password against a salted PBKDF2 hash bundled in `shared_login_credentials.py`. The current shared username is `main`; clones that include this file will require the same password. After sign-in, the app opens a blank workspace; choose a screen from the menu. Use **Log out** in the menu to return to sign-in.

To set a new shared username/password, run `.\.venv\Scripts\python.exe create_shared_login.py`, then commit and distribute the generated `shared_login_credentials.py`. The password itself is entered without being echoed and is not written to the file.

**Important:** this is a deterrent, not owner-only access control. Anyone who can edit a clone can replace the hash or bypass the login; a committed hash can also be attacked offline. Keep the repository private if the shared password is sensitive. Local application data remains in `betting_assistant.db`.

## Test

```powershell
.\.venv\Scripts\python.exe -m unittest
```
