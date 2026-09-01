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

# Импортируем классы из Unification и PnP_Manager
try:
    from Unification import DatabaseManager, DatabaseTab, CodeTab, DescriptionTab
except Exception as e:
    DatabaseManager = None
    DatabaseTab = None
    CodeTab = None
    DescriptionTab = None
    print(f"Warning: Could not import Unification directly: {e}")

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
        self.root.geometry("1520x960")
        self.root.minsize(1280, 780)

        # Тема оформления — строго Dark Navy SaaS
        self.current_theme = "dark"
        self.style = ttk.Style()
        self._setup_window_icon()

        # База данных для унификации (сохраняем рядом с exe в portable-режиме)
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            user_db_path = os.path.join(exe_dir, "database.txt")
            bundled_db_path = os.path.join(CURRENT_DIR, "database.txt")
            if not os.path.exists(user_db_path) and os.path.exists(bundled_db_path):
                try:
                    import shutil
                    shutil.copy2(bundled_db_path, user_db_path)
                except Exception:
                    pass
            db_path = user_db_path if os.path.exists(user_db_path) else bundled_db_path
        else:
            db_path = os.path.join(CURRENT_DIR, "Unification", "database.txt")
            if not os.path.exists(db_path):
                db_path = os.path.join(CURRENT_DIR, "database.txt")
        self.db_manager = DatabaseManager(db_path) if DatabaseManager else None

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

        # 2. Правая рабочая область (Хедер + Контент)
        self.right_workspace = tk.Frame(self.layout_frame, bg=t["bg_app"])
        self.right_workspace.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Верхний хедер
        self._build_top_header(self.right_workspace)

        # Верхняя панель быстрых действий (Action Bar)
        self._build_action_bar(self.right_workspace)

        # Главный контейнер страниц
        self.pages_container = tk.Frame(self.right_workspace, bg=t["bg_app"])
        self.pages_container.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        # Создаем страницы
        self.pages = {}
        self._build_page_dashboard(self.pages_container)
        self._build_page_step1(self.pages_container)
        self._build_page_step2(self.pages_container)
        self._build_page_step3(self.pages_container)
        self._build_page_compare_pnp(self.pages_container)
        self._build_page_compare_bom(self.pages_container)
        self._build_page_database(self.pages_container)

        # Показываем стартовую страницу Dashboard
        self.show_page("dashboard")

    # =========================================================================
    # Левый сайдбар (Dark Navy SaaS Sidebar)
    # =========================================================================
    def _build_sidebar(self, parent):
        t = THEMES["dark"]
        self.sidebar_frame = tk.Frame(parent, width=240, bg=t["bg_sidebar"])
        self.sidebar_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar_frame.pack_propagate(False)

        # Логотип и бренд
        brand_frame = tk.Frame(self.sidebar_frame, bg=t["bg_sidebar"], padx=18, pady=16)
        brand_frame.pack(fill=tk.X)

        logo_title = tk.Label(
            brand_frame,
            text="⚡ SMD Hub",
            font=("Segoe UI", 15, "bold"),
            bg=t["bg_sidebar"],
            fg=t["text_primary"]
        )
        logo_title.pack(anchor="w")

        logo_sub = tk.Label(
            brand_frame,
            text="SMD Production Suite",
            font=("Segoe UI", 8),
            bg=t["bg_sidebar"],
            fg=t["text_muted"]
        )
        logo_sub.pack(anchor="w", pady=(1, 0))

        # Разделитель
        sep = tk.Frame(self.sidebar_frame, height=1, bg=t["border"])
        sep.pack(fill=tk.X, padx=14, pady=(0, 10))

        # Контейнер для навигационных элементов
        self.nav_items_frame = tk.Frame(self.sidebar_frame, bg=t["bg_sidebar"], padx=8)
        self.nav_items_frame.pack(fill=tk.BOTH, expand=True)

        self.nav_widgets = {}
        self.hovered_nav_id = None

        # 1. Dashboard
        self._add_nav_item("dashboard", "📊  Обзор (Dashboard)", lambda: self.show_page("dashboard"))

        # 2. Сквозной заказ (Заголовок группы)
        group_label = tk.Label(
            self.nav_items_frame,
            text="СКВОЗНОЙ ЗАКАЗ",
            font=("Segoe UI", 8, "bold"),
            bg=t["bg_sidebar"],
            fg=t["text_muted"],
            anchor="w",
            padx=10,
            pady=8
        )
        group_label.pack(fill=tk.X, pady=(6, 2))

        # Поддерево шагов с точками-маркерами (Sub-tree timeline)
        tree_container = tk.Frame(self.nav_items_frame, bg=t["bg_sidebar"])
        tree_container.pack(fill=tk.X, padx=(4, 0))

        self._add_nav_subitem(tree_container, "step1", "1. Унификация BOM", lambda: self.show_page("step1"))
        self._add_nav_subitem(tree_container, "step2", "2. Объединение P&P", lambda: self.show_page("step2"))
        self._add_nav_subitem(tree_container, "step3", "3. Финальная сверка", lambda: self.show_page("step3"))

        # 3. Сервисные модули
        group_label2 = tk.Label(
            self.nav_items_frame,
            text="СЕРВИСЫ И БАЗЫ",
            font=("Segoe UI", 8, "bold"),
            bg=t["bg_sidebar"],
            fg=t["text_muted"],
            anchor="w",
            padx=10,
            pady=8
        )
        group_label2.pack(fill=tk.X, pady=(10, 2))

        self._add_nav_item("compare_pnp", "🔄  Сравнение P&P", lambda: self.show_page("compare_pnp"))
        self._add_nav_item("compare_bom", "🔄  Сверка BOM", lambda: self.show_page("compare_bom"))
        self._add_nav_item("database", "🗄️  База данных", lambda: self.show_page("database"))
        self._add_nav_item("barcode", "📷  Barcode Decoder", self.open_barcode_decoder)

        # Привязка сброса наведения при выходе мыши из сайдбара
        self.sidebar_frame.bind("<Leave>", self._on_sidebar_leave)
        self.nav_items_frame.bind("<Leave>", self._on_sidebar_leave)
        tree_container.bind("<Leave>", self._on_sidebar_leave)

        # Нижняя карточка пользователя
        user_card = tk.Frame(self.sidebar_frame, bg=t["bg_card"], padx=12, pady=10, highlightbackground=t["border"], highlightthickness=1)
        user_card.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=12)

        user_top = tk.Frame(user_card, bg=t["bg_card"])
        user_top.pack(fill=tk.X)

        tk.Label(user_top, text="👤 Оператор SMD", font=("Segoe UI", 9, "bold"), bg=t["bg_card"], fg=t["text_primary"]).pack(side=tk.LEFT)
        tk.Label(user_top, text="🟢 Готов", font=("Segoe UI", 8), bg=t["bg_card"], fg=t["success_fg"]).pack(side=tk.RIGHT)

        tk.Label(user_card, text="PnP Manager v1.2 SaaS", font=("Segoe UI", 8), bg=t["bg_card"], fg=t["text_muted"]).pack(anchor="w", pady=(2, 0))

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
            fnt = ("Segoe UI", 9, "bold")
        elif state == "hover":
            bg_col = "#141f38"
            fg_col = "#f8fafc"
            dot_col = "#38bdf8"
            ind_col = "#141f38"
            fnt = ("Segoe UI", 9)
        else: # normal
            bg_col = t["bg_sidebar"]           # #090d1a
            fg_col = t["text_secondary"]       # #94a3b8
            dot_col = t["text_muted"]          # #64748b
            ind_col = t["bg_sidebar"]          # #090d1a
            fnt = ("Segoe UI", 9)

        item["frame"].configure(bg=bg_col)
        item["label"].configure(bg=bg_col, fg=fg_col, font=fnt)
        if "indicator" in item:
            item["indicator"].configure(bg=ind_col)
        if "line_box" in item:
            item["line_box"].configure(bg=bg_col)
        if "dot" in item:
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

    def _add_nav_item(self, item_id: str, text: str, command):
        t = THEMES["dark"]
        btn_frame = tk.Frame(self.nav_items_frame, bg=t["bg_sidebar"], cursor="hand2")
        btn_frame.pack(fill=tk.X, pady=2)

        # Индикатор слева
        indicator = tk.Frame(btn_frame, width=3, bg=t["bg_sidebar"])
        indicator.pack(side=tk.LEFT, fill=tk.Y)

        label = tk.Label(
            btn_frame,
            text=text,
            font=("Segoe UI", 9),
            bg=t["bg_sidebar"],
            fg=t["text_secondary"],
            anchor="w",
            padx=10,
            pady=7
        )
        label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.nav_widgets[item_id] = {
            "frame": btn_frame,
            "label": label,
            "indicator": indicator,
            "is_subitem": False
        }

        def on_click(e=None):
            command()

        for w in (btn_frame, label, indicator):
            w.bind("<Button-1>", on_click)
            w.bind("<Enter>", lambda e, i=item_id: self._on_nav_enter(i))
            w.bind("<Leave>", lambda e, i=item_id: self._on_nav_leave(i))

    def _add_nav_subitem(self, container, item_id: str, text: str, command):
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
            text=text,
            font=("Segoe UI", 9),
            bg=t["bg_sidebar"],
            fg=t["text_secondary"],
            anchor="w",
            padx=4,
            pady=6
        )
        label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.nav_widgets[item_id] = {
            "frame": btn_frame,
            "label": label,
            "line_box": line_box,
            "dot": dot,
            "is_subitem": True
        }

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
            ("database", "База данных"),
            ("compare_pnp", "Сравнение P&P"),
            ("compare_bom", "Сверка BOM")
        ]

        for tab_id, tab_title in tabs:
            tab_box = tk.Frame(self.header_tabs_frame, bg=t["bg_header"], cursor="hand2", padx=12)
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

        db_count = len(self.db_manager.data) if self.db_manager else 0
        self.badge_db = tk.Label(
            right_header,
            text=f"🗄️ База: {db_count} записей",
            font=("Segoe UI", 8, "bold"),
            bg=t["bg_card"],
            fg=t["text_header"],
            padx=10,
            pady=4,
            cursor="hand2"
        )
        self.badge_db.pack(side=tk.LEFT, padx=6, pady=12)
        self.badge_db.bind("<Button-1>", lambda e: self.show_page("database"))
        ToolTip(self.badge_db, "Открыть базу данных (database.txt)")

        btn_faq = tk.Button(
            right_header,
            text="📖 FAQ & Справка",
            font=("Segoe UI", 8),
            bg=t["btn_sec_bg"],
            fg=t["btn_sec_fg"],
            relief="flat",
            padx=8,
            pady=3,
            cursor="hand2",
            command=lambda: show_faq_dialog(self.root, "dark")
        )
        btn_faq.pack(side=tk.LEFT, padx=4, pady=12)

        btn_feedback = tk.Button(
            right_header,
            text="✉️ Обратная связь",
            font=("Segoe UI", 8),
            bg=t["btn_sec_bg"],
            fg=t["btn_sec_fg"],
            relief="flat",
            padx=8,
            pady=3,
            cursor="hand2",
            command=lambda: show_feedback_dialog(self.root, "dark")
        )
        btn_feedback.pack(side=tk.LEFT, padx=4, pady=12)

    # =========================================================================
    # Верхняя панель действий (Action Bar)
    # =========================================================================
    def _build_action_bar(self, parent):
        t = THEMES["dark"]
        self.action_bar = tk.Frame(parent, height=50, bg=t["bg_app"], padx=16, pady=8)
        self.action_bar.pack(fill=tk.X)

        # Ярко-голубые кнопки-пилюли в стиле референса
        self.btn_act_new = tk.Button(
            self.action_bar,
            text="➕ Загрузить BOM / Создать заказ ▼",
            font=("Segoe UI", 9, "bold"),
            bg=t["accent"],
            fg=t["accent_text"],
            activebackground=t["accent_hover"],
            activeforeground=t["accent_text"],
            relief="flat",
            padx=14,
            pady=6,
            cursor="hand2",
            command=lambda: self.show_page("step1")
        )
        self.btn_act_new.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_act_merge = tk.Button(
            self.action_bar,
            text="⚙️ Сшить P&P координаты",
            font=("Segoe UI", 9),
            bg=t["btn_sec_bg"],
            fg=t["btn_sec_fg"],
            activebackground=t["btn_sec_hover"],
            activeforeground=t["text_primary"],
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            command=lambda: self.show_page("step2")
        )
        self.btn_act_merge.pack(side=tk.LEFT, padx=4)

        self.btn_act_check = tk.Button(
            self.action_bar,
            text="🔍 Проверить и сформировать отчет",
            font=("Segoe UI", 9),
            bg=t["btn_sec_bg"],
            fg=t["btn_sec_fg"],
            activebackground=t["btn_sec_hover"],
            activeforeground=t["text_primary"],
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            command=lambda: self.show_page("step3")
        )
        self.btn_act_check.pack(side=tk.LEFT, padx=4)

        # Правый статус текущего процесса
        self.lbl_pipeline_status = tk.Label(
            self.action_bar,
            text="📍 Процесс: Шаг 1 (Унификация) ➔ Шаг 2 (Объединение) ➔ Шаг 3 (Сверка)",
            font=("Segoe UI", 8),
            bg=t["bg_app"],
            fg=t["text_muted"]
        )
        self.lbl_pipeline_status.pack(side=tk.RIGHT, padx=4)

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
        for pid, item in self.nav_widgets.items():
            is_active = (pid == page_id)
            if item.get("is_subitem"):
                item["frame"].configure(bg=t["nav_active_bg"] if is_active else t["bg_sidebar"])
                item["label"].configure(
                    bg=t["nav_active_bg"] if is_active else t["bg_sidebar"],
                    fg=t["text_primary"] if is_active else t["text_secondary"],
                    font=("Segoe UI", 9, "bold" if is_active else "normal")
                )
                item["dot"].configure(
                    bg=t["nav_active_bg"] if is_active else t["bg_sidebar"],
                    fg=t["accent"] if is_active else t["text_muted"]
                )
            else:
                item["frame"].configure(bg=t["nav_active_bg"] if is_active else t["bg_sidebar"])
                item["label"].configure(
                    bg=t["nav_active_bg"] if is_active else t["bg_sidebar"],
                    fg=t["text_primary"] if is_active else t["text_secondary"],
                    font=("Segoe UI", 9, "bold" if is_active else "normal")
                )
                if "indicator" in item:
                    item["indicator"].configure(bg=t["nav_active_border"] if is_active else t["bg_sidebar"])

        # Обновляем горизонтальные вкладки в хедере
        for tid, tab in self.header_tabs.items():
            is_active = (tid == page_id)
            tab["label"].configure(
                fg=t["text_header"] if is_active else t["text_secondary"]
            )
            tab["underline"].configure(
                bg=t["nav_active_border"] if is_active else t["bg_header"]
            )

        # Обновляем бейдж базы
        if hasattr(self, 'badge_db') and self.db_manager:
            self.badge_db.configure(text=f"🗄️ База: {len(self.db_manager.data)} записей")

    # =========================================================================
    # Страница 0: Dashboard (Обзор состояния заказа)
    # =========================================================================
    def _build_page_dashboard(self, parent):
        t = THEMES["dark"]
        page = tk.Frame(parent, bg=t["bg_app"])
        self.pages["dashboard"] = page

        # Метрические карточки в один ряд (как в современных SaaS-дашбордах)
        metrics_frame = tk.Frame(page, bg=t["bg_app"])
        metrics_frame.pack(fill=tk.X, pady=(0, 14))

        db_count = len(self.db_manager.data) if self.db_manager else 0

        cards_data = [
            ("🗄️ База данных", f"{db_count}", "Записей в database.txt", lambda: self.show_page("database")),
            ("🗂️ Исходный BOM", "Не загружен" if not self.unified_bom_path else os.path.basename(self.unified_bom_path), "Файл спецификации компонентов", lambda: self.show_page("step1")),
            ("📍 Монтажный P&P", "Не загружен" if not self.merged_pnp_path else os.path.basename(self.merged_pnp_path), "Координаты расстановщика", lambda: self.show_page("step2")),
            ("🔍 Статус проверки", "Готов к работе", "Финальный выходной контроль", lambda: self.show_page("step3"))
        ]

        for title, value, subtitle, cmd in cards_data:
            card = tk.Frame(metrics_frame, bg=t["bg_card"], padx=16, pady=14, cursor="hand2",
                            highlightbackground=t["border"], highlightthickness=1)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

            tk.Label(card, text=title, font=("Segoe UI", 9, "bold"), bg=t["bg_card"], fg=t["text_header"]).pack(anchor="w")
            lbl_val = tk.Label(card, text=value, font=("Segoe UI", 13, "bold"), bg=t["bg_card"], fg=t["text_primary"])
            lbl_val.pack(anchor="w", pady=(4, 2))
            tk.Label(card, text=subtitle, font=("Segoe UI", 8), bg=t["bg_card"], fg=t["text_muted"]).pack(anchor="w")

            card.bind("<Button-1>", lambda e, c=cmd: c())
            lbl_val.bind("<Button-1>", lambda e, c=cmd: c())

        # Главная карточка: Пошаговый пайплайн заказа
        pipeline_card = tk.Frame(page, bg=t["bg_card"], padx=20, pady=18, highlightbackground=t["border"], highlightthickness=1)
        pipeline_card.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            pipeline_card,
            text="🚀 Сквозной производственный цикл подготовки монтажа",
            font=("Segoe UI", 12, "bold"),
            bg=t["bg_card"],
            fg=t["text_primary"]
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            pipeline_card,
            text="Выполняйте этапы последовательно. Результат каждого шага автоматически передается на следующий этап без необходимости повторного выбора файлов.",
            font=("Segoe UI", 9),
            bg=t["bg_card"],
            fg=t["text_secondary"]
        ).pack(anchor="w", pady=(0, 16))

        # 3 большие карточки шагов
        steps_box = tk.Frame(pipeline_card, bg=t["bg_card"])
        steps_box.pack(fill=tk.BOTH, expand=True)

        step_cards_info = [
            ("Шаг 1: 🗂️ Унификация BOM",
             "Нормализация заводских кодов (Samsung, Murata, Yageo, TDK, Р1-12...) и русскоязычных описаний. Приведение к единому складскому стандарту.",
             "Начать унификацию BOM ➔", "step1"),
            ("Шаг 2: ⚙️ Объединение P&P + BOM",
             "Сшивание монтажных координат (X, Y, Rotation, Side) с унифицированными наименованиями. Автоподбор колонок и конвертация mil/мм.",
             "Перейти к объединению P&P ➔", "step2"),
            ("Шаг 3: 🔍 Финальная сверка",
             "Контроль DNP позиций, выявление пропущенных или лишних элементов, сводная статистика по слоям TOP/BOTTOM и экспорт для автомата.",
             "Перейти к сверке ➔", "step3")
        ]

        for st_title, st_desc, st_btn, st_target in step_cards_info:
            c = tk.Frame(steps_box, bg=t["bg_card_inner"], padx=16, pady=16, highlightbackground=t["border"], highlightthickness=1)
            c.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6)

            tk.Label(c, text=st_title, font=("Segoe UI", 11, "bold"), bg=t["bg_card_inner"], fg=t["text_header"]).pack(anchor="w")
            tk.Label(c, text=st_desc, font=("Segoe UI", 9), bg=t["bg_card_inner"], fg=t["text_secondary"], wraplength=260, justify=tk.LEFT).pack(anchor="w", pady=(8, 14), fill=tk.BOTH, expand=True)

            btn = tk.Button(
                c,
                text=st_btn,
                font=("Segoe UI", 9, "bold"),
                bg=t["accent"],
                fg=t["accent_text"],
                activebackground=t["accent_hover"],
                activeforeground=t["accent_text"],
                relief="flat",
                padx=12,
                pady=6,
                cursor="hand2",
                command=lambda target=st_target: self.show_page(target)
            )
            btn.pack(side=tk.BOTTOM, fill=tk.X)

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
            text="✅ Готово: Перейти к Объединению P&P (Шаг 2) ➔",
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
                for col in self.merge_tab.bom_columns:
                    if "унифиц" in col.lower() or "unified" in col.lower() or "part" in col.lower():
                        self.merge_tab.bom_data_cb.set(col)
                        break

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
                text="✅ Сформировать и перейти к Сверке (Шаг 3) ➔",
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
# Точка входа
# =============================================================================
def main():
    root = tk.Tk()
    app = SMDHubApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
