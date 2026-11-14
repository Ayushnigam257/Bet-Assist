# Betting Assistant — Setup and Run

## Requirements

- Windows
- Python 3.10 or later, with Tkinter available

The app uses Python's standard library. No additional pip packages are needed.

## Setup

1. Clone or download the project.
2. Open PowerShell in the project folder.
3. (Optional) Create a virtual environment:

   ```powershell
   py -3 -m venv .venv
   ```

4. Confirm `shared_login_credentials.py` is present. Clones need the same shared credentials file from the project repository.

## Run

With the optional virtual environment:

```powershell
.\.venv\Scripts\python.exe app.py
```

Without a virtual environment:

```powershell
py app.py
```

Sign in using the shared username and password configured for the project. The default shared username is `main`; the password is not documented here. The app creates `betting_assistant.db` in the project folder for local match, user, and entry data.

## Change the shared login

Run the credential setup tool:

```powershell
.\.venv\Scripts\python.exe create_shared_login.py
```

Without a virtual environment, run `py create_shared_login.py`.

It asks for a username and password without displaying the password, then updates `shared_login_credentials.py`. Commit and push that file so future clones receive the updated credentials. This embedded login is not tamper-proof: anyone who can edit a clone can replace or bypass its check.

## Run tests

```powershell
.\.venv\Scripts\python.exe -m unittest
```

Without a virtual environment, run `py -m unittest`.
