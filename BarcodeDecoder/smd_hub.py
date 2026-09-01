#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smd_hub.py — Главный Лаунчер и Единая Интегрированная Среда подготовки монтажа SMD.
Экосистема объединяет:
1. Сквозной пошаговый мастер заказа (Master Workflow):
   - Шаг 1: Унификация BOM (нормализация наименований)
   - Шаг 2: Объединение P&P и BOM (автоматическая передача унифицированного BOM, привязка координат)
   - Шаг 3: Сверка P&P с BOM (автоматический предвыбор колонок, проверка DNP, нестыковок и экспорт)
2. Дополнительные сервисные инструменты (боковое меню):
   - Сравнение версий P&P
   - Сверка спецификаций BOM
   - Управление базой соответствий (database.txt)
   - Barcode Decoder (сканер/декодер катушек)
3. Единое ядро парсинга smd_engine (16 брендов, 2D токенизация, 0 Ом с погрешностью)
4. Дизайн-система с переключением тем (Dark/Light), всплывающими подсказками (Tooltips) и FAQ.
"""

import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd

# Добавляем пути к модулям экосистемы
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
    enable_smooth_mousewheel
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
# Главное окно SMD Hub
# =============================================================================
class SMDHubApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SMD Hub — Интегрированная среда подготовки монтажа SMD")
        self.root.geometry("1450x980")
        self.root.minsize(1200, 800)

        # Тема оформления
        self.current_theme = get_system_theme()
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

        self.current_step = 1

        # Построение интерфейса
        self._build_ui()
        self.apply_theme(self.current_theme)
        enable_smooth_mousewheel(self.root)

    def _setup_window_icon(self):
        icon_path = os.path.join(CURRENT_DIR, "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

    def apply_theme(self, theme_name: str):
        """Применяет тему ко всем элементам главного окна и подчинённых вкладок."""
        self.current_theme = theme_name
        t = THEMES[theme_name]
        self.root.configure(bg=t["bg_app"])
        set_window_titlebar_theme(self.root, t["is_dark"])
        apply_ttk_theme(self.style, theme_name)

        # Обновляем заголовок и панели
        if hasattr(self, 'header_frame'):
            self.header_frame.configure(bg=t["bg_card"])
            if hasattr(self, 'title_box'):
                self.title_box.configure(bg=t["bg_card"])
            if hasattr(self, 'btn_box'):
                self.btn_box.configure(bg=t["bg_card"])
            self.header_title.configure(bg=t["bg_card"], fg=t["text_primary"])
            self.header_subtitle.configure(bg=t["bg_card"], fg=t["text_muted"])
            self.btn_theme.configure(text="☀️ Светлая тема" if t["is_dark"] else "🌙 Тёмная тема",
                                     bg=t["btn_sec_bg"], fg=t["btn_sec_fg"])
            self.btn_faq.configure(bg=t["btn_sec_bg"], fg=t["btn_sec_fg"])
            self.btn_feedback.configure(bg=t["btn_sec_bg"], fg=t["btn_sec_fg"])

        if hasattr(self, 'main_body'):
            self.main_body.configure(bg=t["bg_app"])
        if hasattr(self, 'center_area'):
            self.center_area.configure(bg=t["bg_app"])

        # Обновляем панель шагов
        if hasattr(self, 'stepper_frame'):
            self.stepper_frame.configure(bg=t["bg_app"])
            self._update_stepper_visuals()

        # Обновляем боковое меню
        if hasattr(self, 'sidebar_frame'):
            self.sidebar_frame.configure(bg=t["bg_card"])
            self.sidebar_title.configure(bg=t["bg_card"], fg=t["accent"])
            for btn in self.sidebar_buttons:
                btn.configure(bg=t["btn_sec_bg"], fg=t["btn_sec_fg"])

        # Рекурсивно стилизуем все дочерние tk/ttk виджеты
        from smd_engine import style_widget_tree
        style_widget_tree(self.root, theme_name)

    def toggle_theme(self):
        new_theme = "light" if self.current_theme == "dark" else "dark"
        self.apply_theme(new_theme)

    # =========================================================================
    # Построение интерфейса
    # =========================================================================
    def _build_ui(self):
        t = THEMES[self.current_theme]

        # 1. Верхний современный Header
        self.header_frame = tk.Frame(self.root, height=64, padx=16, pady=10, bg=t["bg_card"])
        self.header_frame.pack(fill=tk.X, side=tk.TOP)

        self.title_box = tk.Frame(self.header_frame, bg=t["bg_card"])
        self.title_box.pack(side=tk.LEFT, fill=tk.Y)

        self.header_title = tk.Label(self.title_box, text="⚡ SMD Hub", font=("Segoe UI", 14, "bold"),
                                     bg=t["bg_card"], fg=t["text_primary"])
        self.header_title.pack(anchor="w")

        self.header_subtitle = tk.Label(
            self.title_box,
            text="Сквозная подготовка заказа: Унификация BOM ➔ Объединение P&P ➔ Сверка и Контроль",
            font=("Segoe UI", 9),
            bg=t["bg_card"],
            fg=t["text_muted"]
        )
        self.header_subtitle.pack(anchor="w")

        # Кнопки в шапке (справа)
        self.btn_box = tk.Frame(self.header_frame, bg=t["bg_card"])
        self.btn_box.pack(side=tk.RIGHT, fill=tk.Y)

        self.btn_theme = tk.Button(self.btn_box, font=("Segoe UI", 9), relief="flat", padx=10, pady=4,
                                   bg=t["btn_sec_bg"], fg=t["btn_sec_fg"],
                                   cursor="hand2", command=self.toggle_theme)
        self.btn_theme.pack(side=tk.LEFT, padx=4)
        ToolTip(self.btn_theme, "Переключение между тёмной и светлой темой оформления")

        self.btn_faq = tk.Button(self.btn_box, text="📖 Инструкция и FAQ", font=("Segoe UI", 9),
                                 bg=t["btn_sec_bg"], fg=t["btn_sec_fg"],
                                 relief="flat", padx=10, pady=4, cursor="hand2",
                                 command=lambda: show_faq_dialog(self.root, self.current_theme))
        self.btn_faq.pack(side=tk.LEFT, padx=4)
        ToolTip(self.btn_faq, "Открыть подробное пошаговое руководство оператора и ответы на вопросы")

        self.btn_feedback = tk.Button(self.btn_box, text="✉️ Написать автору", font=("Segoe UI", 9),
                                      bg=t["btn_sec_bg"], fg=t["btn_sec_fg"],
                                      relief="flat", padx=10, pady=4, cursor="hand2",
                                      command=lambda: show_feedback_dialog(self.root, self.current_theme))
        self.btn_feedback.pack(side=tk.LEFT, padx=4)
        ToolTip(self.btn_feedback, "Связаться с разработчиком (kean5782@yandex.ru)")

        # 2. Главная горизонтальная область (Боковое меню + Основной контент)
        self.main_body = tk.Frame(self.root, bg=t["bg_app"])
        self.main_body.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # Боковая панель сервисных утилит (Secondary Tools)
        self._build_sidebar(self.main_body)

        # Центральная рабочая зона мастера заказа (Master Stepper Wizard)
        self.center_area = tk.Frame(self.main_body, bg=t["bg_app"])
        self.center_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))

        # 3. Интерактивный Степпер (Timeline)
        self._build_stepper(self.center_area)

        # 4. Основной контейнер шагов (с скрытыми вкладками, управляемый степпером)
        self.wizard_notebook = ttk.Notebook(self.center_area, style="Hidden.TNotebook")
        self.wizard_notebook.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        self._build_step1_unification(self.wizard_notebook)
        self._build_step2_merge(self.wizard_notebook)
        self._build_step3_check(self.wizard_notebook)

        self.wizard_notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    # =========================================================================
    # Боковая панель сервисных утилит
    # =========================================================================
    def _build_sidebar(self, parent):
        t = THEMES[self.current_theme]
        self.sidebar_frame = tk.Frame(parent, width=260, padx=12, pady=12, bg=t["bg_card"])
        self.sidebar_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar_frame.pack_propagate(False)

        self.sidebar_title = tk.Label(self.sidebar_frame, text="🛠️ ДОП. СЕРВИСЫ", font=("Segoe UI", 9, "bold"),
                                      bg=t["bg_card"], fg=t["accent"])
        self.sidebar_title.pack(anchor="w", pady=(0, 10))

        self.sidebar_buttons = []

        services = [
            ("🔄 Сравнить P&P версии", self.open_compare_pnp, "Сравнить две ревизии файла координат P&P"),
            ("🔄 Сверить BOM версии", self.open_compare_bom, "Сравнить две версии спецификаций BOM"),
            ("🗄️ База соответствий", self.open_db_manager, "Открыть справочник пользовательских названий (database.txt)"),
            ("📷 Barcode Decoder", self.open_barcode_decoder, "Запустить сканер и декодер штрихкодов катушек")
        ]

        for text, cmd, tip in services:
            btn = tk.Button(self.sidebar_frame, text=text, font=("Segoe UI", 9),
                            bg=t["btn_sec_bg"], fg=t["btn_sec_fg"],
                            relief="flat", anchor="w", padx=12, pady=8, cursor="hand2", command=cmd)
            btn.pack(fill=tk.X, pady=4)
            ToolTip(btn, tip)
            self.sidebar_buttons.append(btn)

        # Информационная плашка
        info_box = tk.Frame(self.sidebar_frame, bg=t["bg_card_inner"], padx=8, pady=8,
                            highlightbackground=t["border"], highlightthickness=1)
        info_box.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Label(info_box, text="💡 Совет оператора:", font=("Segoe UI", 8, "bold"),
                 bg=t["bg_card_inner"], fg=t["accent"]).pack(anchor="w")
        tk.Label(info_box, text="Для нового заказа выполняйте Шаги 1, 2 и 3 последовательно. Файлы передаются автоматически.",
                 font=("Segoe UI", 8), bg=t["bg_card_inner"], fg=t["text_secondary"], justify=tk.LEFT, wraplength=180).pack(anchor="w", pady=(2, 0))

    # =========================================================================
    # Интерактивный Степпер (Шаги 1 -> 2 -> 3)
    # =========================================================================
    def _build_stepper(self, parent):
        t = THEMES[self.current_theme]
        self.stepper_frame = tk.Frame(parent, height=44, padx=5, pady=4, bg=t["bg_app"])
        self.stepper_frame.pack(fill=tk.X)

        self.step_buttons = []
        steps = [
            ("1. 🗂️ Унификация BOM", 0, "Шаг 1: Приведение названий компонентов в BOM к стандарту склада"),
            ("2. ⚙️ Объединение P&P + BOM", 1, "Шаг 2: Сшивание координат монтажа с унифицированным BOM"),
            ("3. 🔍 Финальная Сверка", 2, "Шаг 3: Проверка DNP, нестыковок и получение готового отчета")
        ]

        for text, idx, tip in steps:
            btn = tk.Button(self.stepper_frame, text=text, font=("Segoe UI", 9, "bold"),
                            relief="flat", padx=14, pady=6, cursor="hand2",
                            command=lambda i=idx: self.go_to_step(i))
            btn.pack(side=tk.LEFT, padx=5)
            ToolTip(btn, tip)
            self.step_buttons.append(btn)

    def _update_stepper_visuals(self):
        t = THEMES[self.current_theme]
        for idx, btn in enumerate(self.step_buttons):
            if idx == self.current_step:
                btn.configure(bg=t["accent"], fg=t["accent_text"], relief="solid", bd=1)
            else:
                btn.configure(bg=t["btn_sec_bg"], fg=t["btn_sec_fg"], relief="flat", bd=0)

    def go_to_step(self, step_index: int):
        self.current_step = step_index
        self.wizard_notebook.select(step_index)
        self._update_stepper_visuals()

    def _on_tab_changed(self, event):
        selected_idx = self.wizard_notebook.index(self.wizard_notebook.select())
        self.current_step = selected_idx
        self._update_stepper_visuals()

    # =========================================================================
    # Шаг 1: Унификация BOM
    # =========================================================================
    def _build_step1_unification(self, notebook):
        self.step1_frame = ttk.Frame(notebook)
        notebook.add(self.step1_frame, text="Шаг 1: Унификация BOM")

        # Внутренний notebook для унификации по коду / описанию
        self.unify_notebook = ttk.Notebook(self.step1_frame)
        self.unify_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        if DescriptionTab and self.db_manager:
            self.desc_tab = DescriptionTab(self.unify_notebook, self.db_manager)
            self.unify_notebook.add(self.desc_tab, text="📝 По описанию (русские параметры)")
            # Перехват сохранения для автопередачи в Шаг 2
            self._patch_unification_save(self.desc_tab, "Description")

        if CodeTab and self.db_manager:
            self.code_tab = CodeTab(self.unify_notebook, self.db_manager)
            self.unify_notebook.add(self.code_tab, text="🔢 По коду (Samsung, Yageo, Murata...)")
            self._patch_unification_save(self.code_tab, "Code")

        # Нижняя панель перехода к Шагу 2
        bottom_bar = tk.Frame(self.step1_frame, pady=8)
        bottom_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.btn_step1_next = tk.Button(
            bottom_bar,
            text="✅ Готово: Перейти к Объединению P&P (Шаг 2) ➔",
            font=("Segoe UI", 10, "bold"),
            bg="#2563eb", fg="#ffffff", padx=16, pady=8, relief="flat", cursor="hand2",
            command=self.complete_step1_and_go_step2
        )
        self.btn_step1_next.pack(side=tk.RIGHT, padx=10)
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
                # Автоматически передаем в Шаг 2
                self.merge_tab.bom_file.set(self.unified_bom_path)
                self.merge_tab.load_bom()
                # Предвыбираем столбец с унифицированным именем
                for col in self.merge_tab.bom_columns:
                    if "унифиц" in col.lower() or "unified" in col.lower() or "part" in col.lower():
                        self.merge_tab.bom_data_cb.set(col)
                        break

        self.go_to_step(1)

    # =========================================================================
    # Шаг 2: Объединение P&P + BOM
    # =========================================================================
    def _build_step2_merge(self, notebook):
        self.step2_frame = ttk.Frame(notebook)
        notebook.add(self.step2_frame, text="Шаг 2: Объединение P&P + BOM")

        if MergeTab:
            self.merge_tab = MergeTab(self.step2_frame, self)
            self.merge_tab.pack(fill=tk.BOTH, expand=True)

            # Перехват сохранения объединенного файла
            orig_merge_save = self.merge_tab.save_bom_settings
            # Добавляем большую кнопку перехода к Шагу 3 внизу MergeTab
            next_btn_frame = tk.Frame(self.step2_frame, pady=8)
            next_btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

            btn_step2_next = tk.Button(
                next_btn_frame,
                text="✅ Сформировать и перейти к Сверке (Шаг 3) ➔",
                font=("Segoe UI", 10, "bold"),
                bg="#2563eb", fg="#ffffff", padx=16, pady=8, relief="flat", cursor="hand2",
                command=self.complete_step2_and_go_step3
            )
            btn_step2_next.pack(side=tk.RIGHT, padx=10)
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
                # Если результат еще не сгенерирован, пробуем объединить
                try:
                    self.merge_tab.merge_data()
                except Exception as e:
                    messagebox.showerror("Ошибка объединения", f"Не удалось объединить P&P и BOM:\n{e}")
                    return

            if self.merge_tab.result_df is not None and hasattr(self, 'check_tab') and self.check_tab:
                # Передаем объединенный датафрейм в сверку
                self.check_tab.update_pnp_data(self.merge_tab.result_df, "Merged_PnP_Output")
                if self.merge_tab.bom_df is not None:
                    self.check_tab.update_bom_data(self.merge_tab.bom_df, self.merge_tab.bom_file.get())

        self.go_to_step(2)

    # =========================================================================
    # Шаг 3: Финальная Сверка P&P с BOM
    # =========================================================================
    def _build_step3_check(self, notebook):
        self.step3_frame = ttk.Frame(notebook)
        notebook.add(self.step3_frame, text="Шаг 3: Сверка P&P с BOM")

        if CheckTab:
            self.check_tab = CheckTab(self.step3_frame, self)
            self.check_tab.pack(fill=tk.BOTH, expand=True)

    # =========================================================================
    # Сервисные диалоги (Secondary Tools)
    # =========================================================================
    def open_compare_pnp(self):
        win = tk.Toplevel(self.root)
        win.title("🔄 Сравнение версий P&P")
        win.geometry("1250x850")
        set_window_titlebar_theme(win, THEMES[self.current_theme]["is_dark"])
        if CompareTab:
            tab = CompareTab(win, self)
            tab.pack(fill=tk.BOTH, expand=True)
            style_widget_tree(win, self.current_theme)
            enable_smooth_mousewheel(win)

    def open_compare_bom(self):
        win = tk.Toplevel(self.root)
        win.title("🔄 Сверка спецификаций BOM")
        win.geometry("1250x850")
        set_window_titlebar_theme(win, THEMES[self.current_theme]["is_dark"])
        if CompareBOMTab:
            tab = CompareBOMTab(win, self)
            tab.pack(fill=tk.BOTH, expand=True)
            style_widget_tree(win, self.current_theme)
            enable_smooth_mousewheel(win)

    def open_db_manager(self):
        win = tk.Toplevel(self.root)
        win.title("🗄️ Управление базой соответствий (database.txt)")
        win.geometry("1150x760")
        set_window_titlebar_theme(win, THEMES[self.current_theme]["is_dark"])
        if DatabaseTab and self.db_manager:
            tab = DatabaseTab(win, self.db_manager)
            tab.pack(fill=tk.BOTH, expand=True)
            style_widget_tree(win, self.current_theme)
            enable_smooth_mousewheel(win)

    def open_barcode_decoder(self):
        try:
            import importlib.util
            barcode_script = os.path.join(CURRENT_DIR, "BarcodeDecoder_1.1.py")
            if not os.path.exists(barcode_script):
                barcode_script = os.path.join(os.path.dirname(__file__), "BarcodeDecoder_1.1.py")
            if os.path.exists(barcode_script):
                spec = importlib.util.spec_from_file_location("barcode_module", barcode_script)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                win = create_styled_toplevel(self.root, "📷 Barcode Decoder v1.1", "1040x820", self.current_theme)
                app = mod.BarcodeDecoderApp(win)
                style_widget_tree(win, self.current_theme)
                enable_smooth_mousewheel(win)
                return
        except Exception as e:
            print(f"Error opening BarcodeDecoder: {e}")
        messagebox.showinfo("Barcode Decoder", "Модуль Barcode Decoder доступен в корневом каталоге.")


# =============================================================================
# Запуск приложения
# =============================================================================
def main():
    root = tk.Tk()
    app = SMDHubApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
