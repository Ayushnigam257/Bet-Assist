import csv
import html
import json
import sqlite3
import tempfile
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable
import webbrowser

from database import Database, USER_FIELDS
from shared_login import authenticate as authenticate_shared_login


APP_DIR = Path(__file__).resolve().parent
DB = Database(APP_DIR / "betting_assistant.db")

COLORS = {
    "background": "#a9a9a9",
    "panel": "#f0f0f0",
    "sidebar": "#d4d0c8",
    "sidebar_active": "#c8c4bc",
    "text": "#000000",
    "muted": "#303030",
    "accent": "#d4d0c8",
    "border": "#808080",
    "success": "#e6f5ee",
}


def money(value: float) -> str:
    return f"{value:,.2f}"


def open_print_preview(title: str, headers: list[str], rows: list[list[Any]]) -> None:
    head = "".join(f"<th>{html.escape(str(header))}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row) + "</tr>"
        for row in rows
    )
    document = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body {{ font: 12px Arial, sans-serif; margin: 24px; }}
h1 {{ font-size: 18px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #888; padding: 5px; text-align: left; }}
th {{ background: #e5e5e5; }}
@media print {{ button {{ display: none; }} }}
</style></head><body><h1>{html.escape(title)}</h1>
<button onclick="window.print()">Print</button>
<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
</body></html>"""
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".html",
        prefix="betting-assistant-",
        delete=False,
    ) as file:
        file.write(document)
        path = Path(file.name)
    if not webbrowser.open(path.resolve().as_uri()):
        raise RuntimeError(f"Could not open the print preview: {path}")


class BettingAssistant(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Betting Assistant Plus")
        self.geometry("1360x768")
        self.minsize(960, 620)
        self.configure(bg=COLORS["background"])

        style = ttk.Style(self)
        available_themes = style.theme_names()
        style.theme_use("winnative" if "winnative" in available_themes else "clam")
        style.configure("TFrame", background=COLORS["background"])
        style.configure("Card.TFrame", background=COLORS["panel"])
        style.configure(
            "TLabel",
            background=COLORS["background"],
            foreground=COLORS["text"],
            font=("Tahoma", 9),
        )
        style.configure(
            "Card.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            font=("Tahoma", 9),
        )
        style.configure(
            "Title.TLabel",
            background=COLORS["background"],
            foreground=COLORS["text"],
            font=("Tahoma", 11, "bold"),
        )
        style.configure(
            "Muted.TLabel",
            background=COLORS["background"],
            foreground=COLORS["muted"],
            font=("Tahoma", 8),
        )
        style.configure(
            "TButton", font=("Tahoma", 8), padding=(3, 2)
        )
        style.configure(
            "Accent.TButton",
            background=COLORS["accent"],
            foreground=COLORS["text"],
            padding=(4, 2),
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#c8c4bc"), ("disabled", "#d4d0c8")],
        )
        style.configure(
            "Treeview",
            background="#808080",
            fieldbackground="#808080",
            foreground=COLORS["text"],
            rowheight=22,
            font=("Tahoma", 8),
        )
        style.configure(
            "Treeview.Heading",
            background="#f0f0f0",
            foreground=COLORS["text"],
            font=("Tahoma", 8, "bold"),
            padding=(3, 2),
        )
        style.map(
            "Treeview",
            background=[("selected", "#ffff80")],
            foreground=[("selected", "#000000")],
        )

        self.match_rows: list[sqlite3.Row] = []
        self.user_rows: list[sqlite3.Row] = []
        self.logged_in_username = ""
        self.settings_unlocked = False
        self.content = tk.Frame(self, bg=COLORS["background"])
        self.content.pack(fill="both", expand=True)
        self.set_logged_out_menu()
        self.show_login()

    def set_logged_out_menu(self) -> None:
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Exit", command=self.destroy)
        self.configure(menu=menu)

    def set_logged_in_menu(self) -> None:
        menu = tk.Menu(self, tearoff=False)

        def add_page_menu(label: str, items: tuple[tuple[str, str], ...]) -> None:
            submenu = tk.Menu(menu, tearoff=False)
            for item_label, page in items:
                if page.startswith("Report:"):
                    target = page.split(":", 1)[1]
                    command = lambda mode=target: self.open_report_mode(mode)
                elif page == "State/Ref":
                    command = self.open_state_ref_window
                else:
                    command = lambda target=page: self.show_page(target)
                submenu.add_command(
                    label=item_label, command=command
                )
            menu.add_cascade(label=label, menu=submenu)

        add_page_menu(
            "Entry",
            (
                ("Entry Panel", "Entries"),
                ("User Entry", "Users"),
                ("State/Ref", "State/Ref"),
            ),
        )
        add_page_menu(
            "Match",
            (("Team Entry", "Matches"), ("Match List", "Matches")),
        )
        result_menu = tk.Menu(menu, tearoff=False)
        result_menu.add_command(
            label="Declare Match/Session/Meter",
            command=self.open_declaration_window,
            accelerator="F5",
        )
        result_menu.add_command(
            label="Connect Report",
            command=self.open_connect_report,
            accelerator="F6",
        )
        result_menu.add_command(
            label="Connect Report Cup",
            command=self.open_connect_report_cup,
            accelerator="Shift+F6",
        )
        menu.add_cascade(label="Result", menu=result_menu)
        self.bind("<F5>", lambda _event: self.open_declaration_window())
        self.bind("<F6>", lambda _event: self.open_connect_report())
        self.bind("<Shift-F6>", lambda _event: self.open_connect_report_cup())
        add_page_menu(
            "Report",
            (
                ("Individual Report", "Report:Individual Report"),
                ("Session Individual Report", "Report:Session Individual Report"),
                ("User Account", "Report:User Account"),
            ),
        )
        settling_menu = tk.Menu(menu, tearoff=False)
        settling_menu.add_command(
            label="Settling Transaction",
            command=lambda: self.open_protected_setting(
                self.open_settling_transaction
            ),
        )
        settling_menu.add_command(
            label="Settling Report",
            command=lambda: self.open_protected_setting(self.open_settling_report),
        )
        settling_menu.add_command(
            label="Commission Report",
            command=lambda: self.open_protected_setting(
                self.open_commission_report
            ),
        )
        settling_menu.add_separator()
        settling_menu.add_command(
            label="Settlement Report",
            command=self.open_connect_report,
        )
        menu.add_cascade(label="Settling", menu=settling_menu)
        settings_menu = tk.Menu(menu, tearoff=False)
        settings_menu.add_command(
            label="Login (Settings)", command=self.login_settings
        )
        settings_menu.add_separator()
        settings_menu.add_command(
            label="Dashboard", command=lambda: self.show_page("Dashboard")
        )
        settings_menu.add_command(
            label="User References", command=lambda: self.show_page("Users")
        )
        settings_menu.add_separator()
        settings_menu.add_command(label="Log out", command=self.show_login)
        menu.add_cascade(label="Settings", menu=settings_menu)
        tools_menu = tk.Menu(menu, tearoff=False)
        tools_menu.add_command(
            label="Refresh",
            command=lambda: self.run_protected_tool(
                "Refresh F1", self.refresh_current_page
            ),
            accelerator="F1",
        )
        tools_menu.add_command(
            label="Add",
            command=lambda: self.run_protected_tool("Add F12", self.open_add_tool),
            accelerator="F12",
        )
        tools_menu.add_command(
            label="Blank Data",
            command=lambda: self.run_protected_tool(
                "Blank Data", self.blank_application_data
            ),
        )
        tools_menu.add_command(
            label="Import Old Data",
            command=lambda: self.run_protected_tool(
                "Import Old Data", self.import_old_data
            ),
        )
        tools_menu.add_command(
            label="Export Match",
            command=lambda: self.run_protected_tool(
                "Export Match", self.export_match
            ),
        )
        tools_menu.add_command(
            label="Unregister",
            command=lambda: self.run_protected_tool(
                "Unregister", self.unregister_application
            ),
        )
        tools_menu.add_separator()
        tools_menu.add_command(
            label="Reports & Accounts",
            command=lambda: self.open_report_mode("User Account"),
        )
        menu.add_cascade(label="Tools", menu=tools_menu)
        menu.add_command(label="Exit", command=self.destroy)
        self.configure(menu=menu)
        self.bind(
            "<F1>",
            lambda _event: self.run_protected_tool(
                "Refresh F1", self.refresh_current_page
            ),
        )
        self.bind(
            "<F12>",
            lambda _event: self.run_protected_tool(
                "Add F12", self.open_add_tool
            ),
        )

    def show_login(self) -> None:
        self.set_logged_out_menu()
        self.settings_unlocked = False
        self.logged_in_username = ""
        for shortcut in ("<F1>", "<F5>", "<F6>", "<F12>", "<Shift-F6>"):
            self.unbind(shortcut)
        for widget in self.content.winfo_children():
            widget.destroy()
        self.content.configure(bg=COLORS["background"])

        card = tk.Frame(
            self.content,
            bg=COLORS["panel"],
            padx=24,
            pady=20,
            relief="groove",
            bd=2,
            highlightbackground=COLORS["border"],
            highlightthickness=0,
        )
        card.place(relx=0.5, rely=0.46, anchor="center", width=370)
        tk.Label(
            card,
            text="Welcome back",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Tahoma", 12, "bold"),
        ).pack(anchor="w")
        tk.Label(
            card,
            text="Sign in to open your Betting Assistant.",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Tahoma", 8),
        ).pack(anchor="w", pady=(4, 14))

        self.login_username_var = tk.StringVar()
        self.login_password_var = tk.StringVar()
        self.login_error_var = tk.StringVar()

        def add_field(label: str, variable: tk.StringVar, masked: bool = False) -> None:
            tk.Label(
                card,
                text=label,
                bg=COLORS["panel"],
                fg=COLORS["text"],
                font=("Tahoma", 8),
            ).pack(anchor="w", pady=(0, 5))
            ttk.Entry(
                card,
                textvariable=variable,
                show="*" if masked else "",
                width=42,
            ).pack(fill="x", pady=(0, 10), ipady=2)

        add_field("Username", self.login_username_var)
        add_field("Password", self.login_password_var, masked=True)

        tk.Label(
            card,
            textvariable=self.login_error_var,
            bg=COLORS["panel"],
            fg="#b42318",
            font=("Tahoma", 8),
        ).pack(anchor="w", pady=(0, 8))
        button = ttk.Button(
            card,
            text="Sign in",
            style="Accent.TButton",
            command=self.submit_login,
        )
        button.pack(fill="x")
        self.bind("<Return>", lambda _event: self.submit_login())

    def submit_login(self) -> None:
        username = self.login_username_var.get()
        password = self.login_password_var.get()
        if not authenticate_shared_login(username, password):
            self.login_error_var.set("Incorrect username or password.")
            self.login_password_var.set("")
            return
        self.unbind("<Return>")
        self.logged_in_username = username
        self.set_logged_in_menu()
        self.show_page("Workspace")

    def login_settings(self) -> bool:
        if self.settings_unlocked:
            return True
        password = simpledialog.askstring(
            "Login (Settings)",
            "Enter Password",
            parent=self,
            show="*",
        )
        if password is None:
            return False
        if not authenticate_shared_login(self.logged_in_username, password):
            messagebox.showerror(
                "Login failed", "Incorrect password.", parent=self
            )
            return False
        self.settings_unlocked = True
        return True

    def open_protected_setting(self, action: Callable[[], None]) -> None:
        if self.login_settings():
            action()

    def run_protected_tool(self, title: str, action: Callable[[], None]) -> None:
        password = simpledialog.askstring(
            f"Login ({title})",
            "Enter Password",
            parent=self,
            show="*",
        )
        if password is None:
            return
        if not authenticate_shared_login(self.logged_in_username, password):
            messagebox.showerror("Login failed", "Incorrect password.", parent=self)
            return
        action()

    def refresh_current_page(self) -> None:
        page = getattr(self, "current_page", "Entries")
        if not messagebox.askyesno(
            "Refresh",
            "Reload this screen? Unsaved form changes will be discarded.",
            parent=self,
        ):
            return
        self.show_page(page)

    def open_add_tool(self) -> None:
        window = self.report_window("Add", "320x210")
        ttk.Label(window, text="Choose what you want to add.").pack(
            padx=12, pady=(16, 8)
        )
        buttons = tk.Frame(window, bg=COLORS["background"])
        buttons.pack(pady=5)

        def open_page(page: str) -> None:
            window.destroy()
            self.show_page(page)

        for label, page in (
            ("Match", "Matches"),
            ("User", "Users"),
            ("Entry", "Entries"),
        ):
            ttk.Button(
                buttons,
                text=label,
                command=lambda target=page: open_page(target),
            ).pack(side="left", padx=4)
        ttk.Button(window, text="Cancel", command=window.destroy).pack(pady=6)

    def blank_application_data(self) -> None:
        if not messagebox.askyesno(
            "Blank Data",
            "This will remove all matches, users, entries, settlement records, "
            "and audit history. Create a backup before continuing.",
            parent=self,
        ):
            return
        backup_path = filedialog.asksaveasfilename(
            parent=self,
            title="Save backup before blanking data",
            initialfile=(
                f"betting_assistant_backup_{datetime.now():%Y%m%d_%H%M%S}.sqlite3"
            ),
            defaultextension=".sqlite3",
            filetypes=(("SQLite database", "*.sqlite3"), ("All files", "*.*")),
        )
        if not backup_path:
            return
        try:
            DB.backup_to(backup_path)
            DB.clear_application_data()
        except (OSError, sqlite3.Error, ValueError) as error:
            messagebox.showerror("Could not blank data", str(error), parent=self)
            return
        self.show_page("Entries")
        messagebox.showinfo(
            "Data cleared",
            f"Application data was cleared. Backup saved to:\n{backup_path}",
            parent=self,
        )

    def import_old_data(self) -> None:
        source_path = filedialog.askopenfilename(
            parent=self,
            title="Import old Betting Assistant data",
            filetypes=(
                ("SQLite databases", "*.db *.sqlite *.sqlite3"),
                ("All files", "*.*"),
            ),
        )
        if not source_path:
            return
        try:
            imported = DB.import_old_database(source_path)
        except (FileNotFoundError, OSError, sqlite3.Error, ValueError) as error:
            messagebox.showerror("Import failed", str(error), parent=self)
            return
        messagebox.showinfo(
            "Import complete",
            "Imported records:\n"
            f'Matches: {imported["matches"]}\n'
            f'Users: {imported["users"]}\n'
            f'Entries: {imported["entries"]}',
            parent=self,
        )
        self.show_page(getattr(self, "current_page", "Entries"))

    def export_match(self) -> None:
        try:
            matches = DB.list_matches()
        except sqlite3.Error as error:
            messagebox.showerror("Could not load matches", str(error), parent=self)
            return
        if not matches:
            messagebox.showinfo("No matches", "There are no matches to export.", parent=self)
            return
        window = self.report_window("Export Match", "420x150")
        match_var = tk.StringVar(value=self.match_label(matches[0]))
        ttk.Label(window, text="Match").pack(anchor="w", padx=12, pady=(12, 4))
        match_combo = ttk.Combobox(
            window,
            textvariable=match_var,
            values=[self.match_label(row) for row in matches],
            state="readonly",
            width=44,
        )
        match_combo.pack(fill="x", padx=12)
        actions = tk.Frame(window, bg=COLORS["background"])
        actions.pack(pady=12)

        def save_export() -> None:
            match = next(
                (row for row in matches if self.match_label(row) == match_var.get()),
                None,
            )
            if match is None:
                messagebox.showerror(
                    "Select a match", "Choose a match to export.", parent=window
                )
                return
            path = filedialog.asksaveasfilename(
                parent=window,
                title="Export Match",
                defaultextension=".csv",
                initialfile=f'match_{match["code"]}.csv',
                filetypes=(("CSV files", "*.csv"),),
            )
            if not path:
                return
            try:
                entries = DB.list_entries(match_id=int(match["id"]))
                with open(path, "w", newline="", encoding="utf-8-sig") as file:
                    writer = csv.writer(file)
                    writer.writerow(
                        ["Match Code", "Date", "Comment", "Teams", "Result", "Winner"]
                    )
                    writer.writerow(
                        [
                            match["code"],
                            match["match_date"],
                            match["comment"],
                            match["teams"],
                            match["result"],
                            match["winner"],
                        ]
                    )
                    writer.writerow([])
                    writer.writerow(
                        [
                            "Entry Date",
                            "User",
                            "Type",
                            "Book",
                            "Patti",
                            "Rate",
                            "Amount",
                            "Mode",
                            "Team",
                            "Session",
                            "Runs",
                            "Yes/No",
                            "Support",
                            "CH",
                        ]
                    )
                    for entry in entries:
                        writer.writerow(
                            [
                                entry["entry_date"],
                                entry["user_name"],
                                entry["entry_type"],
                                entry["book_no"],
                                entry["patti_number"],
                                entry["rate"],
                                entry["amount"],
                                entry["mode"],
                                entry["team"],
                                entry["session"],
                                entry["runs"],
                                entry["yes_no"],
                                entry["support"],
                                entry["charge"],
                            ]
                        )
            except (OSError, sqlite3.Error) as error:
                messagebox.showerror("Export failed", str(error), parent=window)
                return
            messagebox.showinfo(
                "Export complete", f"Saved match data to:\n{path}", parent=window
            )
            window.destroy()

        ttk.Button(
            actions,
            text="Export",
            style="Accent.TButton",
            command=save_export,
        ).pack(side="left", padx=4)
        ttk.Button(actions, text="Close", command=window.destroy).pack(
            side="left", padx=4
        )

    def unregister_application(self) -> None:
        messagebox.showinfo(
            "Unregister",
            "This application build uses a shared password and has no separate "
            "registration record. No data or login settings were changed.",
            parent=self,
        )

    def open_settling_transaction(self) -> None:
        try:
            users = DB.list_users()
            stored = DB.list_settling_transactions()
        except sqlite3.Error as error:
            messagebox.showerror("Could not load settlements", str(error), parent=self)
            return

        name_values = list(
            dict.fromkeys(
                [self.user_label(user) for user in users]
                + [str(row["name"]) for row in stored]
            )
        )
        window = self.report_window("Settling Transaction", "820x540")
        window.minsize(720, 500)
        header = tk.Frame(window, bg=COLORS["panel"], padx=8, pady=7)
        header.pack(fill="x", padx=8, pady=(8, 5))
        opening_var = tk.StringVar(value="0.00")
        date_var = tk.StringVar(value=date.today().isoformat())
        closing_var = tk.StringVar(value="0.00")
        ttk.Label(header, text="Opening Balance").grid(row=0, column=0, padx=4)
        opening_entry = ttk.Entry(header, textvariable=opening_var, width=11)
        opening_entry.grid(row=0, column=1, padx=4)
        date_entry = tk.Entry(
            header,
            textvariable=date_var,
            width=23,
            justify="center",
            bg="#f1ae63",
            fg=COLORS["text"],
            relief="sunken",
        )
        date_entry.grid(row=0, column=2, columnspan=2, padx=8, sticky="ew")
        ttk.Label(header, text="Closing Balance").grid(row=0, column=4, padx=4)
        ttk.Label(
            header, textvariable=closing_var, relief="sunken", width=11
        ).grid(row=0, column=5, padx=4)
        header.grid_columnconfigure(2, weight=1)
        body = tk.Frame(window, bg=COLORS["background"])
        body.pack(fill="both", expand=True, padx=8, pady=4)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=4)
        body.grid_rowconfigure(0, weight=1)
        name_frame = tk.Frame(body, bg=COLORS["panel"])
        name_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        name_list = tk.Listbox(
            name_frame,
            exportselection=False,
            bg="#ffffff",
            selectbackground="#d6e5f5",
            selectforeground=COLORS["text"],
        )
        name_list.pack(fill="both", expand=True)
        for item in name_values:
            name_list.insert(tk.END, item)
        transaction_frame = tk.Frame(body, bg=COLORS["panel"])
        transaction_frame.grid(row=0, column=1, sticky="nsew")
        tree = self.make_tree(
            transaction_frame,
            (
                ("date", "DATE", 70),
                ("name", "NAME", 90),
                ("naam", "NAAM", 70),
                ("jama", "JAMA", 70),
                ("balance", "BALANCE", 80),
                ("charge", "CH", 60),
                ("code", "CODE", 60),
            ),
            height=15,
        )
        name_var = tk.StringVar(value=name_values[0] if name_values else "")
        side_var = tk.StringVar(value="NAAM")
        amount_var = tk.StringVar()
        balance_var = tk.StringVar()
        charge_var = tk.StringVar(value="0")
        code_var = tk.StringVar()
        third_party_var = tk.StringVar()
        category_var = tk.StringVar(value="Regular")
        editing_id: int | None = None
        active_category: str | None = None
        active_dates: tuple[str, str] | None = None
        active_all_names = False
        rows_by_id: dict[int, sqlite3.Row] = {}
        tallied_var = tk.BooleanVar()

        def persist_opening_balance(show_error: bool = True) -> bool:
            name = name_var.get().strip()
            try:
                amount = float(opening_var.get().replace(",", ""))
                if not name:
                    return False
                DB.set_settling_opening_balance(name, amount)
            except (ValueError, sqlite3.Error) as error:
                if show_error:
                    messagebox.showerror(
                        "Invalid opening balance", str(error), parent=window
                    )
                return False
            return True

        def refresh(selected_id: int | None = None) -> None:
            name = (
                None
                if active_all_names
                else (name_var.get().strip() or None)
            )
            start_date, end_date = active_dates or (None, None)
            try:
                rows = DB.list_settling_transactions(
                    name=name,
                    category=active_category,
                    start_date=start_date,
                    end_date=end_date,
                )
                latest = DB.list_settling_transactions(name=name)
                opening = DB.get_settling_opening_balance(name) if name else 0.0
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Could not load settlement records", str(error), parent=window
                )
                return
            tree.delete(*tree.get_children())
            rows_by_id.clear()
            for row in rows:
                transaction_id = int(row["id"])
                rows_by_id[transaction_id] = row
                tree.insert(
                    "",
                    "end",
                    iid=str(transaction_id),
                    values=(
                        row["entry_date"],
                        row["name"],
                        money(float(row["amount"]))
                        if row["side"] == "NAAM"
                        else "",
                        money(float(row["amount"]))
                        if row["side"] == "JAMA"
                        else "",
                        money(float(row["balance"])),
                        money(float(row["charge"])),
                        row["code"],
                    ),
                )
            if selected_id is not None and tree.exists(str(selected_id)):
                tree.selection_set(str(selected_id))
            closing_var.set(
                money(float(latest[0]["balance"])) if latest else money(opening)
            )
            selected_row = (
                rows_by_id.get(selected_id) if selected_id is not None else None
            )
            tallied_var.set(bool(selected_row["tallied"]) if selected_row else False)

        def load_name(name: str) -> None:
            nonlocal active_category, active_dates, active_all_names, editing_id
            name_var.set(name)
            try:
                opening = DB.get_settling_opening_balance(name) if name else 0.0
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Could not load opening balance", str(error), parent=window
                )
                return
            opening_var.set(money(opening))
            active_category = None
            active_dates = None
            active_all_names = False
            editing_id = None
            refresh()

        def select_name(_event: tk.Event | None = None) -> None:
            selection = name_list.curselection()
            if selection:
                load_name(name_list.get(selection[0]))

        name_list.bind("<<ListboxSelect>>", select_name)

        def update_tallied_control(_event: tk.Event | None = None) -> None:
            selection = tree.selection()
            row = rows_by_id.get(int(selection[0])) if selection else None
            tallied_var.set(bool(row["tallied"]) if row else False)

        tree.bind("<<TreeviewSelect>>", update_tallied_control)
        previous_button = ttk.Button(header, text="Add Previous Balance")
        previous_button.grid(row=1, column=5, sticky="e", padx=4, pady=(4, 0))

        form = tk.Frame(window, bg=COLORS["panel"], padx=5, pady=4)
        form.pack(fill="x", padx=8, pady=(3, 8))

        def add_form_field(
            label: str, variable: tk.StringVar, column: int, width: int = 12
        ) -> ttk.Entry:
            ttk.Label(form, text=label).grid(
                row=0, column=column, sticky="w", padx=3, pady=(0, 2)
            )
            entry = ttk.Entry(form, textvariable=variable, width=width)
            entry.grid(row=1, column=column, sticky="ew", padx=3)
            return entry

        add_form_field("Balance", balance_var, 0, 9)
        ttk.Label(form, text="Name").grid(row=0, column=1, sticky="w", padx=3, pady=(0, 2))
        form_name_combo = ttk.Combobox(
            form,
            textvariable=name_var,
            values=name_values,
            state="normal",
            width=16,
        )
        form_name_combo.grid(row=1, column=1, sticky="ew", padx=3)
        add_form_field("Amount", amount_var, 2, 9)
        add_form_field("Third Party", third_party_var, 3, 15)
        ttk.Label(form, text="Side").grid(row=0, column=4, sticky="w", padx=3, pady=(0, 2))
        ttk.Combobox(
            form,
            textvariable=side_var,
            values=("NAAM", "JAMA"),
            state="readonly",
            width=7,
        ).grid(row=1, column=4, sticky="ew", padx=3)
        add_form_field("CH", charge_var, 5, 7)
        add_form_field("Code", code_var, 6, 8)
        ttk.Label(form, text="Category").grid(row=0, column=7, sticky="w", padx=3, pady=(0, 2))
        ttk.Combobox(
            form,
            textvariable=category_var,
            values=("Regular", "Monday Final"),
            state="readonly",
            width=10,
        ).grid(row=1, column=7, sticky="ew", padx=3)
        ttk.Button(form, text="OK", command=lambda: save_transaction()).grid(
            row=1, column=8, sticky="ew", padx=3
        )
        ttk.Button(form, text="Close", command=window.destroy).grid(
            row=1, column=9, sticky="ew", padx=3
        )
        for column, weight in enumerate((1, 2, 1, 2, 1, 1, 1, 1, 1, 1)):
            form.grid_columnconfigure(column, weight=weight)

        actions = tk.Frame(window, bg=COLORS["background"])
        actions.pack(fill="x", padx=8, pady=4, before=form)
        ttk.Button(actions, text="Delete", command=lambda: delete_selected()).pack(
            side="left", padx=2
        )
        ttk.Button(actions, text="Modify", command=lambda: modify_selected()).pack(
            side="left", padx=2
        )
        ttk.Button(actions, text="Print", command=lambda: print_transactions()).pack(
            side="left", padx=2
        )
        ttk.Button(
            actions,
            text="Monday Final ALL",
            command=lambda: set_filter("monday_all"),
        ).pack(side="left", padx=2)
        ttk.Button(
            actions,
            text="Monday Final",
            command=lambda: set_filter("monday"),
        ).pack(side="left", padx=2)
        ttk.Button(
            actions,
            text="Last Week Records",
            command=lambda: set_filter("last_week"),
        ).pack(side="left", padx=2)
        ttk.Checkbutton(
            actions,
            text="Tallied",
            variable=tallied_var,
            command=lambda: toggle_tallied(),
        ).pack(side="left", padx=6)
        ttk.Button(actions, text="+", command=lambda: set_filter("all")).pack(
            side="left", padx=2
        )

        def clear_form() -> None:
            nonlocal editing_id
            editing_id = None
            amount_var.set("")
            balance_var.set("")
            charge_var.set("0")
            code_var.set("")
            third_party_var.set("")
            category_var.set("Regular")

        def modify_selected() -> None:
            nonlocal editing_id
            selection = tree.selection()
            row = rows_by_id.get(int(selection[0])) if selection else None
            if row is None:
                messagebox.showinfo(
                    "Select a record", "Choose a record to modify.", parent=window
                )
                return
            editing_id = int(row["id"])
            date_var.set(row["entry_date"])
            name_var.set(row["name"])
            side_var.set(row["side"])
            amount_var.set(str(row["amount"]))
            balance_var.set(str(row["balance"]))
            charge_var.set(str(row["charge"]))
            code_var.set(row["code"])
            third_party_var.set(row["third_party"])
            category_var.set(row["category"])

        def save_transaction() -> None:
            nonlocal editing_id
            if not name_var.get().strip():
                messagebox.showerror(
                    "Name required", "Choose or enter a settlement name.", parent=window
                )
                return
            if not persist_opening_balance():
                return
            try:
                datetime.strptime(date_var.get().strip(), "%Y-%m-%d")
                amount = float(amount_var.get().replace(",", ""))
                balance = float(balance_var.get().replace(",", ""))
                charge = float(charge_var.get().replace(",", "") or "0")
                DB.save_settling_transaction(
                    editing_id,
                    {
                        "entry_date": date_var.get().strip(),
                        "name": name_var.get().strip(),
                        "side": side_var.get(),
                        "amount": amount,
                        "balance": balance,
                        "charge": charge,
                        "code": code_var.get(),
                        "third_party": third_party_var.get(),
                        "category": category_var.get(),
                    },
                )
            except ValueError as error:
                messagebox.showerror(
                    "Invalid settlement entry",
                    f"Enter a valid date and numeric amount, balance, and CH.\n{error}",
                    parent=window,
                )
                return
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Could not save settlement", str(error), parent=window
                )
                return
            name = name_var.get().strip()
            if name not in name_values:
                name_values.append(name)
                name_list.insert(tk.END, name)
                form_name_combo.configure(values=name_values)
            selected_id = editing_id
            clear_form()
            refresh(selected_id)

        def delete_selected() -> None:
            selection = tree.selection()
            if not selection:
                messagebox.showinfo(
                    "Select a record", "Choose a record to delete.", parent=window
                )
                return
            transaction_id = int(selection[0])
            if not messagebox.askyesno(
                "Delete settlement",
                "Delete the selected settlement record?",
                parent=window,
            ):
                return
            try:
                DB.delete_settling_transaction(transaction_id)
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Could not delete settlement", str(error), parent=window
                )
                return
            clear_form()
            refresh()

        def print_transactions() -> None:
            headers, rows = self.report_tree_rows(tree)
            try:
                self.print_report_rows(
                    "Settling Transaction", headers, rows, window
                )
            except (OSError, RuntimeError) as error:
                messagebox.showerror(
                    "Print preview failed", str(error), parent=window
                )

        def toggle_tallied() -> None:
            selection = tree.selection()
            if not selection:
                tallied_var.set(False)
                messagebox.showinfo(
                    "Select a record",
                    "Choose a record to change its tallied status.",
                    parent=window,
                )
                return
            transaction_id = int(selection[0])
            try:
                DB.set_settling_tallied(transaction_id, tallied_var.get())
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Could not update tallied status", str(error), parent=window
                )
                return
            refresh(transaction_id)

        def set_filter(filter_name: str) -> None:
            nonlocal active_category, active_dates, active_all_names
            active_category = None
            active_dates = None
            active_all_names = False
            if filter_name == "monday_all":
                active_category = "Monday Final"
                active_all_names = True
            elif filter_name == "monday":
                active_category = "Monday Final"
            elif filter_name == "last_week":
                today = date.today()
                last_monday = today - timedelta(days=today.weekday() + 7)
                last_sunday = last_monday + timedelta(days=6)
                active_dates = (last_monday.isoformat(), last_sunday.isoformat())
            elif filter_name != "all":
                return
            refresh()

        def add_previous_balance() -> None:
            name = name_var.get().strip()
            if not name:
                messagebox.showinfo(
                    "Select a name", "Choose or enter a name first.", parent=window
                )
                return
            try:
                previous = DB.list_settling_transactions(name=name)
                value = (
                    float(previous[0]["balance"])
                    if previous
                    else DB.get_settling_opening_balance(name)
                )
                opening_var.set(money(value))
                persist_opening_balance()
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Could not load previous balance", str(error), parent=window
                )

        previous_button.configure(command=add_previous_balance)
        form_name_combo.bind("<<ComboboxSelected>>", lambda _event: load_name(name_var.get()))
        opening_entry.bind("<FocusOut>", lambda _event: persist_opening_balance())
        if name_values:
            name_list.selection_set(0)
            load_name(name_values[0])
        else:
            refresh()

    def open_settling_report(self) -> None:
        window = self.report_window("Settling Report", "820x620")
        controls = tk.Frame(window, bg=COLORS["background"], padx=8, pady=7)
        controls.pack(fill="x")
        date_var = tk.StringVar(value=date.today().isoformat())
        ttk.Label(controls, text="Date").pack(side="left", padx=4)
        date_entry = ttk.Entry(controls, textvariable=date_var, width=15)
        date_entry.pack(side="left", padx=4)
        stamp_var = tk.StringVar()
        ttk.Label(controls, textvariable=stamp_var).pack(side="right", padx=8)
        tables = tk.Frame(window, bg=COLORS["background"])
        tables.pack(fill="both", expand=True, padx=8, pady=4)
        tables.grid_columnconfigure(0, weight=1)
        tables.grid_columnconfigure(1, weight=1)
        tables.grid_rowconfigure(0, weight=1)
        naam_frame = tk.LabelFrame(
            tables, text="NAAM", bg=COLORS["panel"], fg=COLORS["text"]
        )
        jama_frame = tk.LabelFrame(
            tables, text="JAMA", bg=COLORS["panel"], fg=COLORS["text"]
        )
        naam_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        jama_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        columns = (("name", "NAME", 200), ("amount", "AMOUNT", 120))
        naam_tree = self.make_tree(naam_frame, columns, height=17)
        jama_tree = self.make_tree(jama_frame, columns, height=17)
        summary = tk.Frame(window, bg=COLORS["panel"], padx=8, pady=6)
        summary.pack(fill="x", padx=8, pady=4)
        naam_total_var = tk.StringVar(value="NAAM Total: 0.00")
        jama_total_var = tk.StringVar(value="JAMA Total: 0.00")
        ttk.Label(summary, textvariable=naam_total_var).pack(side="left", padx=8)
        ttk.Label(summary, textvariable=jama_total_var).pack(side="left", padx=18)
        ttk.Label(summary, text="Final Total: Not calculated").pack(
            side="right", padx=8
        )

        def report_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            try:
                datetime.strptime(date_var.get().strip(), "%Y-%m-%d")
            except ValueError as error:
                raise ValueError("Enter a date as YYYY-MM-DD.") from error
            records = DB.list_settling_transactions(
                start_date=date_var.get().strip(),
                end_date=date_var.get().strip(),
            )
            grouped: list[dict[str, float]] = [{}, {}]
            for record in records:
                index = 0 if record["side"] == "NAAM" else 1
                group = grouped[index]
                name = str(record["name"])
                group[name] = group.get(name, 0.0) + float(record["amount"])
            return (
                [{"name": name, "amount": amount} for name, amount in grouped[0].items()],
                [{"name": name, "amount": amount} for name, amount in grouped[1].items()],
            )

        def refresh() -> None:
            try:
                naam_rows, jama_rows = report_rows()
            except ValueError as error:
                messagebox.showerror("Invalid report date", str(error), parent=window)
                return
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Could not load settling report", str(error), parent=window
                )
                return
            for tree, rows in ((naam_tree, naam_rows), (jama_tree, jama_rows)):
                tree.delete(*tree.get_children())
                for row in sorted(rows, key=lambda item: item["name"].casefold()):
                    tree.insert(
                        "", "end", values=(row["name"], money(row["amount"]))
                    )
            naam_total_var.set(
                f"NAAM Total: {money(sum(row['amount'] for row in naam_rows))}"
            )
            jama_total_var.set(
                f"JAMA Total: {money(sum(row['amount'] for row in jama_rows))}"
            )
            stamp_var.set(f"Date :: {date_var.get().strip()}")

        actions = tk.Frame(window, bg=COLORS["background"])
        actions.pack(pady=(4, 9))

        def print_report(mode: str) -> None:
            try:
                naam_rows, jama_rows = report_rows()
            except ValueError as error:
                messagebox.showerror("Invalid report date", str(error), parent=window)
                return
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Could not load settling report", str(error), parent=window
                )
                return
            if mode == "4 row":
                headers = ["NAAM", "AMOUNT", "JAMA", "AMOUNT"]
                row_count = max(len(naam_rows), len(jama_rows))
                rows = [
                    [
                        naam_rows[index]["name"] if index < len(naam_rows) else "",
                        money(naam_rows[index]["amount"])
                        if index < len(naam_rows)
                        else "",
                        jama_rows[index]["name"] if index < len(jama_rows) else "",
                        money(jama_rows[index]["amount"])
                        if index < len(jama_rows)
                        else "",
                    ]
                    for index in range(row_count)
                ]
            elif mode == "2 row":
                headers = ["SIDE", "NAME", "AMOUNT"]
                rows = [
                    [side, row["name"], money(row["amount"])]
                    for side, source in (("NAAM", naam_rows), ("JAMA", jama_rows))
                    for row in source
                ]
            else:
                try:
                    users = DB.list_users()
                except sqlite3.Error as error:
                    messagebox.showerror(
                        "Could not load State/Ref values", str(error), parent=window
                    )
                    return
                states_by_name = {
                    self.user_label(user): str(user["state_ref"])
                    for user in users
                }
                headers = ["STATE/REF", "SIDE", "NAME", "AMOUNT"]
                rows = [
                    [
                        states_by_name.get(row["name"], ""),
                        side,
                        row["name"],
                        money(row["amount"]),
                    ]
                    for side, source in (("NAAM", naam_rows), ("JAMA", jama_rows))
                    for row in source
                ]
                rows.sort(
                    key=lambda row: (
                        row[0].casefold(),
                        row[2].casefold(),
                        row[1],
                    )
                )
            try:
                self.print_report_rows(
                    f"Settling Report - {mode.title()}",
                    headers,
                    rows,
                    window,
                )
            except (OSError, RuntimeError) as error:
                messagebox.showerror(
                    "Print preview failed", str(error), parent=window
                )

        ttk.Button(
            actions,
            text="4 Row Print",
            command=lambda: print_report("4 row"),
        ).pack(side="left", padx=4)
        ttk.Button(
            actions,
            text="2 Row Print",
            command=lambda: print_report("2 row"),
        ).pack(side="left", padx=4)
        ttk.Button(
            actions,
            text="Print Statewise",
            command=lambda: print_report("statewise"),
        ).pack(side="left", padx=4)
        ttk.Button(actions, text="Close", command=window.destroy).pack(
            side="left", padx=4
        )
        ttk.Button(controls, text="Refresh", command=refresh).pack(
            side="left", padx=4
        )
        date_entry.bind("<Return>", lambda _event: refresh())
        refresh()

    def open_commission_report(self) -> None:
        try:
            users = DB.list_users()
        except sqlite3.Error as error:
            messagebox.showerror("Could not load users", str(error), parent=self)
            return
        window = self.report_window("Commission Report", "980x600")
        body = tk.Frame(window, bg=COLORS["background"])
        body.pack(fill="both", expand=True, padx=8, pady=8)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=3)
        body.grid_rowconfigure(0, weight=1)
        selection_frame = tk.Frame(body, bg=COLORS["panel"])
        selection_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        user_list = tk.Listbox(
            selection_frame,
            selectmode=tk.EXTENDED,
            exportselection=False,
            bg="#808080",
            selectbackground="#ffff80",
            selectforeground=COLORS["text"],
        )
        user_list.pack(fill="both", expand=True)
        for user in users:
            user_list.insert(tk.END, self.user_label(user))
        report_frame = tk.Frame(body, bg=COLORS["panel"])
        report_frame.grid(row=0, column=1, sticky="nsew")
        tree = self.make_tree(
            report_frame,
            (
                ("name", "NAME", 145),
                ("state", "STATE/REF", 100),
                ("match_commission", "MATCH COMM", 100),
                ("session_commission", "SESSION COMM", 100),
                ("match_patti", "MATCH PATTI", 95),
                ("session_patti", "SESSION PATTI", 95),
                ("meter_patti", "METER PATTI", 95),
            ),
            height=19,
        )
        select_all_var = tk.BooleanVar()
        actions = tk.Frame(window, bg=COLORS["background"])
        actions.pack(fill="x", padx=10, pady=(0, 9))

        def set_all_users() -> None:
            user_list.selection_clear(0, tk.END)
            if select_all_var.get():
                user_list.selection_set(0, tk.END)

        ttk.Checkbutton(
            actions,
            text="Select All",
            variable=select_all_var,
            command=set_all_users,
        ).pack(side="left", padx=5)

        def show_selected() -> None:
            selection = user_list.curselection()
            tree.delete(*tree.get_children())
            for index in selection:
                user = users[index]
                tree.insert(
                    "",
                    "end",
                    values=(
                        user["name"],
                        user["state_ref"],
                        money(float(user["match_commission"])),
                        money(float(user["session_commission"])),
                        money(float(user["patti_match"])),
                        money(float(user["patti_session"])),
                        money(float(user["patti_meter"])),
                    ),
                )

        ttk.Button(
            actions, text="Show", style="Accent.TButton", command=show_selected
        ).pack(side="left", padx=5)
        ttk.Button(actions, text="Close", command=window.destroy).pack(
            side="left", padx=5
        )
    def page_header(self, title: str, subtitle: str) -> tk.Frame:
        header = tk.Frame(self.content, bg=COLORS["background"])
        header.pack(fill="x", padx=8, pady=(7, 5))
        title_bar = tk.Frame(
            header,
            bg="#d6e5f5",
            relief="raised",
            bd=1,
        )
        title_bar.pack(fill="x")
        tk.Label(
            title_bar,
            text=title,
            bg="#d6e5f5",
            fg="#263d57",
            font=("Tahoma", 9, "bold"),
            padx=7,
            pady=3,
        ).pack(anchor="w")
        tk.Label(
            header,
            text=subtitle,
            bg=COLORS["background"],
            fg=COLORS["text"],
            font=("Tahoma", 8),
            padx=4,
            pady=3,
        ).pack(anchor="w")
        return header

    def show_page(self, name: str) -> None:
        if name != "Entries":
            self.unbind("<F8>")
        for widget in self.content.winfo_children():
            widget.destroy()
        page = {
            "Workspace": self.build_workspace,
            "Dashboard": self.build_dashboard,
            "Matches": self.build_matches,
            "Users": self.build_users,
            "Entries": self.build_entries,
            "Results": self.build_results,
            "Reports": self.build_reports,
        }[name]
        self.current_page = name
        page()

    def build_workspace(self) -> None:
        self.content.configure(bg=COLORS["background"])

    def open_report_mode(self, mode: str) -> None:
        handlers = {
            "Connect Report": self.open_connect_report,
            "Individual Report": self.open_individual_report,
            "Session Individual Report": self.open_session_individual_report,
            "User Account": self.open_user_account_report,
        }
        handler = handlers.get(mode)
        if handler is None:
            raise ValueError(f"Unknown report type: {mode}")
        handler()

    @staticmethod
    def make_tree(
        parent: tk.Widget,
        columns: tuple[tuple[str, str, int], ...],
        height: int = 12,
        selectmode: str = "browse",
    ) -> ttk.Treeview:
        tree = ttk.Treeview(
            parent,
            columns=tuple(column[0] for column in columns),
            show="headings",
            height=height,
            selectmode=selectmode,
        )
        for key, title, width in columns:
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=60, anchor="w")
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        return tree

    def show_logs(self, entity: str, entity_id: int | None = None) -> None:
        logs = DB.list_logs(entity, entity_id)
        window = tk.Toplevel(self)
        window.title(f"{entity.title()} Log")
        window.geometry("800x420")
        window.configure(bg=COLORS["background"])
        frame = tk.Frame(window, bg=COLORS["panel"])
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        tree = self.make_tree(
            frame,
            (
                ("time", "AT TIME", 160),
                ("action", "ACTION", 120),
                ("id", "RECORD", 90),
                ("details", "DETAILS", 420),
            ),
            height=14,
        )
        for row in logs:
            details = json.dumps(
                json.loads(row["details"]), ensure_ascii=False
            )
            tree.insert(
                "",
                "end",
                values=(row["created_at"], row["action"], row["entity_id"], details),
            )
        ttk.Button(window, text="Close", command=window.destroy).pack(pady=(0, 8))

    @staticmethod
    def print_tree(tree: ttk.Treeview, title: str) -> None:
        headers = [tree.heading(column, "text") for column in tree["columns"]]
        rows = [list(tree.item(item, "values")) for item in tree.get_children()]
        open_print_preview(title, headers, rows)

    def build_dashboard(self) -> None:
        self.page_header("Dashboard", "Overview of matches, users, and today's entries")
        metrics = DB.dashboard_metrics()
        summary = tk.LabelFrame(
            self.content,
            text="Today's summary",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Tahoma", 8, "bold"),
            padx=6,
            pady=6,
            relief="groove",
        )
        summary.pack(fill="x", padx=8, pady=(0, 6))
        card_data = (
            ("OPEN MATCHES", str(metrics["open_matches"])),
            ("USERS", str(metrics["users"])),
            ("ENTRIES TODAY", str(metrics["today_entries"])),
            ("AMOUNT TODAY", money(float(metrics["today_amount"]))),
        )
        for index, (caption, value) in enumerate(card_data):
            cell = tk.Frame(summary, bg=COLORS["panel"], padx=4)
            cell.grid(row=0, column=index, sticky="ew")
            summary.grid_columnconfigure(index, weight=1)
            tk.Label(
                cell,
                text=caption,
                bg=COLORS["panel"],
                fg=COLORS["text"],
                font=("Tahoma", 8, "bold"),
            ).pack(anchor="w", pady=(0, 3))
            tk.Label(
                cell,
                text=value,
                bg="#e8e8e8",
                fg=COLORS["text"],
                font=("Tahoma", 10, "bold"),
                relief="sunken",
                bd=1,
                padx=5,
                pady=3,
            ).pack(fill="x")

        recent = tk.LabelFrame(
            self.content,
            text="Recent entries",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Tahoma", 8, "bold"),
            padx=5,
            pady=5,
            relief="groove",
        )
        recent.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        table_frame = tk.Frame(recent, bg=COLORS["panel"])
        table_frame.pack(fill="both", expand=True)
        tree = self.make_tree(
            table_frame,
            (
                ("date", "DATE", 105),
                ("match", "MATCH", 190),
                ("user", "NAME", 170),
                ("type", "TYPE", 100),
                ("team", "TEAM", 120),
                ("rate", "RATE", 100),
                ("amount", "AMOUNT", 120),
            ),
            height=15,
        )
        for row in DB.list_entries()[:15]:
            tree.insert(
                "",
                "end",
                values=(
                    row["entry_date"],
                    f'{row["match_code"]} - {row["match_comment"]}',
                    row["user_name"],
                    row["entry_type"],
                    row["team"],
                    money(row["rate"]),
                    money(row["amount"]),
                ),
            )

    def build_matches(self) -> None:
        self.page_header(
            "Matches", "Create match records and manage their participating teams"
        )
        container = tk.Frame(self.content, bg=COLORS["background"])
        container.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        form = tk.LabelFrame(
            container,
            text="Match details",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            padx=14,
            pady=12,
            font=("Tahoma", 9, "bold"),
        )
        form.pack(fill="x", pady=(0, 14))
        self.match_id: int | None = None
        self.match_code_var = tk.StringVar(value=str(DB.next_match_code()))
        self.match_date_var = tk.StringVar(value=date.today().isoformat())
        self.match_comment_var = tk.StringVar()
        self.match_teams_var = tk.StringVar()
        fields = (
            ("Code", self.match_code_var, 10),
            ("Date (YYYY-MM-DD)", self.match_date_var, 16),
            ("Comment", self.match_comment_var, 30),
            ("Teams (comma separated)", self.match_teams_var, 36),
        )
        for column, (label, variable, width) in enumerate(fields):
            field = tk.Frame(form, bg=COLORS["panel"])
            field.grid(row=0, column=column, sticky="w", padx=(0, 12))
            tk.Label(
                field, text=label, bg=COLORS["panel"], fg=COLORS["muted"]
            ).pack(anchor="w", pady=(0, 5))
            ttk.Entry(field, textvariable=variable, width=width).pack(anchor="w")
        button_row = tk.Frame(form, bg=COLORS["panel"])
        button_row.grid(row=1, column=0, columnspan=4, sticky="w", pady=(13, 0))
        self.match_save_button = ttk.Button(
            button_row, text="Save match", style="Accent.TButton", command=self.save_match
        )
        self.match_save_button.pack(side="left")
        ttk.Button(button_row, text="Clear", command=self.clear_match_form).pack(side="left", padx=7)
        ttk.Button(button_row, text="Delete selected", command=self.delete_matches).pack(side="left")
        ttk.Button(button_row, text="Log", command=lambda: self.show_logs("match", self.match_id)).pack(side="left", padx=7)

        table = tk.Frame(container, bg=COLORS["panel"])
        table.pack(fill="both", expand=True)
        self.matches_tree = self.make_tree(
            table,
            (
                ("code", "CODE", 75),
                ("date", "DATE", 120),
                ("comment", "COMMENT", 230),
                ("teams", "TEAMS", 340),
                ("result", "RESULT", 115),
                ("winner", "WON", 130),
            ),
            selectmode="extended",
        )
        self.matches_tree.bind("<<TreeviewSelect>>", self.on_match_selected)
        self.matches_tree.bind("<Double-1>", self.open_team_entry_window)
        self.refresh_matches()

    def refresh_matches(self) -> None:
        self.match_rows = DB.list_matches()
        if not hasattr(self, "matches_tree"):
            return
        self.matches_tree.delete(*self.matches_tree.get_children())
        for row in self.match_rows:
            self.matches_tree.insert(
                "", "end", iid=str(row["id"]),
                values=(
                    row["code"],
                    row["match_date"],
                    row["comment"],
                    row["teams"],
                    row["result"],
                    row["winner"],
                ),
            )

    def on_match_selected(self, _event: tk.Event) -> None:
        selection = self.matches_tree.selection()
        if not selection:
            return
        match_id = int(selection[0])
        row = next((item for item in self.match_rows if item["id"] == match_id), None)
        if row is None:
            return
        self.match_id = match_id
        if hasattr(self, "match_save_button"):
            self.match_save_button.configure(text="Modify match")
        self.match_code_var.set(str(row["code"]))
        self.match_date_var.set(row["match_date"])
        self.match_comment_var.set(row["comment"])
        self.match_teams_var.set(row["teams"])

    def clear_match_form(self) -> None:
        self.match_id = None
        if hasattr(self, "match_save_button"):
            self.match_save_button.configure(text="Save match")
        self.match_code_var.set(str(DB.next_match_code()))
        self.match_date_var.set(date.today().isoformat())
        self.match_comment_var.set("")
        self.match_teams_var.set("")
        if self.matches_tree.selection():
            self.matches_tree.selection_remove(self.matches_tree.selection())

    def save_match(self) -> None:
        try:
            code = int(self.match_code_var.get().strip())
            date.fromisoformat(self.match_date_var.get().strip())
            comment = self.match_comment_var.get().strip()
            teams = [team.strip() for team in self.match_teams_var.get().split(",") if team.strip()]
            if not comment:
                raise ValueError("Enter a match comment.")
            if len(teams) < 2:
                raise ValueError("Enter at least two teams, separated by commas.")
            if len(teams) > 12:
                raise ValueError("A match can have at most 12 teams.")
            DB.save_match(
                self.match_id,
                code,
                self.match_date_var.get().strip(),
                comment,
                ", ".join(teams),
            )
        except ValueError as error:
            messagebox.showerror("Check match details", str(error), parent=self)
            return
        except sqlite3.IntegrityError as error:
            messagebox.showerror("Could not save match", str(error), parent=self)
            return
        self.refresh_matches()
        self.clear_match_form()

    def delete_match(self) -> None:
        if self.match_id is None:
            messagebox.showinfo("Select a match", "Choose a match to delete.", parent=self)
            return
        if not messagebox.askyesno(
            "Delete match",
            "Delete this match? Matches with saved entries cannot be deleted.",
            parent=self,
        ):
            return
        try:
            DB.delete_match(self.match_id)
        except sqlite3.IntegrityError:
            messagebox.showerror(
                "Match has entries",
                "This match has saved entries. Delete or retain those records before removing the match.",
                parent=self,
            )
            return
        self.refresh_matches()
        self.clear_match_form()

    def delete_matches(self) -> None:
        selected = self.matches_tree.selection()
        if not selected:
            messagebox.showinfo("Select matches", "Choose one or more matches to delete.", parent=self)
            return
        if not messagebox.askyesno(
            "Delete matches",
            f"Delete {len(selected)} selected match(es)? Matches with entries cannot be deleted.",
            parent=self,
        ):
            return
        try:
            DB.delete_matches([int(item) for item in selected])
        except sqlite3.IntegrityError:
            messagebox.showerror(
                "Some matches have entries",
                "No selected matches were deleted because at least one contains saved entries.",
                parent=self,
            )
            return
        self.refresh_matches()
        self.clear_match_form()

    def open_team_entry_window(self, event: tk.Event) -> None:
        clicked_item = self.matches_tree.identify_row(event.y)
        if not clicked_item:
            return
        self.matches_tree.selection_set(clicked_item)
        initial_row = next(
            (row for row in self.match_rows if int(row["id"]) == int(clicked_item)),
            None,
        )
        if initial_row is None:
            return

        window = tk.Toplevel(self)
        window.title("Team Entry")
        window.geometry("1080x620")
        window.minsize(860, 560)
        window.configure(bg=COLORS["background"])
        window.transient(self)

        column_keys = ("code", "date", "comment") + tuple(
            f"team_{index}" for index in range(1, 13)
        )
        style = ttk.Style(window)
        style.configure(
            "TeamEntry.Treeview",
            background="#808080",
            fieldbackground="#808080",
            foreground=COLORS["text"],
            rowheight=22,
            font=("Tahoma", 8),
        )
        style.map(
            "TeamEntry.Treeview",
            background=[("selected", "#f5a6e8")],
            foreground=[("selected", COLORS["text"])],
        )
        style.configure(
            "TeamEntry.Treeview.Heading",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            font=("Tahoma", 8, "bold"),
            padding=(3, 2),
        )

        list_frame = tk.Frame(window, bg=COLORS["panel"])
        list_frame.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        popup_tree = ttk.Treeview(
            list_frame,
            columns=column_keys,
            show="headings",
            height=8,
            selectmode="extended",
            style="TeamEntry.Treeview",
        )
        column_labels = ("CODE", "DATE", "COMMENT") + tuple(
            f"TEAM{index}" for index in range(1, 13)
        )
        column_widths = (70, 105, 190) + (74,) * 12
        for key, label, width in zip(column_keys, column_labels, column_widths):
            popup_tree.heading(key, text=label)
            popup_tree.column(key, width=width, minwidth=55, anchor="w")
        vertical_scroll = ttk.Scrollbar(
            list_frame, orient="vertical", command=popup_tree.yview
        )
        horizontal_scroll = ttk.Scrollbar(
            list_frame, orient="horizontal", command=popup_tree.xview
        )
        popup_tree.configure(
            yscrollcommand=vertical_scroll.set,
            xscrollcommand=horizontal_scroll.set,
        )
        popup_tree.grid(row=0, column=0, sticky="nsew")
        vertical_scroll.grid(row=0, column=1, sticky="ns")
        horizontal_scroll.grid(row=1, column=0, sticky="ew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        form = tk.LabelFrame(
            window,
            text="Team Details",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Tahoma", 8, "bold"),
            padx=7,
            pady=5,
        )
        form.pack(fill="x", padx=8, pady=4)
        popup_id: int | None = None
        code_var = tk.StringVar()
        date_var = tk.StringVar()
        comment_var = tk.StringVar()
        team_vars = [tk.StringVar() for _ in range(12)]
        row_by_id: dict[int, sqlite3.Row] = {}

        top_fields = tk.Frame(form, bg=COLORS["panel"])
        top_fields.pack(fill="x", pady=(0, 5))
        for column, (label, variable, width) in enumerate(
            (
                ("Code", code_var, 9),
                ("Date (YYYY-MM-DD)", date_var, 15),
                ("Comment", comment_var, 38),
            )
        ):
            field = tk.Frame(top_fields, bg=COLORS["panel"])
            field.grid(row=0, column=column, sticky="w", padx=(0, 8))
            tk.Label(
                field, text=label, bg=COLORS["panel"], fg=COLORS["text"]
            ).pack(anchor="w")
            ttk.Entry(field, textvariable=variable, width=width).pack(anchor="w")
        top_fields.grid_columnconfigure(2, weight=1)

        teams_frame = tk.Frame(form, bg=COLORS["panel"])
        teams_frame.pack(fill="x")
        for index, variable in enumerate(team_vars):
            row_index, column = divmod(index, 3)
            field = tk.Frame(teams_frame, bg=COLORS["panel"])
            field.grid(
                row=row_index,
                column=column,
                sticky="ew",
                padx=(0, 8),
                pady=2,
            )
            tk.Label(
                field,
                text=f"Team_{index + 1}",
                bg=COLORS["panel"],
                fg=COLORS["text"],
            ).pack(anchor="w")
            ttk.Entry(field, textvariable=variable).pack(fill="x")
            teams_frame.grid_columnconfigure(column, weight=1)

        def clear_form() -> None:
            nonlocal popup_id
            popup_id = None
            code_var.set(str(DB.next_match_code()))
            date_var.set(date.today().isoformat())
            comment_var.set("")
            for variable in team_vars:
                variable.set("")
            selection = popup_tree.selection()
            if selection:
                popup_tree.selection_remove(*selection)

        def load_match(row: sqlite3.Row) -> None:
            nonlocal popup_id
            popup_id = int(row["id"])
            code_var.set(str(row["code"]))
            date_var.set(str(row["match_date"]))
            comment_var.set(str(row["comment"]))
            teams = [team.strip() for team in str(row["teams"]).split(",")]
            for index, variable in enumerate(team_vars):
                variable.set(teams[index] if index < len(teams) else "")

        def refresh_popup(select_id: int | None = None) -> None:
            nonlocal row_by_id
            rows = DB.list_matches()
            row_by_id = {int(row["id"]): row for row in rows}
            popup_tree.delete(*popup_tree.get_children())
            for row in rows:
                teams = [team.strip() for team in str(row["teams"]).split(",")]
                popup_tree.insert(
                    "",
                    "end",
                    iid=str(row["id"]),
                    values=(
                        row["code"],
                        row["match_date"],
                        row["comment"],
                        *(teams[index] if index < len(teams) else "" for index in range(12)),
                    ),
                )
            if select_id is not None and select_id in row_by_id:
                popup_tree.selection_set(str(select_id))
                popup_tree.focus(str(select_id))
                load_match(row_by_id[select_id])

        def on_popup_select(_event: tk.Event | None = None) -> None:
            selection = popup_tree.selection()
            if selection:
                row = row_by_id.get(int(selection[0]))
                if row is not None:
                    load_match(row)

        def save_popup_match(match_id: int | None) -> bool:
            try:
                code = int(code_var.get().strip())
                match_date = date_var.get().strip()
                date.fromisoformat(match_date)
                comment = comment_var.get().strip()
                teams = [variable.get().strip() for variable in team_vars]
                teams = [team for team in teams if team]
                if not comment:
                    raise ValueError("Enter a match comment.")
                if len(teams) < 2:
                    raise ValueError("Enter at least two teams.")
                DB.save_match(match_id, code, match_date, comment, ", ".join(teams))
            except ValueError as error:
                messagebox.showerror("Check team details", str(error), parent=window)
                return False
            except sqlite3.IntegrityError as error:
                messagebox.showerror("Could not save match", str(error), parent=window)
                return False
            return True

        def save_new() -> None:
            if save_popup_match(None):
                self.refresh_matches()
                refresh_popup()
                clear_form()

        def modify_selected() -> None:
            if popup_id is None:
                messagebox.showinfo(
                    "Select a match", "Choose a match to modify.", parent=window
                )
                return
            match_id = popup_id
            if save_popup_match(match_id):
                self.refresh_matches()
                refresh_popup(match_id)

        def delete_selected() -> None:
            if popup_id is None:
                messagebox.showinfo(
                    "Select a match", "Choose a match to delete.", parent=window
                )
                return
            if not messagebox.askyesno(
                "Delete match",
                "Delete this match? Matches with saved entries cannot be deleted.",
                parent=window,
            ):
                return
            try:
                DB.delete_match(popup_id)
            except sqlite3.IntegrityError:
                messagebox.showerror(
                    "Match has entries",
                    "This match has saved entries and cannot be deleted.",
                    parent=window,
                )
                return
            self.refresh_matches()
            refresh_popup()
            clear_form()

        def delete_multiple() -> None:
            selected = popup_tree.selection()
            if not selected:
                messagebox.showinfo(
                    "Select matches", "Choose one or more matches to delete.", parent=window
                )
                return
            if not messagebox.askyesno(
                "Delete matches",
                f"Delete {len(selected)} selected match(es)? Matches with saved entries cannot be deleted.",
                parent=window,
            ):
                return
            try:
                DB.delete_matches([int(item) for item in selected])
            except sqlite3.IntegrityError:
                messagebox.showerror(
                    "Some matches have entries",
                    "No selected matches were deleted because at least one contains saved entries.",
                    parent=window,
                )
                return
            self.refresh_matches()
            refresh_popup()
            clear_form()

        popup_tree.bind("<<TreeviewSelect>>", on_popup_select)

        actions = tk.Frame(window, bg=COLORS["background"])
        actions.pack(fill="x", padx=8, pady=(3, 8))
        ttk.Button(actions, text="Save", command=save_new).pack(side="left", padx=2)
        ttk.Button(actions, text="Delete", command=delete_selected).pack(
            side="left", padx=2
        )
        ttk.Button(actions, text="Modify", command=modify_selected).pack(
            side="left", padx=2
        )
        ttk.Button(
            actions,
            text="Print",
            command=lambda: self.print_tree(popup_tree, "Team Entry"),
        ).pack(side="left", padx=2)
        ttk.Button(actions, text="Close", command=window.destroy).pack(
            side="left", padx=2
        )
        ttk.Button(actions, text="Clear", command=clear_form).pack(
            side="left", padx=2
        )
        ttk.Button(actions, text="Multiple Delete", command=delete_multiple).pack(
            side="left", padx=2
        )
        ttk.Button(
            actions,
            text="Log",
            command=lambda: self.show_logs("match", popup_id),
        ).pack(side="left", padx=2)

        refresh_popup(int(initial_row["id"]))

    def refresh_state_ref_choices(self) -> None:
        combo = getattr(self, "user_state_ref_combo", None)
        if combo is None or not combo.winfo_exists():
            return
        combo.configure(values=[row["name"] for row in DB.list_state_refs()])

    def open_state_ref_window(self) -> None:
        window = tk.Toplevel(self)
        window.title("State")
        window.geometry("360x420")
        window.minsize(300, 320)
        window.configure(bg=COLORS["background"])
        window.transient(self)

        table = tk.Frame(window, bg=COLORS["panel"])
        table.pack(fill="both", expand=True, padx=8, pady=8)
        tree = self.make_tree(
            table,
            (("sl", "Sl", 55), ("name", "States", 230)),
            height=14,
            selectmode="extended",
        )

        def refresh() -> None:
            rows = DB.list_state_refs()
            tree.delete(*tree.get_children())
            for index, row in enumerate(rows, start=1):
                tree.insert(
                    "",
                    "end",
                    iid=str(row["id"]),
                    values=(index, row["name"]),
                )

        def delete_selected() -> None:
            selected = tree.selection()
            if not selected:
                messagebox.showinfo(
                    "Select State/Ref",
                    "Choose one or more State/Ref values to delete.",
                    parent=window,
                )
                return
            if not messagebox.askyesno(
                "Delete State/Ref",
                f"Delete {len(selected)} selected State/Ref value(s)?",
                parent=window,
            ):
                return
            try:
                DB.delete_state_refs([int(item) for item in selected])
                refresh()
                self.refresh_state_ref_choices()
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Could not delete State/Ref values", str(error), parent=window
                )

        def clear_values() -> None:
            rows = DB.list_state_refs()
            if not rows:
                return
            if not messagebox.askyesno(
                "Clear State/Ref",
                "Remove all reusable State/Ref choices? Values saved on users will remain unchanged.",
                parent=window,
            ):
                return
            try:
                DB.delete_state_refs([int(row["id"]) for row in rows])
                refresh()
                self.refresh_state_ref_choices()
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Could not clear State/Ref values", str(error), parent=window
                )

        actions = tk.Frame(window, bg=COLORS["background"])
        actions.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(actions, text="Delete", command=delete_selected).pack(
            side="left", padx=3
        )
        ttk.Button(actions, text="Close", command=window.destroy).pack(
            side="left", padx=3
        )
        ttk.Button(actions, text="Clear", command=clear_values).pack(
            side="left", padx=3
        )
        refresh()

    def build_users(self) -> None:
        self.page_header(
            "Users & references",
            "Maintain contact details, commission references, limits, and permissions",
        )
        container = tk.Frame(self.content, bg=COLORS["background"])
        container.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        actions = tk.Frame(container, bg=COLORS["background"])
        actions.pack(fill="x", pady=(0, 12))
        self.user_search_var = tk.StringVar()
        ttk.Label(actions, text="Search").pack(side="left", padx=(0, 5))
        search_entry = ttk.Entry(
            actions, textvariable=self.user_search_var, width=28
        )
        search_entry.pack(side="left", padx=(0, 8))
        self.user_search_var.trace_add("write", lambda *_args: self.refresh_users())
        ttk.Button(actions, text="Search", command=self.refresh_users).pack(
            side="left", padx=(0, 7)
        )
        ttk.Button(
            actions,
            text="Add user",
            style="Accent.TButton",
            command=lambda: self.open_user_form(None),
        ).pack(side="left", padx=2)
        ttk.Button(actions, text="Edit selected", command=self.edit_user).pack(
            side="left", padx=2
        )
        ttk.Button(actions, text="Delete selected", command=self.delete_users).pack(
            side="left", padx=2
        )
        ttk.Button(
            actions,
            text="Log",
            command=lambda: self.show_logs("user", self.selected_user_id()),
        ).pack(side="left", padx=2)

        table = tk.Frame(container, bg=COLORS["panel"])
        table.pack(fill="both", expand=True)
        self.users_tree = self.make_tree(
            table,
            (
                ("name", "NAME", 200),
                ("state", "STATE / REF", 150),
                ("phone", "TELEPHONE", 140),
                ("match", "MATCH COMMISSION", 150),
                ("session", "SESSION COMMISSION", 165),
                ("limit", "LIMIT", 110),
                ("patti", "PATTI M/S/M", 145),
            ),
            selectmode="extended",
        )
        self.users_tree.bind("<Double-1>", lambda _event: self.edit_user())
        search_entry.focus_set()
        self.refresh_users()

    def refresh_users(self) -> None:
        search = self.user_search_var.get() if hasattr(self, "user_search_var") else ""
        self.user_rows = DB.list_users(search)
        if not hasattr(self, "users_tree"):
            return
        self.users_tree.delete(*self.users_tree.get_children())
        for row in self.user_rows:
            self.users_tree.insert(
                "", "end", iid=str(row["id"]),
                values=(
                    row["name"],
                    row["state_ref"],
                    row["phone"],
                    row["match_commission"],
                    row["session_commission"],
                    f'{row["limit_mode"]} {money(row["limit_amount"])}'.strip(),
                    f'{row["patti_match"]}/{row["patti_session"]}/{row["patti_meter"]}',
                ),
            )

    def selected_user(self) -> sqlite3.Row | None:
        selection = self.users_tree.selection()
        if not selection:
            return None
        user_id = int(selection[0])
        return next((row for row in self.user_rows if row["id"] == user_id), None)

    def selected_user_id(self) -> int | None:
        row = self.selected_user()
        return None if row is None else int(row["id"])

    def edit_user(self) -> None:
        row = self.selected_user()
        if row is None:
            messagebox.showinfo("Select a user", "Choose a user to edit.", parent=self)
            return
        self.open_user_form(row)

    def delete_user(self) -> None:
        row = self.selected_user()
        if row is None:
            messagebox.showinfo("Select a user", "Choose a user to delete.", parent=self)
            return
        if not messagebox.askyesno(
            "Delete user",
            "Delete this user? Users with saved entries cannot be deleted.",
            parent=self,
        ):
            return
        try:
            DB.delete_user(int(row["id"]))
        except sqlite3.IntegrityError:
            messagebox.showerror(
                "User has entries",
                "This user has saved entries. Keep the user record so entry history remains intact.",
                parent=self,
            )
            return
        self.refresh_users()

    def delete_users(self) -> None:
        selected = self.users_tree.selection()
        if not selected:
            messagebox.showinfo("Select users", "Choose one or more users to delete.", parent=self)
            return
        if not messagebox.askyesno(
            "Delete users",
            f"Delete {len(selected)} selected user(s)? Users with entries cannot be deleted.",
            parent=self,
        ):
            return
        try:
            DB.delete_users([int(item) for item in selected])
        except sqlite3.IntegrityError:
            messagebox.showerror(
                "Some users have entries",
                "No selected users were deleted because at least one has saved entries.",
                parent=self,
            )
            return
        self.refresh_users()

    def open_user_form(self, row: sqlite3.Row | None) -> None:
        window = tk.Toplevel(self)
        window.title("Edit user" if row else "Add user")
        window.geometry("880x650")
        window.minsize(760, 580)
        window.configure(bg=COLORS["background"])
        window.transient(self)
        window.grab_set()

        canvas = tk.Canvas(window, bg=COLORS["background"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(window, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=COLORS["background"], padx=20, pady=16)
        inner.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        vars: dict[str, tk.StringVar] = {}
        bool_vars: dict[str, tk.BooleanVar] = {}
        self.user_state_ref_combo: ttk.Combobox | None = None
        state_ref_values = [item["name"] for item in DB.list_state_refs()]

        def section(title: str, fields: tuple[tuple[str, str], ...], columns: int = 2) -> None:
            frame = tk.LabelFrame(
                inner,
                text=title,
                bg=COLORS["panel"],
                fg=COLORS["text"],
                padx=12,
                pady=10,
                font=("Tahoma", 8, "bold"),
            )
            frame.pack(fill="x", pady=(0, 10))
            for index, (field, label) in enumerate(fields):
                position = index % columns
                row_index = index // columns
                cell = tk.Frame(frame, bg=COLORS["panel"])
                cell.grid(
                    row=row_index,
                    column=position,
                    sticky="ew",
                    padx=(0, 16),
                    pady=5,
                )
                tk.Label(
                    cell, text=label, bg=COLORS["panel"], fg=COLORS["muted"]
                ).pack(anchor="w", pady=(0, 3))
                vars[field] = tk.StringVar(
                    value="" if row is None else str(row[field] or "")
                )
                if field == "limit_mode":
                    ttk.Combobox(
                        cell,
                        textvariable=vars[field],
                        values=("", "Amount", "Match", "Session"),
                        state="readonly",
                        width=31,
                    ).pack(anchor="w")
                elif field == "state_ref":
                    self.user_state_ref_combo = ttk.Combobox(
                        cell,
                        textvariable=vars[field],
                        values=state_ref_values,
                        state="normal",
                        width=34,
                    )
                    self.user_state_ref_combo.pack(anchor="w")
                else:
                    ttk.Entry(cell, textvariable=vars[field], width=34).pack(anchor="w")
                frame.grid_columnconfigure(position, weight=1)

        section(
            "Basic details",
            (("name", "Name *"), ("state_ref", "State / reference"), ("phone", "Telephone no.")),
            3,
        )
        section(
            "Commission references",
            (
                ("match_comm_1", "Match Comm 1"),
                ("match_comm_2", "Match Comm 2"),
                ("session_comm_1", "Session Comm 1"),
                ("session_comm_2", "Session Comm 2"),
                ("match_patti_1", "Match Patti 1"),
                ("match_patti_2", "Match Patti 2"),
                ("session_patti_1", "Session Patti 1"),
                ("session_patti_2", "Session Patti 2"),
                ("cutting_reference", "Cutting reference"),
            ),
            3,
        )
        section(
            "Limits, commissions, and patti %",
            (
                ("limit_mode", "Limit mode"),
                ("limit_amount", "Limit amount"),
                ("patti_match", "Match patti %"),
                ("patti_session", "Session patti %"),
                ("patti_meter", "Meter patti %"),
                ("session_commission", "Session commission"),
                ("match_commission", "Match commission"),
            ),
            3,
        )
        permission_box = tk.LabelFrame(
            inner,
            text="Permissions",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            padx=12,
            pady=10,
            font=("Tahoma", 8, "bold"),
        )
        permission_box.pack(fill="x", pady=(0, 10))
        permissions = (
            ("match_commission_all", "Apply match commission to all"),
            ("match_dibba", "Match dibba"),
            ("session_dibba", "Session dibba"),
            ("show_dibba_user", "Show dibba user"),
            ("cutting_user", "Cutting user"),
            ("dibba_account", "Dibba account"),
        )
        for index, (field, label) in enumerate(permissions):
            bool_vars[field] = tk.BooleanVar(
                value=bool(row[field]) if row is not None else False
            )
            ttk.Checkbutton(
                permission_box, text=label, variable=bool_vars[field]
            ).grid(row=index // 3, column=index % 3, sticky="w", padx=8, pady=5)

        button_row = tk.Frame(inner, bg=COLORS["background"])
        button_row.pack(fill="x", pady=(2, 10))

        def save() -> None:
            values: dict[str, Any] = {}
            try:
                for field in USER_FIELDS:
                    if field in bool_vars:
                        values[field] = int(bool_vars[field].get())
                    elif field in {
                        "limit_amount",
                        "patti_match",
                        "patti_session",
                        "patti_meter",
                        "session_commission",
                        "match_commission",
                    }:
                        text = vars[field].get().strip()
                        values[field] = 0.0 if not text else float(text)
                        if values[field] < 0:
                            raise ValueError(f"{field.replace('_', ' ').title()} cannot be negative.")
                    else:
                        values[field] = vars[field].get().strip()
                if not values["name"]:
                    raise ValueError("Enter the user's name.")
                DB.save_user(None if row is None else int(row["id"]), values)
            except ValueError as error:
                messagebox.showerror("Check user details", str(error), parent=window)
                return
            except sqlite3.Error as error:
                messagebox.showerror("Could not save user", str(error), parent=window)
                return
            self.refresh_state_ref_choices()
            self.refresh_users()
            window.destroy()

        def clear_form() -> None:
            for field, variable in vars.items():
                variable.set("0" if field in {
                    "limit_amount",
                    "patti_match",
                    "patti_session",
                    "patti_meter",
                    "session_commission",
                    "match_commission",
                } else "")
            for variable in bool_vars.values():
                variable.set(False)

        ttk.Button(
            button_row,
            text="Modify" if row else "Save",
            style="Accent.TButton",
            command=save,
        ).pack(side="left")
        ttk.Button(button_row, text="Clear", command=clear_form).pack(side="left", padx=7)
        ttk.Button(button_row, text="Close", command=window.destroy).pack(side="left")

    def build_entries(self) -> None:
        self.page_header(
            "Entry panel", "Record match, session, or meter transactions"
        )
        container = tk.Frame(self.content, bg=COLORS["background"])
        container.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.entry_id: int | None = None
        self.match_rows = DB.list_matches()
        self.user_rows = DB.list_users()
        if not self.match_rows or not self.user_rows:
            note = tk.LabelFrame(
                container,
                text="Before entering transactions",
                bg=COLORS["panel"],
                fg=COLORS["text"],
                padx=18,
                pady=16,
            )
            note.pack(fill="x")
            tk.Label(
                note,
                text="Create at least one match and one user first. Their records will be available here.",
                bg=COLORS["panel"],
                fg=COLORS["muted"],
            ).pack(anchor="w")
            actions = tk.Frame(note, bg=COLORS["panel"])
            actions.pack(anchor="w", pady=(12, 0))
            ttk.Button(actions, text="Go to Matches", command=lambda: self.show_page("Matches")).pack(side="left")
            ttk.Button(actions, text="Go to Users", command=lambda: self.show_page("Users")).pack(side="left", padx=8)
            return

        selector = tk.LabelFrame(
            container,
            text="Match details",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            padx=12,
            pady=10,
        )
        selector.pack(fill="x", pady=(0, 10))
        self.entry_match_var = tk.StringVar()
        self.entry_match_combo = ttk.Combobox(
            selector,
            textvariable=self.entry_match_var,
            state="readonly",
            width=38,
            values=[self.match_label(row) for row in self.match_rows],
        )
        self.entry_match_var.set(self.match_label(self.match_rows[0]))
        self.entry_match_combo.grid(row=0, column=1, padx=(8, 20), pady=4)
        ttk.Label(selector, text="Match").grid(row=0, column=0, sticky="e")
        self.entry_match_combo.bind("<<ComboboxSelected>>", self.update_team_choices)

        ttk.Label(selector, text="Book No.").grid(row=0, column=2, sticky="e")
        self.entry_book_var = tk.StringVar(value="1")
        self.entry_book_combo = ttk.Combobox(
            selector, textvariable=self.entry_book_var, state="readonly", width=8
        )
        self.entry_book_combo.grid(row=0, column=3, padx=6, pady=4)
        self.entry_book_combo.bind("<<ComboboxSelected>>", self.on_book_changed)
        ttk.Button(selector, text="New Book", command=self.add_book).grid(
            row=0, column=4, padx=4
        )
        ttk.Button(selector, text="Save Book", command=self.save_book_details).grid(
            row=0, column=5, padx=4
        )

        ttk.Label(selector, text="Mundi").grid(row=1, column=0, sticky="e")
        self.book_mundi_var = tk.StringVar()
        ttk.Entry(selector, textvariable=self.book_mundi_var, width=24).grid(
            row=1, column=1, sticky="w", padx=(8, 20), pady=4
        )
        ttk.Label(selector, text="Mundi Rate").grid(row=1, column=2, sticky="e")
        self.book_mundi_rate_var = tk.StringVar(value="0")
        ttk.Entry(selector, textvariable=self.book_mundi_rate_var, width=10).grid(
            row=1, column=3, sticky="w", padx=6, pady=4
        )
        self.cutting_book_var = tk.BooleanVar()
        self.dibba_book_var = tk.BooleanVar()
        self.f8_enabled_var = tk.BooleanVar()
        ttk.Checkbutton(
            selector, text="Cutting Book", variable=self.cutting_book_var
        ).grid(row=1, column=4, sticky="w")
        ttk.Checkbutton(
            selector, text="Dibba Book", variable=self.dibba_book_var
        ).grid(row=1, column=5, sticky="w")
        ttk.Checkbutton(
            selector, text="F8", variable=self.f8_enabled_var
        ).grid(row=1, column=6, sticky="w")
        self.book_status_var = tk.StringVar()
        ttk.Label(selector, textvariable=self.book_status_var).grid(
            row=2, column=0, columnspan=4, sticky="w", padx=4, pady=3
        )
        self.close_book_button = ttk.Button(
            selector, text="Close Book", command=self.toggle_book_closed
        )
        self.close_book_button.grid(row=2, column=4, padx=4, sticky="w")
        self.entry_team_a_var = tk.StringVar()
        self.entry_team_b_var = tk.StringVar()
        ttk.Label(selector, textvariable=self.entry_team_a_var).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=4, pady=(5, 0)
        )
        ttk.Label(selector, textvariable=self.entry_team_b_var).grid(
            row=3, column=2, columnspan=2, sticky="w", padx=4, pady=(5, 0)
        )
        ttk.Label(selector, text="Avg K: Not calculated").grid(
            row=3, column=4, sticky="w", padx=4, pady=(5, 0)
        )
        ttk.Label(selector, text="Avg L: Not calculated").grid(
            row=3, column=5, sticky="w", padx=4, pady=(5, 0)
        )

        form = tk.LabelFrame(
            container,
            text="Entry details",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            padx=12,
            pady=10,
        )
        form.pack(fill="x", pady=(0, 10))
        self.entry_vars = {
            key: tk.StringVar()
            for key in (
                "date",
                "type",
                "patti",
                "rate",
                "amount",
                "mode",
                "team",
                "user",
                "session",
                "runs",
                "yes_no",
                "support",
                "charge",
            )
        }
        self.entry_vars["date"].set(date.today().isoformat())
        self.entry_vars["type"].set("Match")
        self.entry_vars["mode"].set("A")
        fields = (
            ("Date", "date", "entry"),
            ("Type", "type", "combo"),
            ("P No.", "patti", "entry"),
            ("Rate", "rate", "entry"),
            ("Amount", "amount", "entry"),
            ("Mode", "mode", "combo"),
            ("Team", "team", "combo"),
            ("Name", "user", "user"),
            ("Session", "session", "entry"),
            ("Runs", "runs", "entry"),
            ("Y/N", "yes_no", "combo"),
            ("Support", "support", "entry"),
            ("CH", "charge", "entry"),
        )
        self.team_combo: ttk.Combobox | None = None
        self.user_combo: ttk.Combobox | None = None
        self.entry_field_widgets: dict[str, tk.Widget] = {}
        for index, (label, key, kind) in enumerate(fields):
            row_index, col_index = divmod(index, 6)
            cell = tk.Frame(form, bg=COLORS["panel"])
            cell.grid(row=row_index, column=col_index, sticky="w", padx=(0, 8), pady=4)
            ttk.Label(cell, text=label).pack(anchor="w", pady=(0, 3))
            if kind == "combo":
                options = {
                    "type": ("Match", "Session", "Meter"),
                    "mode": ("K", "L", "A", "B", "Back", "Lay"),
                    "team": (),
                    "yes_no": ("", "Yes", "No"),
                }[key]
                widget = ttk.Combobox(
                    cell,
                    textvariable=self.entry_vars[key],
                    values=options,
                    state="readonly",
                    width=15,
                )
                if key == "team":
                    self.team_combo = widget
                widget.pack(anchor="w")
            elif kind == "user":
                labels = [self.user_label(row) for row in self.user_rows]
                self.user_combo = ttk.Combobox(
                    cell,
                    textvariable=self.entry_vars[key],
                    values=labels,
                    state="readonly",
                    width=19,
                )
                self.user_combo.pack(anchor="w")
                widget = self.user_combo
            else:
                widget = ttk.Entry(cell, textvariable=self.entry_vars[key], width=17)
                widget.pack(anchor="w")
            self.entry_field_widgets[key] = widget

        actions = tk.Frame(form, bg=COLORS["panel"])
        actions.grid(row=3, column=0, columnspan=6, sticky="w", pady=(8, 0))
        ttk.Button(actions, text="OK", style="Accent.TButton", command=self.save_entry).pack(side="left")
        ttk.Button(actions, text="R", command=self.clear_entry_form).pack(side="left", padx=4)
        ttk.Button(actions, text="Modify", command=self.modify_entry).pack(side="left", padx=5)
        ttk.Button(actions, text="Delete", command=self.delete_entry).pack(side="left")
        ttk.Button(actions, text="Log", command=self.show_entry_log).pack(side="left", padx=5)
        ttk.Button(actions, text="Print", command=self.print_entries).pack(side="left")
        ttk.Button(actions, text="Cancel", command=self.clear_entry_form).pack(side="left", padx=5)
        ttk.Button(actions, text="Status", command=self.show_entry_status).pack(side="left")
        ttk.Button(actions, text="Close", command=lambda: self.show_page("Dashboard")).pack(side="left", padx=5)
        ttk.Button(actions, text="Runs", command=self.prepare_runs_entry).pack(side="left", padx=5)
        ttk.Button(actions, text="Fancy", command=self.prepare_fancy_entry).pack(side="left")
        ttk.Button(actions, text="+/-", command=self.toggle_entry_back_lay).pack(side="left", padx=5)
        ttk.Button(actions, text="View", command=self.view_current_entries).pack(side="left")
        ttk.Button(actions, text="Add Session", command=self.add_entry_session).pack(side="left", padx=5)
        ttk.Button(actions, text="Sel", command=self.select_entry_session).pack(side="left")
        ttk.Button(actions, text="Meter", command=self.prepare_meter_entry).pack(side="left", padx=5)
        ttk.Button(actions, text="View Trns.", command=self.view_session_transactions).pack(side="left")

        table = tk.Frame(container, bg=COLORS["panel"])
        table.pack(fill="both", expand=True)
        table.grid_rowconfigure(0, weight=1)
        table.grid_columnconfigure(0, weight=4)
        table.grid_columnconfigure(1, weight=1)
        entries_frame = tk.Frame(table, bg=COLORS["panel"])
        entries_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        account_frame = tk.Frame(table, bg=COLORS["panel"])
        account_frame.grid(row=0, column=1, sticky="nsew")
        self.entries_tree = self.make_tree(
            entries_frame,
            (
                ("date", "DATE", 95),
                ("sl", "SL", 50),
                ("book", "BOOK", 55),
                ("type", "TYPE", 85),
                ("patti", "P NO.", 65),
                ("rate", "RATE", 80),
                ("amount", "AMOUNT", 95),
                ("mode", "MODE", 75),
                ("team", "TEAM", 100),
                ("user", "NAME", 145),
                ("team_a", "A", 105),
                ("team_b", "B", 105),
                ("session", "SESSION", 115),
                ("runs", "RUNS", 70),
                ("yes_no", "Y/N", 55),
                ("support", "SUPP", 110),
                ("charge", "CH", 75),
                ("time", "AT TIME", 150),
            ),
            selectmode="extended",
        )
        horizontal_scrollbar = ttk.Scrollbar(
            entries_frame, orient="horizontal", command=self.entries_tree.xview
        )
        self.entries_tree.configure(xscrollcommand=horizontal_scrollbar.set)
        self.entries_tree.tag_configure("K", background="#ffff80")
        self.entries_tree.tag_configure("L", background="#f5a6e8")
        horizontal_scrollbar.grid(row=1, column=0, columnspan=2, sticky="ew")
        entries_frame.grid_rowconfigure(0, weight=1)
        entries_frame.grid_columnconfigure(0, weight=1)
        self.entries_tree.bind("<<TreeviewSelect>>", self.on_entry_selected)
        ttk.Label(account_frame, text="User totals (X/Z not calculated)").pack(
            anchor="w", pady=(0, 3)
        )
        account_tree_frame = tk.Frame(account_frame, bg=COLORS["panel"])
        account_tree_frame.pack(fill="both", expand=True)
        self.entry_account_tree = self.make_tree(
            account_tree_frame,
            (
                ("name", "NAME", 115),
                ("charge", "CH", 65),
                ("team_a", "A", 75),
                ("team_b", "B", 75),
            ),
            height=12,
        )
        self.entry_team_totals_var = tk.StringVar()
        ttk.Label(account_frame, textvariable=self.entry_team_totals_var).pack(
            anchor="w", pady=(5, 0)
        )
        self.entry_total_var = tk.StringVar()
        ttk.Label(container, textvariable=self.entry_total_var).pack(anchor="e", pady=(7, 0))
        self.refresh_book_choices()
        self.update_team_choices()
        self.refresh_entries()
        self.bind("<F8>", self.on_entry_f8)

    @staticmethod
    def match_label(row: sqlite3.Row) -> str:
        return f'{row["code"]} - {row["comment"]} [#{row["id"]}]'

    @staticmethod
    def user_label(row: sqlite3.Row) -> str:
        return f'{row["name"]} [#{row["id"]}]'

    def selected_match_id(self) -> int | None:
        label = self.entry_match_var.get()
        row = next((item for item in self.match_rows if self.match_label(item) == label), None)
        return None if row is None else int(row["id"])

    def update_team_choices(self, _event: tk.Event | None = None) -> None:
        if not hasattr(self, "entry_match_var") or self.team_combo is None:
            return
        match_id = self.selected_match_id()
        row = next((item for item in self.match_rows if item["id"] == match_id), None)
        teams = [] if row is None else [team.strip() for team in row["teams"].split(",") if team.strip()]
        self.team_combo.configure(values=teams)
        if teams and self.entry_vars["team"].get() not in teams:
            self.entry_vars["team"].set(teams[0])
        self.refresh_entries()
        self.refresh_book_choices()

    def refresh_book_choices(self) -> None:
        if not hasattr(self, "entry_book_combo"):
            return
        match_id = self.selected_match_id()
        if match_id is None:
            return
        books = DB.list_books(match_id)
        book_numbers = [str(row["book_no"]) for row in books]
        self.entry_book_combo.configure(values=book_numbers)
        if self.entry_book_var.get() not in book_numbers:
            self.entry_book_var.set(book_numbers[0])
        self.on_book_changed()

    def on_book_changed(self, _event: tk.Event | None = None) -> None:
        if not hasattr(self, "entry_book_var"):
            return
        match_id = self.selected_match_id()
        if match_id is None:
            return
        try:
            book = DB.get_book(match_id, int(self.entry_book_var.get()))
        except (ValueError, LookupError):
            return
        self.update_book_details(book)
        if self.entry_id is not None:
            current_ids = {
                int(row["id"])
                for row in DB.list_entries(
                    match_id=match_id,
                    book_no=int(self.entry_book_var.get()),
                )
            }
            if self.entry_id not in current_ids:
                self.clear_entry_form()
        self.refresh_entries()

    def update_book_details(self, book: sqlite3.Row) -> None:
        self.book_mundi_var.set(book["mundi"])
        self.book_mundi_rate_var.set(str(book["mundi_rate"]))
        self.cutting_book_var.set(bool(book["cutting_book"]))
        self.dibba_book_var.set(bool(book["dibba_book"]))
        self.f8_enabled_var.set(bool(book["f8_enabled"]))
        closed = bool(book["is_closed"])
        self.book_status_var.set("Book is closed" if closed else "Book is open")
        self.close_book_button.configure(text="Open Book" if closed else "Close Book")

    def add_book(self) -> None:
        match_id = self.selected_match_id()
        if match_id is None:
            return
        books = DB.list_books(match_id)
        next_book = max((int(row["book_no"]) for row in books), default=0) + 1
        DB.save_book(match_id, next_book)
        self.refresh_book_choices()
        self.entry_book_var.set(str(next_book))
        self.on_book_changed()

    def save_book_details(self) -> None:
        match_id = self.selected_match_id()
        if match_id is None:
            return
        try:
            book_no = int(self.entry_book_var.get())
            mundi_rate = float(self.book_mundi_rate_var.get() or "0")
            if mundi_rate < 0:
                raise ValueError("Mundi rate cannot be negative.")
            DB.save_book(
                match_id,
                book_no,
                self.book_mundi_var.get().strip(),
                mundi_rate,
                self.cutting_book_var.get(),
                self.dibba_book_var.get(),
                self.f8_enabled_var.get(),
            )
        except ValueError as error:
            messagebox.showerror("Check book details", str(error), parent=self)
            return
        except sqlite3.Error as error:
            messagebox.showerror("Could not save book", str(error), parent=self)
            return
        self.on_book_changed()

    def toggle_book_closed(self) -> None:
        match_id = self.selected_match_id()
        if match_id is None:
            return
        book_no = int(self.entry_book_var.get())
        book = DB.get_book(match_id, book_no)
        closing = not bool(book["is_closed"])
        if closing and not messagebox.askyesno(
            "Close book",
            "Close this book to new entries? You can reopen it later.",
            parent=self,
        ):
            return
        DB.set_book_closed(match_id, book_no, closing)
        self.on_book_changed()

    def on_entry_f8(self, _event: tk.Event) -> str | None:
        if self.f8_enabled_var.get() and hasattr(self, "entry_vars"):
            self.save_entry()
            return "break"
        return None

    def prepare_runs_entry(self) -> None:
        self.entry_vars["type"].set("Session")
        self.entry_field_widgets["runs"].focus_set()

    def prepare_fancy_entry(self) -> None:
        self.entry_vars["type"].set("Session")
        if not self.entry_vars["session"].get().strip():
            self.entry_vars["session"].set("Fancy")
        self.entry_field_widgets["rate"].focus_set()

    def prepare_meter_entry(self) -> None:
        self.entry_vars["type"].set("Meter")
        self.entry_field_widgets["rate"].focus_set()

    def toggle_entry_back_lay(self) -> None:
        current = self.entry_vars["mode"].get()
        pairs = {"K": "L", "L": "K", "Back": "Lay", "Lay": "Back"}
        self.entry_vars["mode"].set(pairs.get(current, "K"))

    def view_current_entries(self) -> None:
        self.show_entry_transactions("Entry transactions")

    def add_entry_session(self) -> None:
        match_id = self.selected_match_id()
        if match_id is None:
            return
        name = simpledialog.askstring("Add session", "Session name:", parent=self)
        if name is None:
            return
        try:
            DB.save_entry_session(match_id, name)
        except ValueError as error:
            messagebox.showerror("Check session name", str(error), parent=self)
            return
        except sqlite3.Error as error:
            messagebox.showerror("Could not save session", str(error), parent=self)
            return
        self.entry_vars["type"].set("Session")
        self.entry_vars["session"].set(name.strip())
        self.entry_field_widgets["session"].focus_set()

    def select_entry_session(self) -> None:
        match_id = self.selected_match_id()
        if match_id is None:
            return
        try:
            sessions = DB.list_entry_sessions(match_id)
        except sqlite3.Error as error:
            messagebox.showerror("Could not load sessions", str(error), parent=self)
            return
        if not sessions:
            messagebox.showinfo(
                "No sessions",
                "Add a session name or save a session entry first.",
                parent=self,
            )
            return
        window = tk.Toplevel(self)
        window.title("Select Session")
        window.transient(self)
        window.grab_set()
        window.configure(bg=COLORS["background"])
        session_list = tk.Listbox(
            window,
            height=min(12, len(sessions)),
            exportselection=False,
            bg="#808080",
            fg=COLORS["text"],
            selectbackground="#ffff80",
            selectforeground=COLORS["text"],
        )
        session_list.pack(fill="both", expand=True, padx=10, pady=10)
        for session in sessions:
            session_list.insert(tk.END, session)
        current = self.entry_vars["session"].get()
        if current in sessions:
            session_list.selection_set(sessions.index(current))

        def choose_session(_event: tk.Event | None = None) -> None:
            selected = session_list.curselection()
            if not selected:
                messagebox.showinfo(
                    "Select a session", "Choose a session from the list.", parent=window
                )
                return
            self.entry_vars["type"].set("Session")
            self.entry_vars["session"].set(session_list.get(selected[0]))
            window.destroy()
            self.entry_field_widgets["session"].focus_set()

        session_list.bind("<Double-Button-1>", choose_session)
        buttons = tk.Frame(window, bg=COLORS["background"])
        buttons.pack(pady=(0, 10))
        ttk.Button(buttons, text="Select", command=choose_session).pack(side="left", padx=4)
        ttk.Button(buttons, text="Close", command=window.destroy).pack(side="left", padx=4)

    def view_session_transactions(self) -> None:
        session = self.entry_vars["session"].get().strip()
        if not session:
            messagebox.showinfo(
                "Select a session",
                "Enter or select a session name to view its transactions.",
                parent=self,
            )
            return
        self.show_entry_transactions(f"Session transactions - {session}", session=session)

    def show_entry_transactions(
        self,
        title: str,
        session: str | None = None,
    ) -> None:
        match_id = self.selected_match_id()
        if match_id is None:
            return
        try:
            rows = DB.list_entries(
                match_id=match_id,
                book_no=int(self.entry_book_var.get()),
                session=session,
            )
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Could not load transactions", str(error), parent=self)
            return
        window = tk.Toplevel(self)
        window.title(title)
        window.geometry("1050x420")
        window.configure(bg=COLORS["background"])
        frame = tk.Frame(window, bg=COLORS["panel"])
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        tree = self.make_tree(
            frame,
            (
                ("date", "DATE", 100),
                ("type", "TYPE", 90),
                ("name", "NAME", 150),
                ("rate", "RATE", 90),
                ("amount", "AMOUNT", 100),
                ("mode", "MODE", 80),
                ("team", "TEAM", 100),
                ("session", "SESSION", 120),
                ("runs", "RUNS", 80),
                ("yes_no", "Y/N", 65),
                ("support", "SUPPORT", 120),
                ("charge", "CH", 80),
            ),
            height=12,
        )
        for row in rows:
            tree.insert(
                "",
                "end",
                values=(
                    row["entry_date"],
                    row["entry_type"],
                    row["user_name"],
                    money(float(row["rate"])),
                    money(float(row["amount"])),
                    row["mode"],
                    row["team"],
                    row["session"],
                    row["runs"],
                    row["yes_no"],
                    row["support"],
                    money(float(row["charge"])),
                ),
            )
        ttk.Button(window, text="Close", command=window.destroy).pack(pady=(0, 8))

    def refresh_entries(self) -> None:
        if not hasattr(self, "entries_tree"):
            return
        match_id = self.selected_match_id()
        try:
            book_no = int(self.entry_book_var.get())
        except ValueError:
            return
        rows = DB.list_entries(match_id=match_id, book_no=book_no)
        match = next(
            (row for row in self.match_rows if int(row["id"]) == match_id),
            None,
        )
        teams = (
            []
            if match is None
            else [team.strip() for team in match["teams"].split(",") if team.strip()]
        )
        team_a = teams[0] if teams else "A"
        team_b = teams[1] if len(teams) > 1 else "B"
        self.entries_tree.heading("team_a", text=team_a)
        self.entries_tree.heading("team_b", text=team_b)
        self.entry_team_a_var.set(f"{team_a}: Not calculated")
        self.entry_team_b_var.set(f"{team_b}: Not calculated")
        self.entries_tree.delete(*self.entries_tree.get_children())
        user_totals: dict[int, dict[str, Any]] = {}
        for index, row in enumerate(rows, start=1):
            account = user_totals.setdefault(
                int(row["user_id"]),
                {"name": row["user_name"], "charge": 0.0},
            )
            account["charge"] += float(row["charge"])
            self.entries_tree.insert(
                "", "end", iid=str(row["id"]),
                values=(
                    row["entry_date"],
                    index,
                    row["book_no"],
                    row["entry_type"],
                    row["patti_number"],
                    money(row["rate"]),
                    money(row["amount"]),
                    row["mode"],
                    row["team"],
                    row["user_name"],
                    "Not calculated",
                    "Not calculated",
                    row["session"],
                    row["runs"],
                    row["yes_no"],
                    row["support"],
                    money(row["charge"]),
                    row["created_at"],
                ),
                tags=(row["mode"],),
            )
        self.entry_account_tree.delete(*self.entry_account_tree.get_children())
        for account in sorted(
            user_totals.values(), key=lambda item: item["name"].casefold()
        ):
            self.entry_account_tree.insert(
                "",
                "end",
                values=(
                    account["name"],
                    money(account["charge"]),
                    "Not calculated",
                    "Not calculated",
                ),
            )
        total = sum(float(row["amount"]) for row in rows)
        total_charge = sum(float(row["charge"]) for row in rows)
        self.entry_total_var.set(
            f"Book {book_no}: {len(rows)} entries | Gross amount: {money(total)} | CH: {money(total_charge)}"
        )
        self.entry_team_totals_var.set(
            f"{team_a}: Not calculated     {team_b}: Not calculated"
        )

    def on_entry_selected(self, _event: tk.Event) -> None:
        selection = self.entries_tree.selection()
        if not selection:
            return
        entry_id = int(selection[0])
        row = next((item for item in DB.list_entries(self.selected_match_id()) if item["id"] == entry_id), None)
        if row is None:
            return
        self.entry_id = entry_id
        self.entry_vars["date"].set(row["entry_date"])
        self.entry_vars["type"].set(row["entry_type"])
        self.entry_vars["patti"].set(row["patti_number"])
        self.entry_vars["rate"].set(str(row["rate"]))
        self.entry_vars["amount"].set(str(row["amount"]))
        self.entry_vars["mode"].set(row["mode"])
        self.entry_vars["team"].set(row["team"])
        user = next((item for item in self.user_rows if item["id"] == row["user_id"]), None)
        self.entry_vars["user"].set("" if user is None else self.user_label(user))
        self.entry_vars["session"].set(row["session"])
        self.entry_vars["runs"].set(row["runs"])
        self.entry_vars["yes_no"].set(row["yes_no"])
        self.entry_vars["support"].set(row["support"])
        self.entry_vars["charge"].set(str(row["charge"]))
        self.entry_book_var.set(str(row["book_no"]))
        self.update_book_details(DB.get_book(int(row["match_id"]), int(row["book_no"])))

    def clear_entry_form(self) -> None:
        self.entry_id = None
        for key, variable in self.entry_vars.items():
            variable.set(date.today().isoformat() if key == "date" else "")
        self.entry_vars["type"].set("Match")
        self.entry_vars["mode"].set("A")
        self.entry_vars["charge"].set("0")
        if self.entries_tree.selection():
            self.entries_tree.selection_remove(self.entries_tree.selection())

    def save_entry(self) -> None:
        try:
            match_id = self.selected_match_id()
            if match_id is None:
                raise ValueError("Select a match.")
            book_no = int(self.entry_book_var.get())
            book = DB.get_book(match_id, book_no)
            if book["is_closed"]:
                raise ValueError("This book is closed. Reopen it before adding or modifying entries.")
            user_label = self.entry_vars["user"].get()
            user = next((item for item in self.user_rows if self.user_label(item) == user_label), None)
            if user is None:
                raise ValueError("Select a user.")
            date.fromisoformat(self.entry_vars["date"].get().strip())
            rate = float(self.entry_vars["rate"].get())
            amount = float(self.entry_vars["amount"].get())
            if rate <= 0 or amount <= 0:
                raise ValueError("Rate and amount must be greater than zero.")
            entry_type = self.entry_vars["type"].get()
            team = self.entry_vars["team"].get()
            if entry_type == "Match" and not team:
                raise ValueError("Choose a team for a match entry.")
            values: dict[str, Any] = {
                "match_id": match_id,
                "book_no": book_no,
                "user_id": int(user["id"]),
                "entry_date": self.entry_vars["date"].get().strip(),
                "entry_type": entry_type,
                "patti_number": self.entry_vars["patti"].get().strip(),
                "rate": rate,
                "amount": amount,
                "mode": self.entry_vars["mode"].get(),
                "team": team,
                "session": self.entry_vars["session"].get().strip(),
                "runs": self.entry_vars["runs"].get().strip(),
                "yes_no": self.entry_vars["yes_no"].get(),
                "support": self.entry_vars["support"].get().strip(),
                "charge": float(self.entry_vars["charge"].get() or "0"),
            }
            if values["charge"] < 0:
                raise ValueError("CH cannot be negative.")
            if values["entry_type"] == "Session" and not values["session"]:
                raise ValueError("Enter a session name for a session entry.")
            DB.save_entry(self.entry_id, values)
        except ValueError as error:
            messagebox.showerror("Check entry details", str(error), parent=self)
            return
        except sqlite3.Error as error:
            messagebox.showerror("Could not save entry", str(error), parent=self)
            return
        self.refresh_entries()
        self.clear_entry_form()

    def delete_entry(self) -> None:
        selected = self.entries_tree.selection()
        if not selected:
            messagebox.showinfo("Select entries", "Choose one or more entries to delete.", parent=self)
            return
        if not messagebox.askyesno("Delete entries", f"Delete {len(selected)} selected entry(s)?", parent=self):
            return
        for entry_id in selected:
            DB.delete_entry(int(entry_id))
        self.refresh_entries()
        self.clear_entry_form()

    def modify_entry(self) -> None:
        if self.entry_id is None:
            messagebox.showinfo("Select an entry", "Choose an entry to modify.", parent=self)
            return
        self.save_entry()

    def show_entry_log(self) -> None:
        self.show_logs("entry", self.entry_id)

    def print_entries(self) -> None:
        try:
            self.print_tree(self.entries_tree, "Entry Panel")
        except (OSError, RuntimeError) as error:
            messagebox.showerror("Print preview failed", str(error), parent=self)

    def show_entry_status(self) -> None:
        if self.entry_id is not None:
            row = next(
                (
                    item
                    for item in DB.list_entries(self.selected_match_id())
                    if int(item["id"]) == self.entry_id
                ),
                None,
            )
            if row is not None:
                messagebox.showinfo(
                    "Entry status",
                    f'Saved entry #{row["id"]}\nCreated: {row["created_at"]}\nBook: {row["book_no"]}',
                    parent=self,
                )
                return
        match_id = self.selected_match_id()
        if match_id is None:
            return
        book = DB.get_book(match_id, int(self.entry_book_var.get()))
        messagebox.showinfo(
            "Entry status",
            f'Book {book["book_no"]}: {"Closed" if book["is_closed"] else "Open"}',
            parent=self,
        )

    def open_declaration_window(self) -> None:
        try:
            matches = DB.list_matches()
        except sqlite3.Error as error:
            messagebox.showerror("Could not load matches", str(error), parent=self)
            return

        team_count = max(
            3,
            max(
                (
                    len([team for team in row["teams"].split(",") if team.strip()])
                    for row in matches
                ),
                default=0,
            ),
        )
        team_columns = tuple(
            (f"team{index}", f"TEAM{index}", 70)
            for index in range(1, team_count + 1)
        )
        columns = (
            ("code", "CODE", 60),
            ("date", "DATE", 100),
            ("comment", "COMMENT", 220),
            ("result", "RESULT", 95),
            *team_columns,
            ("winner", "WON", 90),
        )
        window = self.report_window("Declaration", "800x600")
        table = tk.Frame(window, bg=COLORS["panel"])
        table.pack(fill="both", expand=True, padx=8, pady=8)
        tree = self.make_tree(table, columns, height=18)
        horizontal_scroll = ttk.Scrollbar(
            table, orient="horizontal", command=tree.xview
        )
        tree.configure(xscrollcommand=horizontal_scroll.set)
        horizontal_scroll.grid(row=1, column=0, sticky="ew")
        buttons = tk.Frame(window, bg=COLORS["background"])
        buttons.pack(pady=(0, 10))

        def find_match(match_id: int) -> sqlite3.Row | None:
            return next(
                (row for row in matches if int(row["id"]) == match_id),
                None,
            )

        def refresh(selected_id: int | None = None) -> None:
            nonlocal matches
            try:
                matches = DB.list_matches()
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Could not refresh declarations", str(error), parent=window
                )
                return
            tree.delete(*tree.get_children())
            for row in matches:
                teams = [
                    team.strip()
                    for team in row["teams"].split(",")
                    if team.strip()
                ]
                values = (
                    row["code"],
                    row["match_date"],
                    row["comment"],
                    row["result"],
                    *teams,
                    *("" for _ in range(team_count - len(teams))),
                    row["winner"],
                )
                tree.insert("", "end", iid=str(row["id"]), values=values)
            if selected_id is not None and tree.exists(str(selected_id)):
                tree.selection_set(str(selected_id))
                tree.see(str(selected_id))
            elif matches:
                tree.selection_set(str(matches[0]["id"]))

        def selected_match() -> sqlite3.Row | None:
            selection = tree.selection()
            return find_match(int(selection[0])) if selection else None

        def declare_selected() -> None:
            row = selected_match()
            if row is None:
                messagebox.showinfo(
                    "Select a match", "Choose a match first.", parent=window
                )
                return
            teams = [
                team.strip()
                for team in row["teams"].split(",")
                if team.strip()
            ]
            if not teams:
                messagebox.showerror(
                    "No teams available",
                    "This match has no teams to declare.",
                    parent=window,
                )
                return
            winner_window = tk.Toplevel(window)
            winner_window.title("Declare Winner")
            winner_window.geometry("340x130")
            winner_window.configure(bg=COLORS["background"])
            winner_window.transient(window)
            winner_window.grab_set()
            ttk.Label(
                winner_window,
                text=f'Select the winning team for match {row["code"]}:',
            ).pack(anchor="w", padx=12, pady=(14, 5))
            winner_var = tk.StringVar(
                value=row["winner"] if row["winner"] in teams else teams[0]
            )
            winner_combo = ttk.Combobox(
                winner_window,
                textvariable=winner_var,
                values=teams,
                state="readonly",
                width=30,
            )
            winner_combo.pack(fill="x", padx=12)

            def save_winner() -> None:
                try:
                    DB.set_result(
                        int(row["id"]), "Declared", winner_var.get()
                    )
                except sqlite3.Error as error:
                    messagebox.showerror(
                        "Could not save result", str(error), parent=winner_window
                    )
                    return
                winner_window.destroy()
                refresh(int(row["id"]))

            winner_buttons = tk.Frame(
                winner_window, bg=COLORS["background"]
            )
            winner_buttons.pack(pady=10)
            ttk.Button(
                winner_buttons,
                text="Declare",
                style="Accent.TButton",
                command=save_winner,
            ).pack(side="left", padx=4)
            ttk.Button(
                winner_buttons,
                text="Cancel",
                command=winner_window.destroy,
            ).pack(side="left", padx=4)
            winner_combo.focus_set()

        def undeclare_selected() -> None:
            row = selected_match()
            if row is None:
                messagebox.showinfo(
                    "Select a match", "Choose a match first.", parent=window
                )
                return
            if row["result"] == "Undeclared":
                return
            try:
                DB.set_result(int(row["id"]), "Undeclared", "")
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Could not undeclare result", str(error), parent=window
                )
                return
            refresh(int(row["id"]))

        def on_double_click(event: tk.Event) -> None:
            item = tree.identify_row(event.y)
            if item:
                tree.selection_set(item)
                declare_selected()

        tree.bind("<Double-1>", on_double_click)
        tree.bind("<Return>", lambda _event: declare_selected())
        ttk.Button(
            buttons,
            text="Undeclare",
            command=undeclare_selected,
        ).pack(side="left", padx=6)
        ttk.Button(
            buttons,
            text="Close",
            command=window.destroy,
        ).pack(side="left", padx=6)
        refresh()

    def build_results(self) -> None:
        self.page_header(
            "Results", "Declare a match result or return it to undeclared status"
        )
        container = tk.Frame(self.content, bg=COLORS["background"])
        container.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.result_matches = DB.list_matches()
        if not self.result_matches:
            ttk.Label(container, text="Create a match to manage its result.").pack(anchor="w")
            ttk.Button(container, text="Go to Matches", command=lambda: self.show_page("Matches")).pack(anchor="w", pady=10)
            return

        controls = tk.LabelFrame(
            container,
            text="Result details",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            padx=14,
            pady=12,
        )
        controls.pack(fill="x", pady=(0, 14))
        self.result_match_var = tk.StringVar()
        self.result_status_var = tk.StringVar(value="Undeclared")
        self.result_winner_var = tk.StringVar()
        ttk.Label(controls, text="Match").grid(row=0, column=0, sticky="e", padx=6)
        self.result_match_combo = ttk.Combobox(
            controls,
            textvariable=self.result_match_var,
            values=[self.match_label(row) for row in self.result_matches],
            state="readonly",
            width=40,
        )
        self.result_match_combo.grid(row=0, column=1, padx=6, pady=5)
        self.result_match_combo.bind("<<ComboboxSelected>>", self.on_result_match_changed)
        ttk.Label(controls, text="Result").grid(row=0, column=2, sticky="e", padx=6)
        self.result_status_combo = ttk.Combobox(
            controls,
            textvariable=self.result_status_var,
            values=("Undeclared", "Declared"),
            state="readonly",
            width=15,
        )
        self.result_status_combo.grid(row=0, column=3, padx=6, pady=5)
        ttk.Label(controls, text="Won").grid(row=0, column=4, sticky="e", padx=6)
        self.result_winner_combo = ttk.Combobox(
            controls,
            textvariable=self.result_winner_var,
            values=(),
            state="readonly",
            width=20,
        )
        self.result_winner_combo.grid(row=0, column=5, padx=6, pady=5)
        self.result_status_combo.bind(
            "<<ComboboxSelected>>", self.on_result_status_changed
        )
        buttons = tk.Frame(controls, bg=COLORS["panel"])
        buttons.grid(row=1, column=0, columnspan=6, sticky="w", padx=4, pady=(9, 0))
        ttk.Button(buttons, text="Save result", style="Accent.TButton", command=self.save_result).pack(side="left")
        ttk.Button(buttons, text="Undeclare", command=self.undeclare_result).pack(side="left", padx=7)
        ttk.Button(buttons, text="Print", command=self.print_results).pack(side="left")
        ttk.Button(buttons, text="Close", command=lambda: self.show_page("Entries")).pack(side="left", padx=7)

        table = tk.Frame(container, bg=COLORS["panel"])
        table.pack(fill="both", expand=True)
        self.results_tree = self.make_tree(
            table,
            (
                ("code", "CODE", 80),
                ("date", "DATE", 120),
                ("comment", "COMMENT", 220),
                ("result", "RESULT", 120),
                ("teams", "TEAMS", 330),
                ("winner", "WON", 150),
            ),
        )
        self.results_tree.bind("<<TreeviewSelect>>", self.on_result_row_selected)
        self.refresh_results()
        self.result_match_var.set(self.match_label(self.result_matches[0]))
        self.on_result_match_changed()

    def result_match(self) -> sqlite3.Row | None:
        label = self.result_match_var.get()
        return next(
            (row for row in self.result_matches if self.match_label(row) == label),
            None,
        )

    def on_result_match_changed(self, _event: tk.Event | None = None) -> None:
        row = self.result_match()
        if row is None:
            return
        teams = [team.strip() for team in row["teams"].split(",") if team.strip()]
        self.result_winner_combo.configure(values=teams)
        self.result_status_var.set(row["result"])
        self.result_winner_var.set(row["winner"] if row["result"] == "Declared" else "")

    def on_result_status_changed(self, _event: tk.Event | None = None) -> None:
        if self.result_status_var.get() == "Undeclared":
            self.result_winner_var.set("")

    def on_result_row_selected(self, _event: tk.Event) -> None:
        selection = self.results_tree.selection()
        if not selection:
            return
        row = next((item for item in self.result_matches if item["id"] == int(selection[0])), None)
        if row is not None:
            self.result_match_var.set(self.match_label(row))
            self.on_result_match_changed()

    def refresh_results(self) -> None:
        self.result_matches = DB.list_matches()
        if not hasattr(self, "results_tree"):
            return
        self.results_tree.delete(*self.results_tree.get_children())
        for row in self.result_matches:
            self.results_tree.insert(
                "", "end", iid=str(row["id"]),
                values=(
                    row["code"],
                    row["match_date"],
                    row["comment"],
                    row["result"],
                    row["teams"],
                    row["winner"],
                ),
            )

    def save_result(self) -> None:
        row = self.result_match()
        if row is None:
            messagebox.showerror("Select a match", "Choose a match first.", parent=self)
            return
        result = self.result_status_var.get()
        winner = self.result_winner_var.get()
        if result == "Declared":
            teams = [team.strip() for team in row["teams"].split(",") if team.strip()]
            if winner not in teams:
                messagebox.showerror(
                    "Select the winner",
                    "Choose a winning team from this match.",
                    parent=self,
                )
                return
        DB.set_result(int(row["id"]), result, winner)
        self.refresh_results()
        self.result_matches = DB.list_matches()
        self.on_result_match_changed()

    def undeclare_result(self) -> None:
        self.result_status_var.set("Undeclared")
        self.result_winner_var.set("")
        self.save_result()

    def print_results(self) -> None:
        try:
            self.print_tree(self.results_tree, "Result Declaration")
        except (OSError, RuntimeError) as error:
            messagebox.showerror("Print preview failed", str(error), parent=self)

    def build_reports(self) -> None:
        self.page_header("Reports & accounts", "Open a report view")
        container = tk.Frame(self.content, bg=COLORS["background"])
        container.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        choices = (
            ("Individual Report", "Review one user's match entries"),
            ("Session Individual Report", "Review sessions and run totals"),
            ("User Account", "Review match accounts by state/reference"),
        )
        for title, description in choices:
            card = tk.LabelFrame(
                container,
                text=title,
                bg=COLORS["panel"],
                fg=COLORS["text"],
                padx=16,
                pady=12,
            )
            card.pack(fill="x", pady=(0, 10))
            ttk.Label(card, text=description).pack(side="left", padx=(0, 18))
            ttk.Button(
                card,
                text="Open",
                style="Accent.TButton",
                command=lambda report=title: self.open_report_mode(report),
            ).pack(side="right")

    def report_window(self, title: str, geometry: str) -> tk.Toplevel:
        window = tk.Toplevel(self)
        window.title(title)
        window.geometry(geometry)
        window.configure(bg=COLORS["background"])
        window.transient(self)
        window.grab_set()
        return window

    def report_user_id(
        self, label: str, users: list[sqlite3.Row]
    ) -> int | None:
        row = next(
            (user for user in users if self.user_label(user) == label),
            None,
        )
        return None if row is None else int(row["id"])

    @staticmethod
    def report_tree_rows(tree: ttk.Treeview) -> tuple[list[str], list[list[Any]]]:
        headers = [tree.heading(column, "text") for column in tree["columns"]]
        rows = [
            list(tree.item(item, "values"))
            for item in tree.get_children()
        ]
        return headers, rows

    def print_report_rows(
        self,
        title: str,
        headers: list[str],
        rows: list[list[Any]],
        parent: tk.Widget,
    ) -> None:
        try:
            open_print_preview(title, headers, rows)
        except (OSError, RuntimeError) as error:
            messagebox.showerror("Print preview failed", str(error), parent=parent)

    def export_report_rows(
        self,
        title: str,
        headers: list[str],
        rows: list[list[Any]],
        parent: tk.Widget,
    ) -> None:
        path = filedialog.asksaveasfilename(
            parent=parent,
            title=f"Export {title}",
            defaultextension=".csv",
            filetypes=(("CSV files", "*.csv"),),
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(headers)
                writer.writerows(rows)
        except OSError as error:
            messagebox.showerror("Export failed", str(error), parent=parent)
            return
        messagebox.showinfo("Report exported", f"Saved CSV report to:\n{path}", parent=parent)

    def report_tree_actions(
        self,
        tree: ttk.Treeview,
        title: str,
        close_window: tk.Toplevel,
    ) -> None:
        headers, rows = self.report_tree_rows(tree)
        self.print_report_rows(title, headers, rows, close_window)

    def open_connect_report(self, cup: bool = False) -> None:
        try:
            matches = DB.list_matches()
            users = DB.list_users() if cup else []
        except sqlite3.Error as error:
            messagebox.showerror(
                "Could not load report filters", str(error), parent=self
            )
            return
        title = "Connect Report Cup" if cup else "Connect Report"
        window = self.report_window(title, "1120x650")
        body = tk.Frame(window, bg=COLORS["background"])
        body.pack(fill="both", expand=True, padx=8, pady=8)
        selection_frame = tk.LabelFrame(
            body,
            text="Select Match / Session / Meter",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            padx=8,
            pady=8,
        )
        selection_frame.pack(side="left", fill="y", padx=(0, 8))
        match_list = tk.Listbox(
            selection_frame,
            selectmode=tk.EXTENDED,
            exportselection=False,
            width=31,
            bg="#808080",
            fg=COLORS["text"],
            selectbackground="#ffff80",
            selectforeground=COLORS["text"],
        )
        match_list.pack(fill="both", expand=True)
        for row in matches:
            match_list.insert(
                tk.END,
                f'{row["code"]}  {row["match_date"]}  {row["comment"]}',
            )
        tables = tk.Frame(body, bg=COLORS["background"])
        tables.pack(side="left", fill="both", expand=True)
        tables.grid_columnconfigure(0, weight=1)
        tables.grid_columnconfigure(1, weight=1)
        tables.grid_rowconfigure(0, weight=1)
        columns = (
            ("name", "NAME", 140),
            ("state", "STATE/REF", 105),
            ("amount", "AMOUNT", 105),
            ("patti", "WITH_PATTI", 110),
            ("charge", "CH", 75),
        )
        trees = []
        for index, title in enumerate(("Match entries", "Session / meter entries")):
            section = tk.LabelFrame(
                tables,
                text=title,
                bg=COLORS["panel"],
                fg=COLORS["text"],
                padx=5,
                pady=5,
            )
            section.grid(row=0, column=index, sticky="nsew", padx=(0, 5))
            tree_frame = tk.Frame(section, bg=COLORS["panel"])
            tree_frame.pack(fill="both", expand=True)
            trees.append(self.make_tree(tree_frame, columns, height=15))
        match_subtotal_var = tk.StringVar(value="Sub Total: 0.00")
        other_subtotal_var = tk.StringVar(value="Sub Total: 0.00")
        final_total_var = tk.StringVar(value="Final Total: Not calculated")
        user_var = tk.StringVar(value="All users")
        footer = tk.Frame(window, bg=COLORS["background"])
        footer.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Label(footer, textvariable=match_subtotal_var).pack(side="left", padx=8)
        ttk.Label(footer, textvariable=other_subtotal_var).pack(side="left", padx=25)
        ttk.Label(footer, textvariable=final_total_var).pack(side="right", padx=8)
        select_all_var = tk.BooleanVar()

        def refresh() -> None:
            selected = match_list.curselection()
            match_ids = [int(matches[index]["id"]) for index in selected]
            user_id = (
                self.report_user_id(user_var.get(), users)
                if cup and user_var.get() != "All users"
                else None
            )
            try:
                entries = DB.list_entries(match_ids=match_ids, user_id=user_id)
            except sqlite3.Error as error:
                messagebox.showerror("Could not load report", str(error), parent=window)
                return
            for tree in trees:
                tree.delete(*tree.get_children())
            grouped: list[dict[int, dict[str, Any]]] = [{}, {}]
            for entry in entries:
                group_index = 0 if entry["entry_type"] == "Match" else 1
                groups = grouped[group_index]
                item = groups.setdefault(
                    int(entry["user_id"]),
                    {
                        "name": entry["user_name"],
                        "state": entry["state_ref"],
                        "amount": 0.0,
                        "patti": 0.0,
                        "charge": 0.0,
                    },
                )
                item["amount"] += float(entry["amount"])
                item["charge"] += float(entry["charge"])
                if entry["patti_number"]:
                    item["patti"] += float(entry["amount"])
            subtotals = []
            for tree, groups in zip(trees, grouped):
                subtotal = 0.0
                for item in sorted(
                    groups.values(),
                    key=lambda value: (
                        str(value["state"]).casefold(),
                        value["name"].casefold(),
                    ),
                ):
                    subtotal += item["amount"]
                    tree.insert(
                        "",
                        "end",
                        values=(
                            item["name"],
                            item["state"],
                            money(item["amount"]),
                            money(item["patti"]),
                            money(item["charge"]),
                        ),
                    )
                subtotals.append(subtotal)
            match_subtotal_var.set(f"Sub Total: {money(subtotals[0])}")
            other_subtotal_var.set(f"Sub Total: {money(subtotals[1])}")
            final_total_var.set("Final Total: Not calculated")

        def set_all_matches() -> None:
            match_list.selection_clear(0, tk.END)
            if select_all_var.get():
                match_list.selection_set(0, tk.END)
            refresh()

        select_all = ttk.Checkbutton(
            selection_frame,
            text="Select All",
            variable=select_all_var,
            command=set_all_matches,
        )
        select_all.pack(anchor="w", pady=(6, 0))
        match_list.bind("<<ListboxSelect>>", lambda _event: refresh())
        actions = tk.Frame(window, bg=COLORS["background"])
        actions.pack(pady=(0, 10))
        if cup:
            ttk.Combobox(
                actions,
                textvariable=user_var,
                values=["All users"] + [self.user_label(row) for row in users],
                state="readonly",
                width=22,
            ).pack(side="left", padx=4)
            ttk.Button(
                actions, text="OK", style="Accent.TButton", command=refresh
            ).pack(side="left", padx=4)
            ttk.Button(actions, text="Close", command=window.destroy).pack(
                side="left", padx=4
            )
            refresh()
            return

        ttk.Button(
            actions, text="Connect", style="Accent.TButton", command=refresh
        ).pack(side="left", padx=4)

        def connect_print(statewise: bool = False) -> None:
            headers = [
                "SECTION",
                *[
                    trees[0].heading(column, "text")
                    for column in trees[0]["columns"]
                ],
            ]
            rows = []
            for section, tree in zip(("Match", "Session / meter"), trees):
                for item in tree.get_children():
                    rows.append([section, *tree.item(item, "values")])
            if statewise and "STATE/REF" in headers:
                state_index = headers.index("STATE/REF")
                rows.sort(
                    key=lambda row: (
                        str(row[state_index]).casefold(),
                        str(row[1]).casefold(),
                    )
                )
            self.print_report_rows(
                "Connect Report - Statewise" if statewise else "Connect Report",
                headers,
                rows,
                window,
            )

        def export_connect() -> None:
            headers = [
                "SECTION",
                *[
                    trees[0].heading(column, "text")
                    for column in trees[0]["columns"]
                ],
            ]
            rows = [
                [section, *tree.item(item, "values")]
                for section, tree in zip(("Match", "Session / meter"), trees)
                for item in tree.get_children()
            ]
            self.export_report_rows("Connect Report", headers, rows, window)

        ttk.Button(actions, text="Print", command=connect_print).pack(side="left", padx=4)
        ttk.Button(
            actions,
            text="Print Statewise",
            command=lambda: connect_print(True),
        ).pack(side="left", padx=4)
        ttk.Button(actions, text="Export CSV", command=export_connect).pack(side="left", padx=4)
        ttk.Button(actions, text="Close", command=window.destroy).pack(side="left", padx=4)
        refresh()

    def open_connect_report_cup(self) -> None:
        self.open_connect_report(cup=True)

    def open_individual_report(self) -> None:
        try:
            matches = DB.list_matches()
            users = DB.list_users()
        except sqlite3.Error as error:
            messagebox.showerror("Could not load report filters", str(error), parent=self)
            return
        window = self.report_window("Individual Report", "1000x640")
        controls = tk.Frame(window, bg=COLORS["panel"], padx=10, pady=9)
        controls.pack(fill="x", padx=8, pady=8)
        user_var = tk.StringVar(
            value=self.user_label(users[0]) if users else "All users"
        )
        user_values = ["All users"] + [self.user_label(row) for row in users]
        ttk.Label(controls, text="Name Of Person").grid(row=0, column=0, padx=4)
        user_combo = ttk.Combobox(
            controls, textvariable=user_var, values=user_values, state="readonly", width=27
        )
        user_combo.grid(row=0, column=1, padx=4)
        total_var = tk.StringVar(value="0")
        ttk.Label(controls, text="Total Entries").grid(row=0, column=2, padx=4)
        ttk.Label(controls, textvariable=total_var, relief="sunken", width=8).grid(row=0, column=3, padx=4)
        date_var = tk.StringVar(value=date.today().isoformat())
        ttk.Label(controls, text="Date").grid(row=0, column=4, padx=4)
        ttk.Entry(controls, textvariable=date_var, width=12).grid(row=0, column=5, padx=4)
        select_all_var = tk.BooleanVar()
        ttk.Checkbutton(controls, text="Check All", variable=select_all_var).grid(
            row=1, column=0, sticky="w", padx=4, pady=(7, 0)
        )
        match_var = tk.StringVar(value=self.match_label(matches[0]) if matches else "")
        ttk.Label(controls, text="Match").grid(row=1, column=1, sticky="e", padx=4, pady=(7, 0))
        match_combo = ttk.Combobox(
            controls,
            textvariable=match_var,
            values=[self.match_label(row) for row in matches],
            state="readonly",
            width=34,
        )
        match_combo.grid(row=1, column=2, columnspan=3, sticky="w", padx=4, pady=(7, 0))
        actual_var = tk.BooleanVar(value=True)
        ttk.Label(
            window, text="A: Not calculated     B: Not calculated"
        ).pack(anchor="w", padx=12, pady=(0, 5))
        table_frame = tk.Frame(window, bg=COLORS["panel"])
        table_frame.pack(fill="both", expand=True, padx=8)
        columns = (
            ("sl", "SL", 55),
            ("rate", "RATE", 90),
            ("amount", "AMOUNT", 115),
            ("support", "SUPPORT", 130),
            ("mode", "MODE", 80),
            ("charge", "CH", 85),
            ("a", "A", 125),
            ("b", "B", 125),
        )
        tree = self.make_tree(table_frame, columns, height=16)

        def match_ids() -> list[int]:
            if select_all_var.get():
                return [int(row["id"]) for row in matches]
            row = next(
                (item for item in matches if self.match_label(item) == match_var.get()),
                None,
            )
            return [] if row is None else [int(row["id"])]

        def refresh() -> None:
            date_filter = date_var.get().strip()
            if date_filter:
                try:
                    datetime.strptime(date_filter, "%Y-%m-%d")
                except ValueError:
                    messagebox.showerror("Invalid date", "Enter a date as YYYY-MM-DD.", parent=window)
                    return
            try:
                entries = DB.list_entries(
                    user_id=self.report_user_id(user_var.get(), users),
                    match_ids=match_ids(),
                    entry_type="Match",
                )
            except sqlite3.Error as error:
                messagebox.showerror("Could not load report", str(error), parent=window)
                return
            if date_filter:
                entries = [row for row in entries if row["entry_date"] == date_filter]
            tree.delete(*tree.get_children())
            total_var.set(str(len(entries)))
            for index, entry in enumerate(entries, start=1):
                tree.insert(
                    "",
                    "end",
                    values=(
                        index,
                        money(float(entry["rate"])),
                        money(float(entry["amount"])) if actual_var.get() else "",
                        entry["support"],
                        entry["mode"],
                        money(float(entry["charge"])),
                        "Not calculated",
                        "Not calculated",
                    ),
                )
            if not select_all_var.get() and match_var.get():
                selected = next(
                    (row for row in matches if self.match_label(row) == match_var.get()),
                    None,
                )
            else:
                selected = None
            if selected is not None:
                teams = [part.strip() for part in selected["teams"].split(",") if part.strip()]
                tree.heading("a", text=teams[0] if teams else "A")
                tree.heading("b", text=teams[1] if len(teams) > 1 else "B")
            else:
                tree.heading("a", text="A")
                tree.heading("b", text="B")

        ttk.Checkbutton(
            window,
            text="Actual Amount",
            variable=actual_var,
            command=refresh,
        ).pack(anchor="w", padx=12, pady=(5, 0))
        for widget in (user_combo, match_combo):
            widget.bind("<<ComboboxSelected>>", lambda _event: refresh())
        select_all_var.trace_add(
            "write", lambda *_args: match_combo.configure(state="disabled" if select_all_var.get() else "readonly")
        )
        select_all_var.trace_add("write", lambda *_args: refresh())
        actions = tk.Frame(window, bg=COLORS["background"])
        actions.pack(pady=(6, 10))
        ttk.Button(actions, text="Refresh", command=refresh).pack(side="left", padx=5)
        ttk.Button(
            actions,
            text="Print",
            command=lambda: self.report_tree_actions(
                tree, "Individual Report", window
            ),
        ).pack(side="left", padx=5)
        ttk.Button(
            actions,
            text="Export CSV",
            command=lambda: self.export_report_rows(
                "Individual Report", *self.report_tree_rows(tree), window
            ),
        ).pack(side="left", padx=5)
        ttk.Button(actions, text="Close", command=window.destroy).pack(side="left", padx=5)
        refresh()

    def open_session_individual_report(self) -> None:
        try:
            matches = DB.list_matches()
            users = DB.list_users()
            sessions = sorted(
                {
                    session
                    for match in matches
                    for session in DB.list_entry_sessions(int(match["id"]))
                },
                key=str.casefold,
            )
        except sqlite3.Error as error:
            messagebox.showerror("Could not load report filters", str(error), parent=self)
            return
        window = self.report_window("Session Individual Report", "1060x680")
        controls = tk.Frame(window, bg=COLORS["panel"], padx=10, pady=9)
        controls.pack(fill="x", padx=8, pady=8)
        user_var = tk.StringVar(
            value=self.user_label(users[0]) if users else "All users"
        )
        ttk.Label(controls, text="User Name").grid(row=0, column=0, padx=4)
        user_combo = ttk.Combobox(
            controls,
            textvariable=user_var,
            values=["All users"] + [self.user_label(row) for row in users],
            state="readonly",
            width=24,
        )
        user_combo.grid(row=0, column=1, padx=4)
        total_var = tk.StringVar(value="0")
        ttk.Label(controls, text="Total Entries").grid(row=0, column=2, padx=4)
        ttk.Label(controls, textvariable=total_var, relief="sunken", width=7).grid(row=0, column=3, padx=4)
        result_var = tk.StringVar(value="Not recorded")
        ttk.Label(controls, text="Result").grid(row=0, column=4, padx=4)
        ttk.Entry(controls, textvariable=result_var, state="readonly", width=15).grid(
            row=0, column=5, padx=4
        )
        session_var = tk.StringVar(value="All sessions")
        ttk.Label(controls, text="Session").grid(row=1, column=0, padx=4, pady=(7, 0))
        session_combo = ttk.Combobox(
            controls,
            textvariable=session_var,
            values=["All sessions"] + sessions,
            state="readonly",
            width=24,
        )
        session_combo.grid(row=1, column=1, padx=4, pady=(7, 0))
        select_all_var = tk.BooleanVar()
        ttk.Checkbutton(
            controls,
            text="Check All",
            variable=select_all_var,
        ).grid(row=1, column=3, padx=4, pady=(7, 0))
        match_var = tk.StringVar(
            value=self.match_label(matches[0]) if matches else ""
        )
        ttk.Label(controls, text="Match").grid(row=1, column=4, padx=4, pady=(7, 0))
        match_combo = ttk.Combobox(
            controls,
            textvariable=match_var,
            values=[self.match_label(row) for row in matches],
            state="readonly",
            width=24,
        )
        match_combo.grid(row=1, column=5, columnspan=2, padx=4, pady=(7, 0))
        actual_var = tk.BooleanVar(value=False)
        show_var = tk.BooleanVar(value=False)
        body = tk.Frame(window, bg=COLORS["background"])
        body.pack(fill="both", expand=True, padx=8)
        body.grid_columnconfigure(0, weight=4)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        left_frame = tk.Frame(body, bg=COLORS["background"])
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        left_frame.grid_columnconfigure(0, weight=1)
        left_frame.grid_rowconfigure(0, weight=4)
        left_frame.grid_rowconfigure(1, weight=1)
        detail_frame = tk.Frame(left_frame, bg=COLORS["panel"])
        detail_frame.grid(row=0, column=0, sticky="nsew")
        lower_frame = tk.Frame(
            left_frame, bg=COLORS["panel"], height=125, padx=8, pady=5
        )
        lower_frame.grid(row=1, column=0, sticky="nsew", pady=(7, 0))
        lower_frame.grid_propagate(False)
        lower_frame.grid_columnconfigure(0, weight=1)
        lower_frame.grid_columnconfigure(1, weight=0)
        run_frame = tk.Frame(body, bg=COLORS["panel"])
        run_frame.grid(row=0, column=1, sticky="nsew")
        tree = self.make_tree(
            detail_frame,
            (
                ("sl", "SL", 45),
                ("name", "NAME", 125),
                ("rate", "RATE", 80),
                ("runs", "RUNS", 75),
                ("amount", "AMOUNT", 90),
                ("yes_no", "Y/N", 55),
                ("date", "DATE", 100),
                ("charge", "CH", 75),
            ),
            height=15,
        )
        run_tree = self.make_tree(
            run_frame,
            (("run", "RUNS", 70), ("amount", "AMOUNT", 110)),
            height=25,
        )
        ttk.Checkbutton(
            controls,
            text="Actual Amount",
            variable=actual_var,
            command=lambda: refresh(),
        ).grid(row=1, column=2, sticky="w", padx=4, pady=(7, 0))
        ttk.Checkbutton(
            lower_frame,
            text="Show",
            variable=show_var,
            command=lambda: update_detail(),
        ).grid(row=0, column=0, sticky="nw")
        detail_var = tk.StringVar()
        ttk.Label(
            lower_frame,
            textvariable=detail_var,
            wraplength=390,
            justify="left",
        ).grid(row=1, column=0, sticky="nw", pady=(3, 0))
        summary = tk.Frame(lower_frame, bg=COLORS["panel"])
        summary.grid(row=0, column=1, rowspan=2, sticky="e", padx=(8, 0))
        session_total_var = tk.StringVar(value="0.00")
        for index, (label, variable) in enumerate(
            (
                ("Session Total", session_total_var),
                ("Commission", None),
                ("Total Amount", None),
            )
        ):
            ttk.Label(summary, text=label).grid(row=index, column=0, sticky="e", padx=(0, 4))
            value_label = (
                ttk.Label(summary, text="Not calculated", relief="sunken", width=14)
                if variable is None
                else ttk.Label(
                    summary, textvariable=variable, relief="sunken", width=14
                )
            )
            value_label.grid(
                row=index, column=1, sticky="e", pady=1
            )
        actions = tk.Frame(lower_frame, bg=COLORS["panel"])
        actions.grid(row=2, column=1, sticky="e", padx=(8, 0), pady=(3, 0))

        def selected_match_ids() -> list[int]:
            if select_all_var.get():
                return [int(row["id"]) for row in matches]
            row = next(
                (item for item in matches if self.match_label(item) == match_var.get()),
                None,
            )
            return [] if row is None else [int(row["id"])]

        entry_by_iid: dict[str, Any] = {}

        def update_detail() -> None:
            selection = tree.selection()
            if not show_var.get():
                detail_var.set("")
                return
            if not selection or selection[0] not in entry_by_iid:
                detail_var.set("Select an entry to show its recorded details.")
                return
            entry = entry_by_iid[selection[0]]
            detail_var.set(
                f"Session: {entry['session'] or '-'}    "
                f"Runs: {entry['runs'] or '-'}    "
                f"Recorded amount: {money(float(entry['amount']))}    "
                f"CH: {money(float(entry['charge']))}"
            )

        def refresh() -> None:
            match_ids = selected_match_ids()
            selected_sessions = [session_var.get()] if session_var.get() != "All sessions" else None
            try:
                entries = DB.list_entries(
                    match_ids=match_ids,
                    user_id=self.report_user_id(user_var.get(), users),
                    entry_type="Session",
                )
            except sqlite3.Error as error:
                messagebox.showerror("Could not load report", str(error), parent=window)
                return
            if selected_sessions:
                entries = [row for row in entries if row["session"] == selected_sessions[0]]
            tree.delete(*tree.get_children())
            entry_by_iid.clear()
            run_tree.delete(*run_tree.get_children())
            run_amounts = {run: 0.0 for run in range(1, 26)}
            for index, entry in enumerate(entries, start=1):
                iid = tree.insert(
                    "",
                    "end",
                    values=(
                        index,
                        entry["user_name"],
                        money(float(entry["rate"])),
                        entry["runs"],
                        money(float(entry["amount"])) if actual_var.get() else "",
                        entry["yes_no"],
                        entry["entry_date"],
                        money(float(entry["charge"])),
                    ),
                )
                entry_by_iid[iid] = entry
                try:
                    run = int(entry["runs"])
                except (TypeError, ValueError):
                    continue
                if 1 <= run <= 25:
                    run_amounts[run] += float(entry["amount"])
            for run, amount in run_amounts.items():
                run_tree.insert(
                    "",
                    "end",
                    iid=str(run),
                    values=(run, money(amount) if actual_var.get() else ""),
                )
            total_var.set(str(len(entries)))
            gross = sum(float(entry["amount"]) for entry in entries)
            session_total_var.set(money(gross))
            update_detail()
            matches_by_id = {int(row["id"]): row for row in matches}
            used_matches = {
                int(entry["match_id"])
                for entry in entries
            }
            if len(used_matches) == 1:
                result = matches_by_id[next(iter(used_matches))]
                result_var.set(
                    result["winner"] if result["result"] == "Declared" else "Not declared"
                )
            elif used_matches:
                result_var.set("Multiple matches")
            else:
                result_var.set("Not recorded")

        for widget in (user_combo, session_combo, match_combo):
            widget.bind("<<ComboboxSelected>>", lambda _event: refresh())
        tree.bind("<<TreeviewSelect>>", lambda _event: update_detail())
        select_all_var.trace_add(
            "write",
            lambda *_args: match_combo.configure(
                state="disabled" if select_all_var.get() else "readonly"
            ),
        )
        select_all_var.trace_add("write", lambda *_args: refresh())
        ttk.Button(
            actions,
            text="Print",
            command=lambda: self.report_tree_actions(
                tree, "Session Individual Report", window
            ),
        ).pack(side="right", padx=5)
        ttk.Button(
            actions,
            text="Export CSV",
            command=lambda: self.export_report_rows(
                "Session Individual Report", *self.report_tree_rows(tree), window
            ),
        ).pack(side="right", padx=5)
        ttk.Button(actions, text="Close", command=window.destroy).pack(side="right", padx=5)
        refresh()

    def open_user_account_report(self) -> None:
        try:
            matches = DB.list_matches()
            users = DB.list_users()
        except sqlite3.Error as error:
            messagebox.showerror("Could not load account filters", str(error), parent=self)
            return
        window = self.report_window("User Account", "600x620")
        heading_var = tk.StringVar(value="Account Status of Match")
        ttk.Label(
            window,
            textvariable=heading_var,
            style="Title.TLabel",
        ).pack(anchor="w", padx=12, pady=(10, 4))
        controls = tk.Frame(window, bg=COLORS["background"], padx=10, pady=5)
        controls.pack(fill="x")
        match_values = ["All matches"] + [self.match_label(row) for row in matches]
        match_var = tk.StringVar(value=match_values[1] if len(match_values) > 1 else "All matches")
        ttk.Label(controls, text="Match").grid(row=0, column=0, padx=4)
        match_combo = ttk.Combobox(
            controls,
            textvariable=match_var,
            values=match_values,
            state="readonly",
            width=36,
        )
        match_combo.grid(row=0, column=1, padx=4)
        states = sorted(
            {str(row["state_ref"]).strip() for row in users if row["state_ref"]},
            key=str.casefold,
        )
        state_var = tk.StringVar(value="ALL")
        ttk.Label(controls, text="State/Ref").grid(row=1, column=0, padx=4, pady=(7, 0))
        state_combo = ttk.Combobox(
            controls,
            textvariable=state_var,
            values=["ALL"] + states,
            state="readonly",
            width=36,
        )
        state_combo.grid(row=1, column=1, padx=4, pady=(7, 0))
        actual_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            controls,
            text="Actual Amount",
            variable=actual_var,
        ).grid(row=0, column=2, padx=8)
        table_frame = tk.Frame(window, bg=COLORS["panel"])
        table_frame.pack(fill="both", expand=True, padx=10, pady=8)
        tree = self.make_tree(
            table_frame,
            (
                ("name", "NAME", 160),
                ("charge", "CH", 90),
                ("a", "A", 120),
                ("b", "B", 120),
            ),
            height=18,
        )
        actions = tk.Frame(window, bg=COLORS["background"])
        actions.pack(fill="x", padx=10, pady=(0, 10))

        def refresh() -> None:
            match = next(
                (row for row in matches if self.match_label(row) == match_var.get()),
                None,
            )
            match_id = None if match is None else int(match["id"])
            try:
                entries = DB.list_entries(match_id=match_id, entry_type="Match")
            except sqlite3.Error as error:
                messagebox.showerror("Could not refresh account", str(error), parent=window)
                return
            state_filter = state_var.get()
            selected_users = [
                user
                for user in users
                if state_filter == "ALL" or user["state_ref"] == state_filter
            ]
            grouped: dict[int, dict[str, float]] = {
                int(user["id"]): {"charge": 0.0}
                for user in selected_users
            }
            for entry in entries:
                user_id = int(entry["user_id"])
                if user_id in grouped:
                    grouped[user_id]["charge"] += float(entry["charge"])
            tree.delete(*tree.get_children())
            charge_total = 0.0
            for user in selected_users:
                account = grouped[int(user["id"])]
                charge_total += account["charge"]
                tree.insert(
                    "",
                    "end",
                    values=(
                        user["name"],
                        money(account["charge"]),
                        "Not calculated" if actual_var.get() else "",
                        "Not calculated" if actual_var.get() else "",
                    ),
                )
            if selected_users:
                tree.insert(
                    "",
                    "end",
                    values=(
                        "TOTAL",
                        money(charge_total),
                        "Not calculated" if actual_var.get() else "",
                        "Not calculated" if actual_var.get() else "",
                    ),
                    tags=("total",),
                )
                tree.tag_configure("total", font=("Tahoma", 8, "bold"))
            heading_var.set(
                "Account Status of Match - "
                + ("All matches" if match is None else self.match_label(match))
            )

        def print_account() -> None:
            self.report_tree_actions(tree, "User Account", window)

        ttk.Button(actions, text="Refresh", style="Accent.TButton", command=refresh).pack(side="left")
        ttk.Button(
            actions,
            text="Print",
            command=print_account,
        ).pack(side="right", padx=5)
        ttk.Button(
            actions,
            text="Export CSV",
            command=lambda: self.export_report_rows(
                "User Account", *self.report_tree_rows(tree), window
            ),
        ).pack(side="right", padx=5)
        ttk.Button(actions, text="Close", command=window.destroy).pack(side="right", padx=5)
        for widget in (match_combo, state_combo):
            widget.bind("<<ComboboxSelected>>", lambda _event: refresh())
        actual_var.trace_add("write", lambda *_args: refresh())
        refresh()


if __name__ == "__main__":
    BettingAssistant().mainloop()
