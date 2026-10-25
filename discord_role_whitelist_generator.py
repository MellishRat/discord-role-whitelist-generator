import json
import os
import subprocess
import sys
import threading
from queue import Queue, Empty
from whitelist_rules import OutputRule, build_lists, normalize_output_filename
from csv_loader import load_members_csv
from profile_manager import Profile, SftpSettings, load_profile, save_profile
from sftp_uploader import upload_lists, validate_settings, paramiko
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
import tkinter as tk
from tkinter import ttk

import pandas as pd

APP_TITLE = "Discord Role Whitelist Generator"
APP_SETTINGS_FILE = Path.home() / ".discord_role_whitelist_generator_settings.json"


class WhitelistGeneratorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1180x820")
        self.root.minsize(980, 650)

        self.csv_path = tk.StringVar()
        self.profile_path = tk.StringVar()
        self.profile_name = tk.StringVar(value="New Profile")
        self.name_column = tk.StringVar(value="Nickname")
        self.output_folder = tk.StringVar(value=str(Path.cwd() / "output"))
        self.dedupe_names = tk.BooleanVar(value=True)
        self.sort_names = tk.BooleanVar(value=True)

        self.sftp_enabled = tk.BooleanVar(value=False)
        self.sftp_host = tk.StringVar()
        self.sftp_port = tk.IntVar(value=22)
        self.sftp_username = tk.StringVar()
        self.sftp_remote_path = tk.StringVar()

        self.df: pd.DataFrame | None = None
        self.role_columns: list[str] = []
        self.output_rules: list[OutputRule] = []
        self.generated_content: dict[str, list[str]] = {}

        self._upload_events = Queue()
        self._upload_active = False
        self._build_ui()
        self.root.after(100, self._poll_upload_events)
        self.load_app_settings()

    def _build_ui(self):
        # The app can be taller than some screens once the SFTP panel is shown, so
        # the whole interface lives inside a vertically scrollable canvas.
        outer = ttk.Frame(self.root)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        self.scroll_canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0)
        self.scroll_canvas.grid(row=0, column=0, sticky="nsew")

        # Leave a little breathing room between the content and the scrollbar.
        self.main_scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=self.scroll_canvas.yview)
        self.main_scrollbar.grid(row=0, column=1, sticky="ns", padx=(8, 8), pady=8)
        self.scroll_canvas.configure(yscrollcommand=self.main_scrollbar.set)

        self.scroll_content = ttk.Frame(self.scroll_canvas, padding=(10, 10, 0, 10))
        self.scroll_window = self.scroll_canvas.create_window((0, 0), window=self.scroll_content, anchor="nw")

        self.scroll_content.bind("<Configure>", self._on_scroll_content_configure)
        self.scroll_canvas.bind("<Configure>", self._on_scroll_canvas_configure)
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)
        self.root.bind_all("<Button-4>", self._on_mousewheel)
        self.root.bind_all("<Button-5>", self._on_mousewheel)

        top = ttk.Frame(self.scroll_content, padding=(0, 0, 10, 8))
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top, text="CSV file:").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.csv_path).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(top, text="Browse CSV", command=self.browse_csv).grid(row=0, column=2, padx=3)
        ttk.Button(top, text="Load CSV", command=self.load_csv).grid(row=0, column=3, padx=3)

        ttk.Label(top, text="Profile:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Entry(top, textvariable=self.profile_path).grid(row=1, column=1, sticky="ew", padx=5, pady=(5, 0))
        ttk.Button(top, text="Load Profile", command=self.load_profile_dialog).grid(row=1, column=2, padx=3, pady=(5, 0))
        ttk.Button(top, text="Save Profile", command=self.save_profile_dialog).grid(row=1, column=3, padx=3, pady=(5, 0))
        top.columnconfigure(1, weight=1)

        main = ttk.PanedWindow(self.scroll_content, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=(0, 10), pady=5)

        left = ttk.Frame(main, padding=8)
        right = ttk.Frame(main, padding=8)
        main.add(left, weight=1)
        main.add(right, weight=2)

        self._build_profile_panel(left)
        self._build_preview_panel(right)

        bottom = ttk.Frame(self.scroll_content, padding=(0, 8, 10, 0))
        bottom.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(bottom, text="Generate Local Files", command=self.generate_files).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="Upload via SFTP", command=self.upload_sftp).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="Open Output Folder", command=lambda: self.open_folder(self.output_folder.get())).pack(side=tk.LEFT, padx=4)
        self.status = tk.StringVar(value="Load a CSV to begin.")
        ttk.Label(bottom, textvariable=self.status).pack(side=tk.LEFT, padx=12)

    def _on_scroll_content_configure(self, _event=None):
        self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))

    def _on_scroll_canvas_configure(self, event):
        # Keep the inner frame the same width as the canvas so horizontal scaling
        # still works, while vertical overflow uses the visible scrollbar.
        self.scroll_canvas.itemconfigure(self.scroll_window, width=event.width)

    def _on_mousewheel(self, event):
        # Windows/macOS use MouseWheel; Linux often uses Button-4/Button-5.
        if getattr(event, "num", None) == 4:
            self.scroll_canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            self.scroll_canvas.yview_scroll(1, "units")
        else:
            self.scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _build_profile_panel(self, parent):
        profile_box = ttk.LabelFrame(parent, text="Profile Settings", padding=8)
        profile_box.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(profile_box, text="Profile name:").grid(row=0, column=0, sticky="w")
        ttk.Entry(profile_box, textvariable=self.profile_name).grid(row=0, column=1, sticky="ew", padx=5)

        ttk.Label(profile_box, text="Name column:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.name_column_combo = ttk.Combobox(profile_box, textvariable=self.name_column, state="readonly")
        self.name_column_combo.grid(row=1, column=1, sticky="ew", padx=5, pady=(5, 0))

        ttk.Label(profile_box, text="Output folder:").grid(row=2, column=0, sticky="w", pady=(5, 0))
        ttk.Entry(profile_box, textvariable=self.output_folder).grid(row=2, column=1, sticky="ew", padx=5, pady=(5, 0))
        ttk.Button(profile_box, text="Browse", command=self.browse_output_folder).grid(row=2, column=2, pady=(5, 0))

        ttk.Checkbutton(profile_box, text="Remove duplicate names", variable=self.dedupe_names).grid(row=3, column=1, sticky="w", pady=(5, 0))
        ttk.Checkbutton(profile_box, text="Sort names A-Z", variable=self.sort_names).grid(row=4, column=1, sticky="w", pady=(2, 0))
        profile_box.columnconfigure(1, weight=1)

        role_box = ttk.LabelFrame(parent, text="Detected Roles", padding=8)
        role_box.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self.role_filter = tk.StringVar()
        self.role_filter.trace_add("write", lambda *_: self.refresh_role_list())
        ttk.Entry(role_box, textvariable=self.role_filter).pack(fill=tk.X, pady=(0, 5))
        self.role_list = tk.Listbox(role_box, selectmode=tk.EXTENDED, height=12, exportselection=False)
        self.role_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        role_scroll = ttk.Scrollbar(role_box, command=self.role_list.yview)
        role_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.role_list.config(yscrollcommand=role_scroll.set)

        buttons = ttk.Frame(parent)
        buttons.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(buttons, text="Add Rule", command=self.add_rule_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(buttons, text="Edit Rule", command=self.edit_selected_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(buttons, text="Delete Rule", command=self.delete_selected_rule).pack(side=tk.LEFT, padx=2)

        rule_box = ttk.LabelFrame(parent, text="Output Rules", padding=8)
        rule_box.pack(fill=tk.BOTH, expand=True)
        self.rule_tree = ttk.Treeview(rule_box, columns=("file", "must", "any", "not"), show="headings", height=8)
        self.rule_tree.heading("file", text="File")
        self.rule_tree.heading("must", text="Must have")
        self.rule_tree.heading("any", text="Any of")
        self.rule_tree.heading("not", text="Must not")
        self.rule_tree.column("file", width=130)
        self.rule_tree.column("must", width=180)
        self.rule_tree.column("any", width=140)
        self.rule_tree.column("not", width=150)
        self.rule_tree.pack(fill=tk.BOTH, expand=True)
        self.rule_tree.bind("<Double-1>", lambda _e: self.edit_selected_rule())

        sftp_box = ttk.LabelFrame(parent, text="Optional SFTP Upload Settings", padding=8)
        sftp_box.pack(fill=tk.X, pady=(8, 0))
        ttk.Checkbutton(sftp_box, text="Enable SFTP upload for this profile", variable=self.sftp_enabled).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(sftp_box, text="Host:").grid(row=1, column=0, sticky="w")
        ttk.Entry(sftp_box, textvariable=self.sftp_host).grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Label(sftp_box, text="Port:").grid(row=2, column=0, sticky="w")
        ttk.Entry(sftp_box, textvariable=self.sftp_port, width=8).grid(row=2, column=1, sticky="w", padx=5)
        ttk.Label(sftp_box, text="Username:").grid(row=3, column=0, sticky="w")
        ttk.Entry(sftp_box, textvariable=self.sftp_username).grid(row=3, column=1, sticky="ew", padx=5)
        ttk.Label(sftp_box, text="Remote path:").grid(row=4, column=0, sticky="w")
        ttk.Entry(sftp_box, textvariable=self.sftp_remote_path).grid(row=4, column=1, sticky="ew", padx=5)
        sftp_box.columnconfigure(1, weight=1)

    def _build_preview_panel(self, parent):
        preview_top = ttk.Frame(parent)
        preview_top.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(preview_top, text="Preview Lists", command=self.preview_lists).pack(side=tk.LEFT, padx=2)
        ttk.Button(preview_top, text="Clear Preview", command=self.clear_preview).pack(side=tk.LEFT, padx=2)
        ttk.Button(preview_top, text="Check Duplicates", command=self.check_duplicates).pack(side=tk.LEFT, padx=2)
        self.preview_summary = tk.StringVar(value="No preview yet.")
        ttk.Label(preview_top, textvariable=self.preview_summary).pack(side=tk.LEFT, padx=10)

        self.preview_tabs = ttk.Notebook(parent)
        self.preview_tabs.pack(fill=tk.BOTH, expand=True)

    def load_app_settings(self):
        try:
            if APP_SETTINGS_FILE.exists():
                settings = json.loads(APP_SETTINGS_FILE.read_text(encoding="utf-8"))
                if settings.get("last_csv"):
                    self.csv_path.set(settings["last_csv"])
                if settings.get("last_output_folder"):
                    self.output_folder.set(settings["last_output_folder"])
                if settings.get("last_profile"):
                    self.profile_path.set(settings["last_profile"])
        except Exception:
            pass

    def save_app_settings(self):
        try:
            settings = {
                "last_csv": self.csv_path.get(),
                "last_output_folder": self.output_folder.get(),
                "last_profile": self.profile_path.get(),
            }
            APP_SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        except Exception:
            pass

    normalize_output_filename = staticmethod(normalize_output_filename)

    def browse_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.csv_path.set(path)
            self.save_app_settings()

    def browse_output_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.output_folder.set(path)
            self.save_app_settings()

    def load_csv(self):
        path = self.csv_path.get().strip()
        if not path:
            messagebox.showwarning("Missing CSV", "Choose a CSV file first.")
            return
        try:
            self.df = load_members_csv(path)
        except Exception as exc:
            self.df = None
            messagebox.showerror("CSV Error", f"Could not load CSV:\n{exc}")
            return

        columns = list(self.df.columns)
        self.name_column_combo["values"] = columns
        if self.name_column.get() not in columns:
            if "Nickname" in columns:
                self.name_column.set("Nickname")
            elif "User" in columns:
                self.name_column.set("User")
            elif columns:
                self.name_column.set(columns[0])

        possible_non_roles = {"User", "ID", self.name_column.get()}
        self.role_columns = [c for c in columns if c not in possible_non_roles]
        self.refresh_role_list()
        self.status.set(f"Loaded {len(self.df)} rows and detected {len(self.role_columns)} possible role columns.")

    def refresh_role_list(self):
        query = self.role_filter.get().strip().lower()
        self.role_list.delete(0, tk.END)
        for role in self.role_columns:
            if not query or query in role.lower():
                self.role_list.insert(tk.END, role)

    def selected_roles_from_list(self) -> list[str]:
        return [self.role_list.get(i) for i in self.role_list.curselection()]

    def add_rule_dialog(self):
        saved_index = {"value": None}

        def save_or_update(rule: OutputRule):
            if self.duplicate_rule_filename_exists(rule.file_name, exclude_index=saved_index["value"]):
                self.warn_duplicate_rule_filename(rule.file_name)
                return False
            if saved_index["value"] is None:
                self.output_rules.append(rule)
                saved_index["value"] = len(self.output_rules) - 1
                self.status.set(f"Added rule: {rule.file_name}")
            else:
                self.output_rules[saved_index["value"]] = rule
                self.status.set(f"Updated rule: {rule.file_name}")
            self.refresh_rules()
            self.rule_tree.selection_set(str(saved_index["value"]))
            return True

        def start_fresh_rule():
            # The dialog stays open after saving so users can quickly add several rules.
            # Clicking New Rule must reset the saved index, otherwise the next save
            # would edit the rule that was just saved instead of appending a new one.
            saved_index["value"] = None
            self.rule_tree.selection_remove(self.rule_tree.selection())

        RuleDialog(
            self.root,
            self.role_columns,
            selected_roles=self.selected_roles_from_list(),
            on_save=save_or_update,
            on_new=start_fresh_rule,
            normalize_filename=self.normalize_output_filename,
        )


    def edit_selected_rule(self):
        selected = self.rule_tree.selection()
        if not selected:
            messagebox.showinfo("No rule selected", "Select an output rule first.")
            return
        index = int(selected[0])
        RuleDialog(
            self.root,
            self.role_columns,
            existing=self.output_rules[index],
            on_save=lambda rule, i=index: self._replace_rule_from_dialog(i, rule),
            normalize_filename=self.normalize_output_filename,
            edit_mode=True,
        )

    def _replace_rule_from_dialog(self, index: int, rule: OutputRule):
        if self.duplicate_rule_filename_exists(rule.file_name, exclude_index=index):
            self.warn_duplicate_rule_filename(rule.file_name)
            return False
        self.output_rules[index] = rule
        self.refresh_rules()
        self.status.set(f"Updated rule: {rule.file_name}")
        return True

    def delete_selected_rule(self):
        selected = self.rule_tree.selection()
        if not selected:
            return
        index = int(selected[0])
        del self.output_rules[index]
        self.refresh_rules()

    def refresh_rules(self):
        for item in self.rule_tree.get_children():
            self.rule_tree.delete(item)
        for i, rule in enumerate(self.output_rules):
            self.rule_tree.insert("", tk.END, iid=str(i), values=(
                rule.file_name,
                ", ".join(rule.must_have_roles),
                ", ".join(rule.any_of_roles),
                ", ".join(rule.must_not_have_roles),
            ))

    def duplicate_rule_filename_exists(self, file_name: str, exclude_index: int | None = None) -> bool:
        """Return True if another output rule already uses this TXT filename."""
        target = self.normalize_output_filename(file_name).casefold()
        for index, rule in enumerate(self.output_rules):
            if exclude_index is not None and index == exclude_index:
                continue
            if self.normalize_output_filename(rule.file_name).casefold() == target:
                return True
        return False

    def warn_duplicate_rule_filename(self, file_name: str):
        messagebox.showwarning(
            "Duplicate output name",
            f"An output rule called '{self.normalize_output_filename(file_name)}' already exists.\n\n"
            "Each output rule needs a unique file name, otherwise one list would overwrite the other when generated.",
        )

    def build_lists(self) -> dict[str, list[str]]:
        return build_lists(self.df, self.output_rules, self.name_column.get(),
                           self.dedupe_names.get(), self.sort_names.get())

    def preview_lists(self):
        try:
            self.generated_content = self.build_lists()
        except Exception as exc:
            messagebox.showerror("Preview Error", str(exc))
            return
        self.clear_preview()
        total = 0
        for file_name, names in self.generated_content.items():
            total += len(names)
            frame = ttk.Frame(self.preview_tabs)
            self.preview_tabs.add(frame, text=f"{file_name} ({len(names)})")
            text = tk.Text(frame, wrap=tk.NONE)
            text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scroll = ttk.Scrollbar(frame, command=text.yview)
            scroll.pack(side=tk.RIGHT, fill=tk.Y)
            text.config(yscrollcommand=scroll.set)
            text.insert(tk.END, "\n".join(names))
        self.preview_summary.set(f"Generated {len(self.generated_content)} lists, {total} total names across all files.")
        self.status.set("Preview ready.")

    def check_duplicates(self):
        try:
            content = self.build_lists()
        except Exception as exc:
            messagebox.showerror("Duplicate Check Error", str(exc))
            return
        seen: dict[str, list[str]] = {}
        for file_name, names in content.items():
            for name in names:
                seen.setdefault(name, []).append(file_name)
        duplicates = {name: files for name, files in seen.items() if len(files) > 1}
        if not duplicates:
            messagebox.showinfo("Duplicate Check", "No duplicate names across output files.")
            return
        lines = []
        for name, files in sorted(duplicates.items(), key=lambda item: item[0].casefold()):
            lines.append(f"{name}: {', '.join(files)}")
        preview = "\n".join(lines[:80])
        extra = "" if len(lines) <= 80 else f"\n\n...and {len(lines) - 80} more."
        messagebox.showwarning("Duplicate Names Found", f"Found {len(duplicates)} names appearing in multiple files:\n\n{preview}{extra}")

    def clear_preview(self):
        for tab in self.preview_tabs.tabs():
            self.preview_tabs.forget(tab)
        self.preview_summary.set("No preview yet.")

    def generate_files(self):
        try:
            self.generated_content = self.build_lists()
        except Exception as exc:
            messagebox.showerror("Generate Error", str(exc))
            return
        out_dir = Path(self.output_folder.get()).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        target_paths = [out_dir / self.normalize_output_filename(file_name) for file_name in self.generated_content]
        existing = [p.name for p in target_paths if p.exists()]
        if existing:
            preview = "\n".join(existing[:20])
            extra = "" if len(existing) <= 20 else f"\n...and {len(existing) - 20} more."
            if not messagebox.askyesno("Overwrite existing files?", f"These files already exist and will be replaced:\n\n{preview}{extra}\n\nContinue?"):
                self.status.set("Generate cancelled.")
                return
        for file_name, names in self.generated_content.items():
            safe_name = self.normalize_output_filename(file_name)
            (out_dir / safe_name).write_text("\n".join(names), encoding="utf-8")
        self.status.set(f"Saved {len(self.generated_content)} files to {out_dir}")
        self.save_app_settings()
        messagebox.showinfo("Done", f"Saved {len(self.generated_content)} files to:\n{out_dir}")

    def upload_sftp(self):
        if not self.sftp_enabled.get():
            messagebox.showwarning("SFTP disabled", "Enable SFTP in the profile settings first.")
            return
        if paramiko is None:
            messagebox.showerror("Missing dependency", "Paramiko is not installed. Run: pip install paramiko")
            return
        if self._upload_active:
            messagebox.showinfo("Upload in progress", "Wait for the current upload to finish.")
            return
        try:
            # Snapshot every Tk variable and generate current rules on the main thread.
            content = self.build_lists()
            settings = SftpSettings(
                enabled=True, host=self.sftp_host.get().strip(),
                port=int(self.sftp_port.get()), username=self.sftp_username.get().strip(),
                remote_path=self.sftp_remote_path.get().strip())
            validate_settings(settings)
            output_folder = self.output_folder.get()
        except Exception as exc:
            messagebox.showerror("Upload Error", str(exc))
            return
        password = simpledialog.askstring("SFTP Password", "Enter SFTP password:", show="*")
        if not password:
            return
        self.generated_content = content
        self._upload_active = True
        self.status.set("Uploading via SFTP...")
        threading.Thread(target=self._upload_sftp_worker,
                         args=(settings, password, content, output_folder), daemon=True).start()

    def _upload_sftp_worker(self, settings, password, content, output_folder):
        # Only plain Python data crosses the thread boundary; no Tk calls here.
        try:
            upload_lists(settings, password, content, output_folder,
                         lambda text: self._upload_events.put(("progress", text)))
            self._upload_events.put(("complete", "All generated files were uploaded."))
        except Exception as exc:
            self._upload_events.put(("error", str(exc)))

    def _poll_upload_events(self):
        try:
            while True:
                kind, text = self._upload_events.get_nowait()
                if kind == "progress":
                    self.status.set(text)
                else:
                    self._upload_active = False
                    if kind == "error":
                        self.status.set("Upload failed.")
                        messagebox.showerror("SFTP Upload Error", text)
                    else:
                        self.status.set("Upload complete.")
                        messagebox.showinfo("Upload Complete", text)
        except Empty:
            pass
        self.root.after(100, self._poll_upload_events)

    def current_profile(self) -> Profile:
        return Profile(
            profile_name=self.profile_name.get(),
            name_column=self.name_column.get(),
            output_folder=self.output_folder.get(),
            dedupe_names=self.dedupe_names.get(),
            sort_names=self.sort_names.get(),
            outputs=self.output_rules,
            sftp=SftpSettings(
                enabled=self.sftp_enabled.get(),
                host=self.sftp_host.get(),
                port=int(self.sftp_port.get()),
                username=self.sftp_username.get(),
                remote_path=self.sftp_remote_path.get(),
            ),
        )

    def apply_profile(self, profile: Profile):
        self.profile_name.set(profile.profile_name)
        self.name_column.set(profile.name_column)
        self.output_folder.set(profile.output_folder)
        self.dedupe_names.set(profile.dedupe_names)
        self.sort_names.set(profile.sort_names)
        self.output_rules = profile.outputs
        self.sftp_enabled.set(profile.sftp.enabled)
        self.sftp_host.set(profile.sftp.host)
        self.sftp_port.set(profile.sftp.port)
        self.sftp_username.set(profile.sftp.username)
        self.sftp_remote_path.set(profile.sftp.remote_path)
        self.refresh_rules()

    def save_profile_dialog(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON profile", "*.json"), ("All files", "*.*")],
            initialfile="whitelist_profile.json",
        )
        if not path:
            return
        profile = self.current_profile()
        save_profile(path, profile)
        self.profile_path.set(path)
        self.save_app_settings()
        self.status.set(f"Saved profile: {path}")

    def load_profile_dialog(self):
        path = filedialog.askopenfilename(filetypes=[("JSON profile", "*.json"), ("All files", "*.*")])
        if path:
            self.load_profile(path)

    def load_profile(self, path: str):
        try:
            profile = load_profile(path)
            self.apply_profile(profile)
            self.profile_path.set(path)
            self.save_app_settings()
            self.status.set(f"Loaded profile: {path}")
        except Exception as exc:
            messagebox.showerror("Profile Error", f"Could not load profile:\n{exc}")

    @staticmethod
    def open_folder(path: str):
        p = Path(path).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(p)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])


class RuleDialog:
    def __init__(self, parent, roles: list[str], existing: OutputRule | None = None, selected_roles: list[str] | None = None, on_save=None, on_new=None, normalize_filename=None, edit_mode: bool = False):
        self.roles = roles
        self.result: OutputRule | None = None
        self.on_save = on_save
        self.on_new = on_new
        self.normalize_filename = normalize_filename or (lambda name: name)
        self.edit_mode = edit_mode
        self.top = tk.Toplevel(parent)
        self.top.title("Edit Output Rule" if edit_mode else "New Output Rule")
        self.top.geometry("760x540")
        self.top.transient(parent)
        self.top.grab_set()

        existing = existing or OutputRule(file_name="New_List")
        selected_roles = selected_roles or []
        self.file_name = tk.StringVar(value=existing.file_name)
        self.filter_var = tk.StringVar()

        top_frame = ttk.Frame(self.top, padding=10)
        top_frame.pack(fill=tk.X)
        ttk.Label(top_frame, text="Output name (.txt is added automatically):").pack(side=tk.LEFT)
        ttk.Entry(top_frame, textvariable=self.file_name).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        body = ttk.Frame(self.top, padding=10)
        body.pack(fill=tk.BOTH, expand=True)

        available_box = ttk.LabelFrame(body, text="Available roles", padding=6)
        available_box.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ttk.Entry(available_box, textvariable=self.filter_var).pack(fill=tk.X, pady=(0, 5))
        self.available = tk.Listbox(available_box, selectmode=tk.EXTENDED, exportselection=False)
        self.available.pack(fill=tk.BOTH, expand=True)

        action_box = ttk.Frame(body)
        action_box.grid(row=0, column=1, sticky="ns", padx=6)
        ttk.Button(action_box, text="Must have →", command=lambda: self.add_to(self.must_have)).pack(fill=tk.X, pady=4)
        ttk.Button(action_box, text="Any of →", command=lambda: self.add_to(self.any_of)).pack(fill=tk.X, pady=4)
        ttk.Button(action_box, text="Must not →", command=lambda: self.add_to(self.must_not)).pack(fill=tk.X, pady=4)
        ttk.Separator(action_box).pack(fill=tk.X, pady=10)
        ttk.Button(action_box, text="Remove selected", command=self.remove_selected).pack(fill=tk.X, pady=4)

        selected_box = ttk.Frame(body)
        selected_box.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        self.must_have = self._make_role_list(selected_box, "Must have roles")
        self.any_of = self._make_role_list(selected_box, "Any one of these roles")
        self.must_not = self._make_role_list(selected_box, "Must not have roles")

        body.columnconfigure(0, weight=1)
        body.columnconfigure(2, weight=1)
        body.rowconfigure(0, weight=1)

        bottom = ttk.Frame(self.top, padding=10)
        bottom.pack(fill=tk.X)
        ttk.Button(bottom, text="Close", command=self.top.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bottom, text="New Rule", command=self.new_rule).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bottom, text="Save Rule", command=self.save).pack(side=tk.RIGHT, padx=4)
        self.dialog_status = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.dialog_status).pack(side=tk.LEFT)

        self.filter_var.trace_add("write", lambda *_: self.refresh_available())
        self.refresh_available()
        for role in existing.must_have_roles or selected_roles:
            self._insert_unique(self.must_have, role)
        for role in existing.any_of_roles:
            self._insert_unique(self.any_of, role)
        for role in existing.must_not_have_roles:
            self._insert_unique(self.must_not, role)

    def _make_role_list(self, parent, title):
        box = ttk.LabelFrame(parent, text=title, padding=5)
        box.pack(fill=tk.BOTH, expand=True, pady=3)
        lb = tk.Listbox(box, selectmode=tk.EXTENDED, height=5, exportselection=False)
        lb.pack(fill=tk.BOTH, expand=True)
        return lb

    def refresh_available(self):
        query = self.filter_var.get().strip().lower()
        self.available.delete(0, tk.END)
        for role in self.roles:
            if not query or query in role.lower():
                self.available.insert(tk.END, role)

    def add_to(self, target: tk.Listbox):
        for index in self.available.curselection():
            self._insert_unique(target, self.available.get(index))

    @staticmethod
    def _insert_unique(listbox: tk.Listbox, value: str):
        existing = list(listbox.get(0, tk.END))
        if value not in existing:
            listbox.insert(tk.END, value)

    def remove_selected(self):
        for lb in (self.must_have, self.any_of, self.must_not):
            for index in reversed(lb.curselection()):
                lb.delete(index)

    @staticmethod
    def values(lb: tk.Listbox) -> list[str]:
        return list(lb.get(0, tk.END))

    def new_rule(self):
        self.file_name.set("New_List")
        self.filter_var.set("")
        for lb in (self.must_have, self.any_of, self.must_not):
            lb.delete(0, tk.END)
        self.refresh_available()
        if self.on_new:
            self.on_new()
        self.status_text("Ready for a new rule. The next save will add a new output rule.")

    def status_text(self, message: str):
        if not hasattr(self, "dialog_status"):
            self.dialog_status = tk.StringVar(value="")
        self.dialog_status.set(message)

    def save(self):
        file_name = self.normalize_filename(self.file_name.get())
        if not file_name:
            messagebox.showwarning("Missing file name", "Enter an output name.")
            return
        self.file_name.set(Path(file_name).stem)
        self.result = OutputRule(
            file_name=file_name,
            must_have_roles=self.values(self.must_have),
            any_of_roles=self.values(self.any_of),
            must_not_have_roles=self.values(self.must_not),
        )
        if self.on_save:
            saved_ok = self.on_save(self.result)
            if saved_ok is False:
                self.dialog_status.set("Not saved: output name is already in use.")
                return
        self.dialog_status.set(f"Saved: {self.result.file_name}. You can keep editing, click New Rule, or Close.")


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    app = WhitelistGeneratorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
