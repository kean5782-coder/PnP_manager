import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
import pandas as pd
import re
from collections import defaultdict
import traceback

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
for p in (PARENT_DIR, CURRENT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import smd_engine
from smd_engine import (
    THEMES, ToolTip, get_system_theme, set_window_titlebar_theme,
    apply_ttk_theme, show_feedback_dialog, show_faq_dialog,
    style_widget_tree, create_styled_toplevel, enable_smooth_mousewheel
)


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def is_empty_ref(value):
    if pd.isna(value):
        return True
    s = str(value).strip()
    return not s or s.lower() == 'nan'


def is_coordinate_empty(value):
    if pd.isna(value):
        return True
    s = str(value).strip()
    return not s or s.lower() == 'nan'


# ==================== ОСНОВНОЕ ПРИЛОЖЕНИЕ ====================
class MainApp:
    def __init__(self, root):
        self.root = root
        root.title("PnP Manager — Менеджер координат и спецификаций SMD")
        root.geometry("1260x840")
        root.minsize(1050, 680)

        # Тема оформления
        self.current_theme = get_system_theme()
        self.style = ttk.Style()
        self._setup_icon()

        # Общие данные
        self.pnp_df = None
        self.bom_df = None
        self.pnp_path = ""
        self.bom_path = ""

        # BOM настройки из MergeTab
        self.bom_ref_col = ""
        self.bom_val_col = ""
        self.bom_sep = ","

        # 1. Верхний современный Header
        self.header_frame = tk.Frame(self.root, height=60, padx=15, pady=8)
        self.header_frame.pack(fill=tk.X, side=tk.TOP)

        title_box = tk.Frame(self.header_frame, bg=self.header_frame["bg"])
        title_box.pack(side=tk.LEFT, fill=tk.Y)

        self.header_title = tk.Label(title_box, text="⚙️ PnP Manager", font=("Segoe UI", 13, "bold"))
        self.header_title.pack(anchor="w")

        self.header_subtitle = tk.Label(
            title_box,
            text="Объединение координат расстановки P&P с BOM, проверка DNP и сравнение ревизий",
            font=("Segoe UI", 8)
        )
        self.header_subtitle.pack(anchor="w")

        # Кнопки в шапке (справа)
        btn_box = tk.Frame(self.header_frame, bg=self.header_frame["bg"])
        btn_box.pack(side=tk.RIGHT, fill=tk.Y)

        self.btn_theme = tk.Button(btn_box, font=("Segoe UI", 8), relief="flat", padx=10, pady=4,
                                   cursor="hand2", command=self.toggle_theme)
        self.btn_theme.pack(side=tk.LEFT, padx=4)
        ToolTip(self.btn_theme, "Переключение между тёмной и светлой темой оформления")

        self.btn_faq = tk.Button(btn_box, text="📖 Справка и FAQ", font=("Segoe UI", 8),
                                 relief="flat", padx=10, pady=4, cursor="hand2",
                                 command=lambda: show_faq_dialog(self.root, self.current_theme))
        self.btn_faq.pack(side=tk.LEFT, padx=4)
        ToolTip(self.btn_faq, "Открыть руководство оператора по расстановке P&P и BOM")

        self.btn_feedback = tk.Button(btn_box, text="✉️ Обратная связь", font=("Segoe UI", 8),
                                      relief="flat", padx=10, pady=4, cursor="hand2",
                                      command=lambda: show_feedback_dialog(self.root, self.current_theme))
        self.btn_feedback.pack(side=tk.LEFT, padx=4)
        ToolTip(self.btn_feedback, "Написать разработчику (kean5782@yandex.ru)")

        # 2. Основной Notebook
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # Создаём вкладки
        self.merge_tab = MergeTab(self.notebook, self)
        self.check_tab = CheckTab(self.notebook, self)
        self.compare_tab = CompareTab(self.notebook, self)
        self.compare_bom_tab = CompareBOMTab(self.notebook, self)

        self.notebook.add(self.merge_tab, text="⚙️ Объединение P&P и BOM")
        self.notebook.add(self.check_tab, text="🔍 Сверка P&P и BOM")
        self.notebook.add(self.compare_tab, text="🔄 Сравнение PNP версий")
        self.notebook.add(self.compare_bom_tab, text="🔄 Сверка BOM спецификаций")

        self.apply_theme(self.current_theme)

    def _setup_icon(self):
        icon_path = os.path.join(PARENT_DIR, "icon.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(CURRENT_DIR, "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

    def apply_theme(self, theme_name: str):
        self.current_theme = theme_name
        t = THEMES[theme_name]
        self.root.configure(bg=t["bg_app"])
        set_window_titlebar_theme(self.root, t["is_dark"])
        apply_ttk_theme(self.style, theme_name)

        if hasattr(self, 'header_frame'):
            self.header_frame.configure(bg=t["bg_card"])
            self.header_title.configure(bg=t["bg_card"], fg=t["text_primary"])
            self.header_subtitle.configure(bg=t["bg_card"], fg=t["text_muted"])
            self.btn_theme.configure(text="☀️ Светлая тема" if t["is_dark"] else "🌙 Тёмная тема",
                                     bg=t["btn_sec_bg"], fg=t["btn_sec_fg"])
            self.btn_faq.configure(bg=t["btn_sec_bg"], fg=t["btn_sec_fg"])
            self.btn_feedback.configure(bg=t["btn_sec_bg"], fg=t["btn_sec_fg"])

        from smd_engine import style_widget_tree
        style_widget_tree(self.root, theme_name)

    def toggle_theme(self):
        new_theme = "light" if self.current_theme == "dark" else "dark"
        self.apply_theme(new_theme)

    def set_pnp_data(self, df, path="", notify_merge=True):
        """Обновляет общий PnP и уведомляет вкладки."""
        self.pnp_df = df
        self.pnp_path = path
        self.check_tab.update_pnp_data(df, path)
        if notify_merge:
            self.merge_tab.update_pnp_data(df, path)

    def set_bom_data(self, df, path=""):
        """Обновляет общий BOM и уведомляет вкладки."""
        self.bom_df = df
        self.bom_path = path
        self.check_tab.update_bom_data(df, path)
        self.merge_tab.update_bom_data(df, path)

    def set_bom_columns(self, ref_col, val_col, sep):
        """Сохраняет выбранные BOM колонки из MergeTab."""
        self.bom_ref_col = ref_col
        self.bom_val_col = val_col
        self.bom_sep = sep

    def get_bom_columns(self):
        """Возвращает сохранённые BOM колонки."""
        return self.bom_ref_col, self.bom_val_col, self.bom_sep


# ==================== ВКЛАДКА "СВЕРКА P&P И BOM" ====================
class CheckTab(ttk.Frame):
    def __init__(self, parent, main_app):
        self.parent = parent
        self.main_app = main_app
        super().__init__(parent)

        # --- Прокручиваемая область ---
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Переменные ---
        self.pnp_path = tk.StringVar()
        self.bom_path = tk.StringVar()

        self.pnp_ref_col = tk.StringVar()
        self.pnp_val_col = tk.StringVar()
        self.pnp_side_col = tk.StringVar()
        self.pnp_x_col = tk.StringVar()
        self.pnp_y_col = tk.StringVar()
        self.pnp_r_col = tk.StringVar()

        self.bom_ref_col = tk.StringVar()
        self.bom_val_col = tk.StringVar()
        self.bom_sep = tk.StringVar(value=",")

        self.df_pnp = None
        self.df_bom = None
        self.all_results = []
        self.filtered_results = []

        self.search_var = tk.StringVar()
        self.status_filter_var = tk.StringVar(value="Все")

        self.create_widgets()

    def create_widgets(self):
        t = THEMES["dark"]
        main_container = tk.Frame(self.scrollable_frame, bg=t["bg_app"])
        main_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        top_frame = tk.Frame(main_container, bg=t["bg_app"])
        top_frame.pack(fill=tk.BOTH, expand=True)

        # ------ 1. Карточка: Исходные файлы для сверки ------
        load_card = tk.Frame(top_frame, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=14, pady=10)
        load_card.pack(fill=tk.X, padx=5, pady=(4, 6))
        load_card.columnconfigure(1, weight=1)

        tk.Label(load_card, text="📁 Исходные файлы для сверки", font=("Segoe UI", 10, "bold"),
                 bg=t["bg_card"], fg=t["accent"]).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

        tk.Label(load_card, text="PNP файл (Excel):", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=1, column=0, sticky="w", pady=4)
        pnp_entry = ttk.Entry(load_card, textvariable=self.pnp_path)
        pnp_entry.grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        btn_pnp_browse = ttk.Button(load_card, text="Обзор...", command=lambda: self.load_file('pnp'))
        btn_pnp_browse.grid(row=1, column=2, padx=2, pady=4)
        btn_pnp_view = ttk.Button(load_card, text="👁️", width=3, command=lambda: self.show_preview(self.df_pnp, "PNP"))
        btn_pnp_view.grid(row=1, column=3, padx=2, pady=4)
        ToolTip(btn_pnp_view, "Предпросмотр данных PNP файла")

        tk.Label(load_card, text="BOM файл (Excel):", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=2, column=0, sticky="w", pady=4)
        bom_entry = ttk.Entry(load_card, textvariable=self.bom_path)
        bom_entry.grid(row=2, column=1, sticky="ew", padx=6, pady=4)
        btn_bom_browse = ttk.Button(load_card, text="Обзор...", command=lambda: self.load_file('bom'))
        btn_bom_browse.grid(row=2, column=2, padx=2, pady=4)
        btn_bom_view = ttk.Button(load_card, text="👁️", width=3, command=lambda: self.show_preview(self.df_bom, "BOM"))
        btn_bom_view.grid(row=2, column=3, padx=2, pady=4)
        ToolTip(btn_bom_view, "Предпросмотр данных BOM файла")

        # ------ 2. Карточка: Настройка сопоставления колонок ------
        col_card = tk.Frame(top_frame, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=14, pady=10)
        col_card.pack(fill=tk.X, padx=5, pady=(4, 6))
        col_card.columnconfigure(1, weight=1)
        col_card.columnconfigure(3, weight=1)

        tk.Label(col_card, text="⚙️ Настройка сопоставления колонок", font=("Segoe UI", 10, "bold"),
                 bg=t["bg_card"], fg=t["accent"]).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

        # PNP REF
        tk.Label(col_card, text="PNP: столбец с референсами", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=1, column=0, sticky="w", pady=3)
        self.pnp_ref_cb = ttk.Combobox(col_card, textvariable=self.pnp_ref_col, state="readonly", width=20)
        self.pnp_ref_cb.grid(row=1, column=1, sticky="ew", padx=6, pady=3)
        self.pnp_ref_cb.bind("<<ComboboxSelected>>", self.on_pnp_ref_selected)

        # PNP Value
        tk.Label(col_card, text="PNP: столбец Parts Name", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=1, column=2, sticky="w", padx=(12, 0), pady=3)
        self.pnp_val_cb = ttk.Combobox(col_card, textvariable=self.pnp_val_col, state="readonly", width=20)
        self.pnp_val_cb.grid(row=1, column=3, sticky="ew", padx=6, pady=3)
        self.pnp_val_cb.bind("<<ComboboxSelected>>", lambda e: self.update_preview('pnp', 'val', self.pnp_val_col.get()))

        # PNP Side
        tk.Label(col_card, text="PNP: столбец стороны (Side)", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=2, column=0, sticky="w", pady=3)
        self.pnp_side_cb = ttk.Combobox(col_card, textvariable=self.pnp_side_col, state="readonly", width=20)
        self.pnp_side_cb.grid(row=2, column=1, sticky="ew", padx=6, pady=3)
        self.pnp_side_cb.bind("<<ComboboxSelected>>", lambda e: self.update_preview('pnp', 'side', self.pnp_side_col.get()))

        # PNP X
        tk.Label(col_card, text="PNP: столбец X", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=2, column=2, sticky="w", padx=(12, 0), pady=3)
        self.pnp_x_cb = ttk.Combobox(col_card, textvariable=self.pnp_x_col, state="readonly", width=20)
        self.pnp_x_cb.grid(row=2, column=3, sticky="ew", padx=6, pady=3)
        self.pnp_x_cb.bind("<<ComboboxSelected>>", lambda e: self.update_preview('pnp', 'x', self.pnp_x_col.get()))

        # PNP Y
        tk.Label(col_card, text="PNP: столбец Y", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=3, column=0, sticky="w", pady=3)
        self.pnp_y_cb = ttk.Combobox(col_card, textvariable=self.pnp_y_col, state="readonly", width=20)
        self.pnp_y_cb.grid(row=3, column=1, sticky="ew", padx=6, pady=3)
        self.pnp_y_cb.bind("<<ComboboxSelected>>", lambda e: self.update_preview('pnp', 'y', self.pnp_y_col.get()))

        # PNP R
        tk.Label(col_card, text="PNP: столбец R (угол)", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=3, column=2, sticky="w", padx=(12, 0), pady=3)
        self.pnp_r_cb = ttk.Combobox(col_card, textvariable=self.pnp_r_col, state="readonly", width=20)
        self.pnp_r_cb.grid(row=3, column=3, sticky="ew", padx=6, pady=3)
        self.pnp_r_cb.bind("<<ComboboxSelected>>", lambda e: self.update_preview('pnp', 'r', self.pnp_r_col.get()))

        # BOM REF
        tk.Label(col_card, text="BOM: столбец с референсами", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=4, column=0, sticky="w", pady=3)
        self.bom_ref_cb = ttk.Combobox(col_card, textvariable=self.bom_ref_col, state="readonly", width=20)
        self.bom_ref_cb.grid(row=4, column=1, sticky="ew", padx=6, pady=3)
        self.bom_ref_cb.bind("<<ComboboxSelected>>", lambda e: self.update_preview('bom', 'ref', self.bom_ref_col.get()))

        # BOM Value
        tk.Label(col_card, text="BOM: столбец со значением", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=4, column=2, sticky="w", padx=(12, 0), pady=3)
        self.bom_val_cb = ttk.Combobox(col_card, textvariable=self.bom_val_col, state="readonly", width=20)
        self.bom_val_cb.grid(row=4, column=3, sticky="ew", padx=6, pady=3)
        self.bom_val_cb.bind("<<ComboboxSelected>>", lambda e: self.update_preview('bom', 'val', self.bom_val_col.get()))

        # BOM Разделитель
        sep_box = tk.Frame(col_card, bg=t["bg_card"])
        sep_box.grid(row=5, column=0, columnspan=4, sticky="w", pady=(6, 0))
        tk.Label(sep_box, text="Разделитель RefDes в BOM:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).pack(side=tk.LEFT)
        bom_sep_e = ttk.Entry(sep_box, textvariable=self.bom_sep, width=6)
        bom_sep_e.pack(side=tk.LEFT, padx=6)
        ToolTip(bom_sep_e, "Разделитель нескольких позиций в одной строке BOM")

        # ------ 3. Карточка: Предпросмотр значений ------
        preview_card = tk.Frame(top_frame, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=14, pady=8)
        preview_card.pack(fill=tk.X, padx=5, pady=(4, 6))

        tk.Label(preview_card, text="📋 Предпросмотр значений", font=("Segoe UI", 10, "bold"),
                 bg=t["bg_card"], fg=t["text_header"]).pack(anchor="w", pady=(0, 4))

        preview_inner = tk.Frame(preview_card, bg=t["bg_card_inner"], highlightbackground=t["border"], highlightthickness=1, padx=10, pady=6)
        preview_inner.pack(fill=tk.X)

        self.preview_label = tk.Label(preview_inner, text="Выберите колонку выше для быстрого просмотра первых 20 значений",
                                      font=("Consolas", 9), bg=t["bg_card_inner"], fg=t["text_secondary"], anchor="w", justify="left", wraplength=1100)
        self.preview_label.pack(fill=tk.X)

        # ------ 4. Карточка: Фильтр результатов ------
        filter_card = tk.Frame(top_frame, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=14, pady=8)
        filter_card.pack(fill=tk.X, padx=5, pady=(4, 6))

        tk.Label(filter_card, text="🔍 Поиск (RefDes или значение):", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).pack(side="left", padx=(0, 6))
        search_ent = ttk.Entry(filter_card, textvariable=self.search_var, width=22)
        search_ent.pack(side="left", padx=4)

        btn_apply_filter = tk.Button(filter_card, text="Применить фильтр", command=self.apply_filter,
                                     bg=t["btn_sec_bg"], fg=t["btn_sec_fg"], activebackground=t["btn_sec_hover"],
                                     font=("Segoe UI", 9), relief="flat", padx=10, pady=4, cursor="hand2")
        btn_apply_filter.pack(side="left", padx=4)

        tk.Label(filter_card, text="Статус:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).pack(side="left", padx=(14, 4))
        self.status_filter_cb = ttk.Combobox(filter_card, textvariable=self.status_filter_var,
                                             values=["Все","OK","Только в PNP","Только в BOM","Несовпадение значений"],
                                             state="readonly", width=18)
        self.status_filter_cb.pack(side="left", padx=4)
        self.status_filter_cb.bind("<<ComboboxSelected>>", lambda e: self.apply_filter())

        btn_reset_filter = tk.Button(filter_card, text="Сбросить фильтр", command=self.reset_filter,
                                     bg=t["btn_sec_bg"], fg=t["text_muted"], activebackground=t["btn_sec_hover"],
                                     font=("Segoe UI", 9), relief="flat", padx=10, pady=4, cursor="hand2")
        btn_reset_filter.pack(side="left", padx=4)

        # Кнопка «Запустить проверку» — выделенная акцентная плашка
        run_frame = tk.Frame(top_frame, bg=t["bg_app"], pady=6)
        run_frame.pack(fill=tk.X)
        btn_run = tk.Button(run_frame, text="🔍 Запустить проверку", command=self.run_check,
                            bg=t["accent"], fg=t["accent_text"], activebackground=t["accent_hover"],
                            activeforeground=t["accent_text"], font=("Segoe UI", 11, "bold"),
                            relief="flat", padx=26, pady=8, cursor="hand2")
        btn_run.pack(anchor="center")

        # ------ 5. Карточка: Результаты проверки ------
        result_card = tk.Frame(top_frame, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=12, pady=10)
        result_card.pack(fill=tk.BOTH, expand=True, padx=5, pady=(4, 6))

        tk.Label(result_card, text="📊 Результаты проверки (клик по заголовку для сортировки)",
                 font=("Segoe UI", 10, "bold"), bg=t["bg_card"], fg=t["text_header"]).pack(anchor="w", pady=(0, 6))

        tree_box = tk.Frame(result_card, bg=t["bg_card"])
        tree_box.pack(fill=tk.BOTH, expand=True)

        columns = ("RefDes", "Статус", "Значение в PNP", "Значение в BOM")
        self.tree = ttk.Treeview(tree_box, columns=columns, show="headings", height=12)
        for col in columns:
            self.tree.heading(col, text=col, command=lambda c=col: self.sort_treeview(c, False))
            self.tree.column(col, width=150)

        # Теги для чередования строк (zebra stripes)
        self.tree.tag_configure("evenrow", background=t["row_even"])
        self.tree.tag_configure("oddrow", background=t["row_odd"])

        self.tree.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(tree_box, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)

        self.tree_placeholder = tk.Label(self.tree, text="Нажмите «🔍 Запустить проверку» для анализа соответствий P&P и BOM",
                                         font=("Segoe UI", 10), bg=t["tree_bg"], fg=t["text_muted"])
        self.tree_placeholder.place(relx=0.5, rely=0.4, anchor="center")

        # Информационная плашка со статистикой
        stats_card = tk.Frame(top_frame, bg=t["bg_card_inner"], highlightbackground=t["border"], highlightthickness=1, padx=12, pady=6)
        stats_card.pack(fill=tk.X, padx=5, pady=(2, 6))

        self.stats_label = tk.Label(stats_card, text="Готов к проверке. Задайте файлы и запустите аудит.",
                                    font=("Segoe UI", 9, "bold"), bg=t["bg_card_inner"], fg=t["text_secondary"], anchor=tk.W)
        self.stats_label.pack(fill=tk.X)

        # ------ Панель экспорта (закреплена снизу) ------
        btn_frame = tk.Frame(main_container, bg=t["bg_app"])
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 2))

        # Группа 1: Отчёт
        tk.Button(btn_frame, text="📥 Экспортировать отчёт по проверке", command=self.export_report,
                  bg=t["btn_sec_bg"], fg=t["btn_sec_fg"], activebackground=t["btn_sec_hover"],
                  font=("Segoe UI", 9), relief="flat", padx=12, pady=6, cursor="hand2").pack(side="left", padx=(0, 6))

        # Разделитель
        tk.Frame(btn_frame, width=1, bg=t["border"]).pack(side="left", fill="y", padx=6, pady=2)

        # Группа 2: PnP только OK
        tk.Button(btn_frame, text="📤 PnP только OK (Excel)", command=self.export_pnp_ok_excel,
                  bg="#059669", fg="#ffffff", activebackground="#10b981",
                  font=("Segoe UI", 9, "bold"), relief="flat", padx=12, pady=6, cursor="hand2").pack(side="left", padx=3)
        tk.Button(btn_frame, text="📤 PnP только OK (TXT)", command=self.export_pnp_ok_txt,
                  bg="#059669", fg="#ffffff", activebackground="#10b981",
                  font=("Segoe UI", 9, "bold"), relief="flat", padx=12, pady=6, cursor="hand2").pack(side="left", padx=3)

        # Разделитель
        tk.Frame(btn_frame, width=1, bg=t["border"]).pack(side="left", fill="y", padx=6, pady=2)

        # Группа 3: Весь PnP
        tk.Button(btn_frame, text="📤 Весь PnP (Excel)", command=self.export_pnp_all_excel,
                  bg=t["accent"], fg=t["accent_text"], activebackground=t["accent_hover"],
                  font=("Segoe UI", 9, "bold"), relief="flat", padx=12, pady=6, cursor="hand2").pack(side="left", padx=3)
        tk.Button(btn_frame, text="📤 Весь PnP (TXT)", command=self.export_pnp_all_txt,
                  bg=t["accent"], fg=t["accent_text"], activebackground=t["accent_hover"],
                  font=("Segoe UI", 9, "bold"), relief="flat", padx=12, pady=6, cursor="hand2").pack(side="left", padx=3)

    # ---------- Вспомогательные методы ----------
    def _is_empty_ref(self, value):
        return is_empty_ref(value)

    def _is_coordinate_empty(self, value):
        return is_coordinate_empty(value)

    def find_duplicates(self, df, ref_col, sep):
        if df is None or ref_col not in df.columns:
            return {}
        sep_pattern = r'\s*' + re.escape(sep) + r'\s*'
        ref_list = []
        for idx, row in df.iterrows():
            if self._is_empty_ref(row[ref_col]):
                continue
            refs_str = str(row[ref_col]).strip()
            parts = re.split(sep_pattern, refs_str)
            for part in parts:
                part = part.strip()
                if part and not self._is_empty_ref(part):
                    ref_list.append((part, idx))
        grouped = defaultdict(list)
        for ref, idx in ref_list:
            grouped[ref].append(idx)
        return {ref: indices for ref, indices in grouped.items() if len(indices) > 1}

    def handle_duplicates(self, df, ref_col, sep, file_desc):
        duplicates = self.find_duplicates(df, ref_col, sep)
        if not duplicates:
            return df

        msg = f"В {file_desc} в столбце '{ref_col}' найдены дублирующиеся REF:\n\n"
        for ref, indices in duplicates.items():
            rows = ', '.join(str(i+1) for i in indices)
            msg += f"  {ref} → строки: {rows}\n"
        msg += "\nВыберите действие:"

        dialog = tk.Toplevel(self.parent)
        dialog.title("Обработка дубликатов")
        dialog.geometry("600x400")
        dialog.transient(self.parent)
        dialog.grab_set()

        text_frame = ttk.Frame(dialog)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        text_widget = tk.Text(text_frame, wrap=tk.WORD, height=15)
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        text_widget.insert(tk.END, msg)
        text_widget.config(state=tk.DISABLED)

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)

        result = {"action": None, "data": None}

        def on_ignore():
            new_df = df.copy()
            sep_pattern = r'\s*' + re.escape(sep) + r'\s*'
            for ref, indices in duplicates.items():
                rows_data = []
                for idx in indices:
                    if idx not in new_df.index:
                        continue
                    refs_str = str(new_df.at[idx, ref_col]) if pd.notna(new_df.at[idx, ref_col]) else ""
                    parts = re.split(sep_pattern, refs_str)
                    rows_data.append((idx, parts))
                for i, (idx, parts) in enumerate(rows_data):
                    if i == 0:
                        continue
                    new_parts = []
                    for p in parts:
                        p = p.strip()
                        if p == ref:
                            new_parts.append(f"{ref}_{i}")
                        else:
                            new_parts.append(p)
                    new_df.at[idx, ref_col] = sep.join(new_parts)
            result["action"] = "ignore"
            result["data"] = new_df
            dialog.destroy()

        def on_delete():
            delete_dialog = tk.Toplevel(dialog)
            delete_dialog.title("Выбор строки для сохранения REF")
            delete_dialog.geometry("700x500")
            delete_dialog.transient(dialog)
            delete_dialog.grab_set()

            ttk.Label(delete_dialog, text="Для каждого дублирующегося REF выберите строку, в которой этот REF должен остаться.\nВ остальных строках этот REF будет удалён (строка сохранится, если в ней есть другие REF).").pack(pady=10)

            main_frame = ttk.Frame(delete_dialog)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            canvas = tk.Canvas(main_frame)
            scrollbar2 = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
            scrollable_frame = ttk.Frame(canvas)

            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )

            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar2.set)

            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar2.pack(side=tk.RIGHT, fill=tk.Y)

            selected_indices = {}

            for ref, indices in duplicates.items():
                frame = ttk.LabelFrame(scrollable_frame, text=f"REF: {ref}", padding=5)
                frame.pack(fill=tk.X, padx=5, pady=5)

                var = tk.StringVar(value=str(indices[0]))
                selected_indices[ref] = var

                for idx in indices:
                    if idx not in df.index:
                        continue
                    row = df.loc[idx]
                    display_text = f"Строка {idx+1}: {ref}"
                    rb = ttk.Radiobutton(frame, text=display_text, variable=var, value=str(idx))
                    rb.pack(anchor=tk.W)

            def confirm_delete():
                try:
                    new_df = df.copy()
                    indices_to_drop = set()
                    sep_pattern = r'\s*' + re.escape(sep) + r'\s*'

                    for ref, var in selected_indices.items():
                        keep_idx = int(var.get())
                        idx_list = duplicates[ref]
                        for idx in idx_list:
                            if idx == keep_idx:
                                continue
                            if idx not in new_df.index:
                                continue
                            refs_str = str(new_df.at[idx, ref_col]) if pd.notna(new_df.at[idx, ref_col]) else ""
                            if refs_str:
                                parts = re.split(sep_pattern, refs_str)
                                new_parts = [p for p in parts if p.strip() != ref]
                                if new_parts:
                                    new_df.at[idx, ref_col] = sep.join(new_parts)
                                else:
                                    indices_to_drop.add(idx)
                            else:
                                indices_to_drop.add(idx)

                    if indices_to_drop:
                        new_df = new_df.drop(index=list(indices_to_drop)).reset_index(drop=True)

                    result["action"] = "delete"
                    result["data"] = new_df
                    delete_dialog.destroy()
                    dialog.destroy()
                except Exception as e:
                    err_msg = f"Ошибка при удалении дубликатов:\n{str(e)}\n\n{traceback.format_exc()}"
                    messagebox.showerror("Ошибка", err_msg, parent=self.parent)
                    delete_dialog.destroy()
                    dialog.destroy()
                    result["action"] = "cancel"

            ttk.Button(delete_dialog, text="Подтвердить", command=confirm_delete).pack(pady=10)
            ttk.Button(delete_dialog, text="Отмена", command=delete_dialog.destroy).pack(pady=5)

        def on_cancel():
            result["action"] = "cancel"
            dialog.destroy()

        ttk.Button(btn_frame, text="Игнорировать (переименовать дубликаты)", command=on_ignore).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить дубликаты", command=on_delete).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=on_cancel).pack(side=tk.LEFT, padx=5)

        self.parent.wait_window(dialog)

        if result["action"] == "cancel":
            return None
        elif result["action"] in ("ignore", "delete"):
            return result["data"]
        return df

    # ---------- Автоматическая обработка дубликатов при выборе REF ----------
    def on_pnp_ref_selected(self, event=None):
        if self.df_pnp is not None and self.pnp_ref_col.get().strip():
            new_df = self.handle_duplicates(self.df_pnp, self.pnp_ref_col.get().strip(), ",",
                                            f"PNP файле '{os.path.basename(self.pnp_path.get())}'")
            if new_df is not None:
                self.df_pnp = new_df
                self.main_app.set_pnp_data(new_df, self.pnp_path.get())
            self.update_preview('pnp', 'ref', self.pnp_ref_col.get())

    def on_bom_ref_selected(self, event=None):
        if self.df_bom is not None and self.bom_ref_col.get().strip():
            sep = self.bom_sep.get().strip() or ","
            new_df = self.handle_duplicates(self.df_bom, self.bom_ref_col.get().strip(), sep,
                                            f"BOM файле '{os.path.basename(self.bom_path.get())}'")
            if new_df is not None:
                self.df_bom = new_df
                self.main_app.set_bom_data(new_df, self.bom_path.get())
            self.update_preview('bom', 'ref', self.bom_ref_col.get())

    # ---------- Загрузка и предпросмотр ----------
    def load_file(self, file_type):
        file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")], parent=self.parent)
        if not file_path:
            return
        try:
            file_path = os.path.abspath(file_path)
            df = pd.read_excel(file_path, engine='openpyxl')
            if file_type == 'pnp':
                self.pnp_path.set(file_path)
                self.df_pnp = df
                cols = list(df.columns)
                self.pnp_ref_cb['values'] = cols
                self.pnp_val_cb['values'] = cols
                self.pnp_side_cb['values'] = cols
                self.pnp_x_cb['values'] = cols
                self.pnp_y_cb['values'] = cols
                self.pnp_r_cb['values'] = cols
                # Применяем автовыбор (точные совпадения)
                self.apply_auto_columns()
                messagebox.showinfo("Загрузка", f"PNP загружен: {len(df)} строк, {len(cols)} колонок.", parent=self.parent)
                self.main_app.set_pnp_data(df, file_path)
                if self.pnp_ref_col.get():
                    self.update_preview('pnp','ref',self.pnp_ref_col.get())
            else:
                self.bom_path.set(file_path)
                self.df_bom = df
                cols = list(df.columns)
                self.bom_ref_cb['values'] = cols
                self.bom_val_cb['values'] = cols
                # Применяем сохранённые BOM колонки из объединителя
                self.apply_bom_columns()
                # Если не применились, пробуем автовыбор по точному совпадению или частичному
                if not self.bom_ref_col.get():
                    # Ищем точное совпадение 'REF' или 'Parts_Name'
                    for col in cols:
                        if col == 'REF':
                            self.bom_ref_cb.set(col)
                            break
                    if not self.bom_ref_col.get():
                        for col in cols:
                            col_low = col.lower()
                            if 'reference' in col_low or 'ref' in col_low:
                                self.bom_ref_cb.set(col)
                                break
                if not self.bom_val_col.get():
                    for col in cols:
                        if col == 'Parts_Name':
                            self.bom_val_cb.set(col)
                            break
                    if not self.bom_val_col.get():
                        for col in cols:
                            col_low = col.lower()
                            if 'pn' in col_low or 'manufacturer' in col_low or 'description' in col_low:
                                self.bom_val_cb.set(col)
                                break
                messagebox.showinfo("Загрузка", f"BOM загружен: {len(df)} строк, {len(cols)} колонок.", parent=self.parent)
                self.main_app.set_bom_data(df, file_path)
                if self.bom_ref_col.get():
                    self.update_preview('bom','ref',self.bom_ref_col.get())
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{str(e)}", parent=self.parent)

    def update_preview(self, file_type, col_type, column_name):
        if not column_name:
            self.preview_label.config(text="Колонка не выбрана")
            return
        df = self.df_pnp if file_type == 'pnp' else self.df_bom
        if df is None or column_name not in df.columns:
            self.preview_label.config(text=f"Колонка '{column_name}' не найдена")
            return

        display_names = {
            ('pnp','ref'): 'PNP REF',
            ('pnp','val'): 'PNP VAL',
            ('pnp','side'): 'PNP SIDE',
            ('pnp','x'): 'PNP X',
            ('pnp','y'): 'PNP Y',
            ('pnp','r'): 'PNP R',
            ('bom','ref'): 'BOM REF',
            ('bom','val'): 'BOM VAL'
        }
        display_name = display_names.get((file_type, col_type), column_name)
        values = df[column_name].fillna('').astype(str).head(20).tolist()
        total_count = len(df[column_name].dropna())
        if values:
            preview_text = f"{display_name} → {column_name}: " + ", ".join(values)
            if total_count > 20:
                preview_text += f" ... и ещё {total_count - 20} значений"
        else:
            preview_text = f"{display_name} → {column_name}: (пусто)"
        self.preview_label.config(text=preview_text)

    def apply_auto_columns(self):
        """Применяет автовыбор колонок PNP по точному совпадению названий."""
        if self.df_pnp is None:
            return
        cols = list(self.df_pnp.columns)
        for col in cols:
            if col == 'REF':
                self.pnp_ref_cb.set(col)
            elif col == 'Parts_Name':
                self.pnp_val_cb.set(col)
            elif col == 'Side':
                self.pnp_side_cb.set(col)
            elif col == 'X':
                self.pnp_x_cb.set(col)
            elif col == 'Y':
                self.pnp_y_cb.set(col)
            elif col == 'R':
                self.pnp_r_cb.set(col)
        if self.pnp_ref_col.get():
            self.update_preview('pnp', 'ref', self.pnp_ref_col.get())

    def apply_bom_columns(self):
        """Применяет сохранённые BOM колонки из MainApp к текущему df_bom."""
        if self.df_bom is None:
            return
        ref_col, val_col, sep = self.main_app.get_bom_columns()
        cols = list(self.df_bom.columns)
        if ref_col and ref_col in cols:
            self.bom_ref_cb.set(ref_col)
        if val_col and val_col in cols:
            self.bom_val_cb.set(val_col)
        if sep:
            self.bom_sep.set(sep)
        # Обновляем предпросмотр
        if self.bom_ref_col.get():
            self.update_preview('bom', 'ref', self.bom_ref_col.get())
        if self.bom_val_col.get():
            self.update_preview('bom', 'val', self.bom_val_col.get())

    # ---------- Основная проверка ----------
    def run_check(self):
        if self.df_pnp is None or self.df_bom is None:
            messagebox.showerror("Ошибка", "Загрузите оба файла!", parent=self.parent)
            return

        pnp_ref = self.pnp_ref_col.get().strip()
        pnp_val = self.pnp_val_col.get().strip()
        pnp_x = self.pnp_x_col.get().strip()
        pnp_y = self.pnp_y_col.get().strip()
        pnp_r = self.pnp_r_col.get().strip()

        bom_ref = self.bom_ref_col.get().strip()
        bom_val = self.bom_val_col.get().strip()

        if not all([pnp_ref, pnp_val, pnp_x, pnp_y, pnp_r, bom_ref, bom_val]):
            messagebox.showerror("Ошибка", "Выберите все необходимые колонки (REF, Value, X, Y, R для PNP и REF, Value для BOM)!", parent=self.parent)
            return

        # Обработка дубликатов в PNP и BOM
        new_pnp = self.handle_duplicates(self.df_pnp, pnp_ref, ",", f"PNP файле '{os.path.basename(self.pnp_path.get())}'")
        if new_pnp is None:
            return
        self.df_pnp = new_pnp
        self.main_app.set_pnp_data(new_pnp, self.pnp_path.get())

        sep = self.bom_sep.get().strip() or ","
        new_bom = self.handle_duplicates(self.df_bom, bom_ref, sep, f"BOM файле '{os.path.basename(self.bom_path.get())}'")
        if new_bom is None:
            return
        self.df_bom = new_bom
        self.main_app.set_bom_data(new_bom, self.bom_path.get())

        try:
            pnp_dict = {}
            pnp_only_refs = set()

            for _, row in self.df_pnp.iterrows():
                if self._is_empty_ref(row[pnp_ref]):
                    continue
                ref = str(row[pnp_ref]).strip()

                x_empty = self._is_coordinate_empty(row[pnp_x])
                y_empty = self._is_coordinate_empty(row[pnp_y])
                r_empty = self._is_coordinate_empty(row[pnp_r])
                if x_empty or y_empty or r_empty:
                    continue

                val = str(row[pnp_val]) if pd.notna(row[pnp_val]) else ""

                if not self._is_empty_ref(val):
                    pnp_dict[ref] = val
                else:
                    pnp_only_refs.add(ref)

            bom_dict = {}
            sep_pattern = r'\s*' + re.escape(sep) + r'\s*'
            for _, row in self.df_bom.iterrows():
                if self._is_empty_ref(row[bom_ref]):
                    continue
                refs_str = str(row[bom_ref]).strip()
                val = str(row[bom_val]) if pd.notna(row[bom_val]) else ""
                for r in re.split(sep_pattern, refs_str):
                    r = r.strip()
                    if r and not self._is_empty_ref(r):
                        bom_dict[r] = val

            all_refs = set(pnp_dict.keys()) | set(bom_dict.keys()) | pnp_only_refs
            self.all_results = []

            for ref in sorted(all_refs):
                if ref in pnp_only_refs:
                    status = "Только в PNP"
                    pv = ""
                    bv = ""
                elif ref in pnp_dict and ref in bom_dict:
                    pv = pnp_dict[ref]
                    bv = bom_dict[ref]
                    if pv != bv:
                        status = "Несовпадение значений"
                    else:
                        status = "OK"
                elif ref in pnp_dict:
                    status = "Только в PNP"
                    pv = pnp_dict[ref]
                    bv = ""
                else:
                    status = "Только в BOM"
                    pv = ""
                    bv = bom_dict[ref]

                self.all_results.append((ref, status, pv, bv))

            self.apply_filter()

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось выполнить проверку:\n{str(e)}", parent=self.parent)

    # ---------- Фильтрация, таблица, статистика ----------
    def apply_filter(self):
        search_text = self.search_var.get().strip().lower()
        status_filter = self.status_filter_var.get()
        self.filtered_results = []
        for row in self.all_results:
            ref, status, pv, bv = row
            if status_filter != "Все" and status != status_filter: continue
            if search_text and search_text not in f"{ref} {pv} {bv}".lower(): continue
            self.filtered_results.append(row)
        self.update_table(self.filtered_results)
        self.update_stats()

    def reset_filter(self):
        self.search_var.set("")
        self.status_filter_var.set("Все")
        self.apply_filter()

    def update_table(self, results):
        for item in self.tree.get_children():
            self.tree.delete(item)
        if hasattr(self, 'tree_placeholder'):
            if results:
                self.tree_placeholder.place_forget()
            else:
                self.tree_placeholder.place(relx=0.5, rely=0.4, anchor="center")
        for idx, row in enumerate(results):
            tag = "evenrow" if idx % 2 == 0 else "oddrow"
            self.tree.insert("", "end", values=row, tags=(tag,))

    def update_stats(self):
        total = len(self.filtered_results)
        only_pnp = sum(1 for r in self.filtered_results if r[1] == "Только в PNP")
        only_bom = sum(1 for r in self.filtered_results if r[1] == "Только в BOM")
        mismatch = sum(1 for r in self.filtered_results if r[1] == "Несовпадение значений")
        ok = sum(1 for r in self.filtered_results if r[1] == "OK")
        t = THEMES["dark"]
        self.stats_label.config(
            text=f"Отфильтровано: {total}  |  OK: {ok}  |  Только в PNP: {only_pnp}  |  Только в BOM: {only_bom}  |  Несовпадений: {mismatch}",
            fg=t["accent"] if total > 0 else t["text_secondary"]
        )

    def sort_treeview(self, col, reverse):
        data = [(self.tree.set(child, col), child) for child in self.tree.get_children('')]
        try:
            data.sort(key=lambda x: float(x[0]), reverse=reverse)
        except ValueError:
            data.sort(key=lambda x: x[0].lower(), reverse=reverse)
        for index, (_, child) in enumerate(data):
            self.tree.move(child, '', index)
        self.tree.heading(col, command=lambda: self.sort_treeview(col, not reverse))

    # ---------- Диалоги для экспорта ----------
    def get_separator_dialog(self):
        t = THEMES["dark"]
        dialog = create_styled_toplevel(self.parent, "Выбор разделителя", "460x260", min_size=(420, 240))
        dialog.transient(self.parent)
        dialog.grab_set()

        content = tk.Frame(dialog, bg=t["bg_app"], padx=20, pady=16)
        content.pack(fill=tk.BOTH, expand=True)

        tk.Label(content, text="Выберите разделитель для формирования .TXT:",
                 font=("Segoe UI", 10, "bold"), bg=t["bg_app"], fg=t["text_header"]).pack(anchor="w", pady=(0, 8))

        card = tk.Frame(content, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=16, pady=12)
        card.pack(fill=tk.X, pady=(0, 12))

        sep_map = {
            "Табуляция (\\t)": "\t",
            "Пробел (␣)": " ",
            "Точка с запятой (;)": ";",
            "Запятая (,)": ",",
            "Вертикальная черта (|)": "|",
        }
        display_options = list(sep_map.keys()) + ["Свой символ..."]

        combo_var = tk.StringVar(value="Табуляция (\\t)")
        custom_var = tk.StringVar(value="")

        tk.Label(card, text="Стандартный разделитель:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).pack(anchor="w", pady=(0, 4))
        combo = ttk.Combobox(card, textvariable=combo_var, values=display_options, state="readonly", width=28, font=("Segoe UI", 9))
        combo.pack(fill=tk.X, pady=(0, 8))

        custom_box = tk.Frame(card, bg=t["bg_card"])
        custom_box.pack(fill=tk.X)

        tk.Label(custom_box, text="Свой разделитель:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_secondary"]).pack(side=tk.LEFT)
        custom_entry = ttk.Entry(custom_box, textvariable=custom_var, width=8, justify="center", state="disabled")
        custom_entry.pack(side=tk.LEFT, padx=8)

        hint_lbl = tk.Label(custom_box, text="(\\t - табуляция, \\s - пробел)", font=("Segoe UI", 8), bg=t["bg_card"], fg=t["text_muted"])
        hint_lbl.pack(side=tk.LEFT)

        def on_combo_change(event=None):
            if combo_var.get() == "Свой символ...":
                custom_entry.configure(state="normal")
                custom_entry.focus()
            else:
                custom_entry.configure(state="disabled")

        combo.bind("<<ComboboxSelected>>", on_combo_change)

        result = {"sep": None}

        def on_ok():
            choice = combo_var.get()
            if choice == "Свой символ...":
                c = custom_var.get()
                if c == r"\t":
                    result["sep"] = "\t"
                elif c in (r"\s", r"\p", "␣"):
                    result["sep"] = " "
                elif c:
                    result["sep"] = c
                else:
                    result["sep"] = "\t"
            else:
                result["sep"] = sep_map.get(choice, "\t")
            dialog.destroy()

        def on_cancel():
            result["sep"] = None
            dialog.destroy()

        dialog.bind("<Return>", lambda e: on_ok())
        dialog.bind("<Escape>", lambda e: on_cancel())

        btn_frame = tk.Frame(content, bg=t["bg_app"])
        btn_frame.pack(fill=tk.X)

        btn_ok = tk.Button(btn_frame, text="OK", command=on_ok,
                           bg=t["accent"], fg=t["accent_text"], activebackground=t["accent_hover"],
                           font=("Segoe UI", 9, "bold"), relief="flat", padx=20, pady=5, cursor="hand2")
        btn_ok.pack(side=tk.LEFT, padx=(0, 8))

        btn_cancel = tk.Button(btn_frame, text="Отмена", command=on_cancel,
                               bg=t["btn_sec_bg"], fg=t["btn_sec_fg"], activebackground=t["btn_sec_hover"],
                               font=("Segoe UI", 9), relief="flat", padx=16, pady=5, cursor="hand2")
        btn_cancel.pack(side=tk.LEFT)

        style_widget_tree(dialog, "dark")
        self.parent.wait_window(dialog)
        return result["sep"]

    def get_replacement_name_dialog(self):
        t = THEMES["dark"]
        dialog = create_styled_toplevel(self.parent, "Замена пустых названий", "460x220", min_size=(400, 200))
        dialog.transient(self.parent)
        dialog.grab_set()

        content = tk.Frame(dialog, bg=t["bg_app"], padx=20, pady=16)
        content.pack(fill=tk.BOTH, expand=True)

        tk.Label(content, text="Введите имя для пустых названий компонентов:",
                 font=("Segoe UI", 10, "bold"), bg=t["bg_app"], fg=t["text_header"]).pack(anchor="w", pady=(0, 8))

        card = tk.Frame(content, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=16, pady=12)
        card.pack(fill=tk.X, pady=(0, 12))

        name_var = tk.StringVar(value="UNKNOWN_PART")
        entry = ttk.Entry(card, textvariable=name_var, width=32, font=("Segoe UI", 9))
        entry.pack(fill=tk.X)
        entry.focus()

        result = {"name": None}

        def on_ok():
            val = name_var.get().strip()
            if val:
                result["name"] = val
            dialog.destroy()

        def on_cancel():
            result["name"] = None
            dialog.destroy()

        dialog.bind("<Return>", lambda e: on_ok())
        dialog.bind("<Escape>", lambda e: on_cancel())

        btn_frame = tk.Frame(content, bg=t["bg_app"])
        btn_frame.pack(fill=tk.X)

        btn_ok = tk.Button(btn_frame, text="OK", command=on_ok,
                           bg=t["accent"], fg=t["accent_text"], activebackground=t["accent_hover"],
                           font=("Segoe UI", 9, "bold"), relief="flat", padx=20, pady=5, cursor="hand2")
        btn_ok.pack(side=tk.LEFT, padx=(0, 8))

        btn_cancel = tk.Button(btn_frame, text="Отмена", command=on_cancel,
                               bg=t["btn_sec_bg"], fg=t["btn_sec_fg"], activebackground=t["btn_sec_hover"],
                               font=("Segoe UI", 9), relief="flat", padx=16, pady=5, cursor="hand2")
        btn_cancel.pack(side=tk.LEFT)

        style_widget_tree(dialog, "dark")
        self.parent.wait_window(dialog)
        return result["name"]

    # ---------- Экспорт PnP ----------
    def _prepare_pnp_data(self, only_ok=False, replacement=None):
        if self.df_pnp is None:
            messagebox.showerror("Ошибка", "Сначала загрузите PNP-файл!", parent=self.parent)
            return None

        if only_ok:
            if not self.all_results:
                messagebox.showwarning("Предупреждение", "Сначала выполните проверку!", parent=self.parent)
                return None
            ok_refs = [ref for ref, status, _, _ in self.all_results if status == "OK"]
            if not ok_refs:
                messagebox.showinfo("Информация", "Нет ни одной позиции со статусом OK. Экспорт невозможен.", parent=self.parent)
                return None
            ref_column = self.pnp_ref_col.get().strip()
            if ref_column not in self.df_pnp.columns:
                messagebox.showerror("Ошибка", f"Столбец '{ref_column}' не найден в PNP-файле!", parent=self.parent)
                return None
            mask = self.df_pnp[ref_column].astype(str).str.strip().isin(ok_refs)
            df_export = self.df_pnp.loc[mask].copy()
        else:
            df_export = self.df_pnp.copy()

        val_col = self.pnp_val_col.get().strip()
        if val_col and val_col in df_export.columns:
            if replacement is not None:
                df_export[val_col] = df_export[val_col].fillna(replacement)
                df_export[val_col] = df_export[val_col].apply(lambda x: replacement if (pd.isna(x) or str(x).strip() == '') else x)
            else:
                df_export[val_col] = df_export[val_col].fillna('')
                df_export[val_col] = df_export[val_col].apply(lambda x: '' if (pd.isna(x) or str(x).strip() == '') else x)

        for col in df_export.columns:
            if col != val_col:
                df_export[col] = df_export[col].fillna('')
                df_export[col] = df_export[col].astype(str).replace('nan', '').replace('None', '')

        return df_export

    def export_pnp_ok_excel(self):
        df = self._prepare_pnp_data(only_ok=True, replacement=None)
        if df is None or len(df) == 0:
            return
        out = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")],
                                           initialfile="PNP_only_OK.xlsx", parent=self.parent)
        if out:
            try:
                df.to_excel(out, index=False)
                messagebox.showinfo("Успех", f"PNP только OK сохранён:\n{out}\nВсего строк: {len(df)}", parent=self.parent)
            except Exception as e:
                messagebox.showerror("Ошибка", str(e), parent=self.parent)

    def export_pnp_ok_txt(self):
        sep = self.get_separator_dialog()
        if sep is None:
            return
        df = self._prepare_pnp_data(only_ok=True, replacement=None)
        if df is None or len(df) == 0:
            return
        out = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")],
                                           initialfile="PNP_only_OK.txt", parent=self.parent)
        if out:
            try:
                df.to_csv(out, sep=sep, index=False, encoding='utf-8')
                messagebox.showinfo("Успех", f"PNP только OK (TXT) сохранён:\n{out}\nВсего строк: {len(df)}", parent=self.parent)
            except Exception as e:
                messagebox.showerror("Ошибка", str(e), parent=self.parent)

    def export_pnp_all_excel(self):
        replacement = self.get_replacement_name_dialog()
        if replacement is None:
            return
        df = self._prepare_pnp_data(only_ok=False, replacement=replacement)
        if df is None:
            return
        out = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")],
                                           initialfile="PNP_all.xlsx", parent=self.parent)
        if out:
            try:
                df.to_excel(out, index=False)
                messagebox.showinfo("Успех", f"Весь PnP сохранён:\n{out}\nВсего строк: {len(df)}", parent=self.parent)
            except Exception as e:
                messagebox.showerror("Ошибка", str(e), parent=self.parent)

    def export_pnp_all_txt(self):
        sep = self.get_separator_dialog()
        if sep is None:
            return
        replacement = self.get_replacement_name_dialog()
        if replacement is None:
            return
        df = self._prepare_pnp_data(only_ok=False, replacement=replacement)
        if df is None:
            return
        out = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")],
                                           initialfile="PNP_all.txt", parent=self.parent)
        if out:
            try:
                df.to_csv(out, sep=sep, index=False, encoding='utf-8')
                messagebox.showinfo("Успех", f"Весь PnP (TXT) сохранён:\n{out}\nВсего строк: {len(df)}", parent=self.parent)
            except Exception as e:
                messagebox.showerror("Ошибка", str(e), parent=self.parent)

    # ---------- Экспорт отчёта ----------
    def export_report(self):
        if not self.filtered_results:
            messagebox.showwarning("Предупреждение", "Нет данных для экспорта. Выполните проверку.", parent=self.parent)
            return
        side_col = self.pnp_side_col.get().strip()
        side_dict = {}
        if side_col and side_col in self.df_pnp.columns:
            for _, row in self.df_pnp.iterrows():
                ref = str(row[self.pnp_ref_col.get()]).strip()
                if ref:
                    side_dict[ref] = str(row[side_col]) if pd.notna(row[side_col]) else ""

        export_data = []
        for ref, status, pv, bv in self.filtered_results:
            side = side_dict.get(ref, "") if side_col else ""
            export_data.append((ref, status, pv, bv, side))

        cols = ["RefDes","Статус","Значение в PNP","Значение в BOM"]
        if side_col: cols.append("Сторона")
        out = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")], parent=self.parent)
        if out:
            try:
                pd.DataFrame(export_data, columns=cols).to_excel(out, index=False)
                messagebox.showinfo("Успех", f"Отчёт сохранён: {out}", parent=self.parent)
            except Exception as e:
                messagebox.showerror("Ошибка", str(e), parent=self.parent)

    # ---------- Методы для обновления данных из MainApp ----------
    def update_pnp_data(self, df, path):
        self.df_pnp = df
        self.pnp_path.set(path)
        cols = list(df.columns) if df is not None else []
        self.pnp_ref_cb['values'] = cols
        self.pnp_val_cb['values'] = cols
        self.pnp_side_cb['values'] = cols
        self.pnp_x_cb['values'] = cols
        self.pnp_y_cb['values'] = cols
        self.pnp_r_cb['values'] = cols
        if df is not None:
            self.apply_auto_columns()
        self.update_preview('pnp', 'ref', self.pnp_ref_col.get())
        self.update_preview('pnp', 'val', self.pnp_val_col.get())
        self.update_preview('pnp', 'side', self.pnp_side_col.get())
        self.update_preview('pnp', 'x', self.pnp_x_col.get())
        self.update_preview('pnp', 'y', self.pnp_y_col.get())
        self.update_preview('pnp', 'r', self.pnp_r_col.get())

    def update_bom_data(self, df, path):
        self.df_bom = df
        self.bom_path.set(path)
        cols = list(df.columns) if df is not None else []
        self.bom_ref_cb['values'] = cols
        self.bom_val_cb['values'] = cols
        if df is not None:
            self.apply_bom_columns()
        self.update_preview('bom', 'ref', self.bom_ref_col.get())
        self.update_preview('bom', 'val', self.bom_val_col.get())

    def show_preview(self, df, file_type):
        """Показывает предпросмотр загруженного DataFrame в отдельном окне."""
        if df is None or df.empty:
            messagebox.showinfo("Информация", f"Файл {file_type} не загружен или пуст.", parent=self.parent)
            return

        preview_window = create_styled_toplevel(self.parent, f"Предпросмотр {file_type}", "1250x750", min_size=(980, 580))

        frame = ttk.Frame(preview_window, padding="5")
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        cols = list(df.columns)
        tree = ttk.Treeview(frame, columns=cols, show="headings")
        tree.tag_configure('odd', background="#0e182e")
        tree.tag_configure('even', background="#131e36")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview, style="Horizontal.TScrollbar")
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=110, minwidth=80, anchor=tk.W)

        for idx, (_, row) in enumerate(df.head(100).iterrows()):
            values = [str(v) if pd.notna(v) else "" for v in row]
            tag = 'even' if idx % 2 == 0 else 'odd'
            tree.insert("", tk.END, values=values, tags=(tag,))

        btn_bar = ttk.Frame(preview_window, padding="5")
        btn_bar.pack(fill=tk.X, pady=5)
        ttk.Label(btn_bar, text=f"Показано {min(len(df), 100)} из {len(df)} строк, {len(cols)} колонок.",
                  foreground="gray").pack(side=tk.TOP, pady=2)
        ttk.Button(btn_bar, text="Закрыть", command=preview_window.destroy).pack(side=tk.BOTTOM, pady=4)

        style_widget_tree(preview_window, "dark")


# ==================== ВКЛАДКА "ОБЪЕДИНЕНИЕ P&P И BOM" ====================
class MergeTab(ttk.Frame):
    def __init__(self, parent, main_app):
        self.parent = parent
        self.main_app = main_app
        super().__init__(parent)

        # --- Прокручиваемая область ---
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Переменные ---
        self.pnp_file = tk.StringVar()
        self.bom_file = tk.StringVar()
        self.pnp_sep = tk.StringVar(value=" ")
        self.pnp_sep_mode = tk.StringVar(value=" ")
        self.pnp_custom_sep = tk.StringVar(value="")
        self.pnp_header = tk.BooleanVar(value=True)
        self.convert_mil = tk.BooleanVar(value=False)
        self.bom_sep = tk.StringVar(value=",")
        self.one_side = tk.BooleanVar(value=False)

        self.pnp_df = None
        self.bom_df = None
        self.pnp_columns = []
        self.bom_columns = []

        self.result_df = None
        self.changed_col = None

        self.create_widgets()
        self.on_sep_changed()
        self.on_one_side_changed()

    def create_widgets(self):
        t = THEMES["dark"]
        main_frame = tk.Frame(self.scrollable_frame, bg=t["bg_app"], padx=8, pady=6)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # =====================================================================
        # 1. КАРТОЧКА: Загрузка файлов (P&P и BOM)
        # =====================================================================
        files_card = tk.Frame(main_frame, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=14, pady=12)
        files_card.pack(fill=tk.X, pady=(0, 8))
        files_card.columnconfigure(1, weight=1)

        tk.Label(files_card, text="📁 Исходные файлы (P&P координаты и BOM спецификация)",
                 font=("Segoe UI", 10, "bold"), bg=t["bg_card"], fg=t["accent"]).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

        # Строка P&P
        tk.Label(files_card, text="Файл P&P:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=1, column=0, sticky="w", pady=4)
        pnp_entry = ttk.Entry(files_card, textvariable=self.pnp_file)
        pnp_entry.grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        pnp_entry.bind("<Return>", lambda e: self.load_pnp())
        btn_pnp_browse = ttk.Button(files_card, text="Обзор...", command=self.browse_pnp)
        btn_pnp_browse.grid(row=1, column=2, padx=2, pady=4)
        btn_pnp_view = ttk.Button(files_card, text="👁️", width=3, command=lambda: self.show_preview(self.pnp_df, "P&P"))
        btn_pnp_view.grid(row=1, column=3, padx=2, pady=4)
        ToolTip(btn_pnp_view, "Предпросмотр файла P&P")

        # Разделители P&P
        sep_box = tk.Frame(files_card, bg=t["bg_card"])
        sep_box.grid(row=2, column=1, sticky="w", padx=6, pady=(0, 6), columnspan=3)
        tk.Label(sep_box, text="Разделитель:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_secondary"]).pack(side=tk.LEFT, padx=(0, 4))
        for sep in [" ", "\t", ",", ";"]:
            ttk.Radiobutton(sep_box, text=repr(sep), variable=self.pnp_sep_mode,
                            value=sep, command=self.on_sep_changed).pack(side=tk.LEFT, padx=3)
        ttk.Radiobutton(sep_box, text="Свой", variable=self.pnp_sep_mode,
                        value="custom", command=self.on_sep_changed).pack(side=tk.LEFT, padx=3)
        self.pnp_custom_entry = ttk.Entry(sep_box, textvariable=self.pnp_custom_sep, width=5, state='disabled')
        self.pnp_custom_entry.pack(side=tk.LEFT, padx=3)
        self.pnp_custom_sep.trace_add('write', self.on_custom_sep_changed)
        ttk.Checkbutton(sep_box, text="Есть заголовок", variable=self.pnp_header,
                        command=lambda: self.load_pnp() if self.pnp_file.get() and os.path.exists(self.pnp_file.get()) else None).pack(side=tk.LEFT, padx=(12, 0))

        # Строка BOM
        tk.Label(files_card, text="Файл BOM:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=3, column=0, sticky="w", pady=4)
        bom_entry = ttk.Entry(files_card, textvariable=self.bom_file)
        bom_entry.grid(row=3, column=1, sticky="ew", padx=6, pady=4)
        bom_entry.bind("<Return>", lambda e: self.load_bom())
        btn_bom_browse = ttk.Button(files_card, text="Обзор...", command=self.browse_bom)
        btn_bom_browse.grid(row=3, column=2, padx=2, pady=4)
        btn_bom_view = ttk.Button(files_card, text="👁️", width=3, command=lambda: self.show_preview(self.bom_df, "BOM"))
        btn_bom_view.grid(row=3, column=3, padx=2, pady=4)
        ToolTip(btn_bom_view, "Предпросмотр файла BOM")

        # =====================================================================
        # 2. КАРТОЧКА: Настройка соответствия столбцов (2 колонки: P&P и BOM)
        # =====================================================================
        cols_container = tk.Frame(main_frame, bg=t["bg_app"])
        cols_container.pack(fill=tk.X, pady=(0, 8))
        cols_container.columnconfigure(0, weight=1)
        cols_container.columnconfigure(1, weight=1)
        cols_container.rowconfigure(0, weight=1)

        # Левая колонка: Параметры P&P
        pnp_card = tk.Frame(cols_container, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=14, pady=12)
        pnp_card.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        pnp_card.columnconfigure(1, weight=1)

        tk.Label(pnp_card, text="⚙️ Столбцы и координаты P&P", font=("Segoe UI", 10, "bold"),
                 bg=t["bg_card"], fg=t["accent"]).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        pnp_fields = [
            ("P&P столбец REF:", self.on_setting_changed, 'REF'),
            ("P&P столбец X:", self.on_setting_changed, 'X'),
            ("P&P столбец Y:", self.on_setting_changed, 'Y'),
            ("P&P столбец Угол (R):", self.on_setting_changed, 'R'),
            ("P&P столбец Зеркало / Сторона:", self.on_mirror_column_selected, None)
        ]

        self.pnp_cbs = {}
        for idx, (label_text, handler, arg) in enumerate(pnp_fields, start=1):
            tk.Label(pnp_card, text=label_text, font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=idx, column=0, sticky="w", pady=3)
            cb = ttk.Combobox(pnp_card, state="readonly", width=22)
            cb.grid(row=idx, column=1, sticky="ew", padx=6, pady=3)
            if arg:
                cb.bind("<<ComboboxSelected>>", lambda e, a=arg: handler(a))
            else:
                cb.bind("<<ComboboxSelected>>", handler)
            self.pnp_cbs[idx - 1] = cb

        self.pnp_ref_cb = self.pnp_cbs[0]
        self.pnp_x_cb = self.pnp_cbs[1]
        self.pnp_y_cb = self.pnp_cbs[2]
        self.pnp_rotate_cb = self.pnp_cbs[3]
        self.pnp_mirror_cb = self.pnp_cbs[4]

        # Стороны TOP/BOTTOM
        tk.Label(pnp_card, text="Значение для TOP:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=6, column=0, sticky="w", pady=3)
        self.top_cb = ttk.Combobox(pnp_card, state="readonly", width=22)
        self.top_cb.grid(row=6, column=1, sticky="ew", padx=6, pady=3)
        self.top_cb.bind("<<ComboboxSelected>>", lambda e: self.on_setting_changed('TOP'))

        tk.Label(pnp_card, text="Значение для BOTTOM:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=7, column=0, sticky="w", pady=3)
        self.bottom_cb = ttk.Combobox(pnp_card, state="readonly", width=22)
        self.bottom_cb.grid(row=7, column=1, sticky="ew", padx=6, pady=3)
        self.bottom_cb.bind("<<ComboboxSelected>>", lambda e: self.on_setting_changed('BOTTOM'))

        pnp_opts = tk.Frame(pnp_card, bg=t["bg_card"])
        pnp_opts.grid(row=8, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Checkbutton(pnp_opts, text="Одна сторона (игнорировать сторону)", variable=self.one_side,
                        command=self.on_one_side_changed).pack(anchor="w", pady=2)
        ttk.Checkbutton(pnp_opts, text="Конвертировать координаты из mil в мм", variable=self.convert_mil,
                        command=lambda: self.on_setting_changed('convert_mil')).pack(anchor="w", pady=2)

        # Правая колонка: Параметры BOM
        bom_card = tk.Frame(cols_container, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=14, pady=12)
        bom_card.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        bom_card.columnconfigure(1, weight=1)

        tk.Label(bom_card, text="🗂️ Столбцы спецификации BOM", font=("Segoe UI", 10, "bold"),
                 bg=t["bg_card"], fg=t["accent"]).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        tk.Label(bom_card, text="BOM столбец с RefDes:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=1, column=0, sticky="w", pady=4)
        self.bom_ref_cb = ttk.Combobox(bom_card, state="readonly", width=22)
        self.bom_ref_cb.grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        self.bom_ref_cb.bind("<<ComboboxSelected>>", lambda e: self.on_setting_changed('bom_ref'))

        # Разделитель RefDes размещён прямо под столбцом RefDes
        sep_ref_frame = tk.Frame(bom_card, bg=t["bg_card"])
        sep_ref_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=3)
        tk.Label(sep_ref_frame, text="Разделитель RefDes в ячейке BOM:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).pack(side=tk.LEFT)
        bom_sep_entry = ttk.Entry(sep_ref_frame, textvariable=self.bom_sep, width=6)
        bom_sep_entry.pack(side=tk.LEFT, padx=6)
        self.bom_sep.trace_add('write', lambda *args: self.save_bom_settings())
        ToolTip(bom_sep_entry, "Символ-разделитель позиционных обозначений в BOM (обычно запятая или пробел)")

        tk.Label(bom_card, text="BOM столбец данных (Унифицированное):", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=3, column=0, sticky="w", pady=(10, 4))
        self.bom_data_cb = ttk.Combobox(bom_card, state="readonly", width=22)
        self.bom_data_cb.grid(row=3, column=1, sticky="ew", padx=6, pady=(10, 4))
        self.bom_data_cb.bind("<<ComboboxSelected>>", lambda e: self.on_setting_changed('bom_data'))
        self.bom_data_cb.bind("<<ComboboxSelected>>", lambda e: self.save_bom_settings())

        # Информационная плашка с подсказкой
        info_box = tk.Frame(bom_card, bg=t["bg_card_inner"], highlightbackground=t["border"], highlightthickness=1, padx=12, pady=10)
        info_box.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(14, 0))

        tk.Label(info_box, text="💡 Совет по выбору столбца", font=("Segoe UI", 9, "bold"),
                 bg=t["bg_card_inner"], fg=t["warning_fg"]).pack(anchor="w")
        tk.Label(info_box, text="Выберите столбец 'Унифицированное наименование',\nсформированный на Шаге 1 для объединения с координатами P&P.",
                 font=("Segoe UI", 8), bg=t["bg_card_inner"], fg=t["text_secondary"], justify="left").pack(anchor="w", pady=(3, 0))

        # =====================================================================
        # 3. КАРТОЧКА: Предпросмотр результата
        # =====================================================================
        preview_card = tk.Frame(main_frame, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=14, pady=12)
        preview_card.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        tk.Label(preview_card, text="📊 Предпросмотр объединенных данных", font=("Segoe UI", 10, "bold"),
                 bg=t["bg_card"], fg=t["text_header"]).pack(anchor="w", pady=(0, 6))

        tree_frame = tk.Frame(preview_card, bg=t["bg_card"])
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.result_tree = ttk.Treeview(tree_frame, columns=(), show="headings", height=10)
        self.result_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Теги для чередования строк (zebra stripes)
        self.result_tree.tag_configure("evenrow", background=t["row_even"])
        self.result_tree.tag_configure("oddrow", background=t["row_odd"])

        scroll_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.result_tree.yview)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.result_tree.configure(yscrollcommand=scroll_y.set)

        self.result_placeholder = tk.Label(self.result_tree,
            text="📊 Здесь появится предпросмотр объединенных данных.\nЗагрузите P&P и BOM, укажите столбцы и нажмите «Обновить предпросмотр».",
            font=("Segoe UI", 10), bg=t["tree_bg"], fg=t["text_muted"])
        self.result_placeholder.place(relx=0.5, rely=0.45, anchor="center")

        # Панель кнопок действий
        btn_frame = tk.Frame(preview_card, bg=t["bg_card"])
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        tk.Button(btn_frame, text="👁️ Обновить предпросмотр", command=lambda: self.on_setting_changed('manual'),
                  bg=t["btn_sec_bg"], fg=t["btn_sec_fg"], activebackground=t["btn_sec_hover"],
                  font=("Segoe UI", 9), relief="flat", padx=12, pady=6, cursor="hand2").pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(btn_frame, text="💾 Объединить и сохранить", command=self.run_merge,
                  bg=t["accent"], fg=t["accent_text"], activebackground=t["accent_hover"],
                  font=("Segoe UI", 10, "bold"), relief="flat", padx=16, pady=6, cursor="hand2").pack(side=tk.LEFT, padx=6)

        tk.Button(btn_frame, text="📤 Выгрузить PnP в Сверку", command=self.export_to_check,
                  bg="#059669", fg="#ffffff", activebackground="#10b981",
                  font=("Segoe UI", 9, "bold"), relief="flat", padx=14, pady=6, cursor="hand2").pack(side=tk.LEFT, padx=6)

        self.status_label = tk.Label(main_frame, text="Готов к объединению", font=("Segoe UI", 8),
                                     bg=t["bg_app"], fg=t["text_muted"], anchor=tk.W, padx=6, pady=4)
        self.status_label.pack(fill=tk.X, pady=(2, 0))

    # ---------- Сохранение BOM настроек ----------
    def save_bom_settings(self):
        """Сохраняет выбранные BOM колонки в MainApp."""
        if self.bom_ref_cb.get() and self.bom_data_cb.get():
            self.main_app.set_bom_columns(
                self.bom_ref_cb.get(),
                self.bom_data_cb.get(),
                self.bom_sep.get()
            )

    # ---------- Вспомогательные методы ----------
    def _is_empty_ref(self, value):
        return is_empty_ref(value)

    # ---------- Обработка дубликатов координат и зеркала P&P ----------
    def find_pnp_coordinate_duplicates(self, ref_col, x_col, y_col, mirror_col, convert_mil):
        if self.pnp_df is None or x_col not in self.pnp_df.columns or y_col not in self.pnp_df.columns:
            return {}
        df = self.pnp_df.copy()
        df[x_col] = pd.to_numeric(df[x_col], errors='coerce')
        df[y_col] = pd.to_numeric(df[y_col], errors='coerce')
        if convert_mil:
            df[x_col] *= 0.0254
            df[y_col] *= 0.0254
        df[x_col] = df[x_col].round(4)
        df[y_col] = df[y_col].round(4)

        if mirror_col is None or mirror_col not in self.pnp_df.columns:
            coord_groups = defaultdict(list)
            for idx, row in df.iterrows():
                x_val = row[x_col]
                y_val = row[y_col]
                if pd.isna(x_val) or pd.isna(y_val):
                    continue
                coord_groups[(x_val, y_val)].append(idx)
            return {coord: indices for coord, indices in coord_groups.items() if len(indices) > 1}

        df[mirror_col] = df[mirror_col].astype(str).str.strip()
        df[mirror_col] = df[mirror_col].replace('nan', '').replace('None', '')
        coord_groups = defaultdict(list)
        for idx, row in df.iterrows():
            x_val = row[x_col]
            y_val = row[y_col]
            mirror_val = row[mirror_col]
            if pd.isna(x_val) or pd.isna(y_val):
                continue
            if pd.isna(mirror_val):
                mirror_val = ''
            coord_groups[(x_val, y_val, mirror_val)].append(idx)
        return {coord: indices for coord, indices in coord_groups.items() if len(indices) > 1}

    def handle_pnp_coordinate_duplicates(self, ref_col, x_col, y_col, mirror_col, convert_mil):
        duplicates = self.find_pnp_coordinate_duplicates(ref_col, x_col, y_col, mirror_col, convert_mil)
        if not duplicates:
            return None

        if mirror_col is None or mirror_col not in self.pnp_df.columns:
            msg = "Найдены компоненты с одинаковыми координатами X и Y (дублирующиеся позиции):\n\n"
            for (x, y), indices in duplicates.items():
                rows = ', '.join(str(i+1) for i in indices)
                refs = []
                for idx in indices:
                    ref_val = self.pnp_df.at[idx, ref_col] if idx in self.pnp_df.index else "?"
                    refs.append(str(ref_val))
                msg += f"  Координаты ({x}, {y}) → строки: {rows}, REF: {', '.join(refs)}\n"
        else:
            msg = "Найдены компоненты с одинаковыми координатами X, Y и зеркалом (дублирующиеся позиции):\n\n"
            for (x, y, mirror), indices in duplicates.items():
                rows = ', '.join(str(i+1) for i in indices)
                refs = []
                for idx in indices:
                    ref_val = self.pnp_df.at[idx, ref_col] if idx in self.pnp_df.index else "?"
                    refs.append(str(ref_val))
                msg += f"  Координаты ({x}, {y}), зеркало '{mirror}' → строки: {rows}, REF: {', '.join(refs)}\n"
        msg += "\nВыберите действие:"

        dialog = tk.Toplevel(self.parent)
        dialog.title("Обработка дублирующихся позиций в P&P")
        dialog.geometry("700x500")
        dialog.transient(self.parent)
        dialog.grab_set()

        text_frame = ttk.Frame(dialog)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        text_widget = tk.Text(text_frame, wrap=tk.WORD, height=15)
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        text_widget.insert(tk.END, msg)
        text_widget.config(state=tk.DISABLED)

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)

        result = {"action": None, "data": None}

        def on_ignore():
            result["action"] = "ignore"
            result["data"] = self.pnp_df.copy()
            dialog.destroy()

        def on_delete():
            delete_dialog = tk.Toplevel(dialog)
            delete_dialog.title("Выбор строки для сохранения")
            delete_dialog.geometry("700x500")
            delete_dialog.transient(dialog)
            delete_dialog.grab_set()

            ttk.Label(delete_dialog, text="Для каждой группы (координаты и зеркало) выберите строку, которую нужно оставить.\nОстальные строки с этой комбинацией будут удалены.").pack(pady=10)

            main_frame = ttk.Frame(delete_dialog)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            canvas = tk.Canvas(main_frame)
            scrollbar2 = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
            scrollable_frame = ttk.Frame(canvas)

            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )

            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar2.set)

            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar2.pack(side=tk.RIGHT, fill=tk.Y)

            selected_indices = {}

            for key, indices in duplicates.items():
                if mirror_col is None or mirror_col not in self.pnp_df.columns:
                    x, y = key
                    label_text = f"Координаты ({x}, {y})"
                else:
                    x, y, mirror = key
                    label_text = f"Координаты ({x}, {y}), зеркало '{mirror}'"

                frame = ttk.LabelFrame(scrollable_frame, text=label_text, padding=5)
                frame.pack(fill=tk.X, padx=5, pady=5)

                var = tk.StringVar(value=str(indices[0]))
                selected_indices[key] = var

                for idx in indices:
                    if idx not in self.pnp_df.index:
                        continue
                    row = self.pnp_df.loc[idx]
                    ref_val = str(row[ref_col]) if pd.notna(row[ref_col]) else "?"
                    display_text = f"Строка {idx+1}: REF={ref_val}"
                    rb = ttk.Radiobutton(frame, text=display_text, variable=var, value=str(idx))
                    rb.pack(anchor=tk.W)

            def confirm_delete():
                try:
                    indices_to_keep = set()
                    for key, var in selected_indices.items():
                        keep_idx = int(var.get())
                        indices_to_keep.add(keep_idx)
                    all_dup_indices = set()
                    for indices in duplicates.values():
                        all_dup_indices.update(indices)
                    indices_to_drop = all_dup_indices - indices_to_keep
                    if indices_to_drop:
                        new_df = self.pnp_df.drop(index=list(indices_to_drop)).reset_index(drop=True)
                    else:
                        new_df = self.pnp_df.copy()
                    result["action"] = "delete"
                    result["data"] = new_df
                    delete_dialog.destroy()
                    dialog.destroy()
                except Exception as e:
                    err_msg = f"Ошибка при удалении дубликатов:\n{str(e)}\n\n{traceback.format_exc()}"
                    messagebox.showerror("Ошибка", err_msg, parent=self.parent)
                    delete_dialog.destroy()
                    dialog.destroy()
                    result["action"] = "cancel"

            ttk.Button(delete_dialog, text="Подтвердить", command=confirm_delete).pack(pady=10)
            ttk.Button(delete_dialog, text="Отмена", command=delete_dialog.destroy).pack(pady=5)

        def on_cancel():
            result["action"] = "cancel"
            dialog.destroy()

        ttk.Button(btn_frame, text="Игнорировать", command=on_ignore).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить дубликаты", command=on_delete).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=on_cancel).pack(side=tk.LEFT, padx=5)

        self.parent.wait_window(dialog)

        if result["action"] == "cancel":
            return "cancel"
        elif result["action"] == "ignore":
            return result["data"]
        elif result["action"] == "delete":
            return result["data"]
        return None

    # ---------- Обработка дубликатов REF в P&P ----------
    def find_pnp_duplicates(self, ref_col):
        if self.pnp_df is None or ref_col not in self.pnp_df.columns:
            return {}
        ref_list = []
        for idx, row in self.pnp_df.iterrows():
            if self._is_empty_ref(row[ref_col]):
                continue
            ref = str(row[ref_col]).strip()
            if ref:
                ref_list.append((ref, idx))
        grouped = defaultdict(list)
        for ref, idx in ref_list:
            grouped[ref].append(idx)
        return {ref: indices for ref, indices in grouped.items() if len(indices) > 1}

    def handle_pnp_duplicates(self, ref_col):
        duplicates = self.find_pnp_duplicates(ref_col)
        if not duplicates:
            return None

        msg = "Найдены дублирующиеся REF в P&P:\n\n"
        for ref, indices in duplicates.items():
            rows = ', '.join(str(i+1) for i in indices)
            msg += f"  {ref} → строки: {rows}\n"
        msg += "\nВыберите действие:"

        dialog = tk.Toplevel(self.parent)
        dialog.title("Обработка дубликатов REF в P&P")
        dialog.geometry("500x300")
        dialog.transient(self.parent)
        dialog.grab_set()

        label = ttk.Label(dialog, text=msg, justify=tk.LEFT)
        label.pack(padx=10, pady=10, fill=tk.X)

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)

        result = {"action": None, "data": None}

        def on_ignore():
            new_df = self.pnp_df.copy()
            for ref, indices in duplicates.items():
                for i, idx in enumerate(indices):
                    if i == 0:
                        continue
                    if idx not in new_df.index:
                        continue
                    new_df.at[idx, ref_col] = f"{ref}_{i}"
            result["action"] = "ignore"
            result["data"] = new_df
            dialog.destroy()

        def on_delete():
            delete_dialog = tk.Toplevel(dialog)
            delete_dialog.title("Выбор строки для сохранения REF")
            delete_dialog.geometry("700x500")
            delete_dialog.transient(dialog)
            delete_dialog.grab_set()

            ttk.Label(delete_dialog, text="Для каждого дублирующегося REF выберите строку, которую нужно оставить.\nОстальные строки будут удалены.").pack(pady=10)

            main_frame = ttk.Frame(delete_dialog)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            canvas = tk.Canvas(main_frame)
            scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
            scrollable_frame = ttk.Frame(canvas)

            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )

            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)

            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            selected_indices = {}

            for ref, indices in duplicates.items():
                frame = ttk.LabelFrame(scrollable_frame, text=f"REF: {ref}", padding=5)
                frame.pack(fill=tk.X, padx=5, pady=5)

                var = tk.StringVar(value=str(indices[0]))
                selected_indices[ref] = var

                for idx in indices:
                    if idx not in self.pnp_df.index:
                        continue
                    row = self.pnp_df.loc[idx]
                    display_text = f"Строка {idx+1}: {ref}"
                    rb = ttk.Radiobutton(frame, text=display_text, variable=var, value=str(idx))
                    rb.pack(anchor=tk.W)

            def confirm_delete():
                try:
                    indices_to_keep = set()
                    for ref, var in selected_indices.items():
                        keep_idx = int(var.get())
                        indices_to_keep.add(keep_idx)
                    all_dup_indices = set()
                    for indices in duplicates.values():
                        all_dup_indices.update(indices)
                    indices_to_drop = all_dup_indices - indices_to_keep
                    if indices_to_drop:
                        new_df = self.pnp_df.drop(index=list(indices_to_drop)).reset_index(drop=True)
                    else:
                        new_df = self.pnp_df.copy()
                    result["action"] = "delete"
                    result["data"] = new_df
                    delete_dialog.destroy()
                    dialog.destroy()
                except Exception as e:
                    err_msg = f"Ошибка при удалении дубликатов REF:\n{str(e)}\n\n{traceback.format_exc()}"
                    messagebox.showerror("Ошибка", err_msg, parent=self.parent)
                    delete_dialog.destroy()
                    dialog.destroy()
                    result["action"] = "cancel"

            ttk.Button(delete_dialog, text="Подтвердить", command=confirm_delete).pack(pady=10)
            ttk.Button(delete_dialog, text="Отмена", command=delete_dialog.destroy).pack(pady=5)

        def on_cancel():
            result["action"] = "cancel"
            dialog.destroy()

        ttk.Button(btn_frame, text="Игнорировать (переименовать дубликаты)", command=on_ignore).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить дубликаты", command=on_delete).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=on_cancel).pack(side=tk.LEFT, padx=5)

        self.parent.wait_window(dialog)

        if result["action"] == "cancel":
            return "cancel"
        elif result["action"] == "ignore":
            return result["data"]
        elif result["action"] == "delete":
            return result["data"]
        return None

    # ---------- Обработка дубликатов BOM ----------
    def find_bom_duplicates(self, ref_col, sep):
        if self.bom_df is None or ref_col not in self.bom_df.columns:
            return {}
        sep_pattern = r'\s*' + re.escape(sep) + r'\s*'
        ref_list = []
        for idx, row in self.bom_df.iterrows():
            if self._is_empty_ref(row[ref_col]):
                continue
            refs_str = str(row[ref_col]).strip()
            parts = re.split(sep_pattern, refs_str)
            for part in parts:
                part = part.strip()
                if part and not self._is_empty_ref(part):
                    ref_list.append((part, idx))
        grouped = defaultdict(list)
        for ref, idx in ref_list:
            grouped[ref].append(idx)
        return {ref: indices for ref, indices in grouped.items() if len(indices) > 1}

    def handle_bom_duplicates(self, ref_col, sep):
        duplicates = self.find_bom_duplicates(ref_col, sep)
        if not duplicates:
            return None

        data_bom_col = self.bom_data_cb.get()

        msg = "Найдены дублирующиеся REF в BOM:\n\n"
        for ref, indices in duplicates.items():
            rows = ', '.join(str(i+1) for i in indices)
            msg += f"  {ref} → строки: {rows}\n"
        msg += "\nВыберите действие:"

        dialog = tk.Toplevel(self.parent)
        dialog.title("Обработка дубликатов в BOM")
        dialog.geometry("500x300")
        dialog.transient(self.parent)
        dialog.grab_set()

        label = ttk.Label(dialog, text=msg, justify=tk.LEFT)
        label.pack(padx=10, pady=10, fill=tk.X)

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)

        result = {"action": None, "data": None}

        def on_ignore():
            new_df = self.bom_df.copy()
            sep_pattern = r'\s*' + re.escape(sep) + r'\s*'
            for ref, indices in duplicates.items():
                values = []
                for idx in indices:
                    if idx in new_df.index:
                        row = new_df.loc[idx]
                        val = row[data_bom_col] if pd.notna(row[data_bom_col]) else ""
                        values.append((idx, val))
                for i, (idx, val) in enumerate(values):
                    if i == 0:
                        continue
                    if idx not in new_df.index:
                        continue
                    refs_str = str(new_df.at[idx, ref_col]) if pd.notna(new_df.at[idx, ref_col]) else ""
                    parts = re.split(sep_pattern, refs_str)
                    new_parts = []
                    for part in parts:
                        part = part.strip()
                        if part == ref:
                            new_parts.append(f"{ref}_{i}")
                        else:
                            new_parts.append(part)
                    new_df.at[idx, ref_col] = sep.join(new_parts)
            result["action"] = "ignore"
            result["data"] = new_df
            dialog.destroy()

        def on_delete():
            delete_dialog = tk.Toplevel(dialog)
            delete_dialog.title("Выбор строки для сохранения REF")
            delete_dialog.geometry("700x500")
            delete_dialog.transient(dialog)
            delete_dialog.grab_set()

            ttk.Label(delete_dialog, text="Для каждого дублирующегося REF выберите строку, в которой этот REF должен остаться.\nВ остальных строках этот REF будет удалён (строка сохранится, если в ней есть другие REF).").pack(pady=10)

            main_frame = ttk.Frame(delete_dialog)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            canvas = tk.Canvas(main_frame)
            scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
            scrollable_frame = ttk.Frame(canvas)

            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )

            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)

            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            selected_indices = {}

            for ref, indices in duplicates.items():
                frame = ttk.LabelFrame(scrollable_frame, text=f"REF: {ref}", padding=5)
                frame.pack(fill=tk.X, padx=5, pady=5)

                var = tk.StringVar(value=str(indices[0]))
                selected_indices[ref] = var

                for idx in indices:
                    if idx not in self.bom_df.index:
                        continue
                    row = self.bom_df.loc[idx]
                    display_text = f"Строка {idx+1}: "
                    ref_val = str(row[ref_col]) if pd.notna(row[ref_col]) else ""
                    data_val = str(row[data_bom_col]) if pd.notna(row[data_bom_col]) else ""
                    display_text += f"RefDes: {ref_val}, Data: {data_val}"
                    rb = ttk.Radiobutton(frame, text=display_text, variable=var, value=str(idx))
                    rb.pack(anchor=tk.W)

            def confirm_delete():
                try:
                    new_df = self.bom_df.copy()
                    indices_to_drop = set()
                    sep_pattern = r'\s*' + re.escape(sep) + r'\s*'

                    for ref, var in selected_indices.items():
                        keep_idx = int(var.get())
                        idx_list = duplicates[ref]
                        for idx in idx_list:
                            if idx == keep_idx:
                                continue
                            if idx not in new_df.index:
                                continue
                            cell_val = new_df.at[idx, ref_col] if idx in new_df.index else None
                            if pd.isna(cell_val):
                                refs_str = ""
                            else:
                                refs_str = str(cell_val)

                            if refs_str:
                                parts = re.split(sep_pattern, refs_str)
                                new_parts = [p for p in parts if p.strip() != ref]
                                if new_parts:
                                    new_df.at[idx, ref_col] = sep.join(new_parts)
                                else:
                                    indices_to_drop.add(idx)
                            else:
                                indices_to_drop.add(idx)

                    if indices_to_drop:
                        new_df = new_df.drop(index=list(indices_to_drop)).reset_index(drop=True)

                    result["action"] = "delete"
                    result["data"] = new_df
                    delete_dialog.destroy()
                    dialog.destroy()
                except Exception as e:
                    err_msg = f"Ошибка при удалении дубликатов:\n{str(e)}\n\n{traceback.format_exc()}"
                    messagebox.showerror("Ошибка", err_msg, parent=self.parent)
                    delete_dialog.destroy()
                    dialog.destroy()
                    result["action"] = "cancel"

            ttk.Button(delete_dialog, text="Подтвердить", command=confirm_delete).pack(pady=10)
            ttk.Button(delete_dialog, text="Отмена", command=delete_dialog.destroy).pack(pady=5)

        def on_cancel():
            result["action"] = "cancel"
            dialog.destroy()

        ttk.Button(btn_frame, text="Игнорировать (переименовать дубликаты)", command=on_ignore).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить дубликаты", command=on_delete).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=on_cancel).pack(side=tk.LEFT, padx=5)

        self.parent.wait_window(dialog)

        if result["action"] == "cancel":
            return "cancel"
        elif result["action"] == "ignore":
            return result["data"]
        elif result["action"] == "delete":
            return result["data"]
        return None

    # ---------- Методы загрузки и навигации ----------
    def browse_pnp(self):
        f = filedialog.askopenfilename(filetypes=[("All supported", "*.txt *.csv *.xlsx *.xls"), ("Text files", "*.txt *.csv"), ("Excel files", "*.xlsx *.xls")], parent=self.parent)
        if f:
            self.pnp_file.set(f)
            self.load_pnp()

    def browse_bom(self):
        f = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls")], parent=self.parent)
        if f:
            self.bom_file.set(f)
            self.load_bom()

    def on_sep_changed(self):
        mode = self.pnp_sep_mode.get()
        if mode == "custom":
            self.pnp_custom_entry.config(state='normal')
            custom_val = self.pnp_custom_sep.get().strip()
            if custom_val:
                self.pnp_sep.set(custom_val)
            else:
                if self.pnp_sep.get() == "":
                    self.pnp_sep.set(" ")
        else:
            self.pnp_custom_entry.config(state='disabled')
            self.pnp_sep.set(mode)
        self.on_setting_changed('pnp_sep')
        if self.pnp_file.get() and os.path.exists(self.pnp_file.get()):
            self.load_pnp()

    def on_custom_sep_changed(self, *args):
        if self.pnp_sep_mode.get() == "custom":
            custom_val = self.pnp_custom_sep.get().strip()
            if custom_val:
                self.pnp_sep.set(custom_val)
            else:
                self.pnp_sep.set(" ")
            self.on_setting_changed('pnp_custom_sep')
            if self.pnp_file.get() and os.path.exists(self.pnp_file.get()):
                self.load_pnp()

    def on_one_side_changed(self):
        state = 'disabled' if self.one_side.get() else 'normal'
        self.pnp_mirror_cb.config(state=state)
        self.top_cb.config(state=state)
        self.bottom_cb.config(state=state)
        if self.one_side.get():
            self.top_cb.set('')
            self.bottom_cb.set('')
            self.pnp_mirror_cb.set('')
        self.on_setting_changed('one_side')

    def load_pnp(self):
        f = self.pnp_file.get()
        if not f or not os.path.exists(f):
            messagebox.showerror("Ошибка", "Файл P&P не выбран или не существует.", parent=self.parent)
            return

        ext = os.path.splitext(f)[1].lower()
        header = 0 if self.pnp_header.get() else None
        try:
            if ext in ['.xlsx', '.xls']:
                sheets = pd.read_excel(f, sheet_name=None, header=header, dtype=str)
                if not sheets:
                    messagebox.showerror("Ошибка", "Файл Excel не содержит листов.", parent=self.parent)
                    return
                if len(sheets) == 1:
                    df = sheets[list(sheets.keys())[0]]
                else:
                    self.select_pnp_sheet(sheets)
                    return
            else:
                sep_mode = self.pnp_sep_mode.get()
                if sep_mode == " ":
                    sep = r'\s+'
                    engine = 'python'
                elif sep_mode == "custom":
                    custom_sep = self.pnp_custom_sep.get().strip()
                    if custom_sep:
                        if len(custom_sep) == 1:
                            sep = custom_sep
                            engine = None
                        else:
                            sep = custom_sep
                            engine = 'python'
                    else:
                        sep = ' '
                        engine = None
                else:
                    sep = self.pnp_sep.get()
                    engine = None

                df = pd.read_csv(f, sep=sep, header=header, dtype=str, encoding='utf-8', engine=engine)

            if df.empty:
                messagebox.showerror("Ошибка", "P&P файл пуст.", parent=self.parent)
                return
            df.columns = [str(c) for c in df.columns]
            self.pnp_df = df
            self.pnp_columns = df.columns.tolist()
            self.pnp_ref_cb['values'] = self.pnp_columns
            self.pnp_x_cb['values'] = self.pnp_columns
            self.pnp_y_cb['values'] = self.pnp_columns
            self.pnp_mirror_cb['values'] = self.pnp_columns
            self.pnp_rotate_cb['values'] = self.pnp_columns
            if self.pnp_header.get():
                for col in self.pnp_columns:
                    cl = col.lower()
                    if 'ref' in cl or 'des' in cl:
                        self.pnp_ref_cb.set(col)
                    elif 'x' in cl and 'center' in cl:
                        self.pnp_x_cb.set(col)
                    elif 'y' in cl and 'center' in cl:
                        self.pnp_y_cb.set(col)
                    elif 'mirror' in cl or 'layer' in cl or 'side' in cl:
                        self.pnp_mirror_cb.set(col)
                    elif 'rotate' in cl or 'orient' in cl:
                        self.pnp_rotate_cb.set(col)
            self.status_label.config(text=f"P&P загружен: {len(df)} строк, {len(self.pnp_columns)} столбцов")
            if self.pnp_mirror_cb.get() and not self.one_side.get():
                self.update_side_options()
            self.main_app.set_pnp_data(df, f)
            self.on_setting_changed('load_pnp')
        except Exception as e:
            messagebox.showerror("Ошибка загрузки P&P", str(e), parent=self.parent)

    def select_pnp_sheet(self, sheets):
        dialog = tk.Toplevel(self.parent)
        dialog.title("Выбор листа PNP")
        dialog.geometry("300x150")
        ttk.Label(dialog, text="Выберите лист с PNP данными:").pack(pady=10)
        var = tk.StringVar()
        cb = ttk.Combobox(dialog, textvariable=var, values=list(sheets.keys()), state="readonly")
        cb.pack(pady=5)
        def confirm():
            sheet_name = var.get()
            if sheet_name:
                dialog.destroy()
                df = sheets[sheet_name]
                df.columns = [str(c) for c in df.columns]
                self.pnp_df = df
                self.pnp_columns = df.columns.tolist()
                self.pnp_ref_cb['values'] = self.pnp_columns
                self.pnp_x_cb['values'] = self.pnp_columns
                self.pnp_y_cb['values'] = self.pnp_columns
                self.pnp_mirror_cb['values'] = self.pnp_columns
                self.pnp_rotate_cb['values'] = self.pnp_columns
                if self.pnp_header.get():
                    for col in self.pnp_columns:
                        cl = col.lower()
                        if 'ref' in cl or 'des' in cl: self.pnp_ref_cb.set(col)
                        elif 'x' in cl and 'center' in cl: self.pnp_x_cb.set(col)
                        elif 'y' in cl and 'center' in cl: self.pnp_y_cb.set(col)
                        elif 'mirror' in cl or 'layer' in cl or 'side' in cl: self.pnp_mirror_cb.set(col)
                        elif 'rotate' in cl or 'orient' in cl: self.pnp_rotate_cb.set(col)
                self.status_label.config(text=f"P&P загружен: лист '{sheet_name}', {len(df)} строк, {len(self.pnp_columns)} столбцов")
                if self.pnp_mirror_cb.get() and not self.one_side.get():
                    self.update_side_options()
                self.main_app.set_pnp_data(df, self.pnp_file.get())
                self.on_setting_changed('load_pnp')
            else:
                messagebox.showwarning("Внимание", "Выберите лист.", parent=self.parent)
        ttk.Button(dialog, text="OK", command=confirm).pack(pady=10)

    def load_bom(self):
        f = self.bom_file.get()
        if not f or not os.path.exists(f):
            messagebox.showerror("Ошибка", "Файл BOM не выбран или не существует.", parent=self.parent)
            return
        try:
            sheets = pd.read_excel(f, sheet_name=None, dtype=str)
            if not sheets:
                messagebox.showerror("Ошибка", "BOM не содержит листов.", parent=self.parent)
                return
            if len(sheets) == 1:
                self._process_bom_sheet(sheets[list(sheets.keys())[0]], list(sheets.keys())[0])
            else:
                self.select_sheet(sheets)
        except Exception as e:
            messagebox.showerror("Ошибка загрузки BOM", str(e), parent=self.parent)

    def select_sheet(self, sheets):
        dialog = tk.Toplevel(self.parent)
        dialog.title("Выбор листа BOM")
        dialog.geometry("300x150")
        ttk.Label(dialog, text="Выберите лист с BOM:").pack(pady=10)
        var = tk.StringVar()
        cb = ttk.Combobox(dialog, textvariable=var, values=list(sheets.keys()), state="readonly")
        cb.pack(pady=5)
        def confirm():
            sheet_name = var.get()
            if sheet_name:
                dialog.destroy()
                self._process_bom_sheet(sheets[sheet_name], sheet_name)
            else:
                messagebox.showwarning("Внимание", "Выберите лист.", parent=self.parent)
        ttk.Button(dialog, text="OK", command=confirm).pack(pady=10)

    def _process_bom_sheet(self, df, sheet_name):
        if df.empty:
            messagebox.showerror("Ошибка", "Лист BOM пуст.", parent=self.parent)
            return
        df.columns = [str(c) for c in df.columns]
        self.bom_df = df
        self.bom_columns = df.columns.tolist()
        self.bom_ref_cb['values'] = self.bom_columns
        self.bom_data_cb['values'] = self.bom_columns

        # Автовыбор: самый правый столбец для данных BOM (по требованию: данные в этом боме всегда там)
        if self.bom_columns:
            self.bom_data_cb.set(self.bom_columns[-1])

        # Автовыбор столбца позиционных обозначений (RefDes)
        for col in self.bom_columns:
            cl = col.lower()
            if 'part reference' in cl or 'refdes' in cl or 'designator' in cl or 'позиц' in cl:
                self.bom_ref_cb.set(col)
                break
        # Сохраняем BOM настройки
        self.save_bom_settings()
        self.status_label.config(text=f"BOM загружен: лист '{sheet_name}', {len(df)} строк, {len(self.bom_columns)} столбцов")
        self.main_app.set_bom_data(df, self.bom_file.get())
        self.on_setting_changed('load_bom')

    def on_mirror_column_selected(self, event=None):
        if not self.one_side.get():
            self.update_side_options()
        self.on_setting_changed('mirror_col')

    def update_side_options(self):
        mirror_col = self.pnp_mirror_cb.get()
        if not mirror_col or self.pnp_df is None or mirror_col not in self.pnp_df.columns:
            self.top_cb['values'] = []
            self.bottom_cb['values'] = []
            self.top_cb.set('')
            self.bottom_cb.set('')
            return
        unique_vals = self.pnp_df[mirror_col].dropna().astype(str).unique()
        unique_vals = sorted([v.strip() for v in unique_vals if v.strip() != ''])
        all_vals = [''] + unique_vals
        self.top_cb['values'] = all_vals
        self.bottom_cb['values'] = all_vals
        if len(unique_vals) >= 2:
            self.top_cb.set(unique_vals[0])
            self.bottom_cb.set(unique_vals[1])
        elif len(unique_vals) == 1:
            self.top_cb.set(unique_vals[0])
            self.bottom_cb.set(unique_vals[0])
        else:
            self.top_cb.set('')
            self.bottom_cb.set('')

    # ---------- Основной метод: обновление результата ----------
    def on_setting_changed(self, changed_col=None):
        self.changed_col = changed_col
        self.build_preview_result(changed_col)
        # Сохраняем BOM настройки, если изменились BOM колонки
        if changed_col in ('bom_ref', 'bom_data', 'bom_sep'):
            self.save_bom_settings()

    def build_preview_result(self, changed_col=None):
        if self.pnp_df is None or self.bom_df is None:
            self.result_tree['columns'] = ()
            for item in self.result_tree.get_children():
                self.result_tree.delete(item)
            self.status_label.config(text="Загрузите P&P и BOM для предпросмотра")
            return

        ref_pnp = self.pnp_ref_cb.get()
        x_col = self.pnp_x_cb.get()
        y_col = self.pnp_y_cb.get()
        rotate_col = self.pnp_rotate_cb.get()
        ref_bom = self.bom_ref_cb.get()
        data_bom = self.bom_data_cb.get()

        if not all([ref_pnp, x_col, y_col, rotate_col, ref_bom, data_bom]):
            self.result_tree['columns'] = ()
            for item in self.result_tree.get_children():
                self.result_tree.delete(item)
            self.status_label.config(text="Выберите все необходимые столбцы (кроме Зеркала, если включена 'Одна сторона')")
            return

        if not self.one_side.get():
            mirror_col = self.pnp_mirror_cb.get()
            top_val = self.top_cb.get().strip()
            bottom_val = self.bottom_cb.get().strip()
            if not mirror_col:
                self.status_label.config(text="Выберите столбец Зеркало (или включите 'Одна сторона')")
                return
        else:
            mirror_col = None
            top_val = bottom_val = ""

        # Обработка дубликатов координат и зеркала
        coord_result = self.handle_pnp_coordinate_duplicates(ref_pnp, x_col, y_col, mirror_col, self.convert_mil.get())
        if isinstance(coord_result, str) and coord_result == "cancel":
            self.status_label.config(text="Операция отменена пользователем")
            self.result_tree['columns'] = ()
            for item in self.result_tree.get_children():
                self.result_tree.delete(item)
            return
        elif coord_result is not None:
            self.pnp_df = coord_result
            self.main_app.set_pnp_data(coord_result, self.pnp_file.get())
            self.status_label.config(text="Дубликаты координат и зеркала в P&P обработаны")

        # Обработка дубликатов REF в P&P
        ref_result = self.handle_pnp_duplicates(ref_pnp)
        if isinstance(ref_result, str) and ref_result == "cancel":
            self.status_label.config(text="Операция отменена пользователем")
            self.result_tree['columns'] = ()
            for item in self.result_tree.get_children():
                self.result_tree.delete(item)
            return
        elif ref_result is not None:
            self.pnp_df = ref_result
            self.main_app.set_pnp_data(ref_result, self.pnp_file.get())
            self.status_label.config(text="Дубликаты REF в P&P обработаны")

        # Обработка дубликатов в BOM
        sep = self.bom_sep.get().strip()
        if not sep:
            sep = ','
        bom_result = self.handle_bom_duplicates(ref_bom, sep)
        if isinstance(bom_result, str) and bom_result == "cancel":
            self.status_label.config(text="Операция отменена пользователем")
            self.result_tree['columns'] = ()
            for item in self.result_tree.get_children():
                self.result_tree.delete(item)
            return
        elif bom_result is not None:
            self.bom_df = bom_result
            self.main_app.set_bom_data(bom_result, self.bom_file.get())
            self.status_label.config(text="Дубликаты в BOM обработаны")

        # Построение результата
        try:
            pnp = self.pnp_df.copy()
            pnp[x_col] = pd.to_numeric(pnp[x_col], errors='coerce')
            pnp[y_col] = pd.to_numeric(pnp[y_col], errors='coerce')
            pnp[rotate_col] = pd.to_numeric(pnp[rotate_col], errors='coerce')
            if self.convert_mil.get():
                pnp[x_col] *= 0.0254
                pnp[y_col] *= 0.0254

            bom_dict = {}
            sep = self.bom_sep.get().strip()
            if not sep:
                sep = ','
            sep_pattern = r'\s*' + re.escape(sep) + r'\s*'
            for _, row in self.bom_df.iterrows():
                if self._is_empty_ref(row[ref_bom]):
                    continue
                refs = str(row[ref_bom]).strip()
                val = str(row[data_bom]) if pd.notna(row[data_bom]) else ""
                for r in re.split(sep_pattern, refs):
                    r = r.strip()
                    if r and not self._is_empty_ref(r):
                        bom_dict[r] = val

            # ИСПРАВЛЕНО: обрезаем референсы в PNP перед маппингом
            pnp['Parts_Name'] = pnp[ref_pnp].astype(str).str.strip().map(bom_dict).fillna("")

            if not self.one_side.get():
                top_low = top_val.lower()
                bottom_low = bottom_val.lower()

                # ИСПРАВЛЕНА логика определения стороны
                def mirror_to_side(v):
                    if pd.isna(v):
                        s = ''
                    else:
                        s = str(v).strip().lower()
                    # Если выбрано пустое значение для TOP, то пустые значения становятся TOP
                    if top_low == '' and s == '':
                        return "TOP"
                    # Если выбрано пустое значение для BOTTOM, то пустые значения становятся BOTTOM
                    if bottom_low == '' and s == '':
                        return "BOTTOM"
                    if top_low and s == top_low:
                        return "TOP"
                    elif bottom_low and s == bottom_low:
                        return "BOTTOM"
                    else:
                        return str(v) if not pd.isna(v) else ''

                result_pnp = pnp[[ref_pnp, x_col, y_col, rotate_col, mirror_col, 'Parts_Name']].copy()
                result_pnp.columns = ['REF', 'X', 'Y', 'R', 'Mirror', 'Parts_Name']
                result_pnp['Side'] = result_pnp['Mirror'].apply(mirror_to_side)
                result_pnp.drop(columns=['Mirror'], inplace=True)
            else:
                result_pnp = pnp[[ref_pnp, x_col, y_col, rotate_col, 'Parts_Name']].copy()
                result_pnp.columns = ['REF', 'X', 'Y', 'R', 'Parts_Name']
                result_pnp['Side'] = ""

            result_pnp['X'] = result_pnp['X'].round(4)
            result_pnp['Y'] = result_pnp['Y'].round(4)

            # Добавляем недостающие из BOM
            bom_refs = set()
            for _, row in self.bom_df.iterrows():
                if self._is_empty_ref(row[ref_bom]):
                    continue
                refs = str(row[ref_bom]).strip()
                for r in re.split(sep_pattern, refs):
                    r = r.strip()
                    if r and not self._is_empty_ref(r):
                        bom_refs.add(r)

            existing_refs = set(result_pnp['REF'].astype(str).str.strip().dropna())
            missing_refs = bom_refs - existing_refs

            if missing_refs:
                missing_rows = []
                for ref in missing_refs:
                    parts_name = bom_dict.get(ref, "")
                    missing_rows.append({
                        'REF': ref,
                        'X': None,
                        'Y': None,
                        'R': None,
                        'Parts_Name': parts_name,
                        'Side': ""
                    })
                missing_df = pd.DataFrame(missing_rows)
                result = pd.concat([result_pnp, missing_df], ignore_index=True)
            else:
                result = result_pnp

            self.result_df = result
            self.display_result_table(result, changed_col)

        except Exception as e:
            self.status_label.config(text=f"Ошибка: {str(e)}")
            self.result_tree['columns'] = ()
            for item in self.result_tree.get_children():
                self.result_tree.delete(item)

    def display_result_table(self, df, changed_col=None):
        cols = list(df.columns)
        self.result_tree['columns'] = cols
        for col in cols:
            display_col = col
            if changed_col and col == changed_col:
                display_col = col + " ★"
            self.result_tree.heading(col, text=display_col)
            self.result_tree.column(col, width=110, anchor=tk.CENTER)

        for item in self.result_tree.get_children():
            self.result_tree.delete(item)

        if hasattr(self, 'result_placeholder'):
            if df is not None and not df.empty:
                self.result_placeholder.place_forget()
            else:
                self.result_placeholder.place(relx=0.5, rely=0.45, anchor="center")

        for idx, row in df.head(100).iterrows():
            tag = "evenrow" if idx % 2 == 0 else "oddrow"
            self.result_tree.insert("", tk.END, values=list(row), tags=(tag,))

        self.status_label.config(text=f"Отображено {len(df.head(100))} из {len(df)} строк. Последнее изменение: {changed_col if changed_col else '—'}")

    # ---------- Сохранение ----------
    def run_merge(self):
        if self.result_df is None:
            messagebox.showerror("Ошибка", "Сначала сформируйте результат (предпросмотр).", parent=self.parent)
            return
        out = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")], parent=self.parent)
        if out:
            try:
                self.result_df.to_excel(out, index=False)
                self.status_label.config(text=f"Сохранён: {os.path.basename(out)}")
                messagebox.showinfo("Успех", f"Файл сохранён как {out}", parent=self.parent)
            except Exception as e:
                messagebox.showerror("Ошибка", str(e), parent=self.parent)

    def export_to_check(self):
        if self.result_df is None:
            messagebox.showerror("Ошибка", "Сначала сформируйте результат (предпросмотр).", parent=self.parent)
            return
        # Сохраняем BOM настройки
        self.save_bom_settings()
        # Передаём PnP в сверку
        self.main_app.set_pnp_data(self.result_df, "from_merge", notify_merge=False)
        # Применяем BOM колонки в сверке (если BOM там загружен)
        self.main_app.check_tab.apply_bom_columns()
        messagebox.showinfo("Успех", "PnP выгружен в Сверку.", parent=self.parent)

    # ---------- Методы для обновления данных из MainApp ----------
    def update_pnp_data(self, df, path):
        self.pnp_df = df
        self.pnp_file.set(path)
        cols = list(df.columns) if df is not None else []
        self.pnp_ref_cb['values'] = cols
        self.pnp_x_cb['values'] = cols
        self.pnp_y_cb['values'] = cols
        self.pnp_mirror_cb['values'] = cols
        self.pnp_rotate_cb['values'] = cols
        if self.pnp_mirror_cb.get() and not self.one_side.get():
            self.update_side_options()
        self.on_setting_changed('pnp_update')

    def update_bom_data(self, df, path):
        self.bom_df = df
        self.bom_file.set(path)
        cols = list(df.columns) if df is not None else []
        self.bom_ref_cb['values'] = cols
        self.bom_data_cb['values'] = cols
        if cols:
            # Автовыбор: самый правый столбец для данных BOM
            self.bom_data_cb.set(cols[-1])
            for col in cols:
                cl = col.lower()
                if 'part reference' in cl or 'refdes' in cl or 'designator' in cl or 'позиц' in cl:
                    self.bom_ref_cb.set(col)
                    break
        self.save_bom_settings()
        self.on_setting_changed('bom_update')

    def show_preview(self, df, file_type):
        if df is None or df.empty:
            messagebox.showinfo("Информация", f"Файл {file_type} не загружен или пуст.", parent=self.parent)
            return

        preview_window = create_styled_toplevel(self.parent, f"Предпросмотр {file_type}", "1250x750", min_size=(980, 580))

        frame = ttk.Frame(preview_window, padding="5")
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        cols = list(df.columns)
        tree = ttk.Treeview(frame, columns=cols, show="headings")
        tree.tag_configure('odd', background="#0e182e")
        tree.tag_configure('even', background="#131e36")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview, style="Horizontal.TScrollbar")
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=110, minwidth=80, anchor=tk.W)

        for idx, (_, row) in enumerate(df.head(100).iterrows()):
            values = [str(v) if pd.notna(v) else "" for v in row]
            tag = 'even' if idx % 2 == 0 else 'odd'
            tree.insert("", tk.END, values=values, tags=(tag,))

        btn_bar = ttk.Frame(preview_window, padding="5")
        btn_bar.pack(fill=tk.X, pady=5)
        ttk.Label(btn_bar, text=f"Показано {min(len(df), 100)} из {len(df)} строк, {len(cols)} колонок.",
                  foreground="gray").pack(side=tk.TOP, pady=2)
        ttk.Button(btn_bar, text="Закрыть", command=preview_window.destroy).pack(side=tk.BOTTOM, pady=4)

        style_widget_tree(preview_window, "dark")


# ==================== ВКЛАДКА "СРАВНЕНИЕ PNP ВЕРСИЙ" ====================
class CompareTab(ttk.Frame):
    def __init__(self, parent, main_app):
        self.parent = parent
        self.main_app = main_app
        super().__init__(parent)

        # --- Прокручиваемая область ---
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Переменные ---
        self.old_file = tk.StringVar()
        self.new_file = tk.StringVar()
        self.old_sep = tk.StringVar(value=" ")
        self.old_sep_mode = tk.StringVar(value=" ")
        self.old_custom_sep = tk.StringVar(value="")
        self.new_sep = tk.StringVar(value=" ")
        self.new_sep_mode = tk.StringVar(value=" ")
        self.new_custom_sep = tk.StringVar(value="")
        self.old_header = tk.BooleanVar(value=True)
        self.new_header = tk.BooleanVar(value=True)

        self.df_old = None
        self.df_new = None
        self.old_columns = []
        self.new_columns = []
        self.old_ref_col = tk.StringVar()
        self.new_ref_col = tk.StringVar()
        self.mapping_entries = []
        self.result_df = None
        self.all_data = []
        self.filter_status = tk.StringVar(value="Все")
        self.tol_xy = tk.StringVar(value="0.01")
        self.tol_r = tk.StringVar(value="0.1")
        self.ref_sep = tk.StringVar(value=",")

        self.one_side = tk.BooleanVar(value=False)
        self.old_side_col = tk.StringVar()
        self.new_side_col = tk.StringVar()
        self.old_top_val = tk.StringVar()
        self.old_bottom_val = tk.StringVar()
        self.new_top_val = tk.StringVar()
        self.new_bottom_val = tk.StringVar()

        self.btn_export_to_merge = None
        self.create_widgets()
        self.on_one_side_changed()

    def get_separator_dialog(self):
        t = THEMES["dark"]
        dialog = create_styled_toplevel(self.parent, "Выбор разделителя", "460x260", min_size=(420, 240))
        dialog.transient(self.parent)
        dialog.grab_set()

        content = tk.Frame(dialog, bg=t["bg_app"], padx=20, pady=16)
        content.pack(fill=tk.BOTH, expand=True)

        tk.Label(content, text="Выберите разделитель для формирования .TXT:",
                 font=("Segoe UI", 10, "bold"), bg=t["bg_app"], fg=t["text_header"]).pack(anchor="w", pady=(0, 8))

        card = tk.Frame(content, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=16, pady=12)
        card.pack(fill=tk.X, pady=(0, 12))

        sep_map = {
            "Табуляция (\\t)": "\t",
            "Пробел (␣)": " ",
            "Точка с запятой (;)": ";",
            "Запятая (,)": ",",
            "Вертикальная черта (|)": "|",
        }
        display_options = list(sep_map.keys()) + ["Свой символ..."]

        combo_var = tk.StringVar(value="Табуляция (\\t)")
        custom_var = tk.StringVar(value="")

        tk.Label(card, text="Стандартный разделитель:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).pack(anchor="w", pady=(0, 4))
        combo = ttk.Combobox(card, textvariable=combo_var, values=display_options, state="readonly", width=28, font=("Segoe UI", 9))
        combo.pack(fill=tk.X, pady=(0, 8))

        custom_box = tk.Frame(card, bg=t["bg_card"])
        custom_box.pack(fill=tk.X)

        tk.Label(custom_box, text="Свой разделитель:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_secondary"]).pack(side=tk.LEFT)
        custom_entry = ttk.Entry(custom_box, textvariable=custom_var, width=8, justify="center", state="disabled")
        custom_entry.pack(side=tk.LEFT, padx=8)

        hint_lbl = tk.Label(custom_box, text="(\\t - табуляция, \\s - пробел)", font=("Segoe UI", 8), bg=t["bg_card"], fg=t["text_muted"])
        hint_lbl.pack(side=tk.LEFT)

        def on_combo_change(event=None):
            if combo_var.get() == "Свой символ...":
                custom_entry.configure(state="normal")
                custom_entry.focus()
            else:
                custom_entry.configure(state="disabled")

        combo.bind("<<ComboboxSelected>>", on_combo_change)

        result = {"sep": None}

        def on_ok():
            choice = combo_var.get()
            if choice == "Свой символ...":
                c = custom_var.get()
                if c == r"\t":
                    result["sep"] = "\t"
                elif c in (r"\s", r"\p", "␣"):
                    result["sep"] = " "
                elif c:
                    result["sep"] = c
                else:
                    result["sep"] = "\t"
            else:
                result["sep"] = sep_map.get(choice, "\t")
            dialog.destroy()

        def on_cancel():
            result["sep"] = None
            dialog.destroy()

        dialog.bind("<Return>", lambda e: on_ok())
        dialog.bind("<Escape>", lambda e: on_cancel())

        btn_frame = tk.Frame(content, bg=t["bg_app"])
        btn_frame.pack(fill=tk.X)

        btn_ok = tk.Button(btn_frame, text="OK", command=on_ok,
                           bg=t["accent"], fg=t["accent_text"], activebackground=t["accent_hover"],
                           font=("Segoe UI", 9, "bold"), relief="flat", padx=20, pady=5, cursor="hand2")
        btn_ok.pack(side=tk.LEFT, padx=(0, 8))

        btn_cancel = tk.Button(btn_frame, text="Отмена", command=on_cancel,
                               bg=t["btn_sec_bg"], fg=t["btn_sec_fg"], activebackground=t["btn_sec_hover"],
                               font=("Segoe UI", 9), relief="flat", padx=16, pady=5, cursor="hand2")
        btn_cancel.pack(side=tk.LEFT)

        style_widget_tree(dialog, "dark")
        self.parent.wait_window(dialog)
        return result["sep"]

    def create_widgets(self):
        t = THEMES["dark"]
        main_frame = tk.Frame(self.scrollable_frame, bg=t["bg_app"], padx=8, pady=6)
        main_frame.pack(fill=tk.BOTH, expand=True)

        top_frame = tk.Frame(main_frame, bg=t["bg_app"])
        top_frame.pack(fill=tk.X, pady=(0, 8))
        top_frame.columnconfigure(0, weight=1)
        top_frame.columnconfigure(1, weight=1)
        top_frame.rowconfigure(0, weight=1)

        # -------------------------------------------------------------
        # Старая версия P&P
        # -------------------------------------------------------------
        old_frame = tk.Frame(top_frame, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=12, pady=10)
        old_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=2)
        old_frame.columnconfigure(1, weight=1)

        tk.Label(old_frame, text="📁 Старая версия P&P", font=("Segoe UI", 10, "bold"),
                 bg=t["bg_card"], fg=t["accent"]).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

        tk.Label(old_frame, text="Файл P&P:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=1, column=0, sticky="w", pady=4)
        old_entry = ttk.Entry(old_frame, textvariable=self.old_file)
        old_entry.grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        old_entry.bind("<Return>", lambda e: self.load_file('old'))
        btn_old_browse = ttk.Button(old_frame, text="Обзор...", command=lambda: self.browse_file('old'))
        btn_old_browse.grid(row=1, column=2, padx=2, pady=4)
        btn_old_view = ttk.Button(old_frame, text="👁️", width=3, command=lambda: self.show_preview(self.df_old, "Старый PNP"))
        btn_old_view.grid(row=1, column=3, padx=2, pady=4)
        ToolTip(btn_old_view, "Предпросмотр старого файла P&P")

        sep_frame_old = tk.Frame(old_frame, bg=t["bg_card"])
        sep_frame_old.grid(row=2, column=0, columnspan=4, sticky="w", pady=(2, 4))
        tk.Label(sep_frame_old, text="Разделитель:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_secondary"]).pack(side=tk.LEFT, padx=(0, 4))
        for sep in [" ", "\t", ",", ";"]:
            ttk.Radiobutton(sep_frame_old, text=repr(sep), variable=self.old_sep_mode,
                            value=sep, command=self.on_old_sep_changed).pack(side=tk.LEFT, padx=3)
        ttk.Radiobutton(sep_frame_old, text="Свой", variable=self.old_sep_mode,
                        value="custom", command=self.on_old_sep_changed).pack(side=tk.LEFT, padx=3)
        self.old_custom_entry = ttk.Entry(sep_frame_old, textvariable=self.old_custom_sep, width=4, state='disabled')
        self.old_custom_entry.pack(side=tk.LEFT, padx=3)
        self.old_custom_sep.trace_add('write', self.on_old_custom_sep_changed)
        ttk.Checkbutton(sep_frame_old, text="Есть заголовок", variable=self.old_header,
                        command=lambda: self.load_file('old') if self.old_file.get() and os.path.exists(self.old_file.get()) else None).pack(side=tk.LEFT, padx=(10, 0))

        # -------------------------------------------------------------
        # Новая версия P&P
        # -------------------------------------------------------------
        new_frame = tk.Frame(top_frame, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=12, pady=10)
        new_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=2)
        new_frame.columnconfigure(1, weight=1)

        tk.Label(new_frame, text="📁 Новая версия P&P", font=("Segoe UI", 10, "bold"),
                 bg=t["bg_card"], fg=t["accent"]).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

        tk.Label(new_frame, text="Файл P&P:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=1, column=0, sticky="w", pady=4)
        new_entry = ttk.Entry(new_frame, textvariable=self.new_file)
        new_entry.grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        new_entry.bind("<Return>", lambda e: self.load_file('new'))
        btn_new_browse = ttk.Button(new_frame, text="Обзор...", command=lambda: self.browse_file('new'))
        btn_new_browse.grid(row=1, column=2, padx=2, pady=4)
        btn_new_view = ttk.Button(new_frame, text="👁️", width=3, command=lambda: self.show_preview(self.df_new, "Новый PNP"))
        btn_new_view.grid(row=1, column=3, padx=2, pady=4)
        ToolTip(btn_new_view, "Предпросмотр нового файла P&P")

        sep_frame_new = tk.Frame(new_frame, bg=t["bg_card"])
        sep_frame_new.grid(row=2, column=0, columnspan=4, sticky="w", pady=(2, 4))
        tk.Label(sep_frame_new, text="Разделитель:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_secondary"]).pack(side=tk.LEFT, padx=(0, 4))
        for sep in [" ", "\t", ",", ";"]:
            ttk.Radiobutton(sep_frame_new, text=repr(sep), variable=self.new_sep_mode,
                            value=sep, command=self.on_new_sep_changed).pack(side=tk.LEFT, padx=3)
        ttk.Radiobutton(sep_frame_new, text="Свой", variable=self.new_sep_mode,
                        value="custom", command=self.on_new_sep_changed).pack(side=tk.LEFT, padx=3)
        self.new_custom_entry = ttk.Entry(sep_frame_new, textvariable=self.new_custom_sep, width=4, state='disabled')
        self.new_custom_entry.pack(side=tk.LEFT, padx=3)
        self.new_custom_sep.trace_add('write', self.on_new_custom_sep_changed)
        ttk.Checkbutton(sep_frame_new, text="Есть заголовок", variable=self.new_header,
                        command=lambda: self.load_file('new') if self.new_file.get() and os.path.exists(self.new_file.get()) else None).pack(side=tk.LEFT, padx=(10, 0))

        self.btn_export_to_merge = tk.Button(new_frame, text="📤 Загрузить новый PnP в объединитель (Шаг 2)",
                                             command=self.export_new_to_merge, bg="#059669", fg="#ffffff",
                                             activebackground="#10b981", activeforeground="#ffffff",
                                             font=("Segoe UI", 9, "bold"), relief="flat", padx=10, pady=4,
                                             state='disabled', cursor="hand2")
        self.btn_export_to_merge.grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 2))

        # -------------------------------------------------------------
        # Настройка параметров сравнения
        # -------------------------------------------------------------
        settings_frame = tk.Frame(main_frame, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=14, pady=12)
        settings_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(settings_frame, text="⚙️ Настройка параметров сравнения",
                 font=("Segoe UI", 10, "bold"), bg=t["bg_card"], fg=t["accent"]).pack(anchor="w", pady=(0, 8))

        id_frame = tk.Frame(settings_frame, bg=t["bg_card"])
        id_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(id_frame, text="Столбец REF (старый):", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=0, column=0, sticky=tk.W, padx=(0, 4), pady=2)
        self.old_ref_cb = ttk.Combobox(id_frame, textvariable=self.old_ref_col, state="readonly", width=18, font=("Segoe UI", 9))
        self.old_ref_cb.grid(row=0, column=1, padx=4, pady=2)
        self.old_ref_cb.bind("<<ComboboxSelected>>", self.on_ref_changed)

        tk.Label(id_frame, text="Столбец REF (новый):", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=0, column=2, sticky=tk.W, padx=(16, 4), pady=2)
        self.new_ref_cb = ttk.Combobox(id_frame, textvariable=self.new_ref_col, state="readonly", width=18, font=("Segoe UI", 9))
        self.new_ref_cb.grid(row=0, column=3, padx=4, pady=2)
        self.new_ref_cb.bind("<<ComboboxSelected>>", self.on_ref_changed)

        tk.Label(id_frame, text="Разделитель REF:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=0, column=4, sticky=tk.W, padx=(16, 4), pady=2)
        ref_sep_entry = ttk.Entry(id_frame, textvariable=self.ref_sep, width=5, justify="center")
        ref_sep_entry.grid(row=0, column=5, padx=4, pady=2, sticky=tk.W)
        self.ref_sep.trace_add('write', lambda *args: self.update_mapping())

        # Настройка стороны (Mirror)
        side_frame = tk.Frame(settings_frame, bg=t["bg_card_inner"], highlightbackground=t["border"], highlightthickness=1, padx=10, pady=8)
        side_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Checkbutton(side_frame, text="Одна сторона (игнорировать сторону монтажа / Side)", variable=self.one_side,
                        command=self.on_one_side_changed).grid(row=0, column=0, columnspan=6, sticky=tk.W, padx=2, pady=(0, 4))

        tk.Label(side_frame, text="Столбец Side (старый):", font=("Segoe UI", 9), bg=t["bg_card_inner"], fg=t["text_primary"]).grid(row=1, column=0, sticky=tk.W, padx=2, pady=2)
        self.old_side_cb = ttk.Combobox(side_frame, textvariable=self.old_side_col, state="readonly", width=16, font=("Segoe UI", 9))
        self.old_side_cb.grid(row=1, column=1, padx=4, pady=2)
        self.old_side_cb.bind("<<ComboboxSelected>>", self.on_old_side_selected)

        tk.Label(side_frame, text="Значение TOP (старый):", font=("Segoe UI", 9), bg=t["bg_card_inner"], fg=t["text_secondary"]).grid(row=1, column=2, sticky=tk.W, padx=(12, 4), pady=2)
        self.old_top_cb = ttk.Combobox(side_frame, textvariable=self.old_top_val, state="readonly", width=12, font=("Segoe UI", 9))
        self.old_top_cb.grid(row=1, column=3, padx=4, pady=2)

        tk.Label(side_frame, text="Значение BOTTOM (старый):", font=("Segoe UI", 9), bg=t["bg_card_inner"], fg=t["text_secondary"]).grid(row=1, column=4, sticky=tk.W, padx=(12, 4), pady=2)
        self.old_bottom_cb = ttk.Combobox(side_frame, textvariable=self.old_bottom_val, state="readonly", width=12, font=("Segoe UI", 9))
        self.old_bottom_cb.grid(row=1, column=5, padx=4, pady=2)

        tk.Label(side_frame, text="Столбец Side (новый):", font=("Segoe UI", 9), bg=t["bg_card_inner"], fg=t["text_primary"]).grid(row=2, column=0, sticky=tk.W, padx=2, pady=2)
        self.new_side_cb = ttk.Combobox(side_frame, textvariable=self.new_side_col, state="readonly", width=16, font=("Segoe UI", 9))
        self.new_side_cb.grid(row=2, column=1, padx=4, pady=2)
        self.new_side_cb.bind("<<ComboboxSelected>>", self.on_new_side_selected)

        tk.Label(side_frame, text="Значение TOP (новый):", font=("Segoe UI", 9), bg=t["bg_card_inner"], fg=t["text_secondary"]).grid(row=2, column=2, sticky=tk.W, padx=(12, 4), pady=2)
        self.new_top_cb = ttk.Combobox(side_frame, textvariable=self.new_top_val, state="readonly", width=12, font=("Segoe UI", 9))
        self.new_top_cb.grid(row=2, column=3, padx=4, pady=2)

        tk.Label(side_frame, text="Значение BOTTOM (новый):", font=("Segoe UI", 9), bg=t["bg_card_inner"], fg=t["text_secondary"]).grid(row=2, column=4, sticky=tk.W, padx=(12, 4), pady=2)
        self.new_bottom_cb = ttk.Combobox(side_frame, textvariable=self.new_bottom_val, state="readonly", width=12, font=("Segoe UI", 9))
        self.new_bottom_cb.grid(row=2, column=5, padx=4, pady=2)

        # Допуски
        tol_frame = tk.Frame(settings_frame, bg=t["bg_card"])
        tol_frame.pack(fill=tk.X)
        tk.Label(tol_frame, text="Допуски отклонений:", font=("Segoe UI", 9, "bold"), bg=t["bg_card"], fg=t["text_primary"]).pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(tol_frame, text="По X, Y (мм):", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_secondary"]).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(tol_frame, textvariable=self.tol_xy, width=8, justify="center").pack(side=tk.LEFT, padx=(0, 16))
        tk.Label(tol_frame, text="По углу R (градусы):", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_secondary"]).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(tol_frame, textvariable=self.tol_r, width=8, justify="center").pack(side=tk.LEFT)

        # -------------------------------------------------------------
        # Столбцы для сравнения и соответствие
        # -------------------------------------------------------------
        compare_frame = tk.Frame(main_frame, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=14, pady=12)
        compare_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        tk.Label(compare_frame, text="📊 Столбцы для сравнения и их соответствие",
                 font=("Segoe UI", 10, "bold"), bg=t["bg_card"], fg=t["accent"]).pack(anchor="w", pady=(0, 8))

        cols_split = tk.Frame(compare_frame, bg=t["bg_card"])
        cols_split.pack(fill=tk.BOTH, expand=True)
        cols_split.columnconfigure(0, weight=1)
        cols_split.columnconfigure(1, weight=1)

        left_frame = tk.Frame(cols_split, bg=t["bg_card"])
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        tk.Label(left_frame, text="Столбцы из старого файла (выберите несколько):", font=("Segoe UI", 9),
                 bg=t["bg_card"], fg=t["text_primary"]).pack(anchor=tk.W, pady=(0, 4))

        listbox_frame = tk.Frame(left_frame, bg=t["border"], highlightthickness=1, highlightbackground=t["border"])
        listbox_frame.pack(fill=tk.BOTH, expand=True)

        self.compare_listbox = tk.Listbox(listbox_frame, selectmode=tk.MULTIPLE, height=6,
                                          bg=t["bg_card_inner"], fg=t["text_primary"],
                                          selectbackground=t["accent"], selectforeground="#ffffff",
                                          relief="flat", font=("Segoe UI", 9), highlightthickness=0)
        self.compare_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scroll_comp = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self.compare_listbox.yview)
        scroll_comp.pack(side=tk.RIGHT, fill=tk.Y)
        self.compare_listbox.config(yscrollcommand=scroll_comp.set)

        btn_add_cols = ttk.Button(left_frame, text="Добавить выбранные ➔", command=self.add_selected_columns)
        btn_add_cols.pack(anchor="w", pady=6)
        ToolTip(btn_add_cols, "Добавить выбранные столбцы в сопоставление")

        right_frame = tk.Frame(cols_split, bg=t["bg_card"])
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        tk.Label(right_frame, text="Соответствие столбцов (старый ➔ новый):", font=("Segoe UI", 9),
                 bg=t["bg_card"], fg=t["text_primary"]).pack(anchor=tk.W, pady=(0, 4))

        mapping_container = tk.Frame(right_frame, bg=t["bg_card_inner"], highlightbackground=t["border"], highlightthickness=1, padx=6, pady=6)
        mapping_container.pack(fill=tk.BOTH, expand=True)

        self.mapping_frame = tk.Frame(mapping_container, bg=t["bg_card_inner"])
        self.mapping_frame.pack(fill=tk.BOTH, expand=True)

        btn_clear = ttk.Button(right_frame, text="🧹 Очистить соответствия", command=self.clear_mapping)
        btn_clear.pack(anchor="w", pady=6)
        ToolTip(btn_clear, "Очистить список сопоставления")

        # -------------------------------------------------------------
        # Кнопка запуска сравнения
        # -------------------------------------------------------------
        action_bar = tk.Frame(main_frame, bg=t["bg_app"])
        action_bar.pack(fill=tk.X, pady=6)

        btn_run = tk.Button(action_bar, text="🔍 Сравнить ревизии P&P", command=self.run_comparison,
                            bg=t["accent"], fg="#ffffff", activebackground=t["accent_hover"], activeforeground="#ffffff",
                            font=("Segoe UI", 11, "bold"), relief="flat", padx=28, pady=7, cursor="hand2")
        btn_run.pack(anchor="center")

        # -------------------------------------------------------------
        # Результаты сравнения
        # -------------------------------------------------------------
        result_card = tk.Frame(main_frame, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=14, pady=12)
        result_card.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        filter_bar = tk.Frame(result_card, bg=t["bg_card"])
        filter_bar.pack(fill=tk.X, pady=(0, 8))

        tk.Label(filter_bar, text="📋 Результаты сравнения", font=("Segoe UI", 10, "bold"),
                 bg=t["bg_card"], fg=t["accent"]).pack(side=tk.LEFT)

        tk.Label(filter_bar, text="Фильтр по статусу:", font=("Segoe UI", 9),
                 bg=t["bg_card"], fg=t["text_secondary"]).pack(side=tk.LEFT, padx=(20, 6))
        self.filter_cb = ttk.Combobox(filter_bar, textvariable=self.filter_status,
                                      values=["Все", "Добавлен", "Удалён", "Изменён", "Не изменён"],
                                      state="readonly", width=15, font=("Segoe UI", 9))
        self.filter_cb.pack(side=tk.LEFT, padx=(0, 6))
        self.filter_cb.bind("<<ComboboxSelected>>", self.apply_filter)

        btn_reset_filter = ttk.Button(filter_bar, text="Сбросить фильтр", command=self.reset_filter)
        btn_reset_filter.pack(side=tk.LEFT)

        tree_container = tk.Frame(result_card, bg=t["bg_card"])
        tree_container.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(tree_container, columns=(), show="headings", height=13)
        self.tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = ttk.Scrollbar(tree_container, orient=tk.HORIZONTAL, command=self.tree.xview)
        hsb.grid(row=1, column=0, sticky="ew")

        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        self.tree.tag_configure('evenrow', background=t["row_even"])
        self.tree.tag_configure('oddrow', background=t["row_odd"])
        self.tree.tag_configure('changed', background="#451a03", foreground="#fde047")
        self.tree.tag_configure('added', background="#064e3b", foreground="#6ee7b7")
        self.tree.tag_configure('deleted', background="#450a0a", foreground="#fca5a5")

        self.tree_placeholder = tk.Label(self.tree, text="Здесь появятся результаты сравнения ревизий P&P.\nЗагрузите старый и новый файлы P&P и нажмите «Сравнить».",
                                         font=("Segoe UI", 10), bg=t["bg_card"], fg=t["text_muted"], justify="center")
        self.tree_placeholder.place(relx=0.5, rely=0.5, anchor="center")

        export_bar = tk.Frame(result_card, bg=t["bg_card"])
        export_bar.pack(fill=tk.X, pady=(10, 0))

        btn_exp_xls = tk.Button(export_bar, text="📥 Экспорт в Excel (.xlsx)", command=self.export_excel,
                                bg="#059669", fg="#ffffff", activebackground="#10b981", activeforeground="#ffffff",
                                font=("Segoe UI", 9, "bold"), relief="flat", padx=14, pady=5, cursor="hand2")
        btn_exp_xls.pack(side=tk.LEFT, padx=(0, 8))

        btn_exp_txt = tk.Button(export_bar, text="📥 Экспорт в TXT (.txt)", command=self.export_txt,
                                bg=t["accent"], fg="#ffffff", activebackground=t["accent_hover"], activeforeground="#ffffff",
                                font=("Segoe UI", 9, "bold"), relief="flat", padx=14, pady=5, cursor="hand2")
        btn_exp_txt.pack(side=tk.LEFT)

        self.status_label = tk.Label(main_frame, text="Готов к работе", font=("Segoe UI", 9),
                                     bg=t["bg_app"], fg=t["text_muted"], anchor="w")
        self.status_label.pack(fill=tk.X, pady=(6, 2))

    # ---------- Обработка разделителей ----------
    def on_old_sep_changed(self):
        mode = self.old_sep_mode.get()
        if mode == "custom":
            self.old_custom_entry.config(state='normal')
            custom_val = self.old_custom_sep.get().strip()
            if custom_val:
                self.old_sep.set(custom_val)
            else:
                if self.old_sep.get() == "":
                    self.old_sep.set(" ")
        else:
            self.old_custom_entry.config(state='disabled')
            self.old_sep.set(mode)
        if self.old_file.get() and os.path.exists(self.old_file.get()):
            self.load_file('old')

    def on_old_custom_sep_changed(self, *args):
        if self.old_sep_mode.get() == "custom":
            custom_val = self.old_custom_sep.get().strip()
            if custom_val:
                self.old_sep.set(custom_val)
            else:
                self.old_sep.set(" ")
            if self.old_file.get() and os.path.exists(self.old_file.get()):
                self.load_file('old')

    def on_new_sep_changed(self):
        mode = self.new_sep_mode.get()
        if mode == "custom":
            self.new_custom_entry.config(state='normal')
            custom_val = self.new_custom_sep.get().strip()
            if custom_val:
                self.new_sep.set(custom_val)
            else:
                if self.new_sep.get() == "":
                    self.new_sep.set(" ")
        else:
            self.new_custom_entry.config(state='disabled')
            self.new_sep.set(mode)
        if self.new_file.get() and os.path.exists(self.new_file.get()):
            self.load_file('new')

    def on_new_custom_sep_changed(self, *args):
        if self.new_sep_mode.get() == "custom":
            custom_val = self.new_custom_sep.get().strip()
            if custom_val:
                self.new_sep.set(custom_val)
            else:
                self.new_sep.set(" ")
            if self.new_file.get() and os.path.exists(self.new_file.get()):
                self.load_file('new')

    # ---------- Обработка стороны ----------
    def on_one_side_changed(self):
        state = 'disabled' if self.one_side.get() else 'normal'
        for widget_name in ['old_side_cb', 'old_top_cb', 'old_bottom_cb',
                            'new_side_cb', 'new_top_cb', 'new_bottom_cb']:
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.config(state=state)
        if self.one_side.get():
            self.old_side_col.set('')
            self.new_side_col.set('')
            self.old_top_val.set('')
            self.old_bottom_val.set('')
            self.new_top_val.set('')
            self.new_bottom_val.set('')
        if hasattr(self, 'mapping_frame'):
            self.update_mapping()

    def on_old_side_selected(self, event=None):
        self.update_side_combos('old')

    def on_new_side_selected(self, event=None):
        self.update_side_combos('new')

    def update_side_combos(self, file_type):
        if file_type == 'old':
            df = self.df_old
            side_col = self.old_side_col.get().strip()
            top_cb = self.old_top_cb
            bottom_cb = self.old_bottom_cb
            top_var = self.old_top_val
            bottom_var = self.old_bottom_val
        else:
            df = self.df_new
            side_col = self.new_side_col.get().strip()
            top_cb = self.new_top_cb
            bottom_cb = self.new_bottom_cb
            top_var = self.new_top_val
            bottom_var = self.new_bottom_val

        if df is None or not side_col or side_col not in df.columns:
            top_cb['values'] = []
            bottom_cb['values'] = []
            top_var.set('')
            bottom_var.set('')
            return

        unique_vals = df[side_col].dropna().astype(str).str.strip()
        unique_vals = unique_vals[unique_vals != ''].unique().tolist()
        unique_vals = sorted(unique_vals)
        all_vals = [''] + unique_vals

        top_cb['values'] = all_vals
        bottom_cb['values'] = all_vals

        if len(unique_vals) >= 2:
            top_var.set(unique_vals[0])
            bottom_var.set(unique_vals[1])
        elif len(unique_vals) == 1:
            top_var.set(unique_vals[0])
            bottom_var.set(unique_vals[0])
        else:
            top_var.set('')
            bottom_var.set('')

    # ---------- Очистка выдачи ----------
    def clear_mapping(self):
        self.mapping_entries = []
        for widget in self.mapping_frame.winfo_children():
            widget.destroy()

    def delete_mapping_entry(self, idx):
        if 0 <= idx < len(self.mapping_entries):
            del self.mapping_entries[idx]
            self.update_mapping()

    # ---------- Обработка дубликатов ----------
    def _is_empty_ref(self, value):
        return is_empty_ref(value)

    def find_duplicates(self, df, ref_col, sep):
        if df is None or ref_col not in df.columns:
            return {}
        sep_pattern = r'\s*' + re.escape(sep) + r'\s*'
        ref_list = []
        for idx, row in df.iterrows():
            if self._is_empty_ref(row[ref_col]):
                continue
            refs_str = str(row[ref_col]).strip()
            parts = re.split(sep_pattern, refs_str)
            for part in parts:
                part = part.strip()
                if part and not self._is_empty_ref(part):
                    ref_list.append((part, idx))
        grouped = defaultdict(list)
        for ref, idx in ref_list:
            grouped[ref].append(idx)
        return {ref: indices for ref, indices in grouped.items() if len(indices) > 1}

    def handle_duplicates(self, df, ref_col, sep, file_desc):
        duplicates = self.find_duplicates(df, ref_col, sep)
        if not duplicates:
            return df

        msg = f"В {file_desc} в столбце '{ref_col}' найдены дублирующиеся REF:\n\n"
        for ref, indices in duplicates.items():
            rows = ', '.join(str(i+1) for i in indices)
            msg += f"  {ref} → строки: {rows}\n"
        msg += "\nВыберите действие:"

        dialog = tk.Toplevel(self.parent)
        dialog.title("Обработка дубликатов")
        dialog.geometry("600x400")
        dialog.transient(self.parent)
        dialog.grab_set()

        text_frame = ttk.Frame(dialog)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        text_widget = tk.Text(text_frame, wrap=tk.WORD, height=15)
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        text_widget.insert(tk.END, msg)
        text_widget.config(state=tk.DISABLED)

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)

        result = {"action": None, "data": None}

        def on_ignore():
            new_df = df.copy()
            sep_pattern = r'\s*' + re.escape(sep) + r'\s*'
            for ref, indices in duplicates.items():
                rows_data = []
                for idx in indices:
                    if idx not in new_df.index:
                        continue
                    refs_str = str(new_df.at[idx, ref_col]) if pd.notna(new_df.at[idx, ref_col]) else ""
                    parts = re.split(sep_pattern, refs_str)
                    rows_data.append((idx, parts))
                for i, (idx, parts) in enumerate(rows_data):
                    if i == 0:
                        continue
                    new_parts = []
                    for p in parts:
                        p = p.strip()
                        if p == ref:
                            new_parts.append(f"{ref}_{i}")
                        else:
                            new_parts.append(p)
                    new_df.at[idx, ref_col] = sep.join(new_parts)
            result["action"] = "ignore"
            result["data"] = new_df
            dialog.destroy()

        def on_delete():
            delete_dialog = tk.Toplevel(dialog)
            delete_dialog.title("Выбор строки для сохранения REF")
            delete_dialog.geometry("700x500")
            delete_dialog.transient(dialog)
            delete_dialog.grab_set()

            ttk.Label(delete_dialog, text="Для каждого дублирующегося REF выберите строку, в которой этот REF должен остаться.\nВ остальных строках этот REF будет удалён (строка сохранится, если в ней есть другие REF).").pack(pady=10)

            main_frame = ttk.Frame(delete_dialog)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            canvas = tk.Canvas(main_frame)
            scrollbar2 = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
            scrollable_frame = ttk.Frame(canvas)

            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )

            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar2.set)

            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar2.pack(side=tk.RIGHT, fill=tk.Y)

            selected_indices = {}

            for ref, indices in duplicates.items():
                frame = ttk.LabelFrame(scrollable_frame, text=f"REF: {ref}", padding=5)
                frame.pack(fill=tk.X, padx=5, pady=5)

                var = tk.StringVar(value=str(indices[0]))
                selected_indices[ref] = var

                for idx in indices:
                    if idx not in df.index:
                        continue
                    row = df.loc[idx]
                    display_text = f"Строка {idx+1}: {ref}"
                    rb = ttk.Radiobutton(frame, text=display_text, variable=var, value=str(idx))
                    rb.pack(anchor=tk.W)

            def confirm_delete():
                try:
                    new_df = df.copy()
                    indices_to_drop = set()
                    sep_pattern = r'\s*' + re.escape(sep) + r'\s*'

                    for ref, var in selected_indices.items():
                        keep_idx = int(var.get())
                        idx_list = duplicates[ref]
                        for idx in idx_list:
                            if idx == keep_idx:
                                continue
                            if idx not in new_df.index:
                                continue
                            refs_str = str(new_df.at[idx, ref_col]) if pd.notna(new_df.at[idx, ref_col]) else ""
                            if refs_str:
                                parts = re.split(sep_pattern, refs_str)
                                new_parts = [p for p in parts if p.strip() != ref]
                                if new_parts:
                                    new_df.at[idx, ref_col] = sep.join(new_parts)
                                else:
                                    indices_to_drop.add(idx)
                            else:
                                indices_to_drop.add(idx)

                    if indices_to_drop:
                        new_df = new_df.drop(index=list(indices_to_drop)).reset_index(drop=True)

                    result["action"] = "delete"
                    result["data"] = new_df
                    delete_dialog.destroy()
                    dialog.destroy()
                except Exception as e:
                    err_msg = f"Ошибка при удалении дубликатов:\n{str(e)}\n\n{traceback.format_exc()}"
                    messagebox.showerror("Ошибка", err_msg, parent=self.parent)
                    delete_dialog.destroy()
                    dialog.destroy()
                    result["action"] = "cancel"

            ttk.Button(delete_dialog, text="Подтвердить", command=confirm_delete).pack(pady=10)
            ttk.Button(delete_dialog, text="Отмена", command=delete_dialog.destroy).pack(pady=5)

        def on_cancel():
            result["action"] = "cancel"
            dialog.destroy()

        ttk.Button(btn_frame, text="Игнорировать (переименовать дубликаты)", command=on_ignore).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить дубликаты", command=on_delete).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=on_cancel).pack(side=tk.LEFT, padx=5)

        self.parent.wait_window(dialog)

        if result["action"] == "cancel":
            return None
        elif result["action"] in ("ignore", "delete"):
            return result["data"]
        return df

    # ---------- Остальные методы ----------
    def browse_file(self, ftype):
        f = filedialog.askopenfilename(filetypes=[("All supported", "*.txt *.csv *.xlsx *.xls"), ("Text files", "*.txt *.csv"), ("Excel files", "*.xlsx *.xls")], parent=self.parent)
        if f:
            if ftype == 'old':
                self.old_file.set(f)
                self.load_file('old')
            else:
                self.new_file.set(f)
                self.load_file('new')

    def load_file(self, ftype):
        f = self.old_file.get() if ftype == 'old' else self.new_file.get()
        if not f or not os.path.exists(f):
            messagebox.showerror("Ошибка", "Файл не выбран или не существует.", parent=self.parent)
            return
        ext = os.path.splitext(f)[1].lower()
        header = 0 if (self.old_header.get() if ftype == 'old' else self.new_header.get()) else None

        try:
            if ext in ['.xlsx', '.xls']:
                df = pd.read_excel(f, engine='openpyxl', header=header, dtype=str)
            else:
                if ftype == 'old':
                    sep_mode = self.old_sep_mode.get()
                    custom_sep_val = self.old_custom_sep.get().strip()
                else:
                    sep_mode = self.new_sep_mode.get()
                    custom_sep_val = self.new_custom_sep.get().strip()

                if sep_mode == " ":
                    sep = r'\s+'
                    engine = 'python'
                elif sep_mode == "custom":
                    if custom_sep_val:
                        sep = custom_sep_val
                        engine = 'python'
                    else:
                        sep = ' '
                        engine = None
                else:
                    sep = self.old_sep.get() if ftype == 'old' else self.new_sep.get()
                    engine = None

                df = pd.read_csv(f, sep=sep, header=header, dtype=str, encoding='utf-8', engine=engine)

            if df.empty:
                messagebox.showerror("Ошибка", "Файл пуст.", parent=self.parent)
                return
            df.columns = [str(c) for c in df.columns]

            if ftype == 'old':
                self.df_old = df
                self.old_columns = df.columns.tolist()
                self.old_ref_cb['values'] = self.old_columns
                self.old_side_cb['values'] = self.old_columns
                self.update_compare_listbox()
                if self.old_side_col.get().strip():
                    self.update_side_combos('old')
                self.status_label.config(text=f"Старый PNP загружен: {len(df)} строк, {len(self.old_columns)} столбцов.")
            else:
                self.df_new = df
                self.new_columns = df.columns.tolist()
                self.new_ref_cb['values'] = self.new_columns
                self.new_side_cb['values'] = self.new_columns
                if self.new_side_col.get().strip():
                    self.update_side_combos('new')
                if self.btn_export_to_merge:
                    self.btn_export_to_merge.config(state='normal')
                self.status_label.config(text=f"Новый PNP загружен: {len(df)} строк, {len(self.new_columns)} столбцов.")

            self.update_mapping()
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e), parent=self.parent)

    def update_compare_listbox(self):
        if self.df_old is not None:
            self.compare_listbox.delete(0, tk.END)
            old_ref = self.old_ref_col.get()
            for col in self.old_columns:
                if col != old_ref:
                    self.compare_listbox.insert(tk.END, col)

    def on_ref_changed(self, event=None):
        self.update_compare_listbox()
        self.update_mapping()

    def add_selected_columns(self):
        selected = self.compare_listbox.curselection()
        if not selected:
            messagebox.showinfo("Информация", "Выберите столбцы из списка.", parent=self.parent)
            return
        existing = [entry['old_col'] for entry in self.mapping_entries]
        for idx in selected:
            col = self.compare_listbox.get(idx)
            if col not in existing:
                self.mapping_entries.append({'old_col': col})
        self.update_mapping()

    def update_mapping(self):
        if not hasattr(self, 'mapping_frame'):
            return
        for widget in self.mapping_frame.winfo_children():
            widget.destroy()

        for i, entry in enumerate(self.mapping_entries):
            old_col = entry['old_col']

            lbl = ttk.Label(self.mapping_frame, text=f"{old_col} →")
            lbl.grid(row=i, column=0, sticky=tk.W, pady=2)

            cb = ttk.Combobox(self.mapping_frame, values=self.new_columns, state="readonly", width=20)
            cb.grid(row=i, column=1, padx=5, pady=2)

            if old_col in self.new_columns:
                cb.set(old_col)
            else:
                for nc in self.new_columns:
                    if old_col.lower() in nc.lower() or nc.lower() in old_col.lower():
                        cb.set(nc)
                        break
            entry['new_col_cb'] = cb

            del_btn = ttk.Button(self.mapping_frame, text="✕", width=3,
                                 command=lambda idx=i: self.delete_mapping_entry(idx))
            del_btn.grid(row=i, column=2, padx=5, pady=2)

    def run_comparison(self):
        if self.df_old is None or self.df_new is None:
            messagebox.showerror("Ошибка", "Загрузите оба файла.", parent=self.parent)
            return
        old_ref = self.old_ref_col.get().strip()
        new_ref = self.new_ref_col.get().strip()
        if not old_ref or not new_ref:
            messagebox.showerror("Ошибка", "Выберите столбцы REF для обоих файлов.", parent=self.parent)
            return
        if not self.mapping_entries:
            messagebox.showerror("Ошибка", "Добавьте столбцы для сравнения.", parent=self.parent)
            return

        sep = self.ref_sep.get().strip() or ","

        new_old = self.handle_duplicates(self.df_old, old_ref, sep,
                                         f"старом файле '{os.path.basename(self.old_file.get())}'")
        if new_old is None:
            return
        self.df_old = new_old

        new_new = self.handle_duplicates(self.df_new, new_ref, sep,
                                         f"новом файле '{os.path.basename(self.new_file.get())}'")
        if new_new is None:
            return
        self.df_new = new_new

        map_dict = {}
        for entry in self.mapping_entries:
            cb = entry.get('new_col_cb')
            if cb is None:
                messagebox.showerror("Ошибка", f"Для столбца '{entry['old_col']}' не выбран столбец в новом файле.", parent=self.parent)
                return
            new_col = cb.get().strip()
            if not new_col:
                messagebox.showerror("Ошибка", f"Для столбца '{entry['old_col']}' не выбран столбец в новом файле.", parent=self.parent)
                return
            map_dict[entry['old_col']] = new_col

        use_side = not self.one_side.get()
        old_side_col = self.old_side_col.get().strip() if use_side else None
        new_side_col = self.new_side_col.get().strip() if use_side else None
        old_top = self.old_top_val.get().strip().lower()
        old_bottom = self.old_bottom_val.get().strip().lower()
        new_top = self.new_top_val.get().strip().lower()
        new_bottom = self.new_bottom_val.get().strip().lower()

        if use_side and (not old_side_col or not new_side_col):
            messagebox.showerror("Ошибка", "Для использования стороны выберите столбцы Side для обоих файлов.", parent=self.parent)
            return

        try:
            tol_xy = float(self.tol_xy.get())
            tol_r = float(self.tol_r.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Некорректное значение допуска.", parent=self.parent)
            return

        old_df = self.df_old.copy()
        new_df = self.df_new.copy()
        old_df[old_ref] = old_df[old_ref].astype(str).str.strip()
        new_df[new_ref] = new_df[new_ref].astype(str).str.strip()
        old_df = old_df[old_df[old_ref] != '']
        new_df = new_df[new_df[new_ref] != '']

        if use_side:
            old_df['_side_raw'] = old_df[old_side_col].astype(str).str.strip().str.lower()
            def normalize_old_side(val):
                if pd.isna(val):
                    s = ''
                else:
                    s = str(val).strip().lower()
                if s == old_top:
                    return 'top'
                elif s == old_bottom:
                    return 'bottom'
                else:
                    return s
            old_df['_side'] = old_df['_side_raw'].apply(normalize_old_side)

            new_df['_side_raw'] = new_df[new_side_col].astype(str).str.strip().str.lower()
            def normalize_new_side(val):
                if pd.isna(val):
                    s = ''
                else:
                    s = str(val).strip().lower()
                if s == new_top:
                    return 'top'
                elif s == new_bottom:
                    return 'bottom'
                else:
                    return s
            new_df['_side'] = new_df['_side_raw'].apply(normalize_new_side)

        old_dict = {}
        for idx, row in old_df.iterrows():
            ref = row[old_ref]
            old_dict[ref] = row

        new_dict = {}
        for idx, row in new_df.iterrows():
            ref = row[new_ref]
            new_dict[ref] = row

        all_refs = sorted(set(old_dict.keys()) | set(new_dict.keys()))
        results = []
        self.tol_xy_val = tol_xy
        self.tol_r_val = tol_r
        self.old_cols_order = list(map_dict.keys())
        self.use_side = use_side

        for ref in all_refs:
            old_row = old_dict.get(ref)
            new_row = new_dict.get(ref)
            if old_row is None:
                status = "Добавлен"
            elif new_row is None:
                status = "Удалён"
            else:
                status = "Не изменён"

            row_data = [ref, status]

            for old_col, new_col in map_dict.items():
                old_val = old_row[old_col] if old_row is not None else ""
                new_val = new_row[new_col] if new_row is not None else ""
                diff = ""
                try:
                    old_num = float(old_val)
                    new_num = float(new_val)
                    diff = new_num - old_num
                    if status == "Не изменён":
                        col_lower = old_col.lower()
                        if ('x' in col_lower or 'y' in col_lower) and abs(diff) > tol_xy:
                            status = "Изменён"
                        elif ('r' in col_lower or 'rotate' in col_lower) and abs(diff) > tol_r:
                            status = "Изменён"
                        else:
                            if abs(diff) > 1e-6:
                                status = "Изменён"
                except:
                    if str(old_val).strip() != str(new_val).strip():
                        if status == "Не изменён":
                            status = "Изменён"
                        diff = ""
                row_data.extend([old_val, new_val, diff])

            if use_side:
                old_side = old_row['_side'] if old_row is not None else ""
                new_side = new_row['_side'] if new_row is not None else ""
                if old_row is not None and new_row is not None:
                    if old_side != new_side and status == "Не изменён":
                        status = "Изменён"
                row_data.extend([old_side, new_side])

            row_data[1] = status
            results.append(row_data)

        headers = ["RefDes", "Статус"]
        for old_col in map_dict.keys():
            headers.extend([f"Старый {old_col}", f"Новый {old_col}", f"Δ{old_col}"])
        if use_side:
            headers.extend(["Старый Side", "Новый Side"])

        self.result_df = pd.DataFrame(results, columns=headers)
        self.all_data = results
        self.map_dict = map_dict
        self.filter_status.set("Все")

        self.tree['columns'] = headers
        for col in headers:
            self.tree.heading(col, text=col, command=lambda c=col: self.sort_treeview(c, False))
            self.tree.column(col, width=90, anchor=tk.CENTER)

        self.apply_filter()

        added = sum(1 for r in results if r[1] == "Добавлен")
        removed = sum(1 for r in results if r[1] == "Удалён")
        changed = sum(1 for r in results if r[1] == "Изменён")
        unchanged = sum(1 for r in results if r[1] == "Не изменён")
        self.status_label.config(text=f"Всего: {len(results)} | Добавлено: {added} | Удалено: {removed} | Изменено: {changed} | Без изменений: {unchanged}")
        messagebox.showinfo("Готово", f"Сравнение завершено.\nДобавлено: {added}\nУдалено: {removed}\nИзменено: {changed}", parent=self.parent)

    def apply_filter(self, event=None):
        filter_text = self.filter_status.get()
        if not self.all_data or not hasattr(self, 'old_cols_order'):
            if hasattr(self, 'tree_placeholder'):
                self.tree_placeholder.place(relx=0.5, rely=0.5, anchor="center")
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        if filter_text == "Все":
            data = self.all_data
        else:
            data = [row for row in self.all_data if row[1] == filter_text]

        if hasattr(self, 'tree_placeholder'):
            if data:
                self.tree_placeholder.place_forget()
            else:
                self.tree_placeholder.place(relx=0.5, rely=0.5, anchor="center")

        old_cols = self.old_cols_order
        n = len(old_cols)
        old_indices = []
        new_indices = []
        delta_indices = []
        for i in range(n):
            base = 2 + 3*i
            old_indices.append(base)
            new_indices.append(base+1)
            delta_indices.append(base+2)

        side_old_idx = None
        side_new_idx = None
        if self.use_side:
            side_old_idx = 2 + 3*n
            side_new_idx = 2 + 3*n + 1

        for row_idx, row in enumerate(data):
            display_row = []
            for idx, val in enumerate(row):
                if idx == 0 or idx == 1:
                    display_row.append(str(val))
                    continue

                is_old = idx in old_indices
                is_new = idx in new_indices
                is_delta = idx in delta_indices
                is_side_old = (side_old_idx is not None and idx == side_old_idx)
                is_side_new = (side_new_idx is not None and idx == side_new_idx)

                if is_old or is_new:
                    if is_old:
                        pair_idx = old_indices.index(idx)
                        old_idx_val = idx
                        new_idx_val = new_indices[pair_idx]
                    else:
                        pair_idx = new_indices.index(idx)
                        new_idx_val = idx
                        old_idx_val = old_indices[pair_idx]

                    old_val = row[old_idx_val]
                    new_val = row[new_idx_val]

                    changed = False
                    try:
                        old_num = float(old_val)
                        new_num = float(new_val)
                        col_name = old_cols[pair_idx].lower()
                        if ('x' in col_name or 'y' in col_name):
                            if abs(old_num - new_num) > self.tol_xy_val:
                                changed = True
                        elif ('r' in col_name or 'rotate' in col_name):
                            if abs(old_num - new_num) > self.tol_r_val:
                                changed = True
                        else:
                            if abs(old_num - new_num) > 1e-6:
                                changed = True
                    except:
                        if str(old_val).strip() != str(new_val).strip():
                            changed = True

                    if changed:
                        display_row.append(f"⚠ {val}")
                    else:
                        display_row.append(str(val))

                elif is_delta:
                    try:
                        num_val = float(val)
                        if abs(num_val) > 0.0001:
                            display_row.append(f"⚠ {num_val:.4f}")
                        else:
                            display_row.append(f"{num_val:.4f}")
                    except:
                        display_row.append(str(val))

                elif is_side_old or is_side_new:
                    display_row.append(str(val))

                else:
                    display_row.append(str(val))

            status = row[1]
            base_zebra = 'evenrow' if row_idx % 2 == 0 else 'oddrow'
            if status == "Изменён":
                tags = ('changed', base_zebra)
            elif status == "Добавлен":
                tags = ('added', base_zebra)
            elif status == "Удалён":
                tags = ('deleted', base_zebra)
            else:
                tags = (base_zebra,)

            self.tree.insert("", tk.END, values=display_row, tags=tags)

        if data:
            added = sum(1 for r in data if r[1] == "Добавлен")
            removed = sum(1 for r in data if r[1] == "Удалён")
            changed = sum(1 for r in data if r[1] == "Изменён")
            unchanged = sum(1 for r in data if r[1] == "Не изменён")
            self.status_label.config(text=f"Отфильтровано: {len(data)} | Добавлено: {added} | Удалено: {removed} | Изменено: {changed} | Без изменений: {unchanged}")
        else:
            self.status_label.config(text="Нет строк для отображения")

    def reset_filter(self):
        self.filter_status.set("Все")
        self.apply_filter()

    def sort_treeview(self, col, reverse):
        items = self.tree.get_children('')
        if not items:
            return
        data = [(self.tree.set(child, col), child) for child in items]
        try:
            data.sort(key=lambda x: float(x[0]), reverse=reverse)
        except ValueError:
            data.sort(key=lambda x: x[0].lower(), reverse=reverse)
        for index, (_, child) in enumerate(data):
            self.tree.move(child, '', index)
        self.tree.heading(col, command=lambda: self.sort_treeview(col, not reverse))

    def export_excel(self):
        if self.result_df is None:
            messagebox.showwarning("Предупреждение", "Сначала выполните сравнение.", parent=self.parent)
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")], parent=self.parent)
        if file_path:
            try:
                self.result_df.to_excel(file_path, index=False)
                messagebox.showinfo("Успех", f"Результат сохранён в {file_path}", parent=self.parent)
            except Exception as e:
                messagebox.showerror("Ошибка", str(e), parent=self.parent)

    def export_txt(self):
        if self.result_df is None:
            messagebox.showwarning("Предупреждение", "Сначала выполните сравнение.", parent=self.parent)
            return
        sep = self.get_separator_dialog()
        if sep is None:
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")], parent=self.parent)
        if file_path:
            try:
                self.result_df.to_csv(file_path, sep=sep, index=False, encoding='utf-8')
                messagebox.showinfo("Успех", f"Результат сохранён в {file_path}", parent=self.parent)
            except Exception as e:
                messagebox.showerror("Ошибка", str(e), parent=self.parent)

    def export_new_to_merge(self):
        if self.df_new is None:
            messagebox.showerror("Ошибка", "Сначала загрузите новый PNP файл.", parent=self.parent)
            return
        self.main_app.set_pnp_data(self.df_new, self.new_file.get())
        messagebox.showinfo("Успех", "Новый PnP загружен в объединитель.", parent=self.parent)

    def update_new_pnp_data(self, df, path):
        self.df_new = df
        self.new_file.set(path)
        self.new_columns = list(df.columns) if df is not None else []
        self.new_ref_cb['values'] = self.new_columns
        self.new_side_cb['values'] = self.new_columns
        self.update_mapping()
        if self.new_side_col.get().strip() and not self.one_side.get():
            self.update_side_combos('new')
        self.status_label.config(text=f"Новый PnP обновлён извне: {os.path.basename(path)}")

    def show_preview(self, df, file_type):
        if df is None or df.empty:
            messagebox.showinfo("Информация", f"Файл {file_type} не загружен или пуст.", parent=self.parent)
            return

        preview_window = create_styled_toplevel(self.parent, f"Предпросмотр {file_type}", "1250x750", min_size=(980, 580))

        frame = ttk.Frame(preview_window, padding="5")
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        cols = list(df.columns)
        tree = ttk.Treeview(frame, columns=cols, show="headings")
        tree.tag_configure('odd', background="#0e182e")
        tree.tag_configure('even', background="#131e36")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview, style="Horizontal.TScrollbar")
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=110, minwidth=80, anchor=tk.W)

        for idx, (_, row) in enumerate(df.head(100).iterrows()):
            values = [str(v) if pd.notna(v) else "" for v in row]
            tag = 'even' if idx % 2 == 0 else 'odd'
            tree.insert("", tk.END, values=values, tags=(tag,))

        btn_bar = ttk.Frame(preview_window, padding="5")
        btn_bar.pack(fill=tk.X, pady=5)
        ttk.Label(btn_bar, text=f"Показано {min(len(df), 100)} из {len(df)} строк, {len(cols)} колонок.",
                  foreground="gray").pack(side=tk.TOP, pady=2)
        ttk.Button(btn_bar, text="Закрыть", command=preview_window.destroy).pack(side=tk.BOTTOM, pady=4)

        style_widget_tree(preview_window, "dark")


# ==================== ВКЛАДКА: СВЕРКА BOM ====================
class CompareBOMTab(ttk.Frame):
    def __init__(self, parent, main_app):
        self.parent = parent
        self.main_app = main_app
        super().__init__(parent)

        # --- Прокручиваемая область ---
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_mousewheel(event):
            try:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Переменные
        self.file1 = tk.StringVar()
        self.file2 = tk.StringVar()
        self.df1 = None
        self.df2 = None
        self.sheets1 = []
        self.sheets2 = []
        self.cols1 = []
        self.cols2 = []

        self.file1_sheet = tk.StringVar()
        self.file2_sheet = tk.StringVar()
        self.col1_var = tk.StringVar()
        self.col2_var = tk.StringVar()

        # Для сравнения в одном файле
        self.one_file_mode = tk.BooleanVar(value=False)

        # Данные для сравнения и фильтрации
        self.comparison_data = []
        self.result_df = None
        self.filter_status = tk.StringVar(value="Все")

        self.create_widgets()

    def get_separator_dialog(self):
        t = THEMES["dark"]
        dialog = create_styled_toplevel(self.parent, "Выбор разделителя", "460x260", min_size=(420, 240))
        dialog.transient(self.parent)
        dialog.grab_set()

        content = tk.Frame(dialog, bg=t["bg_app"], padx=20, pady=16)
        content.pack(fill=tk.BOTH, expand=True)

        tk.Label(content, text="Выберите разделитель для формирования .TXT:",
                 font=("Segoe UI", 10, "bold"), bg=t["bg_app"], fg=t["text_header"]).pack(anchor="w", pady=(0, 8))

        card = tk.Frame(content, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=16, pady=12)
        card.pack(fill=tk.X, pady=(0, 12))

        sep_map = {
            "Табуляция (\\t)": "\t",
            "Пробел (␣)": " ",
            "Точка с запятой (;)": ";",
            "Запятая (,)": ",",
            "Вертикальная черта (|)": "|",
        }
        display_options = list(sep_map.keys()) + ["Свой символ..."]

        combo_var = tk.StringVar(value="Табуляция (\\t)")
        custom_var = tk.StringVar(value="")

        tk.Label(card, text="Стандартный разделитель:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).pack(anchor="w", pady=(0, 4))
        combo = ttk.Combobox(card, textvariable=combo_var, values=display_options, state="readonly", width=28, font=("Segoe UI", 9))
        combo.pack(fill=tk.X, pady=(0, 8))

        custom_box = tk.Frame(card, bg=t["bg_card"])
        custom_box.pack(fill=tk.X)

        tk.Label(custom_box, text="Свой разделитель:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_secondary"]).pack(side=tk.LEFT)
        custom_entry = ttk.Entry(custom_box, textvariable=custom_var, width=8, justify="center", state="disabled")
        custom_entry.pack(side=tk.LEFT, padx=8)

        hint_lbl = tk.Label(custom_box, text="(\\t - табуляция, \\s - пробел)", font=("Segoe UI", 8), bg=t["bg_card"], fg=t["text_muted"])
        hint_lbl.pack(side=tk.LEFT)

        def on_combo_change(event=None):
            if combo_var.get() == "Свой символ...":
                custom_entry.configure(state="normal")
                custom_entry.focus()
            else:
                custom_entry.configure(state="disabled")

        combo.bind("<<ComboboxSelected>>", on_combo_change)

        result = {"sep": None}

        def on_ok():
            choice = combo_var.get()
            if choice == "Свой символ...":
                c = custom_var.get()
                if c == r"\t":
                    result["sep"] = "\t"
                elif c in (r"\s", r"\p", "␣"):
                    result["sep"] = " "
                elif c:
                    result["sep"] = c
                else:
                    result["sep"] = "\t"
            else:
                result["sep"] = sep_map.get(choice, "\t")
            dialog.destroy()

        def on_cancel():
            result["sep"] = None
            dialog.destroy()

        dialog.bind("<Return>", lambda e: on_ok())
        dialog.bind("<Escape>", lambda e: on_cancel())

        btn_frame = tk.Frame(content, bg=t["bg_app"])
        btn_frame.pack(fill=tk.X)

        btn_ok = tk.Button(btn_frame, text="OK", command=on_ok,
                           bg=t["accent"], fg=t["accent_text"], activebackground=t["accent_hover"],
                           font=("Segoe UI", 9, "bold"), relief="flat", padx=20, pady=5, cursor="hand2")
        btn_ok.pack(side=tk.LEFT, padx=(0, 8))

        btn_cancel = tk.Button(btn_frame, text="Отмена", command=on_cancel,
                               bg=t["btn_sec_bg"], fg=t["btn_sec_fg"], activebackground=t["btn_sec_hover"],
                               font=("Segoe UI", 9), relief="flat", padx=16, pady=5, cursor="hand2")
        btn_cancel.pack(side=tk.LEFT)

        style_widget_tree(dialog, "dark")
        self.parent.wait_window(dialog)
        return result["sep"]

    def create_widgets(self):
        t = THEMES["dark"]
        main_frame = tk.Frame(self.scrollable_frame, bg=t["bg_app"], padx=8, pady=6)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # -------------------------------------------------------------
        # Верхняя панель: выбор файлов BOM 1 и BOM 2
        # -------------------------------------------------------------
        top_frame = tk.Frame(main_frame, bg=t["bg_app"])
        top_frame.pack(fill=tk.X, pady=(0, 8))
        top_frame.columnconfigure(0, weight=1)
        top_frame.columnconfigure(1, weight=1)
        top_frame.rowconfigure(0, weight=1)

        # Карточка BOM 1
        card1 = tk.Frame(top_frame, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=12, pady=10)
        card1.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=2)
        card1.columnconfigure(1, weight=1)

        tk.Label(card1, text="📁 Файл BOM 1", font=("Segoe UI", 10, "bold"),
                 bg=t["bg_card"], fg=t["accent"]).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

        tk.Label(card1, text="Файл:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=1, column=0, sticky="w", pady=4)
        entry1 = ttk.Entry(card1, textvariable=self.file1)
        entry1.grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        entry1.bind("<Return>", lambda e: self.load_file(1, self.file1.get()))
        btn_browse1 = ttk.Button(card1, text="Обзор...", command=lambda: self.browse_file(1))
        btn_browse1.grid(row=1, column=2, padx=2, pady=4)
        btn_view1 = ttk.Button(card1, text="👁️", width=3, command=lambda: self.show_preview(self.df1, "BOM 1"))
        btn_view1.grid(row=1, column=3, padx=2, pady=4)
        ToolTip(btn_view1, "Предпросмотр файла BOM 1")

        sheet_box1 = tk.Frame(card1, bg=t["bg_card"])
        sheet_box1.grid(row=2, column=0, columnspan=4, sticky="w", pady=(2, 2))
        tk.Label(sheet_box1, text="Лист:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_secondary"]).pack(side=tk.LEFT, padx=(0, 6))
        self.sheet1_cb = ttk.Combobox(sheet_box1, textvariable=self.file1_sheet, state="readonly", width=22, font=("Segoe UI", 9))
        self.sheet1_cb.pack(side=tk.LEFT)
        self.sheet1_cb.bind("<<ComboboxSelected>>", self.on_sheet1_selected)

        # Карточка BOM 2
        card2 = tk.Frame(top_frame, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=12, pady=10)
        card2.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=2)
        card2.columnconfigure(1, weight=1)

        tk.Label(card2, text="📁 Файл BOM 2", font=("Segoe UI", 10, "bold"),
                 bg=t["bg_card"], fg=t["accent"]).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

        tk.Label(card2, text="Файл:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=1, column=0, sticky="w", pady=4)
        self.entry2 = ttk.Entry(card2, textvariable=self.file2)
        self.entry2.grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        self.entry2.bind("<Return>", lambda e: self.load_file(2, self.file2.get()))
        self.btn_browse2 = ttk.Button(card2, text="Обзор...", command=lambda: self.browse_file(2))
        self.btn_browse2.grid(row=1, column=2, padx=2, pady=4)
        btn_view2 = ttk.Button(card2, text="👁️", width=3, command=lambda: self.show_preview(self.df2, "BOM 2"))
        btn_view2.grid(row=1, column=3, padx=2, pady=4)
        ToolTip(btn_view2, "Предпросмотр файла BOM 2")

        sheet_box2 = tk.Frame(card2, bg=t["bg_card"])
        sheet_box2.grid(row=2, column=0, columnspan=4, sticky="w", pady=(2, 2))
        tk.Label(sheet_box2, text="Лист:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_secondary"]).pack(side=tk.LEFT, padx=(0, 6))
        self.sheet2_cb = ttk.Combobox(sheet_box2, textvariable=self.file2_sheet, state="readonly", width=22, font=("Segoe UI", 9))
        self.sheet2_cb.pack(side=tk.LEFT)
        self.sheet2_cb.bind("<<ComboboxSelected>>", self.on_sheet2_selected)

        chk_one = ttk.Checkbutton(card2, text="Сравнивать в одном файле (BOM 2 как второй лист того же файла)",
                                  variable=self.one_file_mode, command=self.on_one_file_mode)
        chk_one.grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 2))

        # -------------------------------------------------------------
        # Настройка столбцов для сверки
        # -------------------------------------------------------------
        col_frame = tk.Frame(main_frame, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=14, pady=12)
        col_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(col_frame, text="⚙️ Выбор столбцов для сверки",
                 font=("Segoe UI", 10, "bold"), bg=t["bg_card"], fg=t["accent"]).pack(anchor="w", pady=(0, 8))

        cols_inner = tk.Frame(col_frame, bg=t["bg_card"])
        cols_inner.pack(fill=tk.X)

        tk.Label(cols_inner, text="Столбец из BOM 1:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=0, column=0, padx=(0, 6), pady=2, sticky=tk.W)
        self.col1_cb = ttk.Combobox(cols_inner, textvariable=self.col1_var, state="readonly", width=28, font=("Segoe UI", 9))
        self.col1_cb.grid(row=0, column=1, padx=(0, 24), pady=2, sticky=tk.W)
        self.col1_cb.bind("<<ComboboxSelected>>", self.on_col1_selected)

        tk.Label(cols_inner, text="Столбец из BOM 2:", font=("Segoe UI", 9), bg=t["bg_card"], fg=t["text_primary"]).grid(row=0, column=2, padx=(0, 6), pady=2, sticky=tk.W)
        self.col2_cb = ttk.Combobox(cols_inner, textvariable=self.col2_var, state="readonly", width=28, font=("Segoe UI", 9))
        self.col2_cb.grid(row=0, column=3, padx=(0, 10), pady=2, sticky=tk.W)
        self.col2_cb.bind("<<ComboboxSelected>>", self.on_col2_selected)

        # -------------------------------------------------------------
        # Кнопка запуска сверки
        # -------------------------------------------------------------
        action_bar = tk.Frame(main_frame, bg=t["bg_app"])
        action_bar.pack(fill=tk.X, pady=6)

        self.compare_btn = tk.Button(action_bar, text="🔍 Сверить столбцы BOM", command=self.run_compare,
                                     bg=t["accent"], fg="#ffffff", activebackground=t["accent_hover"], activeforeground="#ffffff",
                                     font=("Segoe UI", 11, "bold"), relief="flat", padx=28, pady=7, cursor="hand2")
        self.compare_btn.pack(anchor="center")

        # -------------------------------------------------------------
        # Карточка результатов сверки
        # -------------------------------------------------------------
        result_card = tk.Frame(main_frame, bg=t["bg_card"], highlightbackground=t["border"], highlightthickness=1, padx=14, pady=12)
        result_card.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        filter_bar = tk.Frame(result_card, bg=t["bg_card"])
        filter_bar.pack(fill=tk.X, pady=(0, 8))

        tk.Label(filter_bar, text="📋 Результаты сверки", font=("Segoe UI", 10, "bold"),
                 bg=t["bg_card"], fg=t["accent"]).pack(side=tk.LEFT)

        tk.Label(filter_bar, text="Фильтр по статусу:", font=("Segoe UI", 9),
                 bg=t["bg_card"], fg=t["text_secondary"]).pack(side=tk.LEFT, padx=(20, 6))
        self.filter_cb = ttk.Combobox(filter_bar, textvariable=self.filter_status,
                                      values=["Все", "Только изменённые", "Без изменений"],
                                      state="readonly", width=18, font=("Segoe UI", 9))
        self.filter_cb.pack(side=tk.LEFT, padx=(0, 6))
        self.filter_cb.bind("<<ComboboxSelected>>", self.apply_filter)

        btn_reset_filter = ttk.Button(filter_bar, text="Сбросить фильтр", command=self.reset_filter)
        btn_reset_filter.pack(side=tk.LEFT, padx=(0, 16))

        self.stats_label = tk.Label(filter_bar, text="Всего: 0 | Изменено: 0 | Без изменений: 0",
                                    font=("Segoe UI", 9, "bold"), bg=t["bg_card"], fg=t["text_muted"])
        self.stats_label.pack(side=tk.RIGHT)

        tree_container = tk.Frame(result_card, bg=t["bg_card"])
        tree_container.pack(fill=tk.BOTH, expand=True)

        columns = ("idx", "val1", "val2", "status", "diff")
        self.tree = ttk.Treeview(tree_container, columns=columns, show="headings", height=13)
        self.tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = ttk.Scrollbar(tree_container, orient=tk.HORIZONTAL, command=self.tree.xview)
        hsb.grid(row=1, column=0, sticky="ew")

        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        self.tree.heading("idx", text="№", command=lambda: self.sort_treeview("idx", False))
        self.tree.heading("val1", text="Значение в BOM 1", command=lambda: self.sort_treeview("val1", False))
        self.tree.heading("val2", text="Значение в BOM 2", command=lambda: self.sort_treeview("val2", False))
        self.tree.heading("status", text="Статус", command=lambda: self.sort_treeview("status", False))
        self.tree.heading("diff", text="Различие", command=lambda: self.sort_treeview("diff", False))

        self.tree.column("idx", width=55, anchor=tk.CENTER)
        self.tree.column("val1", width=200, anchor=tk.W)
        self.tree.column("val2", width=200, anchor=tk.W)
        self.tree.column("status", width=120, anchor=tk.CENTER)
        self.tree.column("diff", width=250, anchor=tk.W)

        self.tree.tag_configure('evenrow', background=t["row_even"])
        self.tree.tag_configure('oddrow', background=t["row_odd"])
        self.tree.tag_configure('changed', background="#451a03", foreground="#fde047")
        self.tree.tag_configure('unchanged', foreground="#6ee7b7")

        self.tree_placeholder = tk.Label(self.tree, text="Здесь появятся результаты сверки столбцов BOM.\nВыберите файлы и столбцы для сравнения, затем нажмите «Сверить столбцы BOM».",
                                         font=("Segoe UI", 10), bg=t["bg_card"], fg=t["text_muted"], justify="center")
        self.tree_placeholder.place(relx=0.5, rely=0.5, anchor="center")

        export_bar = tk.Frame(result_card, bg=t["bg_card"])
        export_bar.pack(fill=tk.X, pady=(10, 0))

        btn_exp_xls = tk.Button(export_bar, text="📥 Экспорт в Excel (.xlsx)", command=self.export_excel,
                                bg="#059669", fg="#ffffff", activebackground="#10b981", activeforeground="#ffffff",
                                font=("Segoe UI", 9, "bold"), relief="flat", padx=14, pady=5, cursor="hand2")
        btn_exp_xls.pack(side=tk.LEFT, padx=(0, 8))

        btn_exp_txt = tk.Button(export_bar, text="📥 Экспорт в TXT (.txt)", command=self.export_txt,
                                bg=t["accent"], fg="#ffffff", activebackground=t["accent_hover"], activeforeground="#ffffff",
                                font=("Segoe UI", 9, "bold"), relief="flat", padx=14, pady=5, cursor="hand2")
        btn_exp_txt.pack(side=tk.LEFT, padx=(0, 8))

        btn_modal_preview = tk.Button(export_bar, text="👁️ В отдельном окне", command=self.show_preview_comparison,
                                      bg=t["btn_sec_bg"], fg=t["btn_sec_fg"], activebackground=t["btn_sec_hover"],
                                      font=("Segoe UI", 9), relief="flat", padx=12, pady=5, cursor="hand2")
        btn_modal_preview.pack(side=tk.LEFT)
        ToolTip(btn_modal_preview, "Развернуть предпросмотр сравнения в отдельном окне")

        self.status_label = tk.Label(main_frame, text="Готов к работе", font=("Segoe UI", 9),
                                     bg=t["bg_app"], fg=t["text_muted"], anchor="w")
        self.status_label.pack(fill=tk.X, pady=(6, 2))

    # ---------- Методы загрузки ----------
    def browse_file(self, num):
        file_types = [
            ("All supported", "*.xlsx *.xls *.csv *.txt"),
            ("Excel files", "*.xlsx *.xls"),
            ("CSV & Text files", "*.csv *.txt"),
            ("All files", "*.*")
        ]
        f = filedialog.askopenfilename(filetypes=file_types, parent=self.parent)
        if f:
            if num == 1:
                self.file1.set(f)
                self.load_file(1, f)
            else:
                self.file2.set(f)
                self.load_file(2, f)

    def load_file(self, num, filepath=None):
        f = filepath or (self.file1.get() if num == 1 else self.file2.get())
        if not f or not os.path.exists(f):
            return
        ext = os.path.splitext(f)[1].lower()
        try:
            if ext in ['.xlsx', '.xls']:
                sheets_dict = pd.read_excel(f, sheet_name=None, dtype=str)
                sheets = list(sheets_dict.keys())
            else:
                sheets = ["Основной лист"]

            if num == 1:
                self.sheets1 = sheets
                self.sheet1_cb['values'] = sheets
                if sheets:
                    self.sheet1_cb.set(sheets[0])
                    self.on_sheet1_selected()
                if self.one_file_mode.get():
                    self.on_one_file_mode()
            else:
                self.sheets2 = sheets
                self.sheet2_cb['values'] = sheets
                if sheets:
                    self.sheet2_cb.set(sheets[0])
                    self.on_sheet2_selected()

            self.status_label.config(text=f"Загружен файл {num}: {os.path.basename(f)}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{str(e)}", parent=self.parent)

    def on_sheet1_selected(self, event=None):
        f = self.file1.get()
        sheet = self.file1_sheet.get()
        if f and os.path.exists(f):
            try:
                ext = os.path.splitext(f)[1].lower()
                if ext in ['.xlsx', '.xls']:
                    self.df1 = pd.read_excel(f, sheet_name=sheet, dtype=str)
                else:
                    self.df1 = pd.read_csv(f, sep=None, engine='python', dtype=str)
                self.cols1 = list(self.df1.columns)
                self.col1_cb['values'] = self.cols1
                if self.cols1 and (not self.col1_var.get() or self.col1_var.get() not in self.cols1):
                    self.col1_cb.set(self.cols1[0])
                self.status_label.config(text=f"BOM 1: загружен лист '{sheet}' ({len(self.df1)} строк, {len(self.cols1)} столбцов)")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось загрузить лист BOM 1:\n{str(e)}", parent=self.parent)

    def on_sheet2_selected(self, event=None):
        f = self.file1.get() if self.one_file_mode.get() else self.file2.get()
        sheet = self.file2_sheet.get()
        if f and os.path.exists(f):
            try:
                ext = os.path.splitext(f)[1].lower()
                if ext in ['.xlsx', '.xls']:
                    self.df2 = pd.read_excel(f, sheet_name=sheet, dtype=str)
                else:
                    self.df2 = pd.read_csv(f, sep=None, engine='python', dtype=str)
                self.cols2 = list(self.df2.columns)
                self.col2_cb['values'] = self.cols2
                if self.cols2 and (not self.col2_var.get() or self.col2_var.get() not in self.cols2):
                    self.col2_cb.set(self.cols2[0])
                self.status_label.config(text=f"BOM 2: загружен лист '{sheet}' ({len(self.df2)} строк, {len(self.cols2)} столбцов)")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось загрузить лист BOM 2:\n{str(e)}", parent=self.parent)

    def on_one_file_mode(self):
        if self.one_file_mode.get():
            self.file2.set(self.file1.get())
            self.entry2.config(state='disabled')
            self.btn_browse2.config(state='disabled')
            self.sheets2 = list(self.sheets1)
            self.sheet2_cb['values'] = self.sheets2
            if len(self.sheets2) > 1:
                self.sheet2_cb.set(self.sheets2[1])
            elif self.sheets2:
                self.sheet2_cb.set(self.sheets2[0])
            self.on_sheet2_selected()
            self.status_label.config(text="Режим одного файла: выберите лист для BOM 2")
        else:
            self.entry2.config(state='normal')
            self.btn_browse2.config(state='normal')
            self.file2.set('')
            self.sheet2_cb['values'] = []
            self.sheet2_cb.set('')
            self.df2 = None
            self.cols2 = []
            self.col2_cb['values'] = []
            self.col2_cb.set('')
            self.status_label.config(text="Режим двух файлов: выберите файл BOM 2")

    def on_col1_selected(self, event=None):
        pass

    def on_col2_selected(self, event=None):
        pass

    def _validate_inputs(self):
        if self.df1 is None:
            messagebox.showerror("Ошибка", "Файл BOM 1 не загружен.", parent=self.parent)
            return False
        if self.df2 is None:
            messagebox.showerror("Ошибка", "Файл BOM 2 не загружен.", parent=self.parent)
            return False
        col1 = self.col1_var.get()
        col2 = self.col2_var.get()
        if not col1 or col1 not in self.df1.columns:
            messagebox.showerror("Ошибка", "Не выбран столбец для BOM 1.", parent=self.parent)
            return False
        if not col2 or col2 not in self.df2.columns:
            messagebox.showerror("Ошибка", "Не выбран столбец для BOM 2.", parent=self.parent)
            return False
        return True

    def run_compare(self):
        if not self._validate_inputs():
            return
        col1 = self.col1_var.get()
        col2 = self.col2_var.get()
        df1 = self.df1.copy()
        df2 = self.df2.copy()

        df1[col1] = df1[col1].astype(str).str.strip().replace("nan", "")
        df2[col2] = df2[col2].astype(str).str.strip().replace("nan", "")

        n1 = len(df1)
        n2 = len(df2)
        max_len = max(n1, n2)

        self.comparison_data = []
        changed_count = 0
        unchanged_count = 0

        for i in range(max_len):
            v1 = df1[col1].iloc[i] if i < n1 else ""
            v2 = df2[col2].iloc[i] if i < n2 else ""
            if v1 == v2:
                status = "Без изменений"
                diff = "Совпадает"
                unchanged_count += 1
            else:
                status = "Изменено"
                diff = f"{v1} ➔ {v2}"
                changed_count += 1

            self.comparison_data.append({
                "idx": i + 1,
                "val1": v1,
                "val2": v2,
                "status": status,
                "diff": diff
            })

        # Формируем result_df для экспорта
        result_df = df1.copy()
        changes_full = []
        for i in range(len(result_df)):
            if i < len(self.comparison_data):
                changes_full.append(self.comparison_data[i]["diff"])
            else:
                changes_full.append("")
        result_df["Изменение_BOM"] = changes_full

        if n2 > n1:
            extra = df2.iloc[n1:].copy()
            for col in df2.columns:
                if col not in result_df.columns:
                    result_df[col] = None
            result_df = pd.concat([result_df, extra], ignore_index=True)
            for i in range(n1, n2):
                if i < len(self.comparison_data):
                    result_df.at[i, "Изменение_BOM"] = self.comparison_data[i]["diff"]

        self.result_df = result_df

        self.tree.heading("val1", text=f"BOM 1 ({col1})")
        self.tree.heading("val2", text=f"BOM 2 ({col2})")

        self.apply_filter()
        self.stats_label.config(text=f"Всего: {max_len} | Изменено: {changed_count} | Без изменений: {unchanged_count}")
        self.status_label.config(text=f"Сверка завершена: {max_len} строк. Изменено: {changed_count}, без изменений: {unchanged_count}.")

    def apply_filter(self, event=None):
        filter_text = self.filter_status.get()
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not self.comparison_data:
            self.tree_placeholder.place(relx=0.5, rely=0.5, anchor="center")
            return

        if filter_text == "Все":
            filtered = self.comparison_data
        elif filter_text == "Только изменённые":
            filtered = [r for r in self.comparison_data if r["status"] == "Изменено"]
        elif filter_text == "Без изменений":
            filtered = [r for r in self.comparison_data if r["status"] == "Без изменений"]
        else:
            filtered = self.comparison_data

        if filtered:
            self.tree_placeholder.place_forget()
        else:
            self.tree_placeholder.place(relx=0.5, rely=0.5, anchor="center")

        for row_idx, r in enumerate(filtered):
            base_zebra = 'evenrow' if row_idx % 2 == 0 else 'oddrow'
            if r["status"] == "Изменено":
                tags = ('changed', base_zebra)
            else:
                tags = ('unchanged', base_zebra)

            self.tree.insert("", tk.END, values=(r["idx"], r["val1"], r["val2"], r["status"], r["diff"]), tags=tags)

    def reset_filter(self):
        self.filter_status.set("Все")
        self.apply_filter()

    def sort_treeview(self, col, reverse):
        items = self.tree.get_children('')
        if not items:
            return
        data = [(self.tree.set(child, col), child) for child in items]
        try:
            data.sort(key=lambda x: float(x[0]), reverse=reverse)
        except ValueError:
            data.sort(key=lambda x: x[0].lower(), reverse=reverse)
        for index, (_, child) in enumerate(data):
            self.tree.move(child, '', index)
        self.tree.heading(col, command=lambda: self.sort_treeview(col, not reverse))

    def export_excel(self):
        if self.result_df is None:
            messagebox.showwarning("Предупреждение", "Сначала выполните сверку.", parent=self.parent)
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")],
                                                 initialfile="BOM_Compare_Result.xlsx", parent=self.parent)
        if file_path:
            try:
                self.result_df.to_excel(file_path, index=False)
                messagebox.showinfo("Успех", f"Результат сохранён в {file_path}", parent=self.parent)
            except Exception as e:
                messagebox.showerror("Ошибка", str(e), parent=self.parent)

    def export_txt(self):
        if self.result_df is None:
            messagebox.showwarning("Предупреждение", "Сначала выполните сверку.", parent=self.parent)
            return
        sep = self.get_separator_dialog()
        if sep is None:
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")],
                                                 initialfile="BOM_Compare_Result.txt", parent=self.parent)
        if file_path:
            try:
                self.result_df.to_csv(file_path, sep=sep, index=False, encoding='utf-8')
                messagebox.showinfo("Успех", f"Результат сохранён в {file_path}", parent=self.parent)
            except Exception as e:
                messagebox.showerror("Ошибка", str(e), parent=self.parent)

    def show_preview(self, df, title):
        if df is None or df.empty:
            messagebox.showinfo("Информация", f"{title} не загружен.", parent=self.parent)
            return
        preview_window = create_styled_toplevel(self.parent, f"Предпросмотр {title}", "1250x750", min_size=(980, 580))
        self._show_dataframe_preview(preview_window, df)

    def _show_dataframe_preview(self, parent, df):
        frame = ttk.Frame(parent, padding="5")
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        cols = list(df.columns)
        tree = ttk.Treeview(frame, columns=cols, show="headings")
        tree.tag_configure('odd', background="#0e182e")
        tree.tag_configure('even', background="#131e36")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview, style="Horizontal.TScrollbar")
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=110, minwidth=80, anchor=tk.W)
        for idx, (_, row) in enumerate(df.head(100).iterrows()):
            values = [str(v) if pd.notna(v) else "" for v in row]
            tag = 'even' if idx % 2 == 0 else 'odd'
            tree.insert("", tk.END, values=values, tags=(tag,))

        btn_bar = ttk.Frame(parent, padding="5")
        btn_bar.pack(fill=tk.X, pady=5)
        ttk.Label(btn_bar, text=f"Показано {min(len(df), 100)} из {len(df)} строк, {len(cols)} колонок.",
                  foreground="gray").pack(side=tk.TOP, pady=2)
        ttk.Button(btn_bar, text="Закрыть", command=parent.destroy).pack(side=tk.BOTTOM, pady=4)

        style_widget_tree(parent, "dark")

    def show_preview_comparison(self):
        if not self.comparison_data:
            if not self._validate_inputs():
                return
            self.run_compare()
            if not self.comparison_data:
                return

        col1 = self.col1_var.get()
        col2 = self.col2_var.get()

        preview_window = create_styled_toplevel(self.parent, "Предпросмотр сверки BOM", "1250x750", min_size=(980, 580))

        frame = ttk.Frame(preview_window, padding="5")
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        columns = ("№", f"BOM 1 ({col1})", f"BOM 2 ({col2})", "Статус", "Различие")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        tree.tag_configure('odd', background="#0e182e")
        tree.tag_configure('even', background="#131e36")
        tree.tag_configure('changed', background="#451a03", foreground="#fde047")
        tree.tag_configure('unchanged', foreground="#6ee7b7")

        tree.heading("№", text="№")
        tree.column("№", width=55, anchor=tk.CENTER)
        tree.heading(f"BOM 1 ({col1})", text=f"BOM 1 ({col1})")
        tree.column(f"BOM 1 ({col1})", width=220, anchor=tk.W)
        tree.heading(f"BOM 2 ({col2})", text=f"BOM 2 ({col2})")
        tree.column(f"BOM 2 ({col2})", width=220, anchor=tk.W)
        tree.heading("Статус", text="Статус")
        tree.column("Статус", width=120, anchor=tk.CENTER)
        tree.heading("Различие", text="Различие")
        tree.column("Различие", width=280, anchor=tk.W)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview, style="Horizontal.TScrollbar")
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        for r in self.comparison_data:
            tag = 'changed' if r["status"] == "Изменено" else 'unchanged'
            tree.insert("", tk.END, values=(r["idx"], r["val1"], r["val2"], r["status"], r["diff"]), tags=(tag,))

        btn_bar = ttk.Frame(preview_window, padding="5")
        btn_bar.pack(fill=tk.X, pady=5)
        ttk.Label(btn_bar, text=f"Всего строк: {len(self.comparison_data)}", foreground="gray").pack(side=tk.TOP, pady=2)
        ttk.Button(btn_bar, text="Закрыть", command=preview_window.destroy).pack(side=tk.BOTTOM, pady=4)

        style_widget_tree(preview_window, "dark")


# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()