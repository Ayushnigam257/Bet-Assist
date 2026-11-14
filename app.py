import csv
import sqlite3
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from database import Database


APP_DIR = Path(__file__).resolve().parent
DB = Database(APP_DIR / "betting_assistant.db")

COLORS = {
    "background": "#f2f5f9",
    "panel": "#ffffff",
    "sidebar": "#17233a",
    "sidebar_active": "#293b5c",
    "text": "#1b2638",
    "muted": "#66758a",
    "accent": "#3169d5",
    "border": "#dce3ed",
    "success": "#e6f5ee",
}


def money(value: float) -> str:
    return f"{value:,.2f}"


class BettingAssistant(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Betting Assistant")
        self.geometry("1320x820")
        self.minsize(1120, 700)
        self.configure(bg=COLORS["background"])

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS["background"])
        style.configure("Card.TFrame", background=COLORS["panel"])
        style.configure(
            "TLabel",
            background=COLORS["background"],
            foreground=COLORS["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Card.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Title.TLabel",
            background=COLORS["background"],
            foreground=COLORS["text"],
            font=("Segoe UI Semibold", 20),
        )
        style.configure(
            "Muted.TLabel",
            background=COLORS["background"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "TButton", font=("Segoe UI", 9), padding=(10, 6)
        )
        style.configure(
            "Accent.TButton",
            background=COLORS["accent"],
            foreground="#ffffff",
            padding=(12, 7),
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#2457b8"), ("disabled", "#9aaed2")],
        )
        style.configure(
            "Treeview",
            background="#ffffff",
            fieldbackground="#ffffff",
            foreground=COLORS["text"],
            rowheight=27,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Treeview.Heading",
            background="#e9eef6",
            foreground=COLORS["text"],
            font=("Segoe UI Semibold", 9),
            padding=(6, 6),
        )

        self.match_rows: list[sqlite3.Row] = []
        self.user_rows: list[sqlite3.Row] = []
        self.active_nav: tk.Button | None = None

        shell = tk.Frame(self, bg=COLORS["background"])
        shell.pack(fill="both", expand=True)
        self.sidebar = tk.Frame(shell, bg=COLORS["sidebar"], width=205)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self.content = tk.Frame(shell, bg=COLORS["background"])
        self.content.pack(side="left", fill="both", expand=True)

        tk.Label(
            self.sidebar,
            text="BETTING\nASSISTANT",
            justify="left",
            bg=COLORS["sidebar"],
            fg="#ffffff",
            font=("Segoe UI Semibold", 16),
            padx=22,
            pady=27,
        ).pack(anchor="w")
        tk.Label(
            self.sidebar,
            text="MANAGE",
            bg=COLORS["sidebar"],
            fg="#8fa2bf",
            font=("Segoe UI Semibold", 8),
            padx=22,
            pady=8,
        ).pack(anchor="w")

        self.nav_buttons: dict[str, tk.Button] = {}
        for label in ("Dashboard", "Matches", "Users", "Entries", "Results", "Reports"):
            button = tk.Button(
                self.sidebar,
                text=f"   {label}",
                anchor="w",
                relief="flat",
                bd=0,
                padx=14,
                pady=11,
                bg=COLORS["sidebar"],
                fg="#d7e0ef",
                activebackground=COLORS["sidebar_active"],
                activeforeground="#ffffff",
                font=("Segoe UI", 10),
                command=lambda page=label: self.show_page(page),
            )
            button.pack(fill="x", padx=10, pady=2)
            self.nav_buttons[label] = button
        tk.Label(
            self.sidebar,
            text="Local database\nSaved on this computer",
            justify="left",
            bg=COLORS["sidebar"],
            fg="#8fa2bf",
            font=("Segoe UI", 8),
            padx=22,
            pady=20,
        ).pack(side="bottom", anchor="w")
        self.show_page("Dashboard")

    def page_header(self, title: str, subtitle: str) -> tk.Frame:
        header = tk.Frame(self.content, bg=COLORS["background"])
        header.pack(fill="x", padx=28, pady=(23, 16))
        ttk.Label(header, text=title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text=subtitle, style="Muted.TLabel").pack(
            anchor="w", pady=(3, 0)
        )
        return header

    def show_page(self, name: str) -> None:
        for widget in self.content.winfo_children():
            widget.destroy()
        for label, button in self.nav_buttons.items():
            button.configure(
                bg=COLORS["sidebar_active"] if label == name else COLORS["sidebar"]
            )
        page = {
            "Dashboard": self.build_dashboard,
            "Matches": self.build_matches,
            "Users": self.build_users,
            "Entries": self.build_entries,
            "Results": self.build_results,
            "Reports": self.build_reports,
        }[name]
        page()

    @staticmethod
    def make_tree(
        parent: tk.Widget,
        columns: tuple[tuple[str, str, int], ...],
        height: int = 12,
    ) -> ttk.Treeview:
        tree = ttk.Treeview(
            parent,
            columns=tuple(column[0] for column in columns),
            show="headings",
            height=height,
            selectmode="browse",
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

    def build_dashboard(self) -> None:
        self.page_header("Dashboard", "Overview of matches, users, and today's entries")
        metrics = DB.dashboard_metrics()
        cards = tk.Frame(self.content, bg=COLORS["background"])
        cards.pack(fill="x", padx=28)
        card_data = (
            ("OPEN MATCHES", str(metrics["open_matches"])),
            ("USERS", str(metrics["users"])),
            ("ENTRIES TODAY", str(metrics["today_entries"])),
            ("AMOUNT TODAY", money(float(metrics["today_amount"]))),
        )
        for index, (caption, value) in enumerate(card_data):
            card = tk.Frame(
                cards,
                bg=COLORS["panel"],
                highlightbackground=COLORS["border"],
                highlightthickness=1,
                padx=18,
                pady=16,
            )
            card.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 10, 0))
            cards.grid_columnconfigure(index, weight=1)
            tk.Label(
                card,
                text=caption,
                bg=COLORS["panel"],
                fg=COLORS["muted"],
                font=("Segoe UI Semibold", 8),
            ).pack(anchor="w")
            tk.Label(
                card,
                text=value,
                bg=COLORS["panel"],
                fg=COLORS["text"],
                font=("Segoe UI Semibold", 19),
            ).pack(anchor="w", pady=(8, 0))

        recent = tk.Frame(self.content, bg=COLORS["background"])
        recent.pack(fill="both", expand=True, padx=28, pady=20)
        tk.Label(
            recent,
            text="Recent entries",
            bg=COLORS["background"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 13),
        ).pack(anchor="w", pady=(0, 10))
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
        container.pack(fill="both", expand=True, padx=28, pady=(0, 24))

        form = tk.LabelFrame(
            container,
            text="Match details",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            padx=14,
            pady=12,
            font=("Segoe UI Semibold", 10),
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
        ttk.Button(button_row, text="Save match", style="Accent.TButton", command=self.save_match).pack(side="left")
        ttk.Button(button_row, text="Clear", command=self.clear_match_form).pack(side="left", padx=7)
        ttk.Button(button_row, text="Delete selected", command=self.delete_match).pack(side="left")

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
        )
        self.matches_tree.bind("<<TreeviewSelect>>", self.on_match_selected)
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
        self.match_code_var.set(str(row["code"]))
        self.match_date_var.set(row["match_date"])
        self.match_comment_var.set(row["comment"])
        self.match_teams_var.set(row["teams"])

    def clear_match_form(self) -> None:
        self.match_id = None
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

    def build_users(self) -> None:
        self.page_header(
            "Users & references",
            "Maintain contact details, commission references, limits, and permissions",
        )
        container = tk.Frame(self.content, bg=COLORS["background"])
        container.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        actions = tk.Frame(container, bg=COLORS["background"])
        actions.pack(fill="x", pady=(0, 12))
        ttk.Button(actions, text="Add user", style="Accent.TButton", command=lambda: self.open_user_form(None)).pack(side="left")
        ttk.Button(actions, text="Edit selected", command=self.edit_user).pack(side="left", padx=7)
        ttk.Button(actions, text="Delete selected", command=self.delete_user).pack(side="left")

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
        )
        self.users_tree.bind("<Double-1>", lambda _event: self.edit_user())
        self.refresh_users()

    def refresh_users(self) -> None:
        self.user_rows = DB.list_users()
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

        def section(title: str, fields: tuple[tuple[str, str], ...], columns: int = 2) -> None:
            frame = tk.LabelFrame(
                inner,
                text=title,
                bg=COLORS["panel"],
                fg=COLORS["text"],
                padx=12,
                pady=10,
                font=("Segoe UI Semibold", 9),
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
            font=("Segoe UI Semibold", 9),
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
            self.refresh_users()
            window.destroy()

        ttk.Button(button_row, text="Save user", style="Accent.TButton", command=save).pack(side="left")
        ttk.Button(button_row, text="Cancel", command=window.destroy).pack(side="left", padx=8)

    def build_entries(self) -> None:
        self.page_header(
            "Entry panel", "Record match, session, or meter transactions"
        )
        container = tk.Frame(self.content, bg=COLORS["background"])
        container.pack(fill="both", expand=True, padx=28, pady=(0, 22))
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
        )
        self.team_combo: ttk.Combobox | None = None
        self.user_combo: ttk.Combobox | None = None
        for index, (label, key, kind) in enumerate(fields):
            row_index, col_index = divmod(index, 6)
            cell = tk.Frame(form, bg=COLORS["panel"])
            cell.grid(row=row_index, column=col_index, sticky="w", padx=(0, 8), pady=4)
            ttk.Label(cell, text=label).pack(anchor="w", pady=(0, 3))
            if kind == "combo":
                options = {
                    "type": ("Match", "Session", "Meter"),
                    "mode": ("A", "B", "Back", "Lay"),
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
            else:
                ttk.Entry(cell, textvariable=self.entry_vars[key], width=17).pack(anchor="w")

        actions = tk.Frame(form, bg=COLORS["panel"])
        actions.grid(row=2, column=0, columnspan=6, sticky="w", pady=(10, 0))
        ttk.Button(actions, text="Save entry", style="Accent.TButton", command=self.save_entry).pack(side="left")
        ttk.Button(actions, text="Clear", command=self.clear_entry_form).pack(side="left", padx=7)
        ttk.Button(actions, text="Delete selected", command=self.delete_entry).pack(side="left")

        table = tk.Frame(container, bg=COLORS["panel"])
        table.pack(fill="both", expand=True)
        self.entries_tree = self.make_tree(
            table,
            (
                ("date", "DATE", 95),
                ("type", "TYPE", 85),
                ("patti", "P NO.", 65),
                ("rate", "RATE", 80),
                ("amount", "AMOUNT", 95),
                ("mode", "MODE", 75),
                ("team", "TEAM", 100),
                ("user", "NAME", 145),
                ("session", "SESSION", 115),
                ("runs", "RUNS", 70),
                ("yes_no", "Y/N", 55),
            ),
        )
        self.entries_tree.bind("<<TreeviewSelect>>", self.on_entry_selected)
        self.entry_total_var = tk.StringVar()
        ttk.Label(container, textvariable=self.entry_total_var).pack(anchor="e", pady=(7, 0))
        self.update_team_choices()
        self.refresh_entries()

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

    def refresh_entries(self) -> None:
        if not hasattr(self, "entries_tree"):
            return
        match_id = self.selected_match_id()
        rows = DB.list_entries(match_id=match_id)
        self.entries_tree.delete(*self.entries_tree.get_children())
        for row in rows:
            self.entries_tree.insert(
                "", "end", iid=str(row["id"]),
                values=(
                    row["entry_date"],
                    row["entry_type"],
                    row["patti_number"],
                    money(row["rate"]),
                    money(row["amount"]),
                    row["mode"],
                    row["team"],
                    row["user_name"],
                    row["session"],
                    row["runs"],
                    row["yes_no"],
                ),
            )
        total = sum(float(row["amount"]) for row in rows)
        self.entry_total_var.set(
            f"{len(rows)} entries     Total amount: {money(total)}"
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

    def clear_entry_form(self) -> None:
        self.entry_id = None
        for key, variable in self.entry_vars.items():
            variable.set(date.today().isoformat() if key == "date" else "")
        self.entry_vars["type"].set("Match")
        self.entry_vars["mode"].set("A")
        if self.entries_tree.selection():
            self.entries_tree.selection_remove(self.entries_tree.selection())

    def save_entry(self) -> None:
        try:
            match_id = self.selected_match_id()
            if match_id is None:
                raise ValueError("Select a match.")
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
            }
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
        if self.entry_id is None:
            messagebox.showinfo("Select an entry", "Choose an entry to delete.", parent=self)
            return
        if not messagebox.askyesno("Delete entry", "Delete this entry?", parent=self):
            return
        DB.delete_entry(self.entry_id)
        self.refresh_entries()
        self.clear_entry_form()

    def build_results(self) -> None:
        self.page_header(
            "Results", "Declare a match result or return it to undeclared status"
        )
        container = tk.Frame(self.content, bg=COLORS["background"])
        container.pack(fill="both", expand=True, padx=28, pady=(0, 24))
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

    def build_reports(self) -> None:
        self.page_header(
            "Reports & accounts",
            "Review match totals or inspect one user's transaction history",
        )
        container = tk.Frame(self.content, bg=COLORS["background"])
        container.pack(fill="both", expand=True, padx=28, pady=(0, 22))
        self.report_matches = DB.list_matches()
        self.report_users = DB.list_users()
        controls = tk.LabelFrame(
            container,
            text="Report filters",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            padx=12,
            pady=10,
        )
        controls.pack(fill="x", pady=(0, 12))
        self.report_mode_var = tk.StringVar(value="User accounts")
        self.report_match_var = tk.StringVar(value="All matches")
        self.report_user_var = tk.StringVar(value="All users")
        ttk.Label(controls, text="View").grid(row=0, column=0, padx=5)
        mode = ttk.Combobox(
            controls,
            textvariable=self.report_mode_var,
            values=("User accounts", "Individual entries"),
            state="readonly",
            width=20,
        )
        mode.grid(row=0, column=1, padx=5)
        ttk.Label(controls, text="Match").grid(row=0, column=2, padx=5)
        self.report_match_combo = ttk.Combobox(
            controls,
            textvariable=self.report_match_var,
            values=["All matches"] + [self.match_label(row) for row in self.report_matches],
            state="readonly",
            width=36,
        )
        self.report_match_combo.grid(row=0, column=3, padx=5)
        ttk.Label(controls, text="User").grid(row=0, column=4, padx=5)
        self.report_user_combo = ttk.Combobox(
            controls,
            textvariable=self.report_user_var,
            values=["All users"] + [self.user_label(row) for row in self.report_users],
            state="readonly",
            width=26,
        )
        self.report_user_combo.grid(row=0, column=5, padx=5)
        ttk.Button(controls, text="Refresh", style="Accent.TButton", command=self.refresh_report).grid(row=0, column=6, padx=8)
        ttk.Button(controls, text="Export CSV", command=self.export_report).grid(row=0, column=7, padx=4)
        mode.bind("<<ComboboxSelected>>", lambda _event: self.refresh_report())
        self.report_table = tk.Frame(container, bg=COLORS["panel"])
        self.report_table.pack(fill="both", expand=True)
        self.report_tree: ttk.Treeview | None = None
        self.report_total_var = tk.StringVar()
        ttk.Label(container, textvariable=self.report_total_var).pack(anchor="e", pady=(7, 0))
        self.refresh_report()

    def refresh_report(self) -> None:
        if not hasattr(self, "report_table"):
            return
        for widget in self.report_table.winfo_children():
            widget.destroy()
        match_label = self.report_match_var.get()
        match = next(
            (row for row in self.report_matches if self.match_label(row) == match_label),
            None,
        )
        user_label = self.report_user_var.get()
        user = next(
            (row for row in self.report_users if self.user_label(row) == user_label),
            None,
        )
        if self.report_mode_var.get() == "User accounts":
            columns = (
                ("name", "NAME", 200),
                ("entries", "ENTRIES", 95),
                ("amount", "GROSS AMOUNT", 145),
                ("team_amount", "TEAM AMOUNT (GROSS)", 190),
                ("match", "MATCH", 230),
            )
        else:
            columns = (
                ("date", "DATE", 100),
                ("match", "MATCH", 220),
                ("type", "TYPE", 95),
                ("user", "NAME", 160),
                ("team", "TEAM", 110),
                ("rate", "RATE", 95),
                ("amount", "AMOUNT", 115),
                ("mode", "MODE", 80),
                ("session", "SESSION", 120),
                ("runs", "RUNS", 75),
            )
        self.report_tree = self.make_tree(self.report_table, columns)
        entries = DB.list_entries(
            None if match is None else int(match["id"]),
            None if user is None else int(user["id"]),
        )
        total_amount = sum(float(row["amount"]) for row in entries)
        if self.report_mode_var.get() == "User accounts":
            grouped: dict[int, dict[str, Any]] = {}
            for entry in entries:
                item = grouped.setdefault(
                    int(entry["user_id"]),
                    {"name": entry["user_name"], "count": 0, "amount": 0.0, "teams": {}, "matches": set()},
                )
                item["count"] += 1
                item["amount"] += float(entry["amount"])
                team = entry["team"] or "Unassigned"
                item["teams"][team] = item["teams"].get(team, 0.0) + float(entry["amount"])
                item["matches"].add(f'{entry["match_code"]} {entry["match_comment"]}')
            for item in sorted(grouped.values(), key=lambda value: value["name"].casefold()):
                team_totals = ", ".join(
                    f"{team}: {money(amount)}"
                    for team, amount in sorted(item["teams"].items())
                )
                self.report_tree.insert(
                    "", "end",
                    values=(
                        item["name"],
                        item["count"],
                        money(item["amount"]),
                        team_totals,
                        ", ".join(sorted(item["matches"])),
                    ),
                )
        else:
            for entry in entries:
                self.report_tree.insert(
                    "", "end",
                    values=(
                        entry["entry_date"],
                        f'{entry["match_code"]} - {entry["match_comment"]}',
                        entry["entry_type"],
                        entry["user_name"],
                        entry["team"],
                        money(entry["rate"]),
                        money(entry["amount"]),
                        entry["mode"],
                        entry["session"],
                        entry["runs"],
                    ),
                )
        self.report_total_var.set(
            f"{len(entries)} entries     Gross amount: {money(total_amount)}"
        )

    def export_report(self) -> None:
        if self.report_tree is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export report",
            defaultextension=".csv",
            filetypes=(("CSV files", "*.csv"),),
        )
        if not path:
            return
        columns = self.report_tree["columns"]
        headers = [self.report_tree.heading(column, "text") for column in columns]
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(headers)
                for item in self.report_tree.get_children():
                    writer.writerow(self.report_tree.item(item, "values"))
        except OSError as error:
            messagebox.showerror("Export failed", str(error), parent=self)
            return
        messagebox.showinfo("Report exported", f"Saved CSV report to:\n{path}", parent=self)


if __name__ == "__main__":
    BettingAssistant().mainloop()
