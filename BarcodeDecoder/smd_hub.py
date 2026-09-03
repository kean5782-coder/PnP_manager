#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smd_hub.py — Главный Лаунчер и Единая Интегрированная Среда подготовки монтажа SMD.
Экосистема в стиле современного Dark Navy SaaS Dashboard:
1. Левый навигационный сайдбар с логотипом, активными плашками и древовидным списком шагов
2. Верхний хедер с горизонтальными вкладками и неоновым подчеркиванием
3. Рабочая область:
   - Dashboard (Обзор состояния заказа и метрики)
   - Шаг 1: Унификация BOM (по коду и описанию)
   - Шаг 2: Объединение P&P + BOM
   - Шаг 3: Финальная сверка и контроль качества
   - Доп. сервисы: Сравнение P&P, Сверка BOM, База соответствий, Barcode Decoder
4. Единый премиальный тёмно-синий стиль (Dark Navy SaaS Palette) без выбора светлой темы.
"""

import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd

# Пути к модулям экосистемы
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

UNIFICATION_DIR = os.path.join(CURRENT_DIR, "Unification")
if UNIFICATION_DIR not in sys.path:
    sys.path.insert(0, UNIFICATION_DIR)

PNP_DIR = os.path.join(CURRENT_DIR, "PnP_Manager")
if PNP_DIR not in sys.path:
    sys.path.insert(0, PNP_DIR)

import smd_engine
from smd_engine import (
    THEMES, ToolTip, get_system_theme, set_window_titlebar_theme,
    apply_ttk_theme, show_feedback_dialog, show_faq_dialog, style_widget_tree,
    enable_smooth_mousewheel, create_styled_toplevel
)

# Импортируем модуль цветных иконок
try:
    from smd_icons import get_icon, apply_label_icon, apply_button_icon
except Exception:
    try:
        import smd_icons
        get_icon = smd_icons.get_icon
        apply_label_icon = smd_icons.apply_label_icon
        apply_button_icon = smd_icons.apply_button_icon
    except Exception:
        def get_icon(*a, **k): return None
        def apply_label_icon(lbl, name, txt="", *a, **k): lbl.configure(text=txt)
        def apply_button_icon(btn, name, txt="", *a, **k):
            if txt: btn.configure(text=txt)

# Импортируем классы из Unification, PnP_Manager, smd_auth и smd_db
try:
    from smd_auth import AccountManager
except Exception:
    import smd_auth
    AccountManager = smd_auth.AccountManager

try:
    from smd_db import DatabaseManager, COMPONENT_CATEGORIES
except Exception:
    try:
        from Unification import DatabaseManager, COMPONENT_CATEGORIES
    except Exception:
        DatabaseManager = None
        COMPONENT_CATEGORIES = []

try:
    from Unification import DatabaseTab, CodeTab, DescriptionTab
except Exception as e:
    DatabaseTab = None
    CodeTab = None
    DescriptionTab = None
    print(f"Warning: Could not import Unification tabs directly: {e}")

try:
    from PnP_Manager import MergeTab, CheckTab, CompareTab, CompareBOMTab
except Exception as e:
    MergeTab = None
    CheckTab = None
    CompareTab = None
    CompareBOMTab = None
    print(f"Warning: Could not import PnP_Manager directly: {e}")


# =============================================================================
# Главное окно SMD Hub (Dark Navy SaaS Dashboard)
# =============================================================================
class SMDHubApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SMD Hub — Интегрированная среда подготовки монтажа SMD")

        # Размер окна: увеличен на 30% как fallback (1660x980) с центрированием
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        target_w = 1660
        target_h = 980
        win_w = min(target_w, max(1280, int(screen_w * 0.94)))
        win_h = min(target_h, max(760, int(screen_h * 0.88)))
        pos_x = max(0, (screen_w - win_w) // 2)
        pos_y = max(0, (screen_h - win_h) // 2 - 20)
        self.root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        self.root.minsize(1280, 720)

        # Автоматический разворот окна на весь экран при запуске (как на Скрине 2)
        try:
            self.root.state('zoomed')
        except Exception:
            pass

        # Тема оформления — строго Dark Navy SaaS
        self.current_theme = "dark"
        self.style = ttk.Style()
        self._setup_window_icon()

        # Инициализация пользователей (учетные записи в %APPDATA%\SMD_Hub\users.json)
        self.account_manager = AccountManager()

        # База данных для унификации (SQLite в %APPDATA%\SMD_Hub\database.db)
        self.db_manager = DatabaseManager() if DatabaseManager else None
        self.db_path = getattr(self.db_manager, "filename", "database.db")

        # Общие переменные сквозного заказа
        self.unified_bom_path = ""
        self.unified_bom_df = None
        self.unified_col_name = "Унифицированное наименование"

        self.merged_pnp_path = ""
        self.merged_pnp_df = None

        self.active_page_id = "dashboard"

        # Построение интерфейса
        self._build_ui()
        self.apply_theme("dark")
        enable_smooth_mousewheel(self.root)

    def _setup_window_icon(self):
        icon_path = os.path.join(CURRENT_DIR, "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

    def apply_theme(self, theme_name: str = "dark"):
        """Применяет тёмную SaaS тему ко всем элементам главного окна."""
        t = THEMES[theme_name]
        self.root.configure(bg=t["bg_app"])
        set_window_titlebar_theme(self.root, is_dark=True)
        apply_ttk_theme(self.style, "dark")
        style_widget_tree(self.root, "dark")

    # =========================================================================
    # Главная компоновка (Left Sidebar + Header + Main Content Area)
    # =========================================================================
    def _build_ui(self):
        t = THEMES["dark"]

        # Основной горизонтальный контейнер
        self.layout_frame = tk.Frame(self.root, bg=t["bg_app"])
        self.layout_frame.pack(fill=tk.BOTH, expand=True)

        # 1. Левый навигационный сайдбар
        self._build_sidebar(self.layout_frame)

        # Тонкий вертикальный разделитель сайдбара
        tk.Frame(self.layout_frame, width=1, bg=t["border"]).pack(side=tk.LEFT, fill=tk.Y)

        # 2. Правая рабочая область (Хедер + Контент)
        self.right_workspace = tk.Frame(self.layout_frame, bg=t["bg_app"])
        self.right_workspace.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Верхний хедер
        self._build_top_header(self.right_workspace)

        # Главный контейнер страниц
        self.pages_container = tk.Frame(self.right_workspace, bg=t["bg_app"])
        self.pages_container.pack(fill=tk.BOTH, expand=True, padx=16, pady=(8, 8))

        # Создаем страницы
        self.pages = {}
        self._build_page_dashboard(self.pages_container)
        self._build_page_step1(self.pages_container)
        self._build_page_step2(self.pages_container)
        self._build_page_step3(self.pages_container)
        self._build_page_compare_pnp(self.pages_container)
        self._build_page_compare_bom(self.pages_container)
        self._build_page_database(self.pages_container)

        # Показываем стартовую страницу Dashboard и актуализируем профиль
        self._update_user_display()
        self.show_page("dashboard")

    # =========================================================================
    # Левый сайдбар (Dark Navy SaaS Sidebar)
    # =========================================================================
    def _build_sidebar(self, parent):
        t = THEMES["dark"]
        self.sidebar_frame = tk.Frame(parent, width=240, bg=t["bg_sidebar"])
        self.sidebar_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar_frame.pack_propagate(False)

        # Логотип и кнопка сворачивания меню
        self.brand_frame = tk.Frame(self.sidebar_frame, bg=t["bg_sidebar"], padx=10, pady=12)
        self.brand_frame.pack(fill=tk.X)

        self.brand_left = tk.Frame(self.brand_frame, bg=t["bg_sidebar"])
        self.brand_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.logo_title = tk.Label(
            self.brand_left,
            font=("Segoe UI", 14, "bold"),
            bg=t["bg_sidebar"],
            fg=t["text_primary"]
        )
        apply_label_icon(self.logo_title, "lightning", "SMD Hub", size=24)
        self.logo_title.pack(anchor="w")

        self.logo_sub = tk.Label(
            self.brand_left,
            text="SMD Production Suite",
            font=("Segoe UI", 8),
            bg=t["bg_sidebar"],
            fg=t["text_muted"]
        )
        self.logo_sub.pack(anchor="w", pady=(1, 0))

        # Кнопка сворачивания/разворачивания сайдбара
        self.btn_collapse = tk.Button(
            self.brand_frame,
            text="◀",
            font=("Segoe UI", 8, "bold"),
            bg=t["bg_card"],
            fg=t["text_secondary"],
            activebackground=t["accent"],
            activeforeground="#ffffff",
            relief="flat",
            padx=7,
            pady=3,
            cursor="hand2",
            command=self.toggle_sidebar
        )
        self.btn_collapse.pack(side=tk.RIGHT)
        ToolTip(self.btn_collapse, "Свернуть боковое меню в компактный режим (иконки)")

        # Разделитель
        sep = tk.Frame(self.sidebar_frame, height=1, bg=t["border"])
        sep.pack(fill=tk.X, padx=14, pady=(0, 10))

        # Контейнер для навигационных элементов
        self.nav_items_frame = tk.Frame(self.sidebar_frame, bg=t["bg_sidebar"], padx=6)
        self.nav_items_frame.pack(fill=tk.BOTH, expand=True)

        self.nav_widgets = {}
        self.hovered_nav_id = None
        self.is_sidebar_collapsed = False

        # 1. Dashboard
        self._add_nav_item("dashboard", "Обзор (Dashboard)", "dashboard", lambda: self.show_page("dashboard"), "Обзор состояния и модулей")

        # 2. Сквозной заказ (Заголовок группы)
        self.group_label = tk.Label(
            self.nav_items_frame,
            text="СКВОЗНОЙ ЗАКАЗ",
            font=("Segoe UI", 8, "bold"),
            bg=t["bg_sidebar"],
            fg=t["text_muted"],
            anchor="w",
            padx=10,
            pady=8
        )
        self.group_label.pack(fill=tk.X, pady=(6, 2))

        # Поддерево шагов с точками-маркерами (Sub-tree timeline)
        self.tree_container = tk.Frame(self.nav_items_frame, bg=t["bg_sidebar"])
        self.tree_container.pack(fill=tk.X, padx=(4, 0))

        self._add_nav_subitem(self.tree_container, "step1", "1. Унификация BOM", "step1", lambda: self.show_page("step1"), "Шаг 1: Унификация спецификации (BOM)")
        self._add_nav_subitem(self.tree_container, "step2", "2. Объединение P&P", "step2", lambda: self.show_page("step2"), "Шаг 2: Объединение координат расстановщика")
        self._add_nav_subitem(self.tree_container, "step3", "3. Финальная сверка", "step3", lambda: self.show_page("step3"), "Шаг 3: Финальный аудит и сверка")

        # 3. Сервисные модули
        self.group_label2 = tk.Label(
            self.nav_items_frame,
            text="СЕРВИСЫ И БАЗЫ",
            font=("Segoe UI", 8, "bold"),
            bg=t["bg_sidebar"],
            fg=t["text_muted"],
            anchor="w",
            padx=10,
            pady=8
        )
        self.group_label2.pack(fill=tk.X, pady=(10, 2))

        self._add_nav_item("compare_pnp", "Сравнение P&P", "compare_pnp", lambda: self.show_page("compare_pnp"), "Сравнение двух файлов координат P&P")
        self._add_nav_item("compare_bom", "Сверка BOM", "compare_bom", lambda: self.show_page("compare_bom"), "Сверка двух спецификаций BOM")
        self._add_nav_item("database", "База данных", "database", lambda: self.show_page("database"), "Справочник замен (database.db)")

        # Привязка сброса наведения при выходе мыши из сайдбара
        self.sidebar_frame.bind("<Leave>", self._on_sidebar_leave)
        self.nav_items_frame.bind("<Leave>", self._on_sidebar_leave)
        self.tree_container.bind("<Leave>", self._on_sidebar_leave)

        # Нижняя плашка пользователя (интерактивная, с возможностью смены аккаунта)
        sep_user = tk.Frame(self.sidebar_frame, height=1, bg=t["border"])
        sep_user.pack(side=tk.BOTTOM, fill=tk.X, padx=14, pady=(0, 6))

        user_card = tk.Frame(self.sidebar_frame, bg=t["bg_sidebar"], padx=10, pady=8, cursor="hand2")
        user_card.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 8))

        user_top = tk.Frame(user_card, bg=t["bg_sidebar"], cursor="hand2")
        user_top.pack(fill=tk.X)

        self.user_title = tk.Label(user_top, font=("Segoe UI", 9, "bold"), bg=t["bg_sidebar"], fg=t["text_primary"], cursor="hand2")
        self.user_title.pack(side=tk.LEFT)

        self.user_status = tk.Label(user_top, font=("Segoe UI", 8), bg=t["bg_sidebar"], fg=t["success_fg"], cursor="hand2")
        self.user_status.pack(side=tk.RIGHT)

        self.user_sub = tk.Label(user_card, text="Роль: Оператор • Нажмите для смены", font=("Segoe UI", 8), bg=t["bg_sidebar"], fg=t["text_muted"], cursor="hand2")
        self.user_sub.pack(anchor="w", pady=(2, 0))

        # Привязка клика и ховера ко всем дочерним элементам плашки
        self.user_card_widget = user_card
        for w in (user_card, user_top, self.user_title, self.user_status, self.user_sub):
            w.bind("<Button-1>", lambda e: self.show_account_dialog())
            w.bind("<Enter>", lambda e: self._on_user_card_hover(True))
            w.bind("<Leave>", lambda e: self._on_user_card_hover(False))

    def _on_user_card_hover(self, entering: bool):
        t = THEMES["dark"]
        bg = "#1e293b" if entering else t["bg_sidebar"]
        if hasattr(self, 'user_card_widget'):
            self.user_card_widget.configure(bg=bg)
            for child in self.user_card_widget.winfo_children():
                try:
                    child.configure(bg=bg)
                    for sub in child.winfo_children():
                        sub.configure(bg=bg)
                except Exception:
                    pass

    def _update_user_display(self):
        """Обновляет отображение пользователя в левой нижней плашке сайдбара."""
        user = self.account_manager.get_active_user()
        disp_name = user.get("display_name", "Технолог")
        role = user.get("role", "operator")
        role_label = "Администратор" if role == "admin" else "Оператор"
        avatar_icon = "admin" if role == "admin" else "user"
        status_icon = "admin" if role == "admin" else "status_green"
        status_text = "Admin" if role == "admin" else "Готов"

        if getattr(self, 'is_sidebar_collapsed', False):
            apply_label_icon(self.user_status, status_icon, "", size=20)
            ToolTip(self.user_status, f"{disp_name} ({role_label})\nНажмите для смены аккаунта")
        else:
            apply_label_icon(self.user_title, avatar_icon, disp_name, size=18)
            apply_label_icon(self.user_status, status_icon, status_text, size=12)
            self.user_sub.configure(text=f"Роль: {role_label} • Сменить аккаунт")

    def show_account_dialog(self):
        """Модальное окно управления аккаунтами, смены пользователя и добавления новых учетных записей."""
        dialog = create_styled_toplevel(self.root, "👤 Управление пользователями и смена аккаунта", "640x520", min_size=(560, 440))
        dialog.transient(self.root)
        dialog.grab_set()

        t = THEMES["dark"]
        main_frame = ttk.Frame(dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        active_u = self.account_manager.get_active_user()
        active_disp = active_u.get("display_name", "Технолог")
        active_role = "Администратор" if active_u.get("role") == "admin" else "Оператор"

        # Плашка текущей сессии
        curr_box = ttk.LabelFrame(main_frame, text="Текущая активная сессия", padding="12")
        curr_box.pack(fill=tk.X, pady=(0, 10))

        lbl_active = ttk.Label(
            curr_box,
            text=f"🟢 {active_disp}   [{active_role}]",
            font=("Segoe UI", 11, "bold")
        )
        lbl_active.pack(side=tk.LEFT)

        ttk.Label(
            curr_box,
            text=f"Логин: @{active_u.get('username', 'user')}",
            foreground="gray",
            font=("Segoe UI", 9)
        ).pack(side=tk.RIGHT)

        # Скроллируемый список пользователей
        users_box = ttk.LabelFrame(main_frame, text="Доступные учетные записи", padding="10")
        users_box.pack(fill=tk.BOTH, expand=True, pady=4)

        canvas = tk.Canvas(users_box, bg=t["bg_card"], highlightthickness=0)
        v_bar = ttk.Scrollbar(users_box, orient="vertical", command=canvas.yview)
        cards_frame = tk.Frame(canvas, bg=t["bg_card"])

        canvas.configure(yscrollcommand=v_bar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_bar.pack(side=tk.RIGHT, fill=tk.Y)

        win_id = canvas.create_window((0, 0), window=cards_frame, anchor="nw")
        cards_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))

        def refresh_users_list():
            for child in cards_frame.winfo_children():
                child.destroy()

            users = self.account_manager.get_all_users()
            is_admin = self.account_manager.is_current_admin()

            for u in users:
                uname = u.get("username", "")
                disp = u.get("display_name", uname)
                role = u.get("role", "operator")
                role_str = "Администратор" if role == "admin" else "Оператор"
                has_pwd = bool(u.get("password_hash"))
                is_curr = (uname == self.account_manager.active_username)

                row = tk.Frame(cards_frame, bg="#1e2536" if is_curr else "#161b26", bd=1, relief="solid", padx=10, pady=8)
                row.pack(fill=tk.X, pady=3, padx=2)

                icon_txt = "🛡️" if role == "admin" else "👤"
                tk.Label(row, text=icon_txt, font=("Segoe UI", 12), bg=row["bg"], fg="#60a5fa").pack(side=tk.LEFT, padx=(0, 8))

                info_col = tk.Frame(row, bg=row["bg"])
                info_col.pack(side=tk.LEFT, fill=tk.Y)
                tk.Label(info_col, text=f"{disp} (@{uname})", font=("Segoe UI", 9, "bold"), bg=row["bg"], fg="#ffffff").pack(anchor="w")
                pwd_hint = "🔒 Требуется пароль" if has_pwd else "🔓 Вход без пароля"
                tk.Label(info_col, text=f"{role_str} • {pwd_hint}", font=("Segoe UI", 8), bg=row["bg"], fg="#94a3b8").pack(anchor="w")

                btn_col = tk.Frame(row, bg=row["bg"])
                btn_col.pack(side=tk.RIGHT)

                if is_curr:
                    tk.Label(btn_col, text="[Активен]", font=("Segoe UI", 9, "bold"), fg="#10b981", bg=row["bg"]).pack(side=tk.LEFT, padx=6)
                else:
                    btn_login = ttk.Button(btn_col, text="Войти ➔", command=lambda un=uname: on_user_select(un))
                    btn_login.pack(side=tk.LEFT, padx=4)

                if is_admin and not is_curr and uname != "admin":
                    btn_del = tk.Button(
                        btn_col, text="🗑️", font=("Segoe UI", 8), bg="#3b1d22", fg="#f87171",
                        relief="flat", cursor="hand2", padx=4,
                        command=lambda un=uname, d=disp: on_delete_user(un, d)
                    )
                    btn_del.pack(side=tk.LEFT, padx=2)

        def on_user_select(username: str):
            user = self.account_manager.users.get(username)
            if not user:
                return

            if not self.account_manager.requires_password(username):
                self.account_manager.login(username)
                self._update_user_display()
                dialog.destroy()
                messagebox.showinfo("Вход выполнен", f"Вы успешно вошли как: {user.get('display_name', username)}")
                return

            pwd_win = create_styled_toplevel(dialog, f"Вход: {user.get('display_name', username)}", "420x210", min_size=(380, 180))
            pwd_win.transient(dialog)
            pwd_win.grab_set()

            pf = ttk.Frame(pwd_win, padding="15")
            pf.pack(fill=tk.BOTH, expand=True)

            ttk.Label(pf, text=f"Введите пароль для пользователя {user.get('display_name')}:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 8))
            pwd_entry = ttk.Entry(pf, show="*")
            pwd_entry.pack(fill=tk.X, pady=(0, 12))
            pwd_entry.focus()

            def try_login():
                p = pwd_entry.get()
                ok, msg = self.account_manager.login(username, p)
                if ok:
                    self._update_user_display()
                    pwd_win.destroy()
                    dialog.destroy()
                    messagebox.showinfo("Вход выполнен", f"Вы вошли под учетной записью:\n{user.get('display_name')}")
                else:
                    messagebox.showerror("Ошибка входа", msg, parent=pwd_win)

            pwd_entry.bind("<Return>", lambda e: try_login())

            btn_box = ttk.Frame(pf)
            btn_box.pack(fill=tk.X)
            ttk.Button(btn_box, text="Войти", style="Accent.TButton", command=try_login).pack(side=tk.LEFT, padx=4)
            ttk.Button(btn_box, text="Отмена", command=pwd_win.destroy).pack(side=tk.LEFT, padx=4)
            style_widget_tree(pwd_win, "dark")

        def on_delete_user(username: str, disp_name: str):
            if messagebox.askyesno("Удаление пользователя", f"Удалить аккаунт '{disp_name}' (@{username})?\nЭто действие необратимо.", parent=dialog):
                ok, msg = self.account_manager.delete_user(username)
                if ok:
                    refresh_users_list()
                    messagebox.showinfo("Успех", msg, parent=dialog)
                else:
                    messagebox.showerror("Ошибка", msg, parent=dialog)

        refresh_users_list()

        # Нижняя панель действий
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(10, 0))

        if self.account_manager.is_current_admin():
            ttk.Button(
                bottom_frame,
                text="➕ Создать новый аккаунт",
                style="Accent.TButton",
                command=lambda: self._open_create_user_modal(dialog, refresh_users_list)
            ).pack(side=tk.LEFT)
        else:
            ttk.Label(
                bottom_frame,
                text="💡 Добавление аккаунтов доступно только Администратору",
                foreground="#94a3b8",
                font=("Segoe UI", 8)
            ).pack(side=tk.LEFT)

        ttk.Button(bottom_frame, text="Закрыть", command=dialog.destroy).pack(side=tk.RIGHT)
        style_widget_tree(dialog, "dark")

    def _open_create_user_modal(self, parent_dialog, on_created_callback):
        modal = create_styled_toplevel(parent_dialog, "➕ Создание нового пользователя", "480x360", min_size=(440, 320))
        modal.transient(parent_dialog)
        modal.grab_set()

        f = ttk.Frame(modal, padding="20")
        f.pack(fill=tk.BOTH, expand=True)
        f.columnconfigure(1, weight=1)

        ttk.Label(f, text="Логин (тех. имя):").grid(row=0, column=0, sticky="w", pady=6)
        u_entry = ttk.Entry(f)
        u_entry.grid(row=0, column=1, sticky="ew", pady=6)
        u_entry.focus()

        ttk.Label(f, text="Имя пользователя (ФИО):").grid(row=1, column=0, sticky="w", pady=6)
        d_entry = ttk.Entry(f)
        d_entry.grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(f, text="Роль пользователя:").grid(row=2, column=0, sticky="w", pady=6)
        role_cb = ttk.Combobox(f, values=["Оператор", "Администратор"], state="readonly")
        role_cb.set("Оператор")
        role_cb.grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(f, text="Пароль (пусто = без пароля):").grid(row=3, column=0, sticky="w", pady=6)
        p1_entry = ttk.Entry(f, show="*")
        p1_entry.grid(row=3, column=1, sticky="ew", pady=6)

        ttk.Label(f, text="Повтор пароля:").grid(row=4, column=0, sticky="w", pady=6)
        p2_entry = ttk.Entry(f, show="*")
        p2_entry.grid(row=4, column=1, sticky="ew", pady=6)

        def save_user():
            un = u_entry.get().strip().lower()
            dn = d_entry.get().strip()
            role_val = "admin" if role_cb.get() == "Администратор" else "operator"
            p1 = p1_entry.get()
            p2 = p2_entry.get()

            if not un:
                messagebox.showerror("Ошибка", "Введите логин.", parent=modal)
                return
            if not dn:
                messagebox.showerror("Ошибка", "Введите имя пользователя.", parent=modal)
                return
            if p1 != p2:
                messagebox.showerror("Ошибка", "Введенные пароли не совпадают.", parent=modal)
                return

            ok, msg = self.account_manager.create_user(un, dn, password=p1, role=role_val)
            if ok:
                messagebox.showinfo("Успех", msg, parent=modal)
                modal.destroy()
                if on_created_callback:
                    on_created_callback()
            else:
                messagebox.showerror("Ошибка", msg, parent=modal)

        btn_row = ttk.Frame(f)
        btn_row.grid(row=5, column=0, columnspan=2, pady=(16, 0))
        ttk.Button(btn_row, text="Создать аккаунт", style="Accent.TButton", command=save_user).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="Отмена", command=modal.destroy).pack(side=tk.LEFT, padx=4)

        style_widget_tree(modal, "dark")

    def toggle_sidebar(self):
        """Сворачивает сайдбар до компактных иконок или разворачивает обратно."""
        self.is_sidebar_collapsed = not getattr(self, 'is_sidebar_collapsed', False)

        if self.is_sidebar_collapsed:
            # 1. Сжатие сайдбара до 64px
            self.sidebar_frame.configure(width=64)

            # Переставляем кнопку раскрытия на самый верх по центру — она видна ВСЕГДА!
            self.brand_left.pack_forget()
            self.btn_collapse.pack_forget()
            self.btn_collapse.configure(text="▶", font=("Segoe UI", 10, "bold"), padx=12, pady=5)
            self.btn_collapse.pack(side=tk.TOP, pady=(4, 6))
            ToolTip(self.btn_collapse, "Развернуть боковое меню (240px)")

            # Скрываем заголовки групп
            self.group_label.pack_forget()
            self.group_label2.pack_forget()

            # Нижняя плашка пользователя: показываем только статус-индикатор
            self.user_title.pack_forget()
            self.user_sub.pack_forget()
            self.user_status.pack_forget()
            role = self.account_manager.get_active_user().get("role", "operator")
            self.user_status.configure(text="🛡️" if role == "admin" else "🟢")
            self.user_status.pack(side=tk.TOP, pady=2)
            ToolTip(self.user_status, f"{self.account_manager.get_active_display_name()}: Сменить пользователя")

            # Переводим навигационные элементы в чистый режим одиночных цветных иконок
            for item in self.nav_widgets.values():
                if item.get("is_subitem") and "line_box" in item:
                    item["line_box"].pack_forget()
                if "indicator" in item:
                    item["indicator"].pack_forget()
                icon_img = item.get("icon_img")
                if icon_img:
                    item["label"].configure(
                        image=icon_img,
                        compound=tk.CENTER,
                        text="",
                        anchor="center",
                        padx=0
                    )
                else:
                    item["label"].configure(
                        text=item.get("icon_key", "")[:1],
                        anchor="center",
                        padx=0,
                        font=("Segoe UI", 12)
                    )
        else:
            # 2. Разворачивание сайдбара до 240px
            self.sidebar_frame.configure(width=240)

            # Восстанавливаем шапку бренда и кнопку сворачивания справа
            self.btn_collapse.pack_forget()
            self.brand_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.btn_collapse.configure(text="◀", font=("Segoe UI", 8, "bold"), padx=6, pady=3)
            self.btn_collapse.pack(side=tk.RIGHT)
            ToolTip(self.btn_collapse, "Свернуть боковое меню в компактный режим (иконки)")

            # Восстанавливаем заголовки групп
            self.group_label.pack(fill=tk.X, pady=(6, 2), before=self.tree_container)
            self.group_label2.pack(fill=tk.X, pady=(10, 2), before=self.nav_widgets["compare_pnp"]["frame"])

            # Восстанавливаем нижнюю плашку пользователя
            self.user_status.pack_forget()
            self.user_title.pack(side=tk.LEFT)
            self.user_status.pack(side=tk.RIGHT)
            self.user_sub.pack(anchor="w", pady=(2, 0))
            self._update_user_display()

            # Восстанавливаем навигационные элементы с цветной иконкой и полным текстом
            for item in self.nav_widgets.values():
                if "indicator" in item:
                    item["indicator"].pack(side=tk.LEFT, fill=tk.Y)
                if item.get("is_subitem") and "line_box" in item:
                    item["line_box"].pack(side=tk.LEFT, fill=tk.Y)
                icon_img = item.get("icon_img")
                pad = 4 if item.get("is_subitem") else 10
                if icon_img:
                    item["label"].configure(
                        image=icon_img,
                        compound=tk.LEFT,
                        text=f"  {item['full_text']}",
                        anchor="w",
                        padx=pad,
                        font=("Segoe UI", 9)
                    )
                else:
                    item["label"].configure(
                        text=item["full_text"],
                        anchor="w",
                        padx=pad,
                        font=("Segoe UI", 9)
                    )

        # Синхронно освежаем подсветку активного пункта
        self._set_nav_item_visual(self.active_page_id, "active")

    def _set_nav_item_visual(self, item_id: str, state: str):
        """
        state: 'active', 'hover', 'normal'
        Синхронно обновляет ВСЕ элементы навигационной строки без артефактов и расхождений.
        """
        if item_id not in self.nav_widgets:
            return
        t = THEMES["dark"]
        item = self.nav_widgets[item_id]

        if state == "active":
            bg_col = "#1e2f4f"
            fg_col = "#ffffff"
            dot_col = "#38bdf8"
            ind_col = "#38bdf8"
            fnt_name = ("Segoe UI", 9, "bold")
        elif state == "hover":
            bg_col = "#18243b"
            fg_col = "#f8fafc"
            dot_col = "#38bdf8"
            ind_col = "#18243b"
            fnt_name = ("Segoe UI", 9)
        else: # normal
            bg_col = t["bg_sidebar"]
            fg_col = t["text_secondary"]
            dot_col = t["text_muted"]
            ind_col = t["bg_sidebar"]
            fnt_name = ("Segoe UI", 9)

        is_collapsed = getattr(self, 'is_sidebar_collapsed', False)
        fnt = ("Segoe UI", 12) if is_collapsed else fnt_name
        anchor_mode = "center" if is_collapsed else "w"

        item["frame"].configure(bg=bg_col)
        item["label"].configure(bg=bg_col, fg=fg_col, font=fnt, anchor=anchor_mode)
        if "indicator" in item and not is_collapsed:
            item["indicator"].configure(bg=ind_col)
        if "line_box" in item and not is_collapsed:
            item["line_box"].configure(bg=bg_col)
        if "dot" in item and not is_collapsed:
            item["dot"].configure(bg=bg_col, fg=dot_col)

    def _on_nav_enter(self, item_id: str):
        """Синхронно активирует hover для выбранного пункта и сбрасывает все остальные."""
        self.hovered_nav_id = item_id
        for pid in self.nav_widgets:
            if pid == self.active_page_id:
                self._set_nav_item_visual(pid, "active")
            elif pid == item_id:
                self._set_nav_item_visual(pid, "hover")
            else:
                self._set_nav_item_visual(pid, "normal")

    def _on_nav_leave(self, item_id: str):
        """Сбрасывает hover состояние пункта."""
        if self.hovered_nav_id == item_id:
            self.hovered_nav_id = None
        if item_id != self.active_page_id:
            self._set_nav_item_visual(item_id, "normal")

    def _on_sidebar_leave(self, e=None):
        """При выходе курсора за пределы сайдбара сбрасывает все неактивные пункты."""
        self.hovered_nav_id = None
        for pid in self.nav_widgets:
            if pid == self.active_page_id:
                self._set_nav_item_visual(pid, "active")
            else:
                self._set_nav_item_visual(pid, "normal")

    def _add_nav_item(self, item_id: str, text: str, icon_key: str, command, tip_text: str = ""):
        t = THEMES["dark"]
        btn_frame = tk.Frame(self.nav_items_frame, bg=t["bg_sidebar"], cursor="hand2")
        btn_frame.pack(fill=tk.X, pady=2)

        # Индикатор слева
        indicator = tk.Frame(btn_frame, width=3, bg=t["bg_sidebar"])
        indicator.pack(side=tk.LEFT, fill=tk.Y)

        label = tk.Label(
            btn_frame,
            font=("Segoe UI", 9),
            bg=t["bg_sidebar"],
            fg=t["text_secondary"],
            anchor="w",
            padx=10,
            pady=7
        )
        icon_img = get_icon(icon_key, 18)
        if icon_img:
            label.configure(image=icon_img, compound=tk.LEFT, text=f"  {text}")
            label.image = icon_img
        else:
            label.configure(text=text)
        label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.nav_widgets[item_id] = {
            "frame": btn_frame,
            "label": label,
            "indicator": indicator,
            "full_text": text,
            "icon_key": icon_key,
            "icon_img": icon_img,
            "is_subitem": False
        }

        if tip_text:
            ToolTip(btn_frame, tip_text)
            ToolTip(label, tip_text)

        def on_click(e=None):
            command()

        for w in (btn_frame, label, indicator):
            w.bind("<Button-1>", on_click)
            w.bind("<Enter>", lambda e, i=item_id: self._on_nav_enter(i))
            w.bind("<Leave>", lambda e, i=item_id: self._on_nav_leave(i))

    def _add_nav_subitem(self, container, item_id: str, text: str, icon_key: str, command, tip_text: str = ""):
        t = THEMES["dark"]
        btn_frame = tk.Frame(container, bg=t["bg_sidebar"], cursor="hand2")
        btn_frame.pack(fill=tk.X, pady=1)

        # Маркерная линия
        line_box = tk.Frame(btn_frame, width=16, bg=t["bg_sidebar"])
        line_box.pack(side=tk.LEFT, fill=tk.Y)

        dot = tk.Label(line_box, text="●", font=("Segoe UI", 6), bg=t["bg_sidebar"], fg=t["text_muted"])
        dot.pack(pady=7)

        label = tk.Label(
            btn_frame,
            font=("Segoe UI", 9),
            bg=t["bg_sidebar"],
            fg=t["text_secondary"],
            anchor="w",
            padx=4,
            pady=6
        )
        icon_img = get_icon(icon_key, 18)
        if icon_img:
            label.configure(image=icon_img, compound=tk.LEFT, text=f"  {text}")
            label.image = icon_img
        else:
            label.configure(text=text)
        label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.nav_widgets[item_id] = {
            "frame": btn_frame,
            "label": label,
            "line_box": line_box,
            "dot": dot,
            "full_text": text,
            "icon_key": icon_key,
            "icon_img": icon_img,
            "is_subitem": True
        }

        if tip_text:
            ToolTip(btn_frame, tip_text)
            ToolTip(label, tip_text)

        def on_click(e=None):
            command()

        for w in (btn_frame, label, line_box, dot):
            w.bind("<Button-1>", on_click)
            w.bind("<Enter>", lambda e, i=item_id: self._on_nav_enter(i))
            w.bind("<Leave>", lambda e, i=item_id: self._on_nav_leave(i))

    # =========================================================================
    # Верхний хедер с горизонтальными вкладками (Category Bar)
    # =========================================================================
    def _build_top_header(self, parent):
        t = THEMES["dark"]
        self.header_frame = tk.Frame(parent, height=52, bg=t["bg_header"], padx=16)
        self.header_frame.pack(fill=tk.X, side=tk.TOP)
        self.header_frame.pack_propagate(False)

        # Горизонтальные вкладки
        self.header_tabs_frame = tk.Frame(self.header_frame, bg=t["bg_header"])
        self.header_tabs_frame.pack(side=tk.LEFT, fill=tk.Y)

        self.header_tabs = {}
        tabs = [
            ("dashboard", "Обзор"),
            ("step1", "Шаг 1: BOM"),
            ("step2", "Шаг 2: P&P"),
            ("step3", "Шаг 3: Сверка"),
            ("compare_pnp", "Сравнение P&P"),
            ("compare_bom", "Сверка BOM"),
            ("database", "База данных")
        ]

        for tab_id, tab_title in tabs:
            tab_box = tk.Frame(self.header_tabs_frame, bg=t["bg_header"], cursor="hand2", padx=9)
            tab_box.pack(side=tk.LEFT, fill=tk.Y)

            tab_lbl = tk.Label(
                tab_box,
                text=tab_title,
                font=("Segoe UI", 9, "bold"),
                bg=t["bg_header"],
                fg=t["text_secondary"],
                pady=14
            )
            tab_lbl.pack()

            underline = tk.Frame(tab_box, height=2, bg=t["bg_header"])
            underline.pack(fill=tk.X, side=tk.BOTTOM)

            def make_cmd(tid=tab_id):
                return lambda e=None: self.show_page(tid)

            cmd = make_cmd(tab_id)
            for w in (tab_box, tab_lbl):
                w.bind("<Button-1>", cmd)

            self.header_tabs[tab_id] = {
                "box": tab_box,
                "label": tab_lbl,
                "underline": underline
            }

        # Правая часть хедера: бейджи статуса и ссылки
        right_header = tk.Frame(self.header_frame, bg=t["bg_header"])
        right_header.pack(side=tk.RIGHT, fill=tk.Y)

        # Бейдж сквозного конвейера
        self.badge_pipeline = tk.Label(
            right_header,
            text="📍 Конвейер: Шаг 1 (BOM)",
            font=("Segoe UI", 8, "bold"),
            bg="#0c4a6e",
            fg="#38bdf8",
            padx=8,
            pady=4,
            cursor="hand2"
        )
        self.badge_pipeline.pack(side=tk.LEFT, padx=3, pady=12)
        self.badge_pipeline.bind("<Button-1>", lambda e: self._on_pipeline_badge_click())
        ToolTip(self.badge_pipeline, "Текущий прогресс сквозного заказа (нажмите для перехода)")

        db_count = len(self.db_manager.data) if self.db_manager else 0
        self.badge_db = tk.Label(
            right_header,
            font=("Segoe UI", 8, "bold"),
            bg=t["bg_card"],
            fg=t["text_header"],
            padx=8,
            pady=4,
            cursor="hand2"
        )
        apply_label_icon(self.badge_db, "database", f"База: {db_count} записей", size=14)
        self.badge_db.pack(side=tk.LEFT, padx=3, pady=12)
        self.badge_db.bind("<Button-1>", lambda e: self.show_page("database"))
        ToolTip(self.badge_db, "Открыть базу данных (database.db)")

        btn_faq = tk.Button(
            right_header,
            font=("Segoe UI", 8),
            bg=t["btn_sec_bg"],
            fg=t["btn_sec_fg"],
            relief="flat",
            padx=8,
            pady=4,
            cursor="hand2",
            command=lambda: show_faq_dialog(self.root, "dark")
        )
        apply_button_icon(btn_faq, "book", "FAQ & Справка", size=14)
        btn_faq.pack(side=tk.LEFT, padx=3, pady=12)

        btn_feedback = tk.Button(
            right_header,
            font=("Segoe UI", 8),
            bg=t["btn_sec_bg"],
            fg=t["btn_sec_fg"],
            relief="flat",
            padx=8,
            pady=4,
            cursor="hand2",
            command=lambda: show_feedback_dialog(self.root, "dark")
        )
        apply_button_icon(btn_feedback, "mail", "Обратная связь", size=14)
        btn_feedback.pack(side=tk.LEFT, padx=(3, 6), pady=12)

        # Тонкая разделительная линия под хедером
        sep_h = tk.Frame(parent, height=1, bg=t["border"])
        sep_h.pack(fill=tk.X, side=tk.TOP)

    def _on_pipeline_badge_click(self):
        """Быстрый переход к текущему активному этапу заказа по клику на бейдж."""
        if getattr(self, 'merged_pnp_path', None):
            self.show_page("step3")
        elif getattr(self, 'unified_bom_path', None):
            self.show_page("step2")
        else:
            self.show_page("step1")

    def _update_dashboard_file_status(self):
        """Обновляет индикаторы открытых файлов и бейджи конвейера в реальном времени."""
        t = THEMES["dark"]
        has_merged = bool(getattr(self, 'merged_pnp_path', None))
        has_bom = bool(getattr(self, 'unified_bom_path', None))

        # 1. Бейдж конвейера в шапке
        if hasattr(self, 'badge_pipeline'):
            if has_merged:
                self.badge_pipeline.configure(
                    text="🟢 Конвейер: Шаг 3 (Сверка)",
                    bg="#064e3b",
                    fg="#34d399"
                )
            elif has_bom:
                self.badge_pipeline.configure(
                    text="🔵 Конвейер: Шаг 2 (P&P)",
                    bg="#1e3a8a",
                    fg="#60a5fa"
                )
            else:
                self.badge_pipeline.configure(
                    text="📍 Конвейер: Шаг 1 (BOM)",
                    bg="#0c4a6e",
                    fg="#38bdf8"
                )

        # 2. Индикаторы файлов в карточках на Dashboard
        if hasattr(self, 'lbl_dash_step1_file'):
            if has_bom:
                fname = os.path.basename(self.unified_bom_path)
                self.lbl_dash_step1_file.configure(
                    text=f"📄 Загружен: {fname}",
                    fg=t["success_fg"],
                    bg="#064e3b"
                )
            else:
                self.lbl_dash_step1_file.configure(
                    text="📄 Файл еще не выбран",
                    fg=t["text_muted"],
                    bg=t["bg_card_inner"]
                )

        if hasattr(self, 'lbl_dash_step2_file'):
            if has_merged:
                fname = os.path.basename(self.merged_pnp_path)
                self.lbl_dash_step2_file.configure(
                    text=f"📍 Сшит: {fname}",
                    fg=t["success_fg"],
                    bg="#064e3b"
                )
            elif has_bom:
                self.lbl_dash_step2_file.configure(
                    text="📍 BOM готов ➔ выберите P&P",
                    fg=t["text_header"],
                    bg="#0c4a6e"
                )
            else:
                self.lbl_dash_step2_file.configure(
                    text="📍 Ожидает исходные файлы",
                    fg=t["text_muted"],
                    bg=t["bg_card_inner"]
                )

        if hasattr(self, 'lbl_dash_step3_file'):
            if has_merged:
                self.lbl_dash_step3_file.configure(
                    text="🛡️ Данные готовы к аудиту",
                    fg=t["success_fg"],
                    bg="#064e3b"
                )
            else:
                self.lbl_dash_step3_file.configure(
                    text="🛡️ Ожидает данные из Шага 2",
                    fg=t["text_muted"],
                    bg=t["bg_card_inner"]
                )

    # =========================================================================
    # Переключение экранов (Show Page)
    # =========================================================================
    def show_page(self, page_id: str):
        self.active_page_id = page_id
        t = THEMES["dark"]

        # Прячем все страницы
        for pid, frame in self.pages.items():
            frame.pack_forget()

        # Показываем целевую страницу
        if page_id in self.pages:
            self.pages[page_id].pack(fill=tk.BOTH, expand=True)

        # Обновляем визуальный статус сайдбара
        for pid in self.nav_widgets:
            self._set_nav_item_visual(pid, "active" if pid == page_id else "normal")

        # Обновляем горизонтальные вкладки в хедере
        for tid, tab in self.header_tabs.items():
            is_active = (tid == page_id)
            tab["label"].configure(
                fg=t["text_header"] if is_active else t["text_secondary"]
            )
            tab["underline"].configure(
                bg=t["nav_active_border"] if is_active else t["bg_header"]
            )

        # Обновляем бейдж базы и индикаторы конвейера
        if hasattr(self, 'badge_db') and self.db_manager:
            apply_label_icon(self.badge_db, "database", f"База: {len(self.db_manager.data)} записей", size=14)
        if page_id == "database" and hasattr(self, 'database_tab') and hasattr(self.database_tab, 'refresh_tree'):
            self.database_tab.refresh_tree()
        self._update_dashboard_file_status()

    # =========================================================================
    # Страница 0: Dashboard (Обзор состояния заказа)
    # =========================================================================
    def _build_page_dashboard(self, parent):
        t = THEMES["dark"]
        page = tk.Frame(parent, bg=t["bg_app"])
        self.pages["dashboard"] = page

        # Холст с плавной прокруткой для идеальной адаптивности на любых мониторах
        canvas = tk.Canvas(page, bg=t["bg_app"], highlightthickness=0)
        v_scroll = ttk.Scrollbar(page, orient=tk.VERTICAL, command=canvas.yview)
        scroll_content = tk.Frame(canvas, bg=t["bg_app"])

        scroll_content.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas_window = canvas.create_window((0, 0), window=scroll_content, anchor="nw")

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=v_scroll.set)

        def _on_mousewheel(event):
            if canvas.winfo_exists():
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # ---------------------------------------------------------------------
        # 1. Заголовочный баннер (Hero Header)
        # ---------------------------------------------------------------------
        hero = tk.Frame(scroll_content, bg=t["bg_card"], padx=20, pady=12, highlightbackground=t["border"], highlightthickness=1)
        hero.pack(fill=tk.X, pady=(0, 10))

        hero_top = tk.Frame(hero, bg=t["bg_card"])
        hero_top.pack(fill=tk.X)

        tk.Label(
            hero_top,
            text="ПРОИЗВОДСТВЕННЫЙ ТЕХНОЛОГИЧЕСКИЙ КОМПЛЕКС",
            font=("Segoe UI", 8, "bold"),
            bg="#0c4a6e",
            fg="#38bdf8",
            padx=10,
            pady=2
        ).pack(side=tk.LEFT)

        self.hero_title = tk.Label(
            hero,
            font=("Segoe UI", 15, "bold"),
            bg=t["bg_card"],
            fg=t["text_primary"]
        )
        apply_label_icon(self.hero_title, "rocket", "Сквозной производственный цикл подготовки SMD-монтажа", size=26)
        self.hero_title.pack(anchor="w", pady=(8, 3))

        tk.Label(
            hero,
            text="Автоматизированный конвейер подготовки данных: от нормализации спецификаций компонентов и сшивания\nкоординат расстановщика до комплексного аудита перед запуском на монтажную линию.",
            font=("Segoe UI", 9),
            bg=t["bg_card"],
            fg=t["text_secondary"],
            justify=tk.LEFT,
            anchor="w"
        ).pack(anchor="w")

        # ---------------------------------------------------------------------
        # 2. Основные этапы конвейера (Шаги 1, 2, 3)
        # ---------------------------------------------------------------------
        steps_container = tk.Frame(scroll_content, bg=t["bg_app"])
        steps_container.pack(fill=tk.X, pady=(0, 10))

        pipeline_steps = [
            {
                "step_num": "ШАГ 1",
                "step_tag": "BOM • СПЕЦИФИКАЦИЯ",
                "badge_bg": "#0c4a6e",
                "badge_fg": "#38bdf8",
                "icon": "step1",
                "title": "Унификация спецификации (BOM)",
                "purpose": "Интеллектуальное приведение перечней элементов и спецификаций из любых CAD-систем (Altium, KiCad, PCAD) к единому стандарту предприятия.",
                "features": [
                    "Автоматическое распознавание партномеров 15+ брендов (Vishay, Murata, Yageo, Samsung, Kemet, TDK, Panasonic, KOA, Bourns, Р1-12/16 и др.).",
                    "Стандартизация: R_<Размер>_<Номинал>_<Допуск> и C_<Размер>_<Диэлектрик>_<Емкость>_<Напряжение>.",
                    "Обязательное отображение допуска у всех резисторов, включая перемычки 0R (R_0603_0R_0%, R_0402_0R_5%).",
                    "Поддержка корпоративного справочника замен database.txt и встроенный интерактивный редактор исключений."
                ],
                "pipeline_note": "⚡ Результат унификации автоматически подставляется в Шаг 2 без необходимости повторного выбора файлов.",
                "btn_text": "Запустить унификацию BOM ➔",
                "target": "step1"
            },
            {
                "step_num": "ШАГ 2",
                "step_tag": "P&P • КООРДИНАТЫ",
                "badge_bg": "#1e3a8a",
                "badge_fg": "#60a5fa",
                "icon": "step2",
                "title": "Объединение P&P и BOM",
                "purpose": "Сшивание файлов монтажных координат расстановщика (Centroid / Pick & Place) с унифицированной спецификацией BOM по позиционным обозначениям.",
                "features": [
                    "Автоматический подбор колонок: Designator (RefDes), Center-X, Center-Y, Rotation, Side/Layer, Footprint.",
                    "Прямая сквозная интеграция с нормализованным BOM из Шага 1 в один клик.",
                    "Автоматическая конвертация координат из дюймов и mils в метрическую систему (мм).",
                    "Разделение слоев платы (TOP / BOTTOM), проверка полярности и поддержка составных корпусов."
                ],
                "pipeline_note": "⚡ Сшитый монтажный файл мгновенно передается в модуль финального аудита Шага 3.",
                "btn_text": "Перейти к объединению P&P ➔",
                "target": "step2"
            },
            {
                "step_num": "ШАГ 3",
                "step_tag": "QA • АУДИТ И КОНТРОЛЬ",
                "badge_bg": "#064e3b",
                "badge_fg": "#34d399",
                "icon": "step3",
                "title": "Финальная сверка и контроль",
                "purpose": "Комплексная трёхсторонняя верификация технологических данных перед непосредственной загрузкой программы в автомат SMD-монтажа.",
                "features": [
                    "Автоматическая фильтрация позиций DNP (Do Not Place / Не устанавливать) для предотвращения ошибочной пайки.",
                    "Выявление критических расхождений: элементы есть в BOM, но отсутствуют в P&P (или наоборот).",
                    "Контроль дубликатов координат, некорректных углов поворота и пропущенных компонентов схемы.",
                    "Формирование сводного аудиторского протокола и экспорт очищенных файлов для автомата."
                ],
                "pipeline_note": "🛡️ Гарантия защиты от брака, остановок сборочной линии и повреждения компонентов.",
                "btn_text": "Перейти к финальной сверке ➔",
                "target": "step3"
            }
        ]

        for s in pipeline_steps:
            card = tk.Frame(steps_container, bg=t["bg_card"], padx=16, pady=12, highlightbackground=t["border"], highlightthickness=1)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6)

            # Верхняя строка бейджей
            badge_row = tk.Frame(card, bg=t["bg_card"])
            badge_row.pack(fill=tk.X, pady=(0, 6))

            tk.Label(
                badge_row,
                text=s["step_num"],
                font=("Segoe UI", 8, "bold"),
                bg=s["badge_bg"],
                fg=s["badge_fg"],
                padx=8,
                pady=2
            ).pack(side=tk.LEFT)

            tk.Label(
                badge_row,
                text=s["step_tag"],
                font=("Segoe UI", 7, "bold"),
                bg=t["bg_card_inner"],
                fg=t["text_muted"],
                padx=8,
                pady=2
            ).pack(side=tk.RIGHT)

            # Заголовок карточки
            title_lbl = tk.Label(
                card,
                font=("Segoe UI", 12, "bold"),
                bg=t["bg_card"],
                fg=t["text_header"]
            )
            apply_label_icon(title_lbl, s.get("icon", "step1"), s.get("title", "Этап"), size=22)
            title_lbl.pack(anchor="w", pady=(2, 4))

            # Назначение
            tk.Label(
                card,
                text=s["purpose"],
                font=("Segoe UI", 9),
                bg=t["bg_card"],
                fg=t["text_secondary"],
                wraplength=340,
                justify=tk.LEFT
            ).pack(anchor="w", pady=(0, 6))

            # Разделитель
            tk.Frame(card, height=1, bg=t["border"]).pack(fill=tk.X, pady=(2, 6))

            # Список возможностей
            tk.Label(
                card,
                text="КЛЮЧЕВЫЕ ВОЗМОЖНОСТИ:",
                font=("Segoe UI", 7, "bold"),
                bg=t["bg_card"],
                fg=t["text_muted"]
            ).pack(anchor="w", pady=(0, 3))

            for feat in s["features"]:
                f_row = tk.Frame(card, bg=t["bg_card"])
                f_row.pack(fill=tk.X, pady=1)
                tk.Label(f_row, text="•", font=("Segoe UI", 9, "bold"), bg=t["bg_card"], fg=t["accent"]).pack(side=tk.LEFT, anchor="n", padx=(0, 4))
                tk.Label(f_row, text=feat, font=("Segoe UI", 8), bg=t["bg_card"], fg=t["text_secondary"], wraplength=320, justify=tk.LEFT).pack(side=tk.LEFT, anchor="w")

            # Блок автоматизации
            note_box = tk.Frame(card, bg=t["bg_card_inner"], padx=10, pady=6, highlightbackground=t["border"], highlightthickness=1)
            note_box.pack(fill=tk.X, pady=(8, 10))
            tk.Label(note_box, text=s["pipeline_note"], font=("Segoe UI", 8), bg=t["bg_card_inner"], fg=t["text_primary"], wraplength=320, justify=tk.LEFT).pack(anchor="w")

            # Кнопка действия (скругленная современная пилюля)
            btn = tk.Button(
                card,
                text=s["btn_text"],
                font=("Segoe UI", 9, "bold"),
                bg=t["accent"],
                fg=t["accent_text"],
                activebackground=t["accent_hover"],
                activeforeground=t["accent_text"],
                relief="flat",
                padx=16,
                pady=8,
                cursor="hand2",
                command=lambda target=s["target"]: self.show_page(target)
            )
            btn.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 2))

            # Индикатор открытого файла / статуса этапа
            lbl_file = tk.Label(
                card,
                text="📄 Файл еще не выбран",
                font=("Segoe UI", 8, "bold"),
                bg=t["bg_card_inner"],
                fg=t["text_muted"],
                padx=10,
                pady=4,
                anchor="w"
            )
            lbl_file.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 6))

            if s["target"] == "step1":
                self.lbl_dash_step1_file = lbl_file
            elif s["target"] == "step2":
                self.lbl_dash_step2_file = lbl_file
            elif s["target"] == "step3":
                self.lbl_dash_step3_file = lbl_file

        # ---------------------------------------------------------------------
        # 3. Дополнительные сервисные инструменты
        # ---------------------------------------------------------------------
        srv_header = tk.Frame(scroll_content, bg=t["bg_app"])
        srv_header.pack(fill=tk.X, pady=(8, 4), padx=6)

        srv_title_lbl = tk.Label(
            srv_header,
            font=("Segoe UI", 11, "bold"),
            bg=t["bg_app"],
            fg=t["text_primary"]
        )
        apply_label_icon(srv_title_lbl, "tools", "Автономные сервисные инструменты", size=18)
        srv_title_lbl.pack(side=tk.LEFT)

        tk.Label(
            srv_header,
            text="Сравнение ревизий проектов и ведение корпоративной базы соответствий",
            font=("Segoe UI", 8),
            bg=t["bg_app"],
            fg=t["text_muted"]
        ).pack(side=tk.LEFT, padx=(12, 0), pady=(2, 0))

        services_container = tk.Frame(scroll_content, bg=t["bg_app"])
        services_container.pack(fill=tk.X, pady=(0, 10))

        services_data = [
            (
                "compare_pnp",
                "Сравнение файлов P&P",
                "Поэлементный анализ различий между двумя файлами координат расстановщика (ревизии Rev.A и Rev.B). Детекция смещений (ΔX, ΔY), изменений углов поворота, удалённых и добавленных компонентов.",
                "Сравнить файлы P&P ➔",
                "compare_pnp"
            ),
            (
                "compare_bom",
                "Сверка спецификаций BOM",
                "Сопоставление двух ревизий спецификаций схемы. Выявление различий в номиналах, количествах, типах корпусов, артикулах и альтернативных компонентах.",
                "Сверить спецификации ➔",
                "compare_bom"
            ),
            (
                "database",
                "База данных замен",
                "Локальный справочник соответствий и синонимов (database.db). Быстрый поиск, добавление правил нормализации и корпоративных артикулов компонентов.",
                "Открыть базу данных ➔",
                "database"
            )
        ]

        for s_icon, s_title, s_desc, s_btn, s_target in services_data:
            s_card = tk.Frame(services_container, bg=t["bg_card"], padx=18, pady=14, highlightbackground=t["border"], highlightthickness=1)
            s_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6)

            card_title_lbl = tk.Label(s_card, font=("Segoe UI", 10, "bold"), bg=t["bg_card"], fg=t["text_header"])
            apply_label_icon(card_title_lbl, s_icon, s_title, size=20)
            card_title_lbl.pack(anchor="w")
            tk.Label(s_card, text=s_desc, font=("Segoe UI", 8), bg=t["bg_card"], fg=t["text_secondary"], wraplength=340, justify=tk.LEFT).pack(anchor="w", pady=(6, 12), fill=tk.BOTH, expand=True)

            s_btn_w = tk.Button(
                s_card,
                text=s_btn,
                font=("Segoe UI", 8, "bold"),
                bg=t["btn_sec_bg"],
                fg=t["btn_sec_fg"],
                activebackground=t["btn_sec_hover"],
                activeforeground=t["text_primary"],
                relief="flat",
                padx=12,
                pady=8,
                cursor="hand2",
                command=lambda target=s_target: self.show_page(target)
            )
            s_btn_w.pack(side=tk.BOTTOM, fill=tk.X)

        # Актуализируем статусы файлов
        self._update_dashboard_file_status()

    # =========================================================================
    # Страница 1: Шаг 1 — Унификация BOM
    # =========================================================================
    def _build_page_step1(self, parent):
        t = THEMES["dark"]
        page = tk.Frame(parent, bg=t["bg_app"])
        self.pages["step1"] = page

        # Внутренний ноутбук для унификации по описанию и по коду
        self.unify_notebook = ttk.Notebook(page)
        self.unify_notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        if DescriptionTab and self.db_manager:
            self.desc_tab = DescriptionTab(self.unify_notebook, self.db_manager)
            self.unify_notebook.add(self.desc_tab, text="📝 По описанию (русские параметры)")
            self._patch_unification_save(self.desc_tab, "Description")

        if CodeTab and self.db_manager:
            self.code_tab = CodeTab(self.unify_notebook, self.db_manager)
            self.unify_notebook.add(self.code_tab, text="🔢 По коду (Samsung, Yageo, Murata...)")
            self._patch_unification_save(self.code_tab, "Code")

        # Нижняя панель перехода к Шагу 2
        bottom_bar = tk.Frame(page, bg=t["bg_app"], pady=4)
        bottom_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.btn_step1_next = tk.Button(
            bottom_bar,
            font=("Segoe UI", 10, "bold"),
            bg=t["accent"],
            fg=t["accent_text"],
            activebackground=t["accent_hover"],
            activeforeground=t["accent_text"],
            padx=18,
            pady=8,
            relief="flat",
            cursor="hand2",
            command=self.complete_step1_and_go_step2
        )
        apply_button_icon(self.btn_step1_next, "check", "Готово: Перейти к Объединению P&P (Шаг 2) ➔", size=18)
        self.btn_step1_next.pack(side=tk.RIGHT)
        ToolTip(self.btn_step1_next, "Сохранить результат унификации и автоматически подставить BOM в Шаг 2")

    def _patch_unification_save(self, tab, tab_type):
        orig_save = tab.save_file
        def wrapped_save():
            if tab.df is None:
                messagebox.showwarning("Предупреждение", "Нет данных для сохранения.")
                return
            file_path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx")],
                title="Сохранить унифицированный BOM"
            )
            if not file_path:
                return
            try:
                tab.df.to_excel(file_path, index=False)
                self.unified_bom_path = file_path
                self.unified_bom_df = tab.df
                messagebox.showinfo("Успех", f"Унифицированный BOM сохранён:\n{file_path}\n\nФайл готов к передаче в Шаг 2 (Объединение).")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")
        tab.save_file = wrapped_save

    def complete_step1_and_go_step2(self):
        """Проверяет сохранение унифицированного BOM и передает его в Шаг 2."""
        current_tab = None
        if hasattr(self, 'unify_notebook'):
            sel = self.unify_notebook.index(self.unify_notebook.select())
            current_tab = self.desc_tab if sel == 0 else self.code_tab

        if current_tab and current_tab.df is not None:
            if not self.unified_bom_path:
                if messagebox.askyesno("Сохранение", "Унифицированный BOM ещё не сохранён на диск. Сохранить сейчас?"):
                    current_tab.save_file()
            if self.unified_bom_path and hasattr(self, 'merge_tab'):
                self.merge_tab.bom_file.set(self.unified_bom_path)
                self.merge_tab.load_bom()
                if self.merge_tab.bom_columns:
                    # Автовыбор: самый правый столбец (данные в этом боме всегда там)
                    self.merge_tab.bom_data_cb.set(self.merge_tab.bom_columns[-1])
                    self.merge_tab.save_bom_settings()
                    self.merge_tab.on_setting_changed('bom_data')

        self.show_page("step2")

    # =========================================================================
    # Страница 2: Шаг 2 — Объединение P&P + BOM
    # =========================================================================
    def _build_page_step2(self, parent):
        t = THEMES["dark"]
        page = tk.Frame(parent, bg=t["bg_app"])
        self.pages["step2"] = page

        if MergeTab:
            self.merge_tab = MergeTab(page, self)
            self.merge_tab.pack(fill=tk.BOTH, expand=True)

            next_btn_frame = tk.Frame(page, bg=t["bg_app"], pady=4)
            next_btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

            btn_step2_next = tk.Button(
                next_btn_frame,
                font=("Segoe UI", 10, "bold"),
                bg=t["accent"],
                fg=t["accent_text"],
                activebackground=t["accent_hover"],
                activeforeground=t["accent_text"],
                padx=18,
                pady=8,
                relief="flat",
                cursor="hand2",
                command=self.complete_step2_and_go_step3
            )
            apply_button_icon(btn_step2_next, "check", "Сформировать и перейти к Сверке (Шаг 3) ➔", size=18)
            btn_step2_next.pack(side=tk.RIGHT)
            ToolTip(btn_step2_next, "Объединить P&P с BOM и автоматически передать файл в модуль сверки (Шаг 3)")

    def set_pnp_data(self, df, path="", notify_merge=True):
        if hasattr(self, 'check_tab') and self.check_tab:
            self.check_tab.update_pnp_data(df, path)
        if notify_merge and hasattr(self, 'merge_tab') and self.merge_tab:
            self.merge_tab.update_pnp_data(df, path)

    def set_bom_data(self, df, path=""):
        if hasattr(self, 'check_tab') and self.check_tab:
            self.check_tab.update_bom_data(df, path)
        if hasattr(self, 'merge_tab') and self.merge_tab:
            self.merge_tab.update_bom_data(df, path)

    def set_bom_columns(self, ref_col, val_col, sep):
        self.bom_ref_col = ref_col
        self.bom_val_col = val_col
        self.bom_sep = sep

    def get_bom_columns(self):
        return getattr(self, 'bom_ref_col', ''), getattr(self, 'bom_val_col', ''), getattr(self, 'bom_sep', ',')

    def complete_step2_and_go_step3(self):
        """Выполняет объединение и передает результаты в Шаг 3 (Сверка)."""
        if hasattr(self, 'merge_tab') and self.merge_tab:
            if self.merge_tab.result_df is None:
                try:
                    self.merge_tab.merge_data()
                except Exception as e:
                    messagebox.showerror("Ошибка объединения", f"Не удалось объединить P&P и BOM:\n{e}")
                    return

            if self.merge_tab.result_df is not None and hasattr(self, 'check_tab') and self.check_tab:
                self.check_tab.update_pnp_data(self.merge_tab.result_df, "Merged_PnP_Output")
                if self.merge_tab.bom_df is not None:
                    self.check_tab.update_bom_data(self.merge_tab.bom_df, self.merge_tab.bom_file.get())

        self.show_page("step3")

    # =========================================================================
    # Страница 3: Шаг 3 — Финальная Сверка P&P с BOM
    # =========================================================================
    def _build_page_step3(self, parent):
        t = THEMES["dark"]
        page = tk.Frame(parent, bg=t["bg_app"])
        self.pages["step3"] = page

        if CheckTab:
            self.check_tab = CheckTab(page, self)
            self.check_tab.pack(fill=tk.BOTH, expand=True)

        # Нижняя панель завершения сессии и сброса
        bottom_bar = tk.Frame(page, bg=t["bg_app"], pady=6)
        bottom_bar.pack(fill=tk.X, side=tk.BOTTOM)

        lbl_info = tk.Label(
            bottom_bar,
            font=("Segoe UI", 9),
            bg=t["bg_app"],
            fg=t["text_muted"]
        )
        apply_label_icon(lbl_info, "step3", "Финальный этап: аудит данных выполнен. Для подготовки нового заказа завершите текущую сессию.", size=16)
        lbl_info.pack(side=tk.LEFT, padx=4)

        btn_finish = tk.Button(
            bottom_bar,
            font=("Segoe UI", 10, "bold"),
            bg="#7f1d1d",
            fg="#fecaca",
            activebackground="#991b1b",
            activeforeground="#ffffff",
            relief="flat",
            padx=18,
            pady=8,
            cursor="hand2",
            command=self.finish_session_and_reset
        )
        apply_button_icon(btn_finish, "reset", "Завершить сессию (Сброс программы) ➔", size=18)
        btn_finish.pack(side=tk.RIGHT, padx=4)
        ToolTip(btn_finish, "Завершить текущую сессию создания файла и полностью сбросить программу до состояния «Только что открыта»")

    def finish_session_and_reset(self):
        """
        Завершает текущую сессию создания файла и сбрасывает программу
        до состояния 'Только что открыта'. Показывает модальное окно с предупреждением.
        """
        t = THEMES["dark"]

        dialog = tk.Toplevel(self.root)
        dialog.title("⚠️ Завершение сессии и сброс программы")
        dw, dh = 580, 420
        dialog.geometry(f"{dw}x{dh}")
        dialog.minsize(540, 390)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=t["bg_app"])
        set_window_titlebar_theme(dialog, True)

        # Центрирование окна относительно главного приложения
        dialog.update_idletasks()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        dx = max(0, rx + (rw - dw) // 2)
        dy = max(0, ry + (rh - dh) // 2)
        dialog.geometry(f"{dw}x{dh}+{dx}+{dy}")

        card = tk.Frame(dialog, bg=t["bg_card"], padx=24, pady=20, highlightbackground="#dc2626", highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        confirmed = {"value": False}

        def on_confirm():
            confirmed["value"] = True
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        # 1. Пакуем панель кнопок снизу (side=tk.BOTTOM) ПЕРВОЙ, чтобы она ВСЕГДА гарантированно отображалась
        btn_box = tk.Frame(card, bg=t["bg_card"])
        btn_box.pack(fill=tk.X, side=tk.BOTTOM, pady=(16, 0))

        btn_cancel = tk.Button(
            btn_box,
            text="Отмена (вернуться к работе)",
            font=("Segoe UI", 9),
            bg=t["btn_sec_bg"],
            fg=t["btn_sec_fg"],
            relief="flat",
            padx=16,
            pady=8,
            cursor="hand2",
            command=on_cancel
        )
        btn_cancel.pack(side=tk.LEFT)

        btn_yes = tk.Button(
            btn_box,
            text="🔄 Да, сбросить всю программу",
            font=("Segoe UI", 9, "bold"),
            bg="#b91c1c",
            fg="#ffffff",
            activebackground="#dc2626",
            activeforeground="#ffffff",
            relief="flat",
            padx=18,
            pady=8,
            cursor="hand2",
            command=on_confirm
        )
        btn_yes.pack(side=tk.RIGHT)

        # 2. Шапка диалога сверху
        header_frame = tk.Frame(card, bg=t["bg_card"])
        header_frame.pack(fill=tk.X, side=tk.TOP, pady=(0, 10))

        tk.Label(
            header_frame,
            text="⚠️ Внимание: Полный сброс программы",
            font=("Segoe UI", 13, "bold"),
            bg=t["bg_card"],
            fg="#f87171"
        ).pack(side=tk.LEFT)

        warning_text = (
            "Вы собираетесь завершить текущую сессию создания файлов.\n\n"
            "Это действие ПОЛНОСТЬЮ СБРОСИТ всю программу до первоначального "
            "состояния «Только что открыта»:\n\n"
            "• Все загруженные спецификации (BOM) и файлы расстановщика (P&P) будут очищены\n"
            "• Все результаты унификации, сопоставления и финальной сверки удалятся\n"
            "• Любые несохранённые промежуточные данные будут утеряны\n\n"
            "Вы действительно хотите завершить сессию и сбросить всё?"
        )

        tk.Label(
            card,
            text=warning_text,
            font=("Segoe UI", 9),
            bg=t["bg_card"],
            fg=t["text_secondary"],
            justify=tk.LEFT,
            wraplength=490
        ).pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 10))

        dialog.wait_window()

        if not confirmed["value"]:
            return

        self.reset_all_data()

    def reset_all_data(self):
        """Полный сброс всех данных программы к состоянию 'Только что открыта'."""
        # 1. Очистка переменных сквозного заказа
        self.unified_bom_path = ""
        self.unified_bom_df = None
        self.merged_pnp_path = ""
        self.merged_pnp_df = None
        self.bom_ref_col = ""
        self.bom_val_col = ""
        self.bom_sep = ","

        # 2. Пересоздание страниц Шагов 1, 2, 3 и вспомогательных модулей
        for pid in ["step1", "step2", "step3", "compare_pnp", "compare_bom"]:
            if pid in self.pages and self.pages[pid]:
                try:
                    self.pages[pid].destroy()
                except Exception:
                    pass

        self._build_page_step1(self.pages_container)
        self._build_page_step2(self.pages_container)
        self._build_page_step3(self.pages_container)
        self._build_page_compare_pnp(self.pages_container)
        self._build_page_compare_bom(self.pages_container)

        # 3. Обновление бейджей и индикаторов файлов
        self._update_dashboard_file_status()

        # 4. Переход на стартовую страницу Dashboard
        self.show_page("dashboard")

        # 5. Уведомление пользователя
        messagebox.showinfo(
            "Сессия завершена",
            "Текущая сессия успешно завершена.\nВсе временные данные очищены, программа сброшена в исходное состояние «Только что открыта»."
        )

    # =========================================================================
    # Страница 4: Сравнение P&P версий
    # =========================================================================
    def _build_page_compare_pnp(self, parent):
        t = THEMES["dark"]
        page = tk.Frame(parent, bg=t["bg_app"])
        self.pages["compare_pnp"] = page

        if CompareTab:
            self.compare_pnp_tab = CompareTab(page, self)
            self.compare_pnp_tab.pack(fill=tk.BOTH, expand=True)

    # =========================================================================
    # Страница 5: Сверка спецификаций BOM
    # =========================================================================
    def _build_page_compare_bom(self, parent):
        t = THEMES["dark"]
        page = tk.Frame(parent, bg=t["bg_app"])
        self.pages["compare_bom"] = page

        if CompareBOMTab:
            self.compare_bom_tab = CompareBOMTab(page, self)
            self.compare_bom_tab.pack(fill=tk.BOTH, expand=True)

    # =========================================================================
    # Страница 6: База данных соответствий
    # =========================================================================
    def _build_page_database(self, parent):
        t = THEMES["dark"]
        page = tk.Frame(parent, bg=t["bg_app"])
        self.pages["database"] = page

        if DatabaseTab and self.db_manager:
            self.database_tab = DatabaseTab(page, self.db_manager)
            self.database_tab.account_manager = self.account_manager
            self.database_tab.pack(fill=tk.BOTH, expand=True)

    # =========================================================================
    # Вспомогательные сервисы
    # =========================================================================
    def open_barcode_decoder(self):
        """Открывает десктопный Barcode Decoder как отдельное окно."""
        try:
            import importlib.util
            barcode_script = os.path.join(CURRENT_DIR, "BarcodeDecoder_1.1.py")
            if not os.path.exists(barcode_script):
                barcode_script = os.path.join(os.path.dirname(__file__), "BarcodeDecoder_1.1.py")
            if os.path.exists(barcode_script):
                spec = importlib.util.spec_from_file_location("barcode_module", barcode_script)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                win = create_styled_toplevel(self.root, "📷 Barcode Decoder v1.1", "1040x820", "dark")
                app = mod.BarcodeDecoderApp(win)
                style_widget_tree(win, "dark")
                enable_smooth_mousewheel(win)
                return
        except Exception as e:
            print(f"Error opening BarcodeDecoder: {e}")
        messagebox.showinfo("Barcode Decoder", "Модуль Barcode Decoder доступен в корневом каталоге.")


# =============================================================================
# Точка входа программы
# =============================================================================
def main():
    root = tk.Tk()
    app = SMDHubApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
