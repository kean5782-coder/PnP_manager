import os
import sys
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
import re

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
for p in (PARENT_DIR, CURRENT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import smd_engine
from smd_engine import (
    THEMES, ToolTip, get_system_theme, set_window_titlebar_theme,
    apply_ttk_theme, show_feedback_dialog, show_faq_dialog,
    style_widget_tree, create_styled_toplevel, enable_smooth_mousewheel,
    VendorRule, VendorParser, format_g
)

# =============================================================================
# Класс для управления базой данных пользовательских названий
# =============================================================================
class DatabaseManager:
    def __init__(self, filename="database.txt"):
        self.filename = filename
        self.backup_filename = filename + ".bak"
        self.data = {}  # key -> user_name
        self.load()

    def load(self):
        """Загружает базу из текстового файла с разделителем табуляции.
           Поддерживает восстановление при ошибках формата."""
        if not os.path.exists(self.filename):
            self.data = {}
            self.save()
            return

        # Пытаемся прочитать файл
        raw_lines = []
        errors = []
        valid_data = {}
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                raw_lines = f.readlines()
        except Exception as e:
            # Если файл не читается, пробуем восстановить из бэкапа
            if os.path.exists(self.backup_filename):
                if self._ask_restore_backup():
                    shutil.copy2(self.backup_filename, self.filename)
                    self.load()  # повторная загрузка
                    return
            self.data = {}
            self.save()
            return

        # Парсим строки
        line_errors = []
        for line_num, line in enumerate(raw_lines, 1):
            line = line.rstrip('\n\r')
            if not line.strip():
                continue  # пустые строки игнорируем
            parts = line.split('\t')
            if len(parts) == 2:
                key, value = parts
                if key.strip() and value.strip():
                    valid_data[key.strip()] = value.strip()
                else:
                    line_errors.append(f"Строка {line_num}: пустой ключ или значение")
            elif len(parts) > 2:
                # Лишние табуляции – объединяем всё после первой табуляции в значение
                key = parts[0].strip()
                value = '\t'.join(parts[1:]).strip()
                if key and value:
                    valid_data[key] = value
                    line_errors.append(f"Строка {line_num}: обнаружена лишняя табуляция (исправлено автоматически)")
                else:
                    line_errors.append(f"Строка {line_num}: некорректный формат (пропущена)")
            else:
                line_errors.append(f"Строка {line_num}: нет разделителя (пропущена)")

        # Если есть ошибки, предлагаем пользователю восстановить
        if line_errors:
            error_msg = "Обнаружены проблемы в файле базы данных:\n" + "\n".join(line_errors[:5])
            if len(line_errors) > 5:
                error_msg += f"\n... и ещё {len(line_errors) - 5} ошибок"
            error_msg += "\n\nХотите автоматически исправить базу (будут сохранены только корректные записи)?"

            from tkinter import messagebox
            if messagebox.askyesno("Восстановление базы данных", error_msg):
                self.data = valid_data
                self.save()
                # Создаём бэкап старого файла
                if os.path.exists(self.filename):
                    shutil.copy2(self.filename, self.backup_filename)
                messagebox.showinfo("Успех", "База данных восстановлена. Некорректные строки удалены.")
            else:
                # Пользователь отказался – загружаем только валидные данные
                self.data = valid_data
                # Но не сохраняем, чтобы пользователь мог вручную править
                messagebox.showwarning("Предупреждение", "Некорректные строки сохранены в файле, но программа будет использовать только валидные записи.")
        else:
            self.data = valid_data

    def save(self):
        """Сохраняет базу в текстовый файл с разделителем табуляции."""
        # Создаём резервную копию перед сохранением
        if os.path.exists(self.filename):
            try:
                shutil.copy2(self.filename, self.backup_filename)
            except:
                pass

        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                for key, value in self.data.items():
                    # Заменяем переносы строк и табуляции внутри значений, чтобы не ломать структуру
                    clean_key = key.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')
                    clean_value = value.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')
                    f.write(f"{clean_key}\t{clean_value}\n")
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Ошибка", f"Не удалось сохранить базу данных:\n{e}")
            # Пытаемся сохранить в резервный файл
            try:
                with open("database_emergency.txt", 'w', encoding='utf-8') as f:
                    for key, value in self.data.items():
                        f.write(f"{key}\t{value}\n")
                messagebox.showinfo("Информация", "Данные сохранены в database_emergency.txt")
            except:
                pass

    def _ask_restore_backup(self):
        """Спрашивает пользователя, восстановить ли базу из бэкапа."""
        from tkinter import messagebox
        return messagebox.askyesno(
            "Восстановление из резервной копии",
            f"Файл базы данных повреждён. Найден резервный файл {self.backup_filename}.\n"
            "Восстановить из него?"
        )

    # --- Остальные методы без изменений ---
    def add_or_update(self, key, value):
        self.data[key] = value
        self.save()

    def delete(self, key):
        if key in self.data:
            del self.data[key]
            self.save()

    def get(self, key):
        return self.data.get(key)

    def contains(self, key):
        return key in self.data

    def get_all(self):
        return list(self.data.items())

    def add_multiple(self, items, overwrite=False):
        added = []
        skipped = []
        for key, value in items:
            if key in self.data:
                if overwrite:
                    self.data[key] = value
                    added.append(key)
                else:
                    skipped.append(key)
            else:
                self.data[key] = value
                added.append(key)
        self.save()
        return added, skipped




# =============================================================================
# НОВОЕ: вкладка "База данных"
# =============================================================================
class DatabaseTab(ttk.Frame):
    def __init__(self, parent, db_manager):
        super().__init__(parent)
        self.db_manager = db_manager
        self.df = None          # исходные данные из файла
        self.edited_df = None   # редактируемая копия
        self.file_path = None
        self.selected_sheet = None
        self.key_column = None
        self.value_column = None
        self.selected_indices = []
        self.preview_window = None
        self.create_widgets()
        self.refresh_tree()

    def create_widgets(self):
        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        v_scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview, style="Vertical.TScrollbar")
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.configure(yscrollcommand=v_scroll.set)

        main_frame = ttk.Frame(canvas, padding="10")
        self.canvas_window = canvas.create_window((0, 0), window=main_frame, anchor='nw')
        main_frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(self.canvas_window, width=e.width))

        # Таблица базы данных
        tree_frame = ttk.LabelFrame(main_frame, text="🗄️ База данных соответствий", padding="8")
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ("key", "value")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=12, selectmode='extended')
        self.tree.tag_configure('odd', background="#232428")
        self.tree.tag_configure('even', background="#2b2d31")
        self.tree.heading("key", text="Название в BOM")
        self.tree.heading("value", text="Пользовательское название")
        self.tree.column("key", width=250, stretch=True)
        self.tree.column("value", width=250, stretch=True)

        scroll_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview, style="Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # Кнопки управления
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        ttk.Button(btn_frame, text="➕ Добавить вручную", command=self.add_manual).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="✏️ Редактировать", command=self.edit_selected).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="🗑️ Удалить", command=self.delete_selected).pack(side=tk.LEFT, padx=3)

        # Загрузка из BOM
        bom_frame = ttk.LabelFrame(main_frame, text="📥 Импорт соответствий из файла BOM", padding="10")
        bom_frame.pack(fill=tk.X, pady=8)
        bom_frame.columnconfigure(1, weight=1)

        ttk.Button(bom_frame, text="📂 Открыть BOM", command=self.load_bom_file).grid(row=0, column=0, padx=4, pady=4, sticky='w')
        self.file_path_var = tk.StringVar()
        path_entry = ttk.Entry(bom_frame, textvariable=self.file_path_var)
        path_entry.grid(row=0, column=1, padx=4, pady=4, sticky='ew')
        ttk.Button(bom_frame, text="📝 Подготовка документа и импорт", style="Accent.TButton", command=self.show_bom_editor).grid(row=0, column=2, padx=4, pady=4, sticky='e')

        row1_frame = ttk.Frame(bom_frame)
        row1_frame.grid(row=1, column=0, columnspan=3, sticky='w', pady=(4, 2))
        ttk.Label(row1_frame, text="Лист в файле:").pack(side=tk.LEFT, padx=(0, 5))
        self.sheet_cb = ttk.Combobox(row1_frame, state="readonly", width=22)
        self.sheet_cb.pack(side=tk.LEFT, padx=5)
        self.sheet_cb.bind("<<ComboboxSelected>>", self.on_sheet_selected)

        ttk.Label(row1_frame, text="💡 Выбор столбцов, цветовая подсветка и импорт производятся в окне подготовки документа.",
                  foreground="gray").pack(side=tk.LEFT, padx=12)

        self.key_col_cb = ttk.Combobox(bom_frame, state="readonly", width=20)
        self.value_col_cb = ttk.Combobox(bom_frame, state="readonly", width=20)

        self.info_label = ttk.Label(main_frame, text="Всего записей: 0", foreground="gray")
        self.info_label.pack(pady=4)

    def refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for idx, (key, value) in enumerate(self.db_manager.get_all()):
            tag = 'even' if idx % 2 == 0 else 'odd'
            self.tree.insert("", tk.END, values=(key, value), tags=(tag,))
        self.info_label.config(text=f"Всего записей: {len(self.db_manager.data)}")

    def add_manual(self):
        dialog = create_styled_toplevel(self, "Добавить запись в базу", "460x190")
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding="15")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Название в BOM:").grid(row=0, column=0, padx=5, pady=6, sticky=tk.W)
        key_entry = ttk.Entry(frame, width=32)
        key_entry.grid(row=0, column=1, padx=5, pady=6)
        key_entry.focus()

        ttk.Label(frame, text="Пользовательское название:").grid(row=1, column=0, padx=5, pady=6, sticky=tk.W)
        value_entry = ttk.Entry(frame, width=32)
        value_entry.grid(row=1, column=1, padx=5, pady=6)

        def on_save():
            key = key_entry.get().strip()
            value = value_entry.get().strip()
            if not key or not value:
                messagebox.showerror("Ошибка", "Оба поля должны быть заполнены.", parent=dialog)
                return
            if self.db_manager.contains(key):
                if not messagebox.askyesno("Дубликат", f"Запись с ключом '{key}' уже существует. Перезаписать?", parent=dialog):
                    return
            self.db_manager.add_or_update(key, value)
            self.refresh_tree()
            dialog.destroy()

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=2, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btn_row, text="💾 Сохранить", style="Accent.TButton", command=on_save).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_row, text="Отмена", command=dialog.destroy).pack(side=tk.LEFT, padx=6)

        style_widget_tree(dialog, "dark")

    def edit_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Информация", "Выберите запись для редактирования.")
            return
        item = selection[0]
        key, value = self.tree.item(item, 'values')
        if not key:
            return

        dialog = create_styled_toplevel(self, "Редактировать запись базы", "460x190")
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding="15")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Название в BOM (ключ):").grid(row=0, column=0, padx=5, pady=6, sticky=tk.W)
        key_entry = ttk.Entry(frame, width=32)
        key_entry.insert(0, key)
        key_entry.config(state=tk.DISABLED)
        key_entry.grid(row=0, column=1, padx=5, pady=6)

        ttk.Label(frame, text="Пользовательское название:").grid(row=1, column=0, padx=5, pady=6, sticky=tk.W)
        value_entry = ttk.Entry(frame, width=32)
        value_entry.insert(0, value)
        value_entry.grid(row=1, column=1, padx=5, pady=6)
        value_entry.focus()

        def on_save():
            new_value = value_entry.get().strip()
            if not new_value:
                messagebox.showerror("Ошибка", "Поле не может быть пустым.", parent=dialog)
                return
            self.db_manager.add_or_update(key, new_value)
            self.refresh_tree()
            dialog.destroy()

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=2, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btn_row, text="💾 Сохранить", style="Accent.TButton", command=on_save).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_row, text="Отмена", command=dialog.destroy).pack(side=tk.LEFT, padx=6)

        style_widget_tree(dialog, "dark")

    def delete_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Информация", "Выберите записи для удаления.")
            return
        if messagebox.askyesno("Подтверждение", f"Удалить {len(selection)} записей?"):
            for item in selection:
                key = self.tree.item(item, 'values')[0]
                self.db_manager.delete(key)
            self.refresh_tree()

    def load_bom_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")])
        if not file_path:
            return
        self.file_path = file_path
        self.file_path_var.set(file_path)
        try:
            self.sheets = pd.ExcelFile(file_path).sheet_names
            self.sheet_cb['values'] = self.sheets
            if self.sheets:
                self.sheet_cb.set(self.sheets[0])
                self.on_sheet_selected()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{e}")

    def on_sheet_selected(self, event=None):
        sheet = self.sheet_cb.get()
        if not sheet:
            return
        self.selected_sheet = sheet
        try:
            self.df = pd.read_excel(self.file_path, sheet_name=sheet)
            self.edited_df = self.df.copy()
            columns = list(self.df.columns)
            self.key_col_cb['values'] = columns
            self.value_col_cb['values'] = columns
            if columns:
                self.key_col_cb.set(columns[0])
                if len(columns) > 1:
                    self.value_col_cb.set(columns[1])
            self.selected_indices = []
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить лист:\n{e}")

    def show_bom_editor(self):
        if self.edited_df is None:
            messagebox.showinfo("Информация", "Сначала загрузите файл BOM и выберите лист.")
            return

        if self.preview_window and self.preview_window.winfo_exists():
            self.preview_window.destroy()

        preview_window = create_styled_toplevel(self, "Подготовка документа – выбор столбцов и импорт соответствий", "1180x680")
        self.preview_window = preview_window

        # Верхняя панель настройки столбцов и фильтра
        control_frame = ttk.LabelFrame(preview_window, text="⚙️ Настройка соответствий и управление импортом", padding="10")
        control_frame.pack(fill=tk.X, padx=10, pady=6)

        columns = list(self.edited_df.columns)

        # Ряд 0: Выбор столбца ключа (BOM), значения (Пользовательское) и кнопки импорта
        row0 = ttk.Frame(control_frame)
        row0.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(row0, text="🔵 Столбец в BOM (ключ):", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        key_col_var = tk.StringVar(value=self.key_col_cb.get() or (columns[0] if columns else ""))
        key_cb = ttk.Combobox(row0, textvariable=key_col_var, values=columns, state="readonly", width=22)
        key_cb.pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(row0, text="🟢 Пользовательское название:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        val_col_var = tk.StringVar(value=self.value_col_cb.get() or (columns[1] if len(columns) > 1 else (columns[0] if columns else "")))
        val_cb = ttk.Combobox(row0, textvariable=val_col_var, values=columns, state="readonly", width=22)
        val_cb.pack(side=tk.LEFT, padx=(0, 15))

        def do_load_from_bom():
            self.key_col_cb.set(key_col_var.get())
            self.value_col_cb.set(val_col_var.get())
            self.load_from_bom()

        def do_check_database():
            self.key_col_cb.set(key_col_var.get())
            self.value_col_cb.set(val_col_var.get())
            self.check_database()

        ttk.Button(row0, text="📥 Загрузить соответствия в базу", style="Accent.TButton", command=do_load_from_bom).pack(side=tk.LEFT, padx=4)
        ttk.Button(row0, text="🔍 Проверка по базе", command=do_check_database).pack(side=tk.LEFT, padx=4)

        # Ряд 1: Фильтр и управление выделением строк
        row1 = ttk.Frame(control_frame)
        row1.pack(fill=tk.X)

        ttk.Label(row1, text="🔍 Фильтр:").pack(side=tk.LEFT, padx=(0, 4))
        filter_entry = ttk.Entry(row1, width=32)
        filter_entry.pack(side=tk.LEFT, padx=(0, 6))

        def clear_filter():
            filter_entry.delete(0, tk.END)
            update_tree()

        ttk.Button(row1, text="✕ Сбросить", command=clear_filter).pack(side=tk.LEFT, padx=(0, 15))

        def add_selected():
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showinfo("Информация", "Не выбрано ни одной строки.", parent=preview_window)
                return
            indices = [int(item) for item in selected_items]
            self.selected_indices = indices
            for item in selected_items:
                tree.item(item, tags=('selected',))
            update_info()
            messagebox.showinfo("Успех", f"Выбрано {len(indices)} строк(и). Теперь нажмите '📥 Загрузить соответствия в базу'.", parent=preview_window)

        def clear_selection():
            tree.selection_remove(*tree.selection())
            for item in tree.get_children():
                tree.item(item, tags=('normal',))
            self.selected_indices = []
            update_info()

        ttk.Button(row1, text="➕ Добавить выделенные строки", command=add_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(row1, text="Снять выделение", command=clear_selection).pack(side=tk.LEFT, padx=4)

        # Область таблицы с данными
        table_frame = ttk.Frame(preview_window, padding="6")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode='extended')
        tree.tag_configure('odd', background="#232428")
        tree.tag_configure('even', background="#2b2d31")
        tree.tag_configure('selected', background="#3b4261")

        def update_column_headers():
            k_col = key_col_var.get()
            v_col = val_col_var.get()
            self.key_col_cb.set(k_col)
            self.value_col_cb.set(v_col)
            for c in columns:
                if c == k_col:
                    tree.heading(c, text=f"🔵 {c} [КЛЮЧ BOM]", command=lambda col=c: sort_column(col, False))
                elif c == v_col:
                    tree.heading(c, text=f"🟢 {c} [ПОЛЬЗОВАТЕЛЬСКОЕ]", command=lambda col=c: sort_column(col, False))
                else:
                    tree.heading(c, text=c, command=lambda col=c: sort_column(col, False))
            legend_label.config(text=f"🔵 Ключ в BOM: '{k_col}'   |   🟢 Пользовательское: '{v_col}'")

        key_cb.bind("<<ComboboxSelected>>", lambda e: update_column_headers())
        val_cb.bind("<<ComboboxSelected>>", lambda e: update_column_headers())

        def sort_column(col, reverse=False):
            items = [(tree.set(item, col), item) for item in tree.get_children('')]
            try:
                items.sort(key=lambda x: float(x[0]) if x[0].replace('.', '').isdigit() else x[0], reverse=reverse)
            except:
                items.sort(key=lambda x: x[0].lower(), reverse=reverse)
            for index, (_, item) in enumerate(items):
                tree.move(item, '', index)
                tag = 'even' if index % 2 == 0 else 'odd'
                tree.item(item, tags=(tag,))
            tree.heading(col, command=lambda: sort_column(col, not reverse))

        for col in columns:
            tree.column(col, width=120, minwidth=80, anchor=tk.W)

        scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=tree.yview, style="Vertical.TScrollbar")
        scroll_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=tree.xview, style="Horizontal.TScrollbar")
        tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        item_to_index = {}

        def update_tree():
            for item in tree.get_children():
                tree.delete(item)
            filter_text = filter_entry.get().strip().lower()
            inserted_count = 0
            for idx, row in self.edited_df.iterrows():
                values = [str(row[col]) if pd.notna(row[col]) else "" for col in columns]
                if all(v.strip() == "" for v in values):
                    continue
                if filter_text:
                    found = False
                    for v in values:
                        if filter_text in v.lower():
                            found = True
                            break
                    if not found:
                        continue
                tag = 'even' if inserted_count % 2 == 0 else 'odd'
                item = tree.insert("", tk.END, values=values, iid=str(idx), tags=(tag,))
                item_to_index[item] = idx
                if idx in self.selected_indices:
                    tree.selection_add(item)
                    tree.item(item, tags=('selected',))
                inserted_count += 1
            update_info()

        # Нижняя статусная панель с подсказкой и кнопкой Закрыть
        bottom_bar = ttk.Frame(preview_window, padding="8")
        bottom_bar.pack(fill=tk.X, side=tk.BOTTOM)

        legend_label = ttk.Label(bottom_bar, text="", font=("Segoe UI", 9, "bold"))
        legend_label.pack(side=tk.LEFT, padx=6)

        info_label = ttk.Label(bottom_bar, text="Выбрано: 0 строк", foreground="gray")
        info_label.pack(side=tk.LEFT, padx=16)

        def update_info():
            count = len(tree.selection())
            info_label.config(text=f"Всего отображено: {len(tree.get_children())}   |   Выбрано: {count} строк")

        tree.bind('<<TreeviewSelect>>', lambda e: update_info())
        ttk.Button(bottom_bar, text="Закрыть", command=preview_window.destroy).pack(side=tk.RIGHT, padx=6)

        filter_entry.bind('<KeyRelease>', lambda e: update_tree())
        update_column_headers()
        update_tree()

        style_widget_tree(preview_window, "dark")

    def load_from_bom(self):
        if self.edited_df is None:
            messagebox.showwarning("Предупреждение", "Сначала загрузите файл BOM и выберите лист.")
            return

        key_col = self.key_col_cb.get()
        value_col = self.value_col_cb.get()
        if not key_col or not value_col:
            messagebox.showwarning("Предупреждение", "Выберите оба столбца.")
            return
        if key_col not in self.edited_df.columns or value_col not in self.edited_df.columns:
            messagebox.showerror("Ошибка", "Выбранные столбцы не найдены в данных.")
            return

        if self.selected_indices:
            filtered_df = self.edited_df.iloc[self.selected_indices]
        else:
            if not messagebox.askyesno("Выбор строк", "Вы не выбрали отдельные строки в редакторе.\nЗагрузить соответствия для ВСЕХ строк?"):
                return
            filtered_df = self.edited_df

        items = []
        for _, row in filtered_df.iterrows():
            key = str(row[key_col]).strip() if pd.notna(row[key_col]) else ""
            value = str(row[value_col]).strip() if pd.notna(row[value_col]) else ""
            if key and value:
                items.append((key, value))

        if not items:
            messagebox.showinfo("Информация", "В выбранных строках нет данных.")
            return

        duplicates = []
        for key, _ in items:
            if self.db_manager.contains(key):
                duplicates.append(key)

        if duplicates:
            choice = messagebox.askyesnocancel(
                "Обнаружены дубликаты",
                f"Найдено {len(duplicates)} дублирующихся записей.\n"
                "Нажмите 'Да' для перезаписи всех дубликатов,\n"
                "'Нет' для пропуска дубликатов,\n"
                "'Отмена' для отмены загрузки."
            )
            if choice is None:
                return
            overwrite = choice
        else:
            overwrite = False

        added, skipped = self.db_manager.add_multiple(items, overwrite=overwrite)
        self.refresh_tree()
        msg = f"Добавлено {len(added)} записей."
        if skipped:
            msg += f" Пропущено (дубликаты) {len(skipped)}."
        messagebox.showinfo("Результат импорта", msg)

    # ===== Проверка по базе =====
    def check_database(self):
        if self.df is None:
            messagebox.showinfo("Информация", "Сначала загрузите файл BOM и выберите лист.")
            return

        key_col = self.key_col_cb.get()
        value_col = self.value_col_cb.get()
        if not key_col or not value_col:
            messagebox.showwarning("Предупреждение", "Выберите оба столбца (название в BOM и пользовательское название).")
            return
        if key_col not in self.df.columns or value_col not in self.df.columns:
            messagebox.showerror("Ошибка", "Выбранные столбцы не найдены в данных.")
            return

        original_values = [str(x) if pd.notna(x) else "" for x in self.df[key_col]]
        current_values = [str(x) if pd.notna(x) else "" for x in self.df[value_col]]

        replacements = []
        for i, (orig, curr) in enumerate(zip(original_values, current_values)):
            if not orig:
                continue
            user_name = self.db_manager.get(orig)
            if user_name and user_name != curr:
                replacements.append((orig, curr, user_name))

        if not replacements:
            messagebox.showinfo("Информация", "Нет совпадений с базой данных для замены.")
            return

        result = self._show_replacement_dialog(replacements)
        if result:
            new_values = current_values[:]
            for orig, curr, user_name in replacements:
                for i, (o, c) in enumerate(zip(original_values, new_values)):
                    if o == orig and c == curr:
                        new_values[i] = user_name
            self.df[value_col] = new_values
            if self.edited_df is not None and value_col in self.edited_df.columns:
                self.edited_df[value_col] = new_values
            messagebox.showinfo("Успех", f"Столбец '{value_col}' обновлён согласно базе данных.")
        else:
            messagebox.showinfo("Отмена", "Замены не применены.")

    def _show_replacement_dialog(self, replacements):
        dialog = create_styled_toplevel(self, "Замена на пользовательские названия", "760x440")
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="Найдены совпадения в базе данных. Вы можете применить замену:",
                  wraplength=650, font=("Segoe UI", 9, "bold")).pack(pady=8)

        frame = ttk.Frame(dialog, padding="5")
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tree = ttk.Treeview(frame, columns=("original", "generated", "user"), show="headings", height=10)
        tree.tag_configure('odd', background="#232428")
        tree.tag_configure('even', background="#2b2d31")
        tree.heading("original", text="Исходное значение")
        tree.heading("generated", text="Сгенерированное")
        tree.heading("user", text="Пользовательское")
        tree.column("original", width=220)
        tree.column("generated", width=220)
        tree.column("user", width=220)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        for idx, (orig, curr, user) in enumerate(replacements):
            tag = 'even' if idx % 2 == 0 else 'odd'
            tree.insert("", tk.END, values=(orig, curr, user), tags=(tag,))

        btn_frame = ttk.Frame(dialog, padding="8")
        btn_frame.pack(fill=tk.X)

        result = [False]

        def on_apply():
            result[0] = True
            dialog.destroy()

        ttk.Button(btn_frame, text="✅ Применить замены", style="Accent.TButton", command=on_apply).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy).pack(side=tk.LEFT, padx=6)

        style_widget_tree(dialog, "dark")
        self.wait_window(dialog)
        return result[0]



    

# =============================================================================
# НОВОЕ: парсинг российских обозначений резисторов (без миллиом)
# =============================================================================
def parse_russian_resistor_value(raw):
    """Преобразует российское обозначение резистора (1кОм, 4.7МОм) в формат с R/K/M.
       Миллиомы (мОм) не поддерживаются."""
    raw = raw.lower().strip()
    raw = raw.replace('ом', '')
    raw = raw.replace('r', '')
    match = re.match(r'([\d.,]+)\s*([ккм]?)', raw)
    if not match:
        return raw
    num_str = match.group(1)
    unit = match.group(2)
    num_str = num_str.replace(',', '.')
    try:
        num = float(num_str)
    except ValueError:
        return raw
    if unit in ('к', 'k'):
        return f"{num:.3g}K"
    elif unit in ('м', 'm'):
        # миллиомы не используем, считаем мегаомами
        return f"{num:.3g}M"
    else:
        if num >= 1000000:
            return f"{num/1000000:.3g}M"
        elif num >= 1000:
            return f"{num/1000:.3g}K"
        else:
            return f"{num:.3g}R"


# =============================================================================
# Класс для хранения правила парсинга одного производителя (используется в CodeTab)
# =============================================================================
class VendorRule:
    def __init__(self, name, comp_type, pattern, size_map, dielectric_map=None, voltage_map=None,
                 tolerance_map=None, value_parser=None, suffix_map=None, is_resistor=False):
        self.name = name
        self.comp_type = comp_type
        self.pattern = re.compile(pattern)
        self.size_map = size_map
        self.dielectric_map = dielectric_map or {}
        self.voltage_map = voltage_map or {}
        self.tolerance_map = tolerance_map or {}
        self.value_parser = value_parser
        self.suffix_map = suffix_map or {}
        self.is_resistor = is_resistor

    def match(self, code):
        m = self.pattern.match(code)
        if m:
            return m.groupdict()
        return None


# =============================================================================
# Парсер для преобразования кода в унифицированное имя (используется в CodeTab)
# =============================================================================
class VendorParser:
    def __init__(self, rules):
        self.rules = rules

    def parse(self, code, vendor_name=None):
        if vendor_name:
            for rule in self.rules:
                if rule.name.lower() == vendor_name.lower():
                    groups = rule.match(code)
                    if groups:
                        return rule, groups
            return None, None
        else:
            for rule in self.rules:
                groups = rule.match(code)
                if groups:
                    return rule, groups
            return None, None

    def convert_to_unified(self, code, rule, groups):
        if rule.is_resistor:
            size_code = groups.get('size')
            size = rule.size_map.get(size_code, size_code)
            raw_value = groups.get('value') or groups.get('code')
            if raw_value:
                # ---- ДОБАВЛЕНО: очистка от лишних символов (тире, подчёркивания) ----
                raw_value = raw_value.strip()
                raw_value = raw_value.lstrip('-')
                raw_value = raw_value.lstrip('_')
                # ---------------------------------------------------------------
                if rule.value_parser:
                    value_str = rule.value_parser(raw_value)
                else:
                    value_str = self._parse_resistor_value(raw_value, rule.suffix_map)
            else:
                value_str = '?'
            tolerance_code = groups.get('tolerance')
            tolerance = rule.tolerance_map.get(tolerance_code, tolerance_code)
            if value_str == '0R':
                return f"R_{size}_0R_{tolerance}"
            else:
                return f"R_{size}_{value_str}_{tolerance}"
        else:
            size_code = groups.get('size')
            size = rule.size_map.get(size_code, size_code)
            dielectric_code = groups.get('dielectric')
            dielectric = rule.dielectric_map.get(dielectric_code, dielectric_code)
            raw_value = groups.get('code')
            if raw_value:
                if rule.value_parser:
                    value_str = rule.value_parser(raw_value)
                else:
                    value_str = self._parse_capacitance_value(raw_value)
            else:
                value_str = '?'
            voltage_code = groups.get('voltage')
            if voltage_code and voltage_code in rule.voltage_map:
                voltage = rule.voltage_map[voltage_code]
            else:
                voltage = '?'
            return f"C_{size}_{dielectric}_{value_str}_{voltage}"
        
    def _parse_resistor_value(self, raw, suffix_map):
        raw = raw.strip().upper()
        raw = re.sub(r'Ω', '', raw)
        raw = re.sub(r'(?i)ом', '', raw)

        if raw == '000' or raw == '0' or raw == '0R':
            return '0R'

        match_inside = re.search(r'([KMR])(\d+)$', raw)
        if match_inside and match_inside.start() < len(raw) - 1:
            letter = match_inside.group(1)
            num_part = raw[:match_inside.start()]
            decimal_part = match_inside.group(2)
            try:
                val = float(f"{num_part}.{decimal_part}")
            except:
                val = 0
            if letter == 'R':
                return f"{val:.3g}R"
            elif letter == 'K':
                return f"{val:.3g}K"
            elif letter == 'M':
                return f"{val:.3g}M"
            else:
                return f"{val:.3g}R"

        if raw[-1] in suffix_map:
            suffix = raw[-1]
            num_part = raw[:-1]
            unit = suffix_map[suffix]
            if 'R' in num_part:
                num_part = num_part.replace('R', '.')
            try:
                val = float(num_part)
            except:
                val = 0
            if unit in ('Ω', 'mΩ'):
                if unit == 'mΩ':
                    val = val / 1000.0
                if val >= 1000000:
                    return f"{val/1000000:.3g}M"
                elif val >= 1000:
                    return f"{val/1000:.3g}K"
                else:
                    return f"{val:.3g}R"
            elif unit == 'KΩ':
                return f"{val:.3g}K"
            elif unit == 'MΩ':
                return f"{val:.3g}M"
            else:
                return f"{num_part}{unit}"

        if len(raw) == 3:
            if raw[0] == 'R' or 'R' in raw:
                raw = raw.replace('R', '.')
                try:
                    val = float(raw)
                except:
                    val = 0
                if val < 1:
                    return f"{val:.3g}R"
                else:
                    return f"{val:.3g}R"
            else:
                try:
                    mantissa = int(raw[:2])
                    multiplier = int(raw[2])
                    val = mantissa * (10 ** multiplier)
                except:
                    return raw
                if val >= 1000000:
                    return f"{val/1000000:.3g}M"
                elif val >= 1000:
                    return f"{val/1000:.3g}K"
                else:
                    return f"{val:.3g}R"
        elif len(raw) == 4:
            if 'R' in raw:
                raw = raw.replace('R', '.')
                try:
                    val = float(raw)
                except:
                    val = 0
                if val < 1:
                    return f"{val:.3g}R"
                else:
                    return f"{val:.3g}R"
            else:
                try:
                    mantissa = int(raw[:3])
                    multiplier = int(raw[3])
                    val = mantissa * (10 ** multiplier)
                except:
                    return raw
                if val >= 1000000:
                    return f"{val/1000000:.3g}M"
                elif val >= 1000:
                    return f"{val/1000:.3g}K"
                else:
                    return f"{val:.3g}R"
        else:
            return raw

    def _parse_capacitance_value(self, raw):
        raw = raw.strip().upper()
        if 'R' in raw:
            raw = raw.replace('R', '.')
            try:
                val = float(raw)
            except:
                val = 0
            if val < 1:
                return f"{val:.2g}pF"
            elif val < 1000:
                if val.is_integer():
                    return f"{int(val)}pF"
                else:
                    return f"{val:.2g}pF"
            elif val < 1000000:
                val_nf = val / 1000
                if val_nf.is_integer():
                    return f"{int(val_nf)}nF"
                else:
                    return f"{val_nf:.2g}nF"
            else:
                val_uf = val / 1000000
                if val_uf.is_integer():
                    return f"{int(val_uf)}uF"
                else:
                    return f"{val_uf:.2g}uF"
        else:
            if len(raw) == 3:
                try:
                    mantissa = int(raw[:2])
                    multiplier = int(raw[2])
                    val = mantissa * (10 ** multiplier)
                except:
                    return raw
                if val < 1000:
                    if val.is_integer():
                        return f"{int(val)}pF"
                    else:
                        return f"{val:.2g}pF"
                elif val < 1000000:
                    val_nf = val / 1000
                    if val_nf.is_integer():
                        return f"{int(val_nf)}nF"
                    else:
                        return f"{val_nf:.2g}nF"
                else:
                    val_uf = val / 1000000
                    if val_uf.is_integer():
                        return f"{int(val_uf)}uF"
                    else:
                        return f"{val_uf:.2g}uF"
            else:
                return raw


# =============================================================================
# Вкладка "Унификация по коду" (полностью автономная) – РАСШИРЕННАЯ
# =============================================================================
class CodeTab(ttk.Frame):
    # Допустимые напряжения для конденсаторов (из правил CodeTab)
    VALID_VOLTAGES = {
        '4V', '6.3V', '10V', '16V', '25V', '35V', '50V', '75V', '100V',
        '200V', '250V', '350V', '500V', '630V', '1000V', '2000V', '3000V',
        '1kV', '2kV', '3.15kV', 'AC250V'
    }
    # Допустимые допуски для резисторов (стандартные значения)
    VALID_TOLERANCES = ['0.05%', '0.1%', '0.25%', '0.5%', '1%', '2%', '5%', '10%', '20%']

    def __init__(self, parent, db_manager):
        super().__init__(parent)
        self.parent = parent
        self.db_manager = db_manager  # добавлено

        # Данные
        self.df = None
        self.file_path = None
        self.selected_sheet = None
        self.selected_code_column = None
        self.parsed_column = None

        # Правила
        self.rules = []
        self.parser = None

        # Переменные интерфейса
        self.file_path_var = tk.StringVar()
        self.sheet_var = tk.StringVar()
        self.code_column_var = tk.StringVar()

        # Флаги для пропуска диалогов
        self.skip_all_resistor_code = False
        self.skip_all_capacitor_code = False

        self.create_widgets()
        self.init_default_rules()

    def create_widgets(self):
        # Основной canvas с прокруткой
        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        v_scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.configure(yscrollcommand=v_scroll.set)

        main_frame = ttk.Frame(canvas, padding="10")
        canvas_window = canvas.create_window((0, 0), window=main_frame, anchor='nw')
        main_frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(canvas_window, width=e.width))

        # ---------- Загрузка файла ----------
        load_frame = ttk.LabelFrame(main_frame, text="1. Загрузка файла", padding="5")
        load_frame.pack(fill=tk.X, pady=5)

        ttk.Button(load_frame, text="Открыть файл", command=self.load_file).pack(side=tk.LEFT, padx=5)
        ttk.Entry(load_frame, textvariable=self.file_path_var, width=50).pack(side=tk.LEFT, padx=5)
        ttk.Button(load_frame, text="📋 Просмотр документа", command=self.show_full_preview).pack(side=tk.LEFT, padx=5)

        # ---------- Выбор листа и столбцов ----------
        select_frame = ttk.LabelFrame(main_frame, text="2. Выбор листа и столбца", padding="5")
        select_frame.pack(fill=tk.X, pady=5)

        ttk.Label(select_frame, text="Лист:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.sheet_combobox = ttk.Combobox(select_frame, state="readonly", width=30, textvariable=self.sheet_var)
        self.sheet_combobox.grid(row=0, column=1, padx=5, pady=2)
        self.sheet_combobox.bind("<<ComboboxSelected>>", self.on_sheet_selected)

        ttk.Label(select_frame, text="Столбец с кодом детали:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.code_combobox = ttk.Combobox(select_frame, state="readonly", width=30, textvariable=self.code_column_var)
        self.code_combobox.grid(row=1, column=1, padx=5, pady=2)
        self.code_combobox.bind("<<ComboboxSelected>>", self.on_code_column_selected)

        # ---------- Правила ----------
        rules_frame = ttk.LabelFrame(main_frame, text="3. Правила парсинга", padding="5")
        rules_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ("Производитель", "Тип", "Шаблон", "Активен")
        self.rules_tree = ttk.Treeview(rules_frame, columns=columns, show="headings", height=6)
        self.rules_tree.heading("Производитель", text="Производитель")
        self.rules_tree.heading("Тип", text="Тип")
        self.rules_tree.heading("Шаблон", text="Шаблон (рег. выражение)")
        self.rules_tree.heading("Активен", text="Активен")
        self.rules_tree.column("Производитель", width=120)
        self.rules_tree.column("Тип", width=80)
        self.rules_tree.column("Шаблон", width=300)
        self.rules_tree.column("Активен", width=60)

        scroll_rules = ttk.Scrollbar(rules_frame, orient=tk.VERTICAL, command=self.rules_tree.yview)
        self.rules_tree.configure(yscrollcommand=scroll_rules.set)
        self.rules_tree.grid(row=0, column=0, sticky="nsew")
        scroll_rules.grid(row=0, column=1, sticky="ns")
        rules_frame.grid_rowconfigure(0, weight=1)
        rules_frame.grid_columnconfigure(0, weight=1)

        btn_rules = ttk.Frame(rules_frame)
        btn_rules.grid(row=1, column=0, columnspan=2, pady=5)
        ttk.Button(btn_rules, text="Добавить правило", command=self.add_rule_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_rules, text="Редактировать правило", command=self.edit_rule_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_rules, text="Удалить правило", command=self.delete_rule).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_rules, text="Восстановить предустановленные", command=self.init_default_rules).pack(side=tk.LEFT, padx=5)

        # ---------- Кнопки действий ----------
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=5)

        ttk.Button(action_frame, text="🔄 Сбросить преобразования (код)", command=self.reset_conversion).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="▶ Применить правила (код)", command=self.apply_rules).pack(side=tk.LEFT, padx=5)
        self.result_preview_btn = ttk.Button(action_frame, text="📊 Полный предпросмотр (код)",
                                             command=self.show_result_preview, state=tk.DISABLED)
        self.result_preview_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="💾 Сохранить результат (код)", command=self.save_file).pack(side=tk.LEFT, padx=5)

        # ---------- Предпросмотр (первые 20 строк) ----------
        preview_frame = ttk.LabelFrame(main_frame, text="4. Предпросмотр (первые 20 строк)", padding="5")
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.preview_tree = ttk.Treeview(preview_frame, columns=("original", "converted"), show="headings", height=10)
        self.preview_tree.heading("original", text="Исходный код")
        self.preview_tree.heading("converted", text="Преобразованное имя")
        self.preview_tree.column("original", width=350)
        self.preview_tree.column("converted", width=350)

        scroll_preview = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.preview_tree.yview)
        self.preview_tree.configure(yscrollcommand=scroll_preview.set)
        self.preview_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_preview.pack(side=tk.RIGHT, fill=tk.Y)

    # ========== Загрузка и выбор данных ----------
    def load_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")])
        if not file_path:
            return
        self.file_path = file_path
        self.file_path_var.set(file_path)

        try:
            self.sheets = pd.ExcelFile(file_path).sheet_names
            self.sheet_combobox['values'] = self.sheets
            if self.sheets:
                self.sheet_combobox.set(self.sheets[0])
                self.on_sheet_selected()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{e}")

    def on_sheet_selected(self, event=None):
        sheet = self.sheet_var.get()
        if not sheet:
            return
        self.selected_sheet = sheet
        try:
            self.df = pd.read_excel(self.file_path, sheet_name=sheet)
            columns = list(self.df.columns)
            self.code_combobox['values'] = columns
            if columns:
                self.code_combobox.set(columns[0])
                self.on_code_column_selected()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить лист:\n{e}")

    # ========== Правила ==========
    def init_default_rules(self):
        self.rules = smd_engine.create_capacitor_rules() + smd_engine.create_resistor_rules()
        self.parser = smd_engine.VendorParser(self.rules)
        self.update_rules_tree()

    def on_code_column_selected(self, event=None):
        self.selected_code_column = self.code_column_var.get()
        if self.selected_code_column and self.df is not None:
            self.update_preview()

    def update_rules_tree(self):
        for item in self.rules_tree.get_children():
            self.rules_tree.delete(item)
        for rule in self.rules:
            self.rules_tree.insert("", tk.END, values=(rule.name, rule.comp_type, rule.pattern.pattern, "Да"))

    def add_rule_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Добавить правило")
        dialog.geometry("600x500")
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="Название производителя:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        name_entry = ttk.Entry(dialog, width=40)
        name_entry.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(dialog, text="Тип компонента (capacitor/resistor):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        comp_type_combo = ttk.Combobox(dialog, values=["capacitor", "resistor"], state="readonly")
        comp_type_combo.grid(row=1, column=1, padx=5, pady=2)
        comp_type_combo.set("capacitor")

        ttk.Label(dialog, text="Регулярное выражение (с именованными группами):").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        pattern_entry = ttk.Entry(dialog, width=60)
        pattern_entry.grid(row=2, column=1, padx=5, pady=2)

        ttk.Label(dialog, text="Маппинг размера (код:значение, через запятую):").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        size_entry = ttk.Entry(dialog, width=60)
        size_entry.grid(row=3, column=1, padx=5, pady=2)

        ttk.Label(dialog, text="Маппинг диэлектрика (только для конденсаторов):").grid(row=4, column=0, sticky=tk.W, padx=5, pady=2)
        dielec_entry = ttk.Entry(dialog, width=60)
        dielec_entry.grid(row=4, column=1, padx=5, pady=2)

        ttk.Label(dialog, text="Маппинг напряжения (только для конденсаторов):").grid(row=5, column=0, sticky=tk.W, padx=5, pady=2)
        volt_entry = ttk.Entry(dialog, width=60)
        volt_entry.grid(row=5, column=1, padx=5, pady=2)

        ttk.Label(dialog, text="Маппинг допуска (код:значение):").grid(row=6, column=0, sticky=tk.W, padx=5, pady=2)
        tol_entry = ttk.Entry(dialog, width=60)
        tol_entry.grid(row=6, column=1, padx=5, pady=2)

        ttk.Label(dialog, text="Суффиксы для резисторов (R:Ω,K:KΩ,M:MΩ,L:mΩ):").grid(row=7, column=0, sticky=tk.W, padx=5, pady=2)
        suffix_entry = ttk.Entry(dialog, width=60)
        suffix_entry.grid(row=7, column=1, padx=5, pady=2)

        def parse_map(text):
            d = {}
            for item in text.split(','):
                if ':' in item:
                    k, v = item.split(':', 1)
                    d[k.strip()] = v.strip()
            return d

        def on_save():
            name = name_entry.get().strip()
            comp_type = comp_type_combo.get()
            pattern_str = pattern_entry.get().strip()
            size_map = parse_map(size_entry.get())
            dielec_map = parse_map(dielec_entry.get())
            volt_map = parse_map(volt_entry.get())
            tol_map = parse_map(tol_entry.get())
            suffix_map = parse_map(suffix_entry.get())
            is_resistor = (comp_type == 'resistor')
            if not name or not pattern_str or not size_map:
                messagebox.showerror("Ошибка", "Название, регулярное выражение и маппинг размера обязательны.")
                return
            try:
                rule = VendorRule(name, comp_type, pattern_str, size_map,
                                  dielectric_map=dielec_map, voltage_map=volt_map,
                                  tolerance_map=tol_map, suffix_map=suffix_map,
                                  is_resistor=is_resistor)
            except Exception as e:
                messagebox.showerror("Ошибка", f"Некорректное регулярное выражение: {e}")
                return
            self.rules.append(rule)
            self.parser = VendorParser(self.rules)
            self.update_rules_tree()
            dialog.destroy()

        ttk.Button(dialog, text="Сохранить", command=on_save).grid(row=8, column=0, columnspan=2, pady=10)

    def edit_rule_dialog(self):
        selected = self.rules_tree.selection()
        if not selected:
            messagebox.showinfo("Информация", "Выберите правило для редактирования.")
            return
        idx = self.rules_tree.index(selected[0])
        if idx < 0 or idx >= len(self.rules):
            return
        messagebox.showinfo("Информация", "Редактирование пока не реализовано, удалите и создайте правило заново.")

    def delete_rule(self):
        selected = self.rules_tree.selection()
        if not selected:
            messagebox.showinfo("Информация", "Выберите правило для удаления.")
            return
        idx = self.rules_tree.index(selected[0])
        if idx < 0 or idx >= len(self.rules):
            return
        del self.rules[idx]
        self.parser = VendorParser(self.rules)
        self.update_rules_tree()

    # ========== Диалог ручного именования ==========
    def ask_user_for_name(self, original_code, comp_type):
        if comp_type == 'resistor' and self.skip_all_resistor_code:
            return None
        if comp_type == 'capacitor' and self.skip_all_capacitor_code:
            return None

        root = tk.Toplevel(self)
        title = f"Ручное именование {comp_type}"
        root.title(title)
        root.geometry("600x200")

        ttk.Label(root, text=f"Код определён как {comp_type}, но не удалось извлечь все части.").pack(pady=5)
        ttk.Label(root, text=f"Оригинал: {original_code[:80]}").pack(pady=5)
        ttk.Label(root, text="Введите унифицированное имя (или оставьте пустым для пропуска):").pack(pady=5)

        entry = ttk.Entry(root, width=60)
        entry.pack(pady=5)

        result = {"value": None, "skip_all": False}

        def on_ok():
            val = entry.get().strip()
            result["value"] = val if val else None
            root.destroy()

        def on_skip_all():
            result["value"] = None
            result["skip_all"] = True
            root.destroy()

        def on_cancel():
            result["value"] = None
            root.destroy()

        button_frame = ttk.Frame(root)
        button_frame.pack(pady=10)

        ttk.Button(button_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Пропустить все", command=on_skip_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Отмена (оставить как есть)", command=on_cancel).pack(side=tk.LEFT, padx=5)

        root.transient(self)
        root.grab_set()
        self.wait_window(root)

        if result.get("skip_all", False):
            if comp_type == 'resistor':
                self.skip_all_resistor_code = True
            elif comp_type == 'capacitor':
                self.skip_all_capacitor_code = True
            return None
        return result["value"]

    # ========== Применение правил ==========
    def apply_rules(self):
        if self.df is None:
            messagebox.showinfo("Информация", "Сначала загрузите файл и выберите лист.")
            return
        if self.selected_code_column is None or self.selected_code_column not in self.df.columns:
            messagebox.showwarning("Предупреждение", "Выберите столбец с кодом детали.")
            return
        if not self.rules:
            messagebox.showwarning("Предупреждение", "Нет ни одного правила парсинга.")
            return

        new_col_name = "Converted_Description_Vendor"
        if new_col_name in self.df.columns:
            i = 1
            while f"{new_col_name}_{i}" in self.df.columns:
                i += 1
            new_col_name = f"{new_col_name}_{i}"

        converted = []
        original_codes = []
        parse_errors = 0

        for idx, row in self.df.iterrows():
            code = str(row[self.selected_code_column]).strip() if pd.notna(row[self.selected_code_column]) else ""
            original_codes.append(code)
            if not code:
                converted.append("")
                continue

            rule, groups = self.parser.parse(code, None)
            if rule and groups:
                try:
                    unified = self.parser.convert_to_unified(code, rule, groups)
                    if '?' in unified or 'ОШИБКА' in unified:
                        comp_type = rule.comp_type
                        user_name = self.ask_user_for_name(code, comp_type)
                        if user_name is not None:
                            unified = user_name
                        else:
                            unified = code
                    converted.append(unified)
                except Exception as e:
                    comp_type = rule.comp_type
                    user_name = self.ask_user_for_name(code, comp_type)
                    if user_name is not None:
                        converted.append(user_name)
                    else:
                        converted.append(code)
                    parse_errors += 1
            else:
                converted.append(code)
                parse_errors += 1

        # Валидация и редактирование невалидных имен
        for i, name in enumerate(converted):
            if name.startswith("R_"):
                valid, _ = self._validate_resistor_name(name)
                if not valid:
                    new_name = self._show_edit_dialog(original_codes[i], name, "resistor")
                    if new_name is not None:
                        converted[i] = new_name
            elif name.startswith("C_"):
                valid, _ = self._validate_capacitor_name(name)
                if not valid:
                    new_name = self._show_edit_dialog(original_codes[i], name, "capacitor")
                    if new_name is not None:
                        converted[i] = new_name

        # ---- ДОБАВЛЕНО: проверка базы данных и замена ----
        # Получаем список исходных кодов и сгенерированных имён
        original_values = [str(x) if pd.notna(x) else "" for x in self.df[self.selected_code_column]]
        converted = self.apply_database_replacements(original_values, converted)

        self.df[new_col_name] = converted
        self.parsed_column = new_col_name
        if parse_errors > 0:
            messagebox.showwarning("Предупреждение", f"Не удалось распознать {parse_errors} строк(и). Они скопированы без изменений.")
        else:
            messagebox.showinfo("Успех", f"Преобразование завершено. Создан столбец: {new_col_name}")

        self.result_preview_btn.config(state=tk.NORMAL)
        self.update_preview()

    # ========== НОВЫЙ МЕТОД: применение замен из базы данных ==========
    def apply_database_replacements(self, original_values, converted_values):
        """
        Проверяет, есть ли для каждого исходного значения пользовательское имя в базе.
        Если есть и оно отличается от сгенерированного, предлагает заменить.
        Возвращает новый список converted_values с применёнными заменами.
        """
        replacements = []
        for orig, conv in zip(original_values, converted_values):
            if not orig:
                continue
            user_name = self.db_manager.get(orig)
            if user_name and user_name != conv:
                replacements.append((orig, conv, user_name))

        if not replacements:
            return converted_values

        # Показываем диалог предпросмотра
        result = self._show_replacement_dialog(replacements)
        if result:  # Применить замены
            new_converted = converted_values[:]
            # Заменяем только те, которые есть в списке replacements
            for orig, conv, user_name in replacements:
                # Ищем все вхождения этого orig и conv (может быть несколько одинаковых)
                for i, (o, c) in enumerate(zip(original_values, new_converted)):
                    if o == orig and c == conv:
                        new_converted[i] = user_name
            return new_converted
        else:
            return converted_values

    def _show_replacement_dialog(self, replacements):
        """Показывает диалог с таблицей замен и возвращает True, если пользователь нажал 'Применить'."""
        dialog = tk.Toplevel(self)
        dialog.title("Замена на пользовательские названия")
        dialog.geometry("700x400")
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="Найдены совпадения в базе данных. Вы можете заменить сгенерированные имена на пользовательские:",
                  wraplength=600).pack(pady=5)

        frame = ttk.Frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tree = ttk.Treeview(frame, columns=("original", "generated", "user"), show="headings", height=10)
        tree.heading("original", text="Исходное значение")
        tree.heading("generated", text="Сгенерированное")
        tree.heading("user", text="Пользовательское")
        tree.column("original", width=200)
        tree.column("generated", width=200)
        tree.column("user", width=200)

        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        for orig, conv, user in replacements:
            tree.insert("", tk.END, values=(orig, conv, user))

        result = {"apply": False}

        def on_apply():
            result["apply"] = True
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Применить замены", command=on_apply).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=on_cancel).pack(side=tk.LEFT, padx=5)

        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")

        self.wait_window(dialog)
        return result["apply"]

    # ========== Остальные методы CodeTab (без изменений) ==========
    def reset_conversion(self):
        if self.df is not None:
            cols_to_drop = [col for col in self.df.columns if col.startswith("Converted_Description_Vendor")]
            if cols_to_drop:
                self.df.drop(columns=cols_to_drop, inplace=True)
        for item in self.preview_tree.get_children():
            self.preview_tree.delete(item)
        self.skip_all_resistor_code = False
        self.skip_all_capacitor_code = False
        self.result_preview_btn.config(state=tk.DISABLED)
        self.parsed_column = None

    def update_preview(self):
        for item in self.preview_tree.get_children():
            self.preview_tree.delete(item)
        if self.df is None or self.parsed_column is None or self.parsed_column not in self.df.columns:
            return
        preview_df = self.df[[self.selected_code_column, self.parsed_column]].copy()
        mask = preview_df[self.selected_code_column].notna() & (preview_df[self.selected_code_column].astype(str).str.strip() != '')
        preview_df = preview_df[mask].head(20)
        for _, row in preview_df.iterrows():
            orig = str(row[self.selected_code_column]) if pd.notna(row[self.selected_code_column]) else ""
            conv = str(row[self.parsed_column]) if pd.notna(row[self.parsed_column]) else ""
            self.preview_tree.insert("", tk.END, values=(orig, conv))

    def _validate_resistor_name(self, name):
        pattern = r'^R_(?P<size>\d{4})_(?P<value>\d*\.?\d*[KMR]?)_(?P<tolerance>\d+\.?\d*%)$'
        m = re.match(pattern, name)
        if not m:
            return False, {}
        size = m.group('size')
        value = m.group('value')
        tol = m.group('tolerance')
        valid_sizes = ['0402','0603','0805','1206','0201','1210','2010','2512','1005']
        if size not in valid_sizes:
            return False, {'size': size}
        if not re.search(r'[KMR]$', value) and not re.search(r'\d+\.?\d*R', value):
            return False, {'value': value}
        if tol not in self.VALID_TOLERANCES:
            return False, {'tolerance': tol}
        return True, {}

    def _validate_capacitor_name(self, name):
        pattern = r'^C_(?P<size>\d{4})_(?P<dielectric>[A-Z0-9]+)_(?P<value>\d*\.?\d*[uUnNpP]?F)_(?P<voltage>\d*\.?\d*[A-Z]*V?)$'
        m = re.match(pattern, name)
        if not m:
            return False, {}
        size = m.group('size')
        dielectric = m.group('dielectric')
        value = m.group('value')
        voltage = m.group('voltage')
        valid_sizes = ['0402','0603','0805','1206','0201','1210','2010','2512','1005']
        valid_dielectrics = ['X5R','X7R','C0G','NPO','X6S','X8R','Y5V','X7S','X6T','X5S','X7T','X8L']
        if size not in valid_sizes:
            return False, {'size': size}
        if dielectric not in valid_dielectrics:
            return False, {'dielectric': dielectric}
        if not re.search(r'[uUnNpP]F$', value):
            return False, {'value': value}
        if voltage not in self.VALID_VOLTAGES:
            return False, {'voltage': voltage}
        return True, {}

    def _show_edit_dialog(self, original_text, current_name, comp_type):
        dialog = tk.Toplevel(self)
        dialog.title(f"Редактирование {comp_type}")
        dialog.geometry("700x500")
        dialog.transient(self)
        dialog.grab_set()

        if comp_type == 'resistor':
            parts = current_name.split('_')
            default_size = parts[1] if len(parts) > 1 else ''
            default_value = parts[2] if len(parts) > 2 else ''
            default_tol = parts[3] if len(parts) > 3 else ''
            labels = ['Размер', 'Номинал', 'Допуск']
            default_values = [default_size, default_value, default_tol]
            keys = ['size', 'value', 'tolerance']
        else:
            parts = current_name.split('_')
            default_size = parts[1] if len(parts) > 1 else ''
            default_diel = parts[2] if len(parts) > 2 else ''
            default_value = parts[3] if len(parts) > 3 else ''
            default_volt = parts[4] if len(parts) > 4 else ''
            labels = ['Размер', 'Диэлектрик', 'Номинал', 'Напряжение']
            default_values = [default_size, default_diel, default_value, default_volt]
            keys = ['size', 'dielectric', 'value', 'voltage']

        info_frame = ttk.Frame(dialog)
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(info_frame, text=f"Исходный код: {original_text}").pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"Текущее имя: {current_name}").pack(anchor=tk.W)

        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        entries = {}
        for i, (label, default) in enumerate(zip(labels, default_values)):
            ttk.Label(main_frame, text=label + ":").grid(row=i, column=0, padx=5, pady=5, sticky=tk.W)
            entry = ttk.Entry(main_frame, width=20)
            entry.insert(0, default)
            entry.grid(row=i, column=1, padx=5, pady=5, sticky=tk.W)
            entries[keys[i]] = entry

        ttk.Label(main_frame, text="Или введите полное имя:").grid(row=len(labels), column=0, padx=5, pady=5, sticky=tk.W)
        full_name_entry = ttk.Entry(main_frame, width=40)
        full_name_entry.grid(row=len(labels), column=1, padx=5, pady=5, sticky=tk.W)

        preview_label = ttk.Label(dialog, text="Предпросмотр: " + current_name, foreground="blue")
        preview_label.pack(pady=5)

        def update_preview(*args):
            if full_name_entry.get().strip():
                new_name = full_name_entry.get().strip()
            else:
                if comp_type == 'resistor':
                    size = entries['size'].get().strip()
                    value = entries['value'].get().strip()
                    tol = entries['tolerance'].get().strip()
                    new_name = f"R_{size}_{value}_{tol}" if size and value and tol else current_name
                else:
                    size = entries['size'].get().strip()
                    diel = entries['dielectric'].get().strip()
                    value = entries['value'].get().strip()
                    volt = entries['voltage'].get().strip()
                    new_name = f"C_{size}_{diel}_{value}_{volt}" if size and diel and value and volt else current_name
            preview_label.config(text="Предпросмотр: " + new_name)

        for entry in entries.values():
            entry.bind('<KeyRelease>', update_preview)
        full_name_entry.bind('<KeyRelease>', update_preview)

        result = {'new_name': None}

        def on_apply():
            if full_name_entry.get().strip():
                result['new_name'] = full_name_entry.get().strip()
            else:
                if comp_type == 'resistor':
                    size = entries['size'].get().strip()
                    value = entries['value'].get().strip()
                    tol = entries['tolerance'].get().strip()
                    if size and value and tol:
                        result['new_name'] = f"R_{size}_{value}_{tol}"
                else:
                    size = entries['size'].get().strip()
                    diel = entries['dielectric'].get().strip()
                    value = entries['value'].get().strip()
                    volt = entries['voltage'].get().strip()
                    if size and diel and value and volt:
                        result['new_name'] = f"C_{size}_{diel}_{value}_{volt}"
            dialog.destroy()

        def on_skip():
            result['new_name'] = None
            dialog.destroy()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="Применить", command=on_apply).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Оставить как есть", command=on_skip).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Отмена (не менять)", command=on_skip).pack(side=tk.LEFT, padx=5)

        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")

        self.wait_window(dialog)
        return result['new_name']

    # ========== Полный предпросмотр документа ==========
    def show_full_preview(self):
        if self.df is None:
            messagebox.showinfo("Информация", "Сначала загрузите файл.")
            return
        self._show_generic_preview(None, None, "Предпросмотр загруженного BOM (код)", all_columns=True)

    def show_result_preview(self):
        if self.df is None or self.parsed_column is None or self.parsed_column not in self.df.columns:
            messagebox.showinfo("Информация", "Сначала примените правила.")
            return
        self._show_generic_preview(self.selected_code_column, self.parsed_column,
                                   "Предпросмотр результатов (код)", all_columns=False)

    def _show_generic_preview(self, col1, col2, title, all_columns=False):
        preview_window = create_styled_toplevel(self, title, "960x540")

        filter_frame = ttk.Frame(preview_window, padding="5")
        filter_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(filter_frame, text="Фильтр:").pack(side=tk.LEFT, padx=5)
        filter_entry = ttk.Entry(filter_frame, width=40)
        filter_entry.pack(side=tk.LEFT, padx=5)

        def clear_filter():
            filter_entry.delete(0, tk.END)
            update_tree()

        ttk.Button(filter_frame, text="Сбросить фильтр", command=clear_filter).pack(side=tk.LEFT, padx=5)

        frame = ttk.Frame(preview_window, padding="5")
        frame.pack(fill=tk.BOTH, expand=True)

        if all_columns:
            columns = list(self.df.columns)
        else:
            columns = [col1, col2]

        tree = ttk.Treeview(frame, columns=columns, show="headings")
        tree.tag_configure('odd', background="#232428")
        tree.tag_configure('even', background="#2b2d31")

        def sort_column(col, reverse=False):
            items = [(tree.set(item, col), item) for item in tree.get_children('')]
            try:
                items.sort(key=lambda x: float(x[0]) if x[0].replace('.', '').isdigit() else x[0], reverse=reverse)
            except:
                items.sort(key=lambda x: x[0].lower(), reverse=reverse)
            for index, (_, item) in enumerate(items):
                tree.move(item, '', index)
                tag = 'even' if index % 2 == 0 else 'odd'
                tree.item(item, tags=(tag,))
            tree.heading(col, command=lambda: sort_column(col, not reverse))

        for col in columns:
            tree.heading(col, text=col, command=lambda c=col: sort_column(c, False))
            tree.column(col, width=120, anchor=tk.W)

        scroll_y = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview, style="Vertical.TScrollbar")
        scroll_x = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview, style="Horizontal.TScrollbar")
        tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        def update_tree():
            for item in tree.get_children():
                tree.delete(item)
            filter_text = filter_entry.get().strip().lower()
            inserted_count = 0
            for _, row in self.df.iterrows():
                values = [str(row[col]) if pd.notna(row[col]) else "" for col in columns]
                if all(v.strip() == "" for v in values):
                    continue
                if filter_text:
                    found = False
                    for v in values:
                        if filter_text in v.lower():
                            found = True
                            break
                    if not found:
                        continue
                tag = 'even' if inserted_count % 2 == 0 else 'odd'
                tree.insert("", tk.END, values=values, tags=(tag,))
                inserted_count += 1

        filter_entry.bind('<KeyRelease>', lambda e: update_tree())
        update_tree()

        btn_bar = ttk.Frame(preview_window, padding="5")
        btn_bar.pack(fill=tk.X, pady=5)
        ttk.Button(btn_bar, text="Закрыть", command=preview_window.destroy).pack(side=tk.BOTTOM, pady=2)

        style_widget_tree(preview_window, "dark")

    # ========== Сохранение ==========
    def save_file(self):
        if self.df is None:
            messagebox.showwarning("Предупреждение", "Нет данных для сохранения.")
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
        if not file_path:
            return
        try:
            self.df.to_excel(file_path, index=False)
            messagebox.showinfo("Успех", f"Файл сохранён:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")


# =============================================================================
# Вкладка "Унификация по описанию" (полностью автономная) – РАСШИРЕННАЯ
# =============================================================================
class DescriptionTab(ttk.Frame):
    # Допустимые напряжения для конденсаторов (из правил CodeTab)
    VALID_VOLTAGES = {
        '4V', '6.3V', '10V', '16V', '25V', '35V', '50V', '75V', '100V',
        '200V', '250V', '350V', '500V', '630V', '1000V', '2000V', '3000V',
        '1kV', '2kV', '3.15kV', 'AC250V'
    }
    # Допустимые допуски для резисторов (стандартные значения)
    VALID_TOLERANCES = ['0.05%', '0.1%', '0.25%', '0.5%', '1%', '2%', '5%', '10%', '20%']

    def __init__(self, parent, db_manager):
        super().__init__(parent)
        self.parent = parent
        self.db_manager = db_manager  # добавлено

        # Данные
        self.df = None
        self.file_path = None
        self.selected_sheet = None
        self.selected_column = None
        self.converted_column = None
        self.separators = [","]

        # Списки кандидатов и прочие переменные
        self.resistor_candidates = []
        self.capacitor_candidates = []
        self.selected_resistor_example = None
        self.selected_capacitor_example = None
        self.parts_example_resistor = []
        self.parts_example_capacitor = []
        self.resistor_indices = {"size": -1, "value": -1, "tolerance": -1}
        self.capacitor_indices = {"size": -1, "dielectric": -1, "value": -1, "voltage": -1}
        self.skip_all_resistor = False
        self.skip_all_capacitor = False
        self.user_defined_names = {}

        # Словари для переопределения индексов по шаблону
        self.user_overrides_resistor = {}
        self.user_overrides_capacitor = {}

        # NEW: переменная для галочки "Номинал в виде кода"
        self.nominal_code_var = tk.BooleanVar(value=False)

        # Паттерны
        self.patterns = {
            'size': re.compile(r'(0402|0603|0805|1206|0201|1210|2012|2512|1005)', re.IGNORECASE),
            'value': re.compile(r'\d+\.?\d*\s*[uµnp]?F|\d+\.?\d*\s*[kKMG]?R?|\d+\.?\d*\s*[kKMG]?Ohm|\d+\.?\d*\s*[kKMG]?Ω|\d+\.?\d*\s*[kKMG]', re.IGNORECASE),
            'tolerance': re.compile(r'%|±|percent', re.IGNORECASE),
            'dielectric': re.compile(r'X5R|X7R|C0G|NPO|X6S|X8R|Y5V|X7S|X6T|X5S|X7T|X8L', re.IGNORECASE),
            'voltage': re.compile(r'\d+\.?\d*\s*[VВ]', re.IGNORECASE)
        }
        self.clean_patterns = {
            'size': re.compile(r'(0402|0603|0805|1206|0201|1210|2012|2512|1005)', re.IGNORECASE),
            'dielectric': re.compile(r'(X5R|X7R|C0G|NPO|X6S|X8R|Y5V|X7S|X6T|X5S|X7T|X8L)', re.IGNORECASE),
            'voltage': re.compile(r'(\d+\.?\d*)\s*[VВ]', re.IGNORECASE),
            'tolerance': re.compile(r'([+-]?\d+\.?\d*%|±\d+%)', re.IGNORECASE),
        }

        self.create_widgets()
        self.update_examples()

    def create_widgets(self):
        # Основной canvas с прокруткой
        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        v_scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.configure(yscrollcommand=v_scroll.set)

        main_frame = ttk.Frame(canvas, padding="10")
        canvas_window = canvas.create_window((0, 0), window=main_frame, anchor='nw')
        main_frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(canvas_window, width=e.width))

        # ---------- Загрузка файла ----------
        load_frame = ttk.LabelFrame(main_frame, text="1. Загрузка файла", padding="5")
        load_frame.pack(fill=tk.X, pady=5)

        ttk.Button(load_frame, text="Открыть файл", command=self.load_file).pack(side=tk.LEFT, padx=5)
        self.file_path_var = tk.StringVar()
        ttk.Entry(load_frame, textvariable=self.file_path_var, width=50).pack(side=tk.LEFT, padx=5)
        ttk.Button(load_frame, text="📋 Просмотр документа", command=self.show_full_preview).pack(side=tk.LEFT, padx=5)

        # ---------- Выбор листа и столбца ----------
        select_frame = ttk.LabelFrame(main_frame, text="2. Выбор листа и столбца", padding="5")
        select_frame.pack(fill=tk.X, pady=5)

        ttk.Label(select_frame, text="Лист:").pack(side=tk.LEFT, padx=5)
        self.sheet_cb = ttk.Combobox(select_frame, state="readonly", width=20)
        self.sheet_cb.pack(side=tk.LEFT, padx=5)
        self.sheet_cb.bind("<<ComboboxSelected>>", self.on_sheet_selected)

        ttk.Label(select_frame, text="Столбец с описанием:").pack(side=tk.LEFT, padx=5)
        self.column_cb = ttk.Combobox(select_frame, state="readonly", width=30)
        self.column_cb.pack(side=tk.LEFT, padx=5)
        self.column_cb.bind("<<ComboboxSelected>>", self.on_column_selected)

        # ---------- Разделитель ----------
        sep_frame = ttk.LabelFrame(main_frame, text="3. Разделитель", padding="5")
        sep_frame.pack(fill=tk.X, pady=5)

        self.sep_var = tk.StringVar(value="comma")
        radio_frame = ttk.Frame(sep_frame)
        radio_frame.pack(fill=tk.X, pady=5)

        ttk.Radiobutton(radio_frame, text="Запятая (,)", variable=self.sep_var, value="comma",
                        command=self.on_separator_changed).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(radio_frame, text="Пробел ( )", variable=self.sep_var, value="space",
                        command=self.on_separator_changed).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(radio_frame, text="Табуляция (\\t)", variable=self.sep_var, value="tab",
                        command=self.on_separator_changed).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(radio_frame, text="Точка с запятой (;)", variable=self.sep_var, value="semicolon",
                        command=self.on_separator_changed).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(radio_frame, text="Свой", variable=self.sep_var, value="custom",
                        command=self.on_separator_changed).pack(side=tk.LEFT, padx=5)

        # NEW: галочка "Номинал в виде кода" – справа от "Свой"
        ttk.Checkbutton(sep_frame, text="Номинал в виде кода", variable=self.nominal_code_var).pack(side=tk.LEFT, padx=5)

        # Поля для пользовательских разделителей (4 штуки)
        self.custom_sep_entries = []
        for i in range(4):
            entry = ttk.Entry(sep_frame, width=8, state=tk.DISABLED)
            entry.pack(side=tk.LEFT, padx=2)
            self.custom_sep_entries.append(entry)

        ttk.Label(sep_frame, text="(\\p - пробел, \\t - табуляция)").pack(side=tk.LEFT, padx=5)

        ttk.Button(sep_frame, text="Применить и обновить примеры", command=self.update_separators).pack(side=tk.LEFT, padx=5)

        self.example_label_resistor = ttk.Label(sep_frame, text="Пример резистора: не найден", foreground="gray")
        self.example_label_resistor.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        self.example_label_capacitor = ttk.Label(sep_frame, text="Пример конденсатора: не найден", foreground="gray")
        self.example_label_capacitor.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        # ---------- Настройки для резисторов и конденсаторов ----------
        self.desc_notebook = ttk.Notebook(main_frame)
        self.desc_notebook.pack(fill=tk.BOTH, expand=True, pady=5)
        self.desc_notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        # Вкладка резисторов
        resistor_frame = ttk.Frame(self.desc_notebook)
        self.desc_notebook.add(resistor_frame, text="Резисторы")
        self.create_resistor_tab(resistor_frame)

        # Вкладка конденсаторов
        capacitor_frame = ttk.Frame(self.desc_notebook)
        self.desc_notebook.add(capacitor_frame, text="Конденсаторы")
        self.create_capacitor_tab(capacitor_frame)

        # ---------- Неопределённые ----------
        unknown_frame = ttk.LabelFrame(main_frame, text="Для строк, не определённых как резистор или конденсатор", padding="5")
        unknown_frame.pack(fill=tk.X, pady=5)

        ttk.Label(unknown_frame, text="Взять значение из столбца:").pack(side=tk.LEFT, padx=5)
        self.unknown_column_cb = ttk.Combobox(unknown_frame, state="readonly", width=30)
        self.unknown_column_cb.pack(side=tk.LEFT, padx=5)
        self.unknown_column_cb.set("Оставить как есть")
        self.unknown_column_cb.bind("<<ComboboxSelected>>", self.on_unknown_column_selected)

        # ---------- Кнопки действий ----------
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=5)

        ttk.Button(action_frame, text="🔄 Сбросить преобразования (описание)", command=self.reset_conversion).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="▶ Применить правила (описание)", command=self.apply_rules).pack(side=tk.LEFT, padx=5)
        self.result_preview_btn = ttk.Button(action_frame, text="📊 Полный предпросмотр (описание)",
                                             command=self.show_result_preview, state=tk.DISABLED)
        self.result_preview_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="💾 Сохранить результат (описание)", command=self.save_file).pack(side=tk.LEFT, padx=5)
        # Новая кнопка проверки по базе
        ttk.Button(action_frame, text="🔍 Проверка по базе", command=self.check_database).pack(side=tk.LEFT, padx=5)

        # ---------- Предпросмотр (первые 20 строк) ----------
        preview_frame = ttk.LabelFrame(main_frame, text="4. Предпросмотр (первые 20 строк)", padding="5")
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.tree = ttk.Treeview(preview_frame, columns=("original", "converted"), show="headings", height=10)
        self.tree.heading("original", text="Исходное описание")
        self.tree.heading("converted", text="Преобразованное")
        self.tree.column("original", width=400)
        self.tree.column("converted", width=400)

        scrollbar = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # ========== Загрузка и выбор данных ==========
    def load_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")])
        if not file_path:
            return

        self.file_path = file_path
        self.file_path_var.set(file_path)

        try:
            self.sheets = pd.ExcelFile(file_path).sheet_names
            self.sheet_cb['values'] = self.sheets
            if self.sheets:
                self.sheet_cb.set(self.sheets[0])
                self.on_sheet_selected()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{e}")

    def on_sheet_selected(self, event=None):
        sheet = self.sheet_cb.get()
        if not sheet:
            return
        self.selected_sheet = sheet
        try:
            self.df = pd.read_excel(self.file_path, sheet_name=sheet)
            self.column_cb['values'] = list(self.df.columns)
            if len(self.df.columns) > 0:
                self.column_cb.set(self.df.columns[0])
                self.on_column_selected()
            self.update_unknown_columns()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить лист:\n{e}")

    def on_column_selected(self, event=None):
        col = self.column_cb.get()
        if not col or col not in self.df.columns:
            return
        self.selected_column = col
        self.update_examples()

    def update_unknown_columns(self):
        columns = ["Оставить как есть"] + list(self.df.columns)
        self.unknown_column_cb['values'] = columns
        if "Оставить как есть" not in self.unknown_column_cb.get():
            self.unknown_column_cb.set("Оставить как есть")

    def on_unknown_column_selected(self, event=None):
        pass

    # ========== Разделитель ==========
    def on_separator_changed(self):
        if self.sep_var.get() == "custom":
            for entry in self.custom_sep_entries:
                entry.config(state=tk.NORMAL)
        else:
            for entry in self.custom_sep_entries:
                entry.config(state=tk.DISABLED)
            self.update_separators()

    def update_separators(self):
        sep_type = self.sep_var.get()
        if sep_type == "comma":
            self.separators = [","]
        elif sep_type == "space":
            self.separators = [" "]
        elif sep_type == "tab":
            self.separators = ["\t"]
        elif sep_type == "semicolon":
            self.separators = [";"]
        elif sep_type == "custom":
            sep_list = []
            for entry in self.custom_sep_entries:
                raw = entry.get().strip()
                if raw:
                    raw = raw.replace('\\p', ' ')
                    raw = raw.replace('\\t', '\t')
                    sep_list.append(raw)
            self.separators = sep_list if sep_list else [',']
        else:
            self.separators = [',']
        self.update_examples()

    def split_parts(self, text):
        """
        Разбивает строку по всем указанным разделителям, но не разбивает
        числа с плавающей точкой (ни с точкой, ни с запятой).
        """
        if not self.separators:
            return [text.strip()] if text.strip() else []

        # Заменяем десятичные точки и запятые на временные маркеры,
        # чтобы они не участвовали в разбиении
        text = re.sub(r'(\d+)\.(\d+)', lambda m: m.group(0).replace('.', '\x01'), text)
        text = re.sub(r'(\d+),(\d+)', lambda m: m.group(0).replace(',', '\x02'), text)

        parts = [text]
        for sep in self.separators:
            new_parts = []
            for p in parts:
                new_parts.extend([x.strip() for x in p.split(sep) if x.strip()])
            parts = new_parts

        # Восстанавливаем десятичные разделители
        restored = []
        for p in parts:
            p = p.replace('\x01', '.')
            p = p.replace('\x02', '.')
            restored.append(p)
        return restored

    # ========== Вкладки резисторов и конденсаторов ==========
    def create_resistor_tab(self, parent):
        frame = parent
        row = 0
        ttk.Label(frame, text="Ключевые слова для определения резистора (через запятую):").grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)
        self.resistor_keywords_entry = ttk.Entry(frame, width=50)
        self.resistor_keywords_entry.grid(row=row, column=1, padx=5, pady=2)
        self.resistor_keywords_entry.bind("<KeyRelease>", self.on_keywords_changed)
        row += 1

        ttk.Label(frame, text="Исключающие слова (через запятую):").grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)
        self.resistor_exclude_entry = ttk.Entry(frame, width=50)
        self.resistor_exclude_entry.grid(row=row, column=1, padx=5, pady=2)
        self.resistor_exclude_entry.bind("<KeyRelease>", self.on_keywords_changed)
        row += 1

        ttk.Label(frame, text="Выбрать пример из списка:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)
        self.resistor_example_cb = ttk.Combobox(frame, state="readonly", width=50)
        self.resistor_example_cb.grid(row=row, column=1, padx=5, pady=2)
        self.resistor_example_cb.bind("<<ComboboxSelected>>", self.on_resistor_example_selected)
        row += 1

        ttk.Label(frame, text="Выберите, какая часть содержит:").grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        row += 1

        ttk.Label(frame, text="Размер:").grid(row=row, column=0, sticky=tk.W, padx=5)
        self.resistor_size_cb = ttk.Combobox(frame, state="readonly", width=30)
        self.resistor_size_cb.grid(row=row, column=1, sticky=tk.W, padx=5)
        self.resistor_size_cb.bind("<<ComboboxSelected>>", self.on_resistor_selection)
        row += 1

        ttk.Label(frame, text="Номинал (с единицами):").grid(row=row, column=0, sticky=tk.W, padx=5)
        self.resistor_value_cb = ttk.Combobox(frame, state="readonly", width=30)
        self.resistor_value_cb.grid(row=row, column=1, sticky=tk.W, padx=5)
        self.resistor_value_cb.bind("<<ComboboxSelected>>", self.on_resistor_selection)
        row += 1

        ttk.Label(frame, text="Допуск:").grid(row=row, column=0, sticky=tk.W, padx=5)
        self.resistor_tolerance_cb = ttk.Combobox(frame, state="readonly", width=30)
        self.resistor_tolerance_cb.grid(row=row, column=1, sticky=tk.W, padx=5)
        self.resistor_tolerance_cb.bind("<<ComboboxSelected>>", self.on_resistor_selection)
        row += 1

        self.resistor_info = ttk.Label(frame, text="Выбрано: размер - не выбран, номинал - не выбран, допуск - не выбран")
        self.resistor_info.grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)

        ttk.Button(frame, text="Обновить список примеров", command=self.update_resistor_candidates).grid(row=row+1, column=0, columnspan=2, pady=5)

    def create_capacitor_tab(self, parent):
        frame = parent
        row = 0

        ttk.Label(frame, text="Ключевые слова для определения конденсатора (через запятую):").grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)
        self.capacitor_keywords_entry = ttk.Entry(frame, width=50)
        self.capacitor_keywords_entry.grid(row=row, column=1, padx=5, pady=2)
        self.capacitor_keywords_entry.bind("<KeyRelease>", self.on_keywords_changed)
        row += 1

        ttk.Label(frame, text="Исключающие слова (через запятую):").grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)
        self.capacitor_exclude_entry = ttk.Entry(frame, width=50)
        self.capacitor_exclude_entry.grid(row=row, column=1, padx=5, pady=2)
        self.capacitor_exclude_entry.bind("<KeyRelease>", self.on_keywords_changed)
        row += 1

        ttk.Label(frame, text="Выбрать пример из списка:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)
        self.capacitor_example_cb = ttk.Combobox(frame, state="readonly", width=50)
        self.capacitor_example_cb.grid(row=row, column=1, padx=5, pady=2)
        self.capacitor_example_cb.bind("<<ComboboxSelected>>", self.on_capacitor_example_selected)
        row += 1

        ttk.Label(frame, text="Выберите, какая часть содержит:").grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        row += 1

        ttk.Label(frame, text="Размер:").grid(row=row, column=0, sticky=tk.W, padx=5)
        self.capacitor_size_cb = ttk.Combobox(frame, state="readonly", width=30)
        self.capacitor_size_cb.grid(row=row, column=1, sticky=tk.W, padx=5)
        self.capacitor_size_cb.bind("<<ComboboxSelected>>", self.on_capacitor_selection)
        row += 1

        ttk.Label(frame, text="Диэлектрик:").grid(row=row, column=0, sticky=tk.W, padx=5)
        self.capacitor_dielectric_cb = ttk.Combobox(frame, state="readonly", width=30)
        self.capacitor_dielectric_cb.grid(row=row, column=1, sticky=tk.W, padx=5)
        self.capacitor_dielectric_cb.bind("<<ComboboxSelected>>", self.on_capacitor_selection)
        row += 1

        ttk.Label(frame, text="Номинал (с единицами):").grid(row=row, column=0, sticky=tk.W, padx=5)
        self.capacitor_value_cb = ttk.Combobox(frame, state="readonly", width=30)
        self.capacitor_value_cb.grid(row=row, column=1, sticky=tk.W, padx=5)
        self.capacitor_value_cb.bind("<<ComboboxSelected>>", self.on_capacitor_selection)
        row += 1

        ttk.Label(frame, text="Напряжение:").grid(row=row, column=0, sticky=tk.W, padx=5)
        self.capacitor_voltage_cb = ttk.Combobox(frame, state="readonly", width=30)
        self.capacitor_voltage_cb.grid(row=row, column=1, sticky=tk.W, padx=5)
        self.capacitor_voltage_cb.bind("<<ComboboxSelected>>", self.on_capacitor_selection)
        row += 1

        self.capacitor_info = ttk.Label(frame, text="Выбрано: размер - не выбран, диэлектрик - не выбран, номинал - не выбран, напряжение - не выбран")
        self.capacitor_info.grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)

        ttk.Button(frame, text="Обновить список примеров", command=self.update_capacitor_candidates).grid(row=row+1, column=0, columnspan=2, pady=5)

    # ========== Обработчики для описательной части ==========
    def on_keywords_changed(self, event=None):
        self.update_examples()

    def on_tab_changed(self, event=None):
        current = self.desc_notebook.index(self.desc_notebook.select())
        if current == 0:
            self.populate_resistor_combos()
        elif current == 1:
            self.populate_capacitor_combos()

    def get_component_type(self, text, res_keywords, cap_keywords, res_exclude, cap_exclude):
        text_lower = text.lower()
        is_resistor = False
        is_capacitor = False

        if res_exclude and any(excl in text_lower for excl in res_exclude):
            is_resistor = False
        else:
            is_resistor = any(kw in text_lower for kw in res_keywords)

        if cap_exclude and any(excl in text_lower for excl in cap_exclude):
            is_capacitor = False
        else:
            is_capacitor = any(kw in text_lower for kw in cap_keywords)

        if is_resistor and is_capacitor:
            return 'resistor'
        elif is_resistor:
            return 'resistor'
        elif is_capacitor:
            return 'capacitor'
        return None

    def has_relevant_pattern(self, parts, comp_type):
        if comp_type == 'resistor':
            patterns = [self.patterns['size'], self.patterns['value'], self.patterns['tolerance']]
        elif comp_type == 'capacitor':
            patterns = [self.patterns['size'], self.patterns['dielectric'], self.patterns['value'], self.patterns['voltage']]
        else:
            return False
        for part in parts:
            for pat in patterns:
                if pat.search(part):
                    return True
        return False

    def update_candidate_lists(self, res_keywords, cap_keywords, res_exclude, cap_exclude):
        self.resistor_candidates = []
        self.capacitor_candidates = []
        if self.df is None or self.selected_column is None:
            return
        for val in self.df[self.selected_column]:
            if pd.isna(val) or str(val).strip() == "":
                continue
            text = str(val).strip()
            detected = self.get_component_type(text, res_keywords, cap_keywords, res_exclude, cap_exclude)
            parts = self.split_parts(text)
            if detected == 'resistor':
                if self.has_relevant_pattern(parts, 'resistor'):
                    self.resistor_candidates.append((text, parts))
            elif detected == 'capacitor':
                if self.has_relevant_pattern(parts, 'capacitor'):
                    self.capacitor_candidates.append((text, parts))

    def update_examples(self):
        res_keywords = [kw.strip().lower() for kw in self.resistor_keywords_entry.get().split(",") if kw.strip()]
        res_exclude = [kw.strip().lower() for kw in self.resistor_exclude_entry.get().split(",") if kw.strip()]
        cap_keywords = [kw.strip().lower() for kw in self.capacitor_keywords_entry.get().split(",") if kw.strip()]
        cap_exclude = [kw.strip().lower() for kw in self.capacitor_exclude_entry.get().split(",") if kw.strip()]

        self.update_candidate_lists(res_keywords, cap_keywords, res_exclude, cap_exclude)

        res_display = [f"{i+1}: {text[:60]}" for i, (text, _) in enumerate(self.resistor_candidates)]
        self.resistor_example_cb['values'] = res_display
        cap_display = [f"{i+1}: {text[:60]}" for i, (text, _) in enumerate(self.capacitor_candidates)]
        self.capacitor_example_cb['values'] = cap_display

        if res_display:
            self.resistor_example_cb.set(res_display[0])
            self.selected_resistor_example = self.resistor_candidates[0]
            self.parts_example_resistor = self.resistor_candidates[0][1]
            repr_text = repr(self.resistor_candidates[0][0])
            self.example_label_resistor.config(text=f"Пример резистора: {repr_text}", foreground="black")
        else:
            self.resistor_example_cb.set("")
            self.selected_resistor_example = None
            self.parts_example_resistor = []
            self.example_label_resistor.config(text="Пример резистора: не найден", foreground="gray")

        if cap_display:
            self.capacitor_example_cb.set(cap_display[0])
            self.selected_capacitor_example = self.capacitor_candidates[0]
            self.parts_example_capacitor = self.capacitor_candidates[0][1]
            repr_text = repr(self.capacitor_candidates[0][0])
            self.example_label_capacitor.config(text=f"Пример конденсатора: {repr_text}", foreground="black")
        else:
            self.capacitor_example_cb.set("")
            self.selected_capacitor_example = None
            self.parts_example_capacitor = []
            self.example_label_capacitor.config(text="Пример конденсатора: не найден", foreground="gray")

        current = self.desc_notebook.index(self.desc_notebook.select())
        if current == 0:
            self.populate_resistor_combos()
        elif current == 1:
            self.populate_capacitor_combos()

    def on_resistor_example_selected(self, event=None):
        idx_str = self.resistor_example_cb.get().split(":")[0]
        try:
            idx = int(idx_str) - 1
            if 0 <= idx < len(self.resistor_candidates):
                self.selected_resistor_example = self.resistor_candidates[idx]
                self.parts_example_resistor = self.resistor_candidates[idx][1]
                repr_text = repr(self.resistor_candidates[idx][0])
                self.example_label_resistor.config(text=f"Пример резистора: {repr_text}", foreground="black")
                self.populate_resistor_combos()
        except:
            pass

    def on_capacitor_example_selected(self, event=None):
        idx_str = self.capacitor_example_cb.get().split(":")[0]
        try:
            idx = int(idx_str) - 1
            if 0 <= idx < len(self.capacitor_candidates):
                self.selected_capacitor_example = self.capacitor_candidates[idx]
                self.parts_example_capacitor = self.capacitor_candidates[idx][1]
                repr_text = repr(self.capacitor_candidates[idx][0])
                self.example_label_capacitor.config(text=f"Пример конденсатора: {repr_text}", foreground="black")
                self.populate_capacitor_combos()
        except:
            pass

    def update_resistor_candidates(self):
        self.update_examples()

    def update_capacitor_candidates(self):
        self.update_examples()

    def get_filtered_options(self, part_type, parts):
        if not parts:
            return ["Не выбрано"]
        pattern = self.patterns.get(part_type)
        if not pattern:
            return ["Не выбрано"] + [f"Часть {i}: {p}" for i, p in enumerate(parts)]

        matching = []
        for i, part in enumerate(parts):
            if pattern.search(part):
                matching.append(i)

        if not matching:
            return ["Не выбрано"] + [f"Часть {i}: {p}" for i, p in enumerate(parts)]

        options = ["Не выбрано"]
        for i in matching:
            options.append(f"Часть {i}: {parts[i]}")
        return options

    def populate_resistor_combos(self):
        parts = self.parts_example_resistor
        self.resistor_size_cb['values'] = self.get_filtered_options('size', parts)
        self.resistor_value_cb['values'] = self.get_filtered_options('value', parts)
        self.resistor_tolerance_cb['values'] = self.get_filtered_options('tolerance', parts)

        def restore(cb):
            current = cb.get()
            if current in cb['values']:
                cb.set(current)
            else:
                cb.set("Не выбрано")

        restore(self.resistor_size_cb)
        restore(self.resistor_value_cb)
        restore(self.resistor_tolerance_cb)
        self.update_resistor_info()

    def populate_capacitor_combos(self):
        parts = self.parts_example_capacitor
        self.capacitor_size_cb['values'] = self.get_filtered_options('size', parts)
        self.capacitor_dielectric_cb['values'] = self.get_filtered_options('dielectric', parts)
        self.capacitor_value_cb['values'] = self.get_filtered_options('value', parts)
        self.capacitor_voltage_cb['values'] = self.get_filtered_options('voltage', parts)

        def restore(cb):
            current = cb.get()
            if current in cb['values']:
                cb.set(current)
            else:
                cb.set("Не выбрано")

        restore(self.capacitor_size_cb)
        restore(self.capacitor_dielectric_cb)
        restore(self.capacitor_value_cb)
        restore(self.capacitor_voltage_cb)
        self.update_capacitor_info()

    def update_resistor_info(self):
        def get_idx(cb):
            val = cb.get()
            if val.startswith("Часть"):
                return int(val.split(":")[0].split()[1])
            return -1

        size_idx = get_idx(self.resistor_size_cb)
        value_idx = get_idx(self.resistor_value_cb)
        tol_idx = get_idx(self.resistor_tolerance_cb)
        info = f"Выбрано: размер - {size_idx if size_idx>=0 else 'не выбран'}, номинал - {value_idx if value_idx>=0 else 'не выбран'}, допуск - {tol_idx if tol_idx>=0 else 'не выбран'}"
        self.resistor_info.config(text=info)

    def update_capacitor_info(self):
        def get_idx(cb):
            val = cb.get()
            if val.startswith("Часть"):
                return int(val.split(":")[0].split()[1])
            return -1

        size_idx = get_idx(self.capacitor_size_cb)
        dielec_idx = get_idx(self.capacitor_dielectric_cb)
        value_idx = get_idx(self.capacitor_value_cb)
        volt_idx = get_idx(self.capacitor_voltage_cb)
        info = f"Выбрано: размер - {size_idx if size_idx>=0 else 'не выбран'}, диэлектрик - {dielec_idx if dielec_idx>=0 else 'не выбран'}, номинал - {value_idx if value_idx>=0 else 'не выбран'}, напряжение - {volt_idx if volt_idx>=0 else 'не выбран'}"
        self.capacitor_info.config(text=info)

    def on_resistor_selection(self, event=None):
        self.update_resistor_info()
        def get_idx(cb):
            val = cb.get()
            if val.startswith("Часть"):
                return int(val.split(":")[0].split()[1])
            return -1
        self.resistor_indices["size"] = get_idx(self.resistor_size_cb)
        self.resistor_indices["value"] = get_idx(self.resistor_value_cb)
        self.resistor_indices["tolerance"] = get_idx(self.resistor_tolerance_cb)

    def on_capacitor_selection(self, event=None):
        self.update_capacitor_info()
        def get_idx(cb):
            val = cb.get()
            if val.startswith("Часть"):
                return int(val.split(":")[0].split()[1])
            return -1
        self.capacitor_indices["size"] = get_idx(self.capacitor_size_cb)
        self.capacitor_indices["dielectric"] = get_idx(self.capacitor_dielectric_cb)
        self.capacitor_indices["value"] = get_idx(self.capacitor_value_cb)
        self.capacitor_indices["voltage"] = get_idx(self.capacitor_voltage_cb)

    # ========== Вспомогательные методы для единиц и допуска ==========
    def _find_adjacent_unit(self, parts, idx, unit_keywords):
        for offset in (-1, 1):
            neighbor_idx = idx + offset
            if 0 <= neighbor_idx < len(parts):
                neighbor = parts[neighbor_idx].strip()
                for kw in unit_keywords:
                    if kw.lower() in neighbor.lower():
                        return neighbor
        return None

    def _normalize_unit(self, unit_str, comp_type='capacitor'):
        unit = unit_str.strip().lower()
        if comp_type == 'capacitor':
            if unit in ('uf', 'мкф', 'µf', 'μf'):
                return 'uF'
            elif unit in ('nf', 'нф'):
                return 'nF'
            elif unit in ('pf', 'пф'):
                return 'pF'
            elif unit in ('f', 'ф'):
                return 'F'
            else:
                return unit
        else:  # resistor
            if unit in ('r', 'ом', 'ohm', 'ω', 'Ω'):
                return 'R'
            elif unit in ('k', 'к', 'кoм', 'kom', 'kohm'):
                return 'K'
            elif unit in ('m', 'м', 'мoм', 'mom', 'mohm'):
                return 'M'
            else:
                return unit

    def normalize_tolerance(self, tol_str):
        if not tol_str:
            return tol_str
        s = tol_str.strip()
        s = re.sub(r'\s+', '', s)
        s = re.sub(r'[±+]', '', s)
        match = re.search(r'(\d+\.?\d*)', s)
        if match:
            num = match.group(1)
            if not s.endswith('%'):
                s = num + '%'
            else:
                s = num + '%'
        else:
            pass
        return s

    # ========== NEW: парсинг кодового номинала (скопировано из VendorParser) ==========
    def _parse_resistor_code(self, raw):
        raw = raw.strip().upper()
        if raw == '000' or raw == '0' or raw == '0R':
            return '0R'
        if len(raw) == 3:
            if 'R' in raw:
                raw = raw.replace('R', '.')
                try:
                    val = float(raw)
                except:
                    val = 0
                if val < 1:
                    return f"{val:.3g}R"
                else:
                    return f"{val:.3g}R"
            else:
                try:
                    mantissa = int(raw[:2])
                    multiplier = int(raw[2])
                    val = mantissa * (10 ** multiplier)
                except:
                    return raw
                if val >= 1000000:
                    return f"{val/1000000:.3g}M"
                elif val >= 1000:
                    return f"{val/1000:.3g}K"
                else:
                    return f"{val:.3g}R"
        elif len(raw) == 4:
            if 'R' in raw:
                raw = raw.replace('R', '.')
                try:
                    val = float(raw)
                except:
                    val = 0
                if val < 1:
                    return f"{val:.3g}R"
                else:
                    return f"{val:.3g}R"
            else:
                try:
                    mantissa = int(raw[:3])
                    multiplier = int(raw[3])
                    val = mantissa * (10 ** multiplier)
                except:
                    return raw
                if val >= 1000000:
                    return f"{val/1000000:.3g}M"
                elif val >= 1000:
                    return f"{val/1000:.3g}K"
                else:
                    return f"{val:.3g}R"
        else:
            return raw

    def _parse_capacitor_code(self, raw):
        raw = raw.strip().upper()
        if 'R' in raw:
            raw = raw.replace('R', '.')
            try:
                val = float(raw)
            except:
                val = 0
            if val < 1:
                return f"{val:.2g}pF"
            elif val < 1000:
                if val.is_integer():
                    return f"{int(val)}pF"
                else:
                    return f"{val:.2g}pF"
            elif val < 1000000:
                val_nf = val / 1000
                if val_nf.is_integer():
                    return f"{int(val_nf)}nF"
                else:
                    return f"{val_nf:.2g}nF"
            else:
                val_uf = val / 1000000
                if val_uf.is_integer():
                    return f"{int(val_uf)}uF"
                else:
                    return f"{val_uf:.2g}uF"
        else:
            if len(raw) == 3:
                try:
                    mantissa = int(raw[:2])
                    multiplier = int(raw[2])
                    val = mantissa * (10 ** multiplier)
                except:
                    return raw
                if val < 1000:
                    if val.is_integer():
                        return f"{int(val)}pF"
                    else:
                        return f"{val:.2g}pF"
                elif val < 1000000:
                    val_nf = val / 1000
                    if val_nf.is_integer():
                        return f"{int(val_nf)}nF"
                    else:
                        return f"{val_nf:.2g}nF"
                else:
                    val_uf = val / 1000000
                    if val_uf.is_integer():
                        return f"{int(val_uf)}uF"
                    else:
                        return f"{val_uf:.2g}uF"
            else:
                return raw

    # ========== NEW: методы валидации и диалог редактирования ==========
    def _validate_resistor_name(self, name):
        pattern = r'^R_(?P<size>\d{4})_(?P<value>\d*\.?\d*[KMR]?)_(?P<tolerance>\d+\.?\d*%)$'
        m = re.match(pattern, name)
        if not m:
            return False, {}
        size = m.group('size')
        value = m.group('value')
        tol = m.group('tolerance')
        valid_sizes = ['0402','0603','0805','1206','0201','1210','2010','2512','1005']
        if size not in valid_sizes:
            return False, {'size': size}
        if not re.search(r'[KMR]$', value) and not re.search(r'\d+\.?\d*R', value):
            return False, {'value': value}
        if tol not in self.VALID_TOLERANCES:
            return False, {'tolerance': tol}
        return True, {}

    def _validate_capacitor_name(self, name):
        pattern = r'^C_(?P<size>\d{4})_(?P<dielectric>[A-Z0-9]+)_(?P<value>\d*\.?\d*[uUnNpP]?F)_(?P<voltage>\d*\.?\d*[A-Z]*V?)$'
        m = re.match(pattern, name)
        if not m:
            return False, {}
        size = m.group('size')
        dielectric = m.group('dielectric')
        value = m.group('value')
        voltage = m.group('voltage')
        valid_sizes = ['0402','0603','0805','1206','0201','1210','2010','2512','1005']
        valid_dielectrics = ['X5R','X7R','C0G','NPO','X6S','X8R','Y5V','X7S','X6T','X5S','X7T','X8L']
        if size not in valid_sizes:
            return False, {'size': size}
        if dielectric not in valid_dielectrics:
            return False, {'dielectric': dielectric}
        if not re.search(r'[uUnNpP]F$', value):
            return False, {'value': value}
        if voltage not in self.VALID_VOLTAGES:
            return False, {'voltage': voltage}
        return True, {}

    def _show_edit_dialog(self, original_text, current_name, comp_type):
        dialog = tk.Toplevel(self)
        dialog.title(f"Редактирование {comp_type}")
        dialog.geometry("700x500")
        dialog.transient(self)
        dialog.grab_set()

        if comp_type == 'resistor':
            parts = current_name.split('_')
            default_size = parts[1] if len(parts) > 1 else ''
            default_value = parts[2] if len(parts) > 2 else ''
            default_tol = parts[3] if len(parts) > 3 else ''
            labels = ['Размер', 'Номинал', 'Допуск']
            default_values = [default_size, default_value, default_tol]
            keys = ['size', 'value', 'tolerance']
        else:
            parts = current_name.split('_')
            default_size = parts[1] if len(parts) > 1 else ''
            default_diel = parts[2] if len(parts) > 2 else ''
            default_value = parts[3] if len(parts) > 3 else ''
            default_volt = parts[4] if len(parts) > 4 else ''
            labels = ['Размер', 'Диэлектрик', 'Номинал', 'Напряжение']
            default_values = [default_size, default_diel, default_value, default_volt]
            keys = ['size', 'dielectric', 'value', 'voltage']

        info_frame = ttk.Frame(dialog)
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(info_frame, text=f"Исходное описание: {original_text}").pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"Текущее имя: {current_name}").pack(anchor=tk.W)

        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        entries = {}
        for i, (label, default) in enumerate(zip(labels, default_values)):
            ttk.Label(main_frame, text=label + ":").grid(row=i, column=0, padx=5, pady=5, sticky=tk.W)
            entry = ttk.Entry(main_frame, width=20)
            entry.insert(0, default)
            entry.grid(row=i, column=1, padx=5, pady=5, sticky=tk.W)
            entries[keys[i]] = entry

        ttk.Label(main_frame, text="Или введите полное имя:").grid(row=len(labels), column=0, padx=5, pady=5, sticky=tk.W)
        full_name_entry = ttk.Entry(main_frame, width=40)
        full_name_entry.grid(row=len(labels), column=1, padx=5, pady=5, sticky=tk.W)

        preview_label = ttk.Label(dialog, text="Предпросмотр: " + current_name, foreground="blue")
        preview_label.pack(pady=5)

        def update_preview(*args):
            if full_name_entry.get().strip():
                new_name = full_name_entry.get().strip()
            else:
                if comp_type == 'resistor':
                    size = entries['size'].get().strip()
                    value = entries['value'].get().strip()
                    tol = entries['tolerance'].get().strip()
                    new_name = f"R_{size}_{value}_{tol}" if size and value and tol else current_name
                else:
                    size = entries['size'].get().strip()
                    diel = entries['dielectric'].get().strip()
                    value = entries['value'].get().strip()
                    volt = entries['voltage'].get().strip()
                    new_name = f"C_{size}_{diel}_{value}_{volt}" if size and diel and value and volt else current_name
            preview_label.config(text="Предпросмотр: " + new_name)

        for entry in entries.values():
            entry.bind('<KeyRelease>', update_preview)
        full_name_entry.bind('<KeyRelease>', update_preview)

        result = {'new_name': None}

        def on_apply():
            if full_name_entry.get().strip():
                result['new_name'] = full_name_entry.get().strip()
            else:
                if comp_type == 'resistor':
                    size = entries['size'].get().strip()
                    value = entries['value'].get().strip()
                    tol = entries['tolerance'].get().strip()
                    if size and value and tol:
                        result['new_name'] = f"R_{size}_{value}_{tol}"
                else:
                    size = entries['size'].get().strip()
                    diel = entries['dielectric'].get().strip()
                    value = entries['value'].get().strip()
                    volt = entries['voltage'].get().strip()
                    if size and diel and value and volt:
                        result['new_name'] = f"C_{size}_{diel}_{value}_{volt}"
            dialog.destroy()

        def on_skip():
            result['new_name'] = None
            dialog.destroy()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="Применить", command=on_apply).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Оставить как есть", command=on_skip).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Отмена (не менять)", command=on_skip).pack(side=tk.LEFT, padx=5)

        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")

        self.wait_window(dialog)
        return result['new_name']

    # ========== Очистка и преобразование ==========
    def reset_conversion(self):
        if self.df is not None:
            cols_to_drop = [col for col in self.df.columns if col.startswith("Converted_Description")]
            if cols_to_drop:
                self.df.drop(columns=cols_to_drop, inplace=True)
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.skip_all_resistor = False
        self.skip_all_capacitor = False
        self.result_preview_btn.config(state=tk.DISABLED)
        self.user_defined_names = {}
        self.converted_column = None
        self.user_overrides_resistor = {}
        self.user_overrides_capacitor = {}

    def clean_part(self, part, part_type):
        if part is None:
            return None
        part = part.strip()
        part = re.sub(r'\s+', '', part)
        part = part.replace('µ', 'u').replace('μ', 'u')

        if part_type == 'value':
            part = part.replace(',', '.')

        if part_type == 'value' or part_type == 'voltage':
            part = re.sub(r'(?i)мкф', 'uF', part)
            part = re.sub(r'(?i)нф', 'nF', part)
            part = re.sub(r'(?i)пф', 'pF', part)
            part = re.sub(r'(?i)ф', 'F', part)
            part = re.sub(r'(?i)ом', 'R', part)
            part = re.sub(r'(?i)к(?:о?м)?', 'K', part)
            part = re.sub(r'(?i)м(?:о?м)?', 'M', part)
            part = re.sub(r'(?i)в', 'V', part)  # кириллическая В -> V

        if part_type == 'dielectric':
            pass

        if part_type == 'size':
            m = self.clean_patterns['size'].search(part)
            if m:
                return m.group(1).upper()
            return ''
        elif part_type == 'dielectric':
            m = self.clean_patterns['dielectric'].search(part)
            if m:
                return m.group(1).upper()
            return part
        elif part_type == 'voltage':
            if 'кВ' in part or 'kV' in part:
                m = re.search(r'(\d+\.?\d*)\s*[кk]В', part)
                if m:
                    return m.group(1) + 'kV'
            if 'AC' in part and ('V' in part or 'В' in part):
                m = re.search(r'AC\s*(\d+\.?\d*)\s*[VВ]', part, re.IGNORECASE)
                if m:
                    return 'AC' + m.group(1) + 'V'
            m = self.clean_patterns['voltage'].search(part)
            if m:
                return m.group(1) + 'V'
            nums = re.search(r'(\d+\.?\d*)', part)
            if nums:
                return nums.group(1) + 'V'
            return part
        elif part_type == 'tolerance':
            m = self.clean_patterns['tolerance'].search(part)
            if m:
                return m.group(1)
            nums = re.search(r'([+-]?\d+\.?\d*)\s*%?', part)
            if nums:
                return nums.group(1) + '%'
            return part
        elif part_type == 'value':
            return part
        return part

    def convert_resistor_value(self, value_str):
        s = value_str.replace(" ", "")
        s = re.sub(r'(?i)ом', 'R', s)
        s = re.sub(r'(?i)к(?:о?м)?', 'K', s)
        s = re.sub(r'(?i)м(?:о?м)?', 'M', s)
        s = re.sub(r'(?i)ohm|Ω', 'R', s)
        s = re.sub(r'(?i)KR', 'K', s)
        s = re.sub(r'(?i)MR', 'M', s)
        s = re.sub(r'(?i)GR', 'G', s)
        s = re.sub(r'(?i)k', 'K', s)
        s = re.sub(r'(?i)в', 'V', s)
        return s

    # ========== Диалог ручного именования (с переопределением) ==========
    def ask_user_for_name(self, original_text, comp_type, parts=None):
        if comp_type == "резистор" and self.skip_all_resistor:
            return None
        if comp_type == "конденсатор" and self.skip_all_capacitor:
            return None

        root = tk.Toplevel(self)
        root.title(f"Ручное именование {comp_type}")
        root.geometry("600x300")

        ttk.Label(root, text=f"Строка определена как {comp_type}, но не удалось извлечь все части.").pack(pady=5)
        ttk.Label(root, text=f"Оригинал: {original_text[:80]}").pack(pady=5)
        if parts is not None:
            ttk.Label(root, text=f"Разбиение: {parts}").pack(pady=5)

        ttk.Label(root, text="Введите название (или оставьте пустым для 'неопределённых'):").pack(pady=5)

        entry = ttk.Entry(root, width=60)
        entry.pack(pady=5)

        result = {"value": None, "skip_all": False, "redefine": False}

        def on_ok():
            val = entry.get().strip()
            result["value"] = val if val else None
            root.destroy()

        def on_skip_all():
            result["value"] = None
            result["skip_all"] = True
            root.destroy()

        def on_cancel():
            result["value"] = None
            root.destroy()

        def on_redefine():
            result["redefine"] = True
            result["value"] = None
            root.destroy()

        button_frame = ttk.Frame(root)
        button_frame.pack(pady=10)

        ttk.Button(button_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Пропустить всё", command=on_skip_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Переопределить параметры", command=on_redefine).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Отмена (оставить как есть)", command=on_cancel).pack(side=tk.LEFT, padx=5)

        root.transient(self)
        root.grab_set()
        self.wait_window(root)

        if result.get("skip_all", False):
            if comp_type == "резистор":
                self.skip_all_resistor = True
            elif comp_type == "конденсатор":
                self.skip_all_capacitor = True
            return None

        if result.get("redefine", False):
            if parts is None:
                parts = self.split_parts(original_text)
            if comp_type == "резистор":
                current_indices = self.resistor_indices.copy()
            else:
                current_indices = self.capacitor_indices.copy()
            new_indices = self.show_fix_dialog_for_single(
                original_text, comp_type, parts, current_indices
            )
            if new_indices is not None:
                key = self._get_pattern_key(original_text, comp_type)
                if comp_type == "резистор":
                    self.user_overrides_resistor[key] = new_indices
                else:
                    self.user_overrides_capacitor[key] = new_indices
                return None
            else:
                return None

        return result["value"]

    # ========== Диалог переопределения для одной строки ==========
    def show_fix_dialog_for_single(self, original_text, comp_type, parts, current_indices):
        dialog = tk.Toplevel(self)
        dialog.title(f"Переопределение параметров для {comp_type}")
        dialog.geometry("700x500")
        dialog.transient(self)
        dialog.grab_set()

        info_frame = ttk.Frame(dialog)
        info_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(info_frame, text=f"Строка: {original_text[:80]}").pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"Разбиение: {parts}").pack(anchor=tk.W)

        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        if comp_type == 'resistor':
            labels = ["Размер:", "Номинал:", "Допуск:"]
            keys = ["size", "value", "tolerance"]
        else:
            labels = ["Размер:", "Диэлектрик:", "Номинал:", "Напряжение:"]
            keys = ["size", "dielectric", "value", "voltage"]

        combos = {}
        for i, (label, key) in enumerate(zip(labels, keys)):
            ttk.Label(main_frame, text=label).grid(row=i, column=0, padx=5, pady=5, sticky=tk.W)
            cb = ttk.Combobox(main_frame, state="readonly", width=50)
            options = ["Не выбрано"] + [f"Часть {j}: {p}" for j, p in enumerate(parts)]
            cb['values'] = options
            if current_indices.get(key, -1) >= 0:
                idx_orig = current_indices[key]
                if 0 <= idx_orig < len(parts):
                    cb.set(f"Часть {idx_orig}: {parts[idx_orig]}")
                else:
                    cb.set("Не выбрано")
            else:
                cb.set("Не выбрано")
            cb.grid(row=i, column=1, padx=5, pady=5, sticky=tk.W)
            combos[key] = cb

        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, pady=10)

        result = {"indices": None}

        def on_apply():
            new_indices = {}
            for key, cb in combos.items():
                val = cb.get()
                if val.startswith("Часть"):
                    idx = int(val.split(":")[0].split()[1])
                    new_indices[key] = idx
                else:
                    new_indices[key] = -1
            result["indices"] = new_indices
            dialog.destroy()

        def on_cancel():
            result["indices"] = None
            dialog.destroy()

        ttk.Button(button_frame, text="Применить", command=on_apply).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Отмена", command=on_cancel).pack(side=tk.LEFT, padx=5)

        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")

        self.wait_window(dialog)
        return result["indices"]

    # ========== Формирование ключа для переопределения ==========
    def _get_pattern_key(self, text, comp_type):
        parts = self.split_parts(text)
        keywords = []
        for p in parts:
            if re.search(r'[A-Za-z]', p) and not re.search(r'\d', p):
                keywords.append(p.strip())
            if len(keywords) >= 2:
                break
        if not keywords:
            keywords = parts[:2] if len(parts) >= 2 else parts
        return ", ".join(keywords)

    # ========== ИСПРАВЛЕННЫЙ МЕТОД apply_rules ==========
    def apply_rules(self):
        if self.df is None or self.selected_column is None:
            messagebox.showwarning("Предупреждение", "Сначала загрузите файл и выберите столбец с описанием.")
            return

        res_keywords = [kw.strip().lower() for kw in self.resistor_keywords_entry.get().split(",") if kw.strip()]
        res_exclude = [kw.strip().lower() for kw in self.resistor_exclude_entry.get().split(",") if kw.strip()]
        cap_keywords = [kw.strip().lower() for kw in self.capacitor_keywords_entry.get().split(",") if kw.strip()]
        cap_exclude = [kw.strip().lower() for kw in self.capacitor_exclude_entry.get().split(",") if kw.strip()]

        r_size = self.resistor_indices["size"]
        r_val = self.resistor_indices["value"]
        r_tol = self.resistor_indices["tolerance"]
        if r_size < 0 or r_val < 0 or r_tol < 0:
            if not messagebox.askyesno("Предупреждение", "Для резисторов не выбраны все параметры (размер, номинал, допуск). Продолжить?"):
                return

        c_size = self.capacitor_indices["size"]
        c_diel = self.capacitor_indices["dielectric"]
        c_val = self.capacitor_indices["value"]
        c_volt = self.capacitor_indices["voltage"]
        if c_size < 0 or c_diel < 0 or c_val < 0 or c_volt < 0:
            if not messagebox.askyesno("Предупреждение", "Для конденсаторов не выбраны все параметры (размер, диэлектрик, номинал, напряжение). Продолжить?"):
                return

        unknown_col = self.unknown_column_cb.get()
        if unknown_col == "Оставить как есть":
            unknown_col = None
        elif unknown_col not in self.df.columns:
            unknown_col = None

        new_column_name = "Converted_Description"
        if new_column_name in self.df.columns:
            i = 1
            while f"{new_column_name}_{i}" in self.df.columns:
                i += 1
            new_column_name = f"{new_column_name}_{i}"

        self.converted_column = new_column_name
        all_converted = []
        original_descriptions = []

        error_info = []

        for idx, value in enumerate(self.df[self.selected_column]):
            if pd.isna(value) or str(value).strip() == "":
                all_converted.append("")
                original_descriptions.append("")
                continue

            original = str(value).strip()
            original_descriptions.append(original)
            parts = self.split_parts(original)
            text_lower = original.lower()

            is_resistor = False
            is_capacitor = False
            if res_exclude and any(excl in text_lower for excl in res_exclude):
                is_resistor = False
            else:
                is_resistor = any(kw in text_lower for kw in res_keywords)
            if cap_exclude and any(excl in text_lower for excl in cap_exclude):
                is_capacitor = False
            else:
                is_capacitor = any(kw in text_lower for kw in cap_keywords)

            key = self._get_pattern_key(original, 'resistor' if is_resistor else 'capacitor')

            if is_resistor:
                if key in self.user_overrides_resistor:
                    override = self.user_overrides_resistor[key]
                    r_size_cur = override.get("size", r_size)
                    r_val_cur = override.get("value", r_val)
                    r_tol_cur = override.get("tolerance", r_tol)
                else:
                    r_size_cur, r_val_cur, r_tol_cur = r_size, r_val, r_tol
            else:
                r_size_cur, r_val_cur, r_tol_cur = r_size, r_val, r_tol

            if is_capacitor:
                if key in self.user_overrides_capacitor:
                    override = self.user_overrides_capacitor[key]
                    c_size_cur = override.get("size", c_size)
                    c_diel_cur = override.get("dielectric", c_diel)
                    c_val_cur = override.get("value", c_val)
                    c_volt_cur = override.get("voltage", c_volt)
                else:
                    c_size_cur, c_diel_cur, c_val_cur, c_volt_cur = c_size, c_diel, c_val, c_volt
            else:
                c_size_cur, c_diel_cur, c_val_cur, c_volt_cur = c_size, c_diel, c_val, c_volt

            used_indices = {}
            if is_resistor:
                used_indices = {"size": r_size_cur, "value": r_val_cur, "tolerance": r_tol_cur}
            elif is_capacitor:
                used_indices = {"size": c_size_cur, "dielectric": c_diel_cur, "value": c_val_cur, "voltage": c_volt_cur}

            if is_resistor:
                size = self.get_part(parts, r_size_cur)
                value_part = self.get_part(parts, r_val_cur)
                tolerance = self.get_part(parts, r_tol_cur)

                size_clean = self.clean_part(size, 'size') if size is not None else ''
                value_clean = self.clean_part(value_part, 'value') if value_part is not None else ''
                tolerance_clean = self.clean_part(tolerance, 'tolerance') if tolerance is not None else ''

                if self.nominal_code_var.get() and value_clean.isdigit() and len(value_clean) in (3, 4):
                    value_clean = self._parse_resistor_code(value_clean)

                if not re.search(r'[KkMmRrΩ]', value_clean):
                    unit = self._find_adjacent_unit(parts, r_val_cur, ['r','k','m','ом','ohm','ω','Ω'])
                    if unit:
                        norm_unit = self._normalize_unit(unit, comp_type='resistor')
                        value_clean = value_clean + norm_unit

                if tolerance_clean:
                    if '%' in tolerance_clean and not re.search(r'\d', tolerance_clean):
                        for offset in (-1, 1):
                            neighbor_idx = r_tol_cur + offset
                            if 0 <= neighbor_idx < len(parts):
                                neighbor = parts[neighbor_idx].strip()
                                nums = re.search(r'(\d+\.?\d*)', neighbor)
                                if nums:
                                    number = nums.group(1)
                                    tolerance_clean = number + '%'
                                    break
                    elif re.search(r'\d', tolerance_clean) and not re.search(r'%', tolerance_clean):
                        for offset in (-1, 1):
                            neighbor_idx = r_tol_cur + offset
                            if 0 <= neighbor_idx < len(parts):
                                neighbor = parts[neighbor_idx].strip()
                                if '%' in neighbor:
                                    tolerance_clean = tolerance_clean + '%'
                                    break

                tolerance_clean = self.normalize_tolerance(tolerance_clean)

                if not (size_clean and value_clean and tolerance_clean):
                    error_info.append((idx, parts, "resistor", key, used_indices))
                    all_converted.append(original)
                    continue
                else:
                    value_converted = self.convert_resistor_value(value_clean)
                    unified = f"R_{size_clean}_{value_converted}_{tolerance_clean}"
                    valid_sizes = ['0402','0603','0805','1206','0201','1210','2010','2512','1005']
                    if size_clean not in valid_sizes or not re.search(r'\d+%', tolerance_clean):
                        error_info.append((idx, parts, "resistor", key, used_indices))
                        all_converted.append(original)
                        continue
                    all_converted.append(unified)

            elif is_capacitor:
                size = self.get_part(parts, c_size_cur)
                dielectric = self.get_part(parts, c_diel_cur)
                value_part = self.get_part(parts, c_val_cur)
                voltage = self.get_part(parts, c_volt_cur)

                size_clean = self.clean_part(size, 'size') if size is not None else ''
                dielectric_clean = self.clean_part(dielectric, 'dielectric') if dielectric is not None else ''
                value_clean = self.clean_part(value_part, 'value') if value_part is not None else ''
                voltage_clean = self.clean_part(voltage, 'voltage') if voltage is not None else ''

                if self.nominal_code_var.get() and value_clean.isdigit() and len(value_clean) in (3, 4):
                    value_clean = self._parse_capacitor_code(value_clean)

                if not re.search(r'[Ffф]', value_clean):
                    unit = self._find_adjacent_unit(parts, c_val_cur, ['uf','мкф','µf','μf','nf','нф','pf','пф','f','ф'])
                    if unit:
                        norm_unit = self._normalize_unit(unit, comp_type='capacitor')
                        value_clean = value_clean + norm_unit

                if not re.search(r'[VvВв]', voltage_clean):
                    unit = self._find_adjacent_unit(parts, c_volt_cur, ['v','в','вольт','volt'])
                    if unit:
                        voltage_clean = voltage_clean + 'V'
                    else:
                        voltage_clean = voltage_clean + 'V'

                if not (size_clean and dielectric_clean and value_clean and voltage_clean):
                    error_info.append((idx, parts, "capacitor", key, used_indices))
                    all_converted.append(original)
                    continue
                else:
                    unified = f"C_{size_clean}_{dielectric_clean}_{value_clean}_{voltage_clean}"
                    valid_sizes = ['0402','0603','0805','1206','0201','1210','2010','2512','1005']
                    valid_dielectrics = ['X5R','X7R','C0G','NPO','X6S','X8R','Y5V','X7S','X6T','X5S','X7T','X8L']
                    if size_clean not in valid_sizes or dielectric_clean not in valid_dielectrics or not re.search(r'[uUnNpP]?F', value_clean) or not re.search(r'\d+V', voltage_clean):
                        error_info.append((idx, parts, "capacitor", key, used_indices))
                        all_converted.append(original)
                        continue
                    all_converted.append(unified)

            else:
                if unknown_col is not None:
                    other_val = self.df.loc[idx, unknown_col]
                    all_converted.append(str(other_val) if pd.notna(other_val) else "")
                else:
                    all_converted.append(original)

        if error_info:
            groups = {}
            for idx, parts, comp_type, key, used_indices in error_info:
                group_key = (comp_type, key)
                if group_key not in groups:
                    groups[group_key] = []
                groups[group_key].append((idx, parts, used_indices))

            for (comp_type, key), items in groups.items():
                first_idx, first_parts, first_used_indices = items[0]
                first_original = self.df.loc[first_idx, self.selected_column]
                new_indices = self.show_fix_dialog_for_single(
                    first_original, comp_type, first_parts, first_used_indices
                )
                if new_indices is not None:
                    if comp_type == "resistor":
                        self.user_overrides_resistor[key] = new_indices
                    else:
                        self.user_overrides_capacitor[key] = new_indices

                    for idx, parts, _ in items:
                        if comp_type == "resistor":
                            r_size_cur = new_indices.get("size", -1)
                            r_val_cur = new_indices.get("value", -1)
                            r_tol_cur = new_indices.get("tolerance", -1)
                            if r_size_cur < 0 or r_val_cur < 0 or r_tol_cur < 0:
                                continue
                            size = self.get_part(parts, r_size_cur)
                            value_part = self.get_part(parts, r_val_cur)
                            tolerance = self.get_part(parts, r_tol_cur)
                            size_clean = self.clean_part(size, 'size') if size is not None else ''
                            value_clean = self.clean_part(value_part, 'value') if value_part is not None else ''
                            tolerance_clean = self.clean_part(tolerance, 'tolerance') if tolerance is not None else ''
                            if self.nominal_code_var.get() and value_clean.isdigit() and len(value_clean) in (3, 4):
                                value_clean = self._parse_resistor_code(value_clean)
                            if not re.search(r'[KkMmRrΩ]', value_clean):
                                unit = self._find_adjacent_unit(parts, r_val_cur, ['r','k','m','ом','ohm','ω','Ω'])
                                if unit:
                                    norm_unit = self._normalize_unit(unit, comp_type='resistor')
                                    value_clean = value_clean + norm_unit
                            if tolerance_clean:
                                if '%' in tolerance_clean and not re.search(r'\d', tolerance_clean):
                                    for offset in (-1, 1):
                                        neighbor_idx = r_tol_cur + offset
                                        if 0 <= neighbor_idx < len(parts):
                                            neighbor = parts[neighbor_idx].strip()
                                            nums = re.search(r'(\d+\.?\d*)', neighbor)
                                            if nums:
                                                number = nums.group(1)
                                                tolerance_clean = number + '%'
                                                break
                                elif re.search(r'\d', tolerance_clean) and not re.search(r'%', tolerance_clean):
                                    for offset in (-1, 1):
                                        neighbor_idx = r_tol_cur + offset
                                        if 0 <= neighbor_idx < len(parts):
                                            neighbor = parts[neighbor_idx].strip()
                                            if '%' in neighbor:
                                                tolerance_clean = tolerance_clean + '%'
                                                break
                            tolerance_clean = self.normalize_tolerance(tolerance_clean)
                            if size_clean and value_clean and tolerance_clean:
                                value_converted = self.convert_resistor_value(value_clean)
                                unified = f"R_{size_clean}_{value_converted}_{tolerance_clean}"
                                all_converted[idx] = unified
                        else:
                            c_size_cur = new_indices.get("size", -1)
                            c_diel_cur = new_indices.get("dielectric", -1)
                            c_val_cur = new_indices.get("value", -1)
                            c_volt_cur = new_indices.get("voltage", -1)
                            if c_size_cur < 0 or c_diel_cur < 0 or c_val_cur < 0 or c_volt_cur < 0:
                                continue
                            size = self.get_part(parts, c_size_cur)
                            dielectric = self.get_part(parts, c_diel_cur)
                            value_part = self.get_part(parts, c_val_cur)
                            voltage = self.get_part(parts, c_volt_cur)
                            size_clean = self.clean_part(size, 'size') if size is not None else ''
                            dielectric_clean = self.clean_part(dielectric, 'dielectric') if dielectric is not None else ''
                            value_clean = self.clean_part(value_part, 'value') if value_part is not None else ''
                            voltage_clean = self.clean_part(voltage, 'voltage') if voltage is not None else ''
                            if self.nominal_code_var.get() and value_clean.isdigit() and len(value_clean) in (3, 4):
                                value_clean = self._parse_capacitor_code(value_clean)
                            if not re.search(r'[Ffф]', value_clean):
                                unit = self._find_adjacent_unit(parts, c_val_cur, ['uf','мкф','µf','μf','nf','нф','pf','пф','f','ф'])
                                if unit:
                                    norm_unit = self._normalize_unit(unit, comp_type='capacitor')
                                    value_clean = value_clean + norm_unit
                            if not re.search(r'[VvВв]', voltage_clean):
                                unit = self._find_adjacent_unit(parts, c_volt_cur, ['v','в','вольт','volt'])
                                if unit:
                                    voltage_clean = voltage_clean + 'V'
                                else:
                                    voltage_clean = voltage_clean + 'V'
                            if size_clean and dielectric_clean and value_clean and voltage_clean:
                                unified = f"C_{size_clean}_{dielectric_clean}_{value_clean}_{voltage_clean}"
                                all_converted[idx] = unified

        # ---- ДОБАВЛЕНО: проверка базы данных и замена ----
        original_values = [str(x) if pd.notna(x) else "" for x in self.df[self.selected_column]]
        all_converted = self.apply_database_replacements(original_values, all_converted)

        self.df[new_column_name] = all_converted
        self.update_preview(new_column_name)
        self.result_preview_btn.config(state=tk.NORMAL)

    # ========== НОВЫЙ МЕТОД: применение замен из базы данных ==========
    def apply_database_replacements(self, original_values, converted_values):
        """
        Проверяет, есть ли для каждого исходного значения пользовательское имя в базе.
        Если есть и оно отличается от сгенерированного, предлагает заменить.
        Возвращает новый список converted_values с применёнными заменами.
        """
        replacements = []
        for orig, conv in zip(original_values, converted_values):
            if not orig:
                continue
            user_name = self.db_manager.get(orig)
            if user_name and user_name != conv:
                replacements.append((orig, conv, user_name))

        if not replacements:
            return converted_values

        # Показываем диалог предпросмотра
        result = self._show_replacement_dialog(replacements)
        if result:  # Применить замены
            new_converted = converted_values[:]
            # Заменяем только те, которые есть в списке replacements
            for orig, conv, user_name in replacements:
                # Ищем все вхождения этого orig и conv (может быть несколько одинаковых)
                for i, (o, c) in enumerate(zip(original_values, new_converted)):
                    if o == orig and c == conv:
                        new_converted[i] = user_name
            return new_converted
        else:
            return converted_values

    # ========== НОВЫЙ МЕТОД: проверка по базе (добавлен) ==========
    def check_database(self):
        """Ручная проверка преобразованного BOM по базе данных с перезаписью ячеек."""
        if self.df is None:
            messagebox.showinfo("Информация", "Сначала загрузите файл.")
            return
        if self.converted_column is None or self.converted_column not in self.df.columns:
            messagebox.showwarning("Предупреждение", "Сначала примените правила преобразования (кнопка 'Применить правила').")
            return

        # Диалог выбора столбцов
        dialog = tk.Toplevel(self)
        dialog.title("Проверка по базе данных")
        dialog.geometry("500x350")
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="Выберите столбец с исходными названиями (ключи):").pack(pady=5)
        key_col_var = tk.StringVar(value=self.selected_column)
        key_combo = ttk.Combobox(dialog, textvariable=key_col_var, values=list(self.df.columns), state="readonly")
        key_combo.pack(pady=5)

        ttk.Label(dialog, text="Выберите столбец для замены (сгенерированные имена):").pack(pady=5)
        val_col_var = tk.StringVar(value=self.converted_column)
        val_combo = ttk.Combobox(dialog, textvariable=val_col_var, values=list(self.df.columns), state="readonly")
        val_combo.pack(pady=5)

        # Предпросмотр первых 10 замен
        preview_frame = ttk.LabelFrame(dialog, text="Предпросмотр (первые 10 строк)", padding="5")
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        preview_tree = ttk.Treeview(preview_frame, columns=("key", "current", "user"), show="headings", height=6)
        preview_tree.heading("key", text="Ключ")
        preview_tree.heading("current", text="Текущее значение")
        preview_tree.heading("user", text="Пользовательское (из базы)")
        preview_tree.column("key", width=150)
        preview_tree.column("current", width=150)
        preview_tree.column("user", width=150)
        preview_tree.pack(fill=tk.BOTH, expand=True)

        def update_preview(*args):
            for item in preview_tree.get_children():
                preview_tree.delete(item)
            key_col = key_col_var.get()
            val_col = val_col_var.get()
            if not key_col or not val_col or key_col == val_col:
                return
            count = 0
            for idx, row in self.df.iterrows():
                if count >= 10:
                    break
                key = str(row[key_col]) if pd.notna(row[key_col]) else ""
                curr = str(row[val_col]) if pd.notna(row[val_col]) else ""
                if key and curr:
                    user_name = self.db_manager.get(key)
                    if user_name and user_name != curr:
                        preview_tree.insert("", tk.END, values=(key, curr, user_name))
                        count += 1
            if count == 0:
                preview_tree.insert("", tk.END, values=("Нет совпадений", "", ""))

        key_combo.bind("<<ComboboxSelected>>", update_preview)
        val_combo.bind("<<ComboboxSelected>>", update_preview)
        update_preview()

        def on_ok():
            key_col = key_col_var.get()
            val_col = val_col_var.get()
            if not key_col or not val_col:
                messagebox.showerror("Ошибка", "Выберите оба столбца.")
                return
            if key_col == val_col:
                messagebox.showerror("Ошибка", "Столбцы должны быть разными.")
                return

            # Собираем данные
            original_values = [str(x) if pd.notna(x) else "" for x in self.df[key_col]]
            current_values = [str(x) if pd.notna(x) else "" for x in self.df[val_col]]

            # Формируем список замен
            replacements = []
            for i, (orig, curr) in enumerate(zip(original_values, current_values)):
                if not orig:
                    continue
                user_name = self.db_manager.get(orig)
                if user_name and user_name != curr:
                    replacements.append((orig, curr, user_name))

            if not replacements:
                messagebox.showinfo("Информация", "Нет совпадений с базой данных для замены.")
                dialog.destroy()
                return

            # Показываем диалог с таблицей замен
            result = self._show_replacement_dialog(replacements)
            if result:
                # Применяем замены – перезаписываем значения в выбранном столбце
                new_values = current_values[:]
                for orig, curr, user_name in replacements:
                    for i, (o, c) in enumerate(zip(original_values, new_values)):
                        if o == orig and c == curr:
                            new_values[i] = user_name
                self.df[val_col] = new_values
                self.converted_column = val_col
                self.update_preview(val_col)
                messagebox.showinfo("Успех", f"Столбец '{val_col}' обновлён согласно базе данных.")
            dialog.destroy()

        ttk.Button(dialog, text="ОК", command=on_ok).pack(pady=10)
        ttk.Button(dialog, text="Отмена", command=dialog.destroy).pack(pady=5)

    def _show_replacement_dialog(self, replacements):
        """Показывает диалог с таблицей замен и возвращает True, если пользователь нажал 'Применить'."""
        dialog = tk.Toplevel(self)
        dialog.title("Замена на пользовательские названия")
        dialog.geometry("700x400")
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="Найдены совпадения в базе данных. Вы можете заменить сгенерированные имена на пользовательские:",
                  wraplength=600).pack(pady=5)

        frame = ttk.Frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tree = ttk.Treeview(frame, columns=("original", "generated", "user"), show="headings", height=10)
        tree.heading("original", text="Исходное описание")
        tree.heading("generated", text="Сгенерированное")
        tree.heading("user", text="Пользовательское")
        tree.column("original", width=200)
        tree.column("generated", width=200)
        tree.column("user", width=200)

        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        for orig, conv, user in replacements:
            tree.insert("", tk.END, values=(orig, conv, user))

        result = {"apply": False}

        def on_apply():
            result["apply"] = True
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Применить замены", command=on_apply).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=on_cancel).pack(side=tk.LEFT, padx=5)

        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")

        self.wait_window(dialog)
        return result["apply"]

    def get_part(self, parts, idx):
        if idx is None or idx < 0 or idx >= len(parts):
            return None
        return parts[idx]

    def update_preview(self, new_col_name):
        for item in self.tree.get_children():
            self.tree.delete(item)
        if self.df is None or new_col_name not in self.df.columns:
            return
        preview_df = self.df[[self.selected_column, new_col_name]].copy()
        mask = preview_df[self.selected_column].notna() & (preview_df[self.selected_column].astype(str).str.strip() != '')
        preview_df = preview_df[mask].head(20)
        for _, row in preview_df.iterrows():
            orig = str(row[self.selected_column]) if pd.notna(row[self.selected_column]) else ""
            conv = str(row[new_col_name]) if pd.notna(row[new_col_name]) else ""
            self.tree.insert("", tk.END, values=(orig, conv))

    # ========== Полный предпросмотр ==========
    def show_full_preview(self):
        if self.df is None:
            messagebox.showinfo("Информация", "Сначала загрузите файл.")
            return
        self._show_generic_preview(None, None, "Предпросмотр загруженного BOM (описание)", all_columns=True)

    def show_result_preview(self):
        if self.df is None or self.converted_column is None or self.converted_column not in self.df.columns:
            messagebox.showinfo("Информация", "Сначала примените правила преобразования.")
            return
        self._show_generic_preview(self.selected_column, self.converted_column,
                                   "Предпросмотр результатов (описание)", all_columns=False)

    def _show_generic_preview(self, col1, col2, title, all_columns=False):
        preview_window = create_styled_toplevel(self, title, "960x540")

        filter_frame = ttk.Frame(preview_window, padding="5")
        filter_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(filter_frame, text="Фильтр:").pack(side=tk.LEFT, padx=5)
        filter_entry = ttk.Entry(filter_frame, width=40)
        filter_entry.pack(side=tk.LEFT, padx=5)

        def clear_filter():
            filter_entry.delete(0, tk.END)
            update_tree()

        ttk.Button(filter_frame, text="Сбросить фильтр", command=clear_filter).pack(side=tk.LEFT, padx=5)

        frame = ttk.Frame(preview_window, padding="5")
        frame.pack(fill=tk.BOTH, expand=True)

        if all_columns:
            columns = list(self.df.columns)
        else:
            columns = [col1, col2]

        tree = ttk.Treeview(frame, columns=columns, show="headings")
        tree.tag_configure('odd', background="#232428")
        tree.tag_configure('even', background="#2b2d31")

        def sort_column(col, reverse=False):
            items = [(tree.set(item, col), item) for item in tree.get_children('')]
            try:
                items.sort(key=lambda x: float(x[0]) if x[0].replace('.', '').isdigit() else x[0], reverse=reverse)
            except:
                items.sort(key=lambda x: x[0].lower(), reverse=reverse)
            for index, (_, item) in enumerate(items):
                tree.move(item, '', index)
                tag = 'even' if index % 2 == 0 else 'odd'
                tree.item(item, tags=(tag,))
            tree.heading(col, command=lambda: sort_column(col, not reverse))

        for col in columns:
            tree.heading(col, text=col, command=lambda c=col: sort_column(c, False))
            tree.column(col, width=120, anchor=tk.W)

        scroll_y = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview, style="Vertical.TScrollbar")
        scroll_x = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview, style="Horizontal.TScrollbar")
        tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        def update_tree():
            for item in tree.get_children():
                tree.delete(item)
            filter_text = filter_entry.get().strip().lower()
            inserted_count = 0
            for _, row in self.df.iterrows():
                if filter_text:
                    found = False
                    for col in columns:
                        val = str(row[col]) if pd.notna(row[col]) else ""
                        if filter_text in val.lower():
                            found = True
                            break
                    if not found:
                        continue
                values = [str(row[col]) if pd.notna(row[col]) else "" for col in columns]
                tag = 'even' if inserted_count % 2 == 0 else 'odd'
                tree.insert("", tk.END, values=values, tags=(tag,))
                inserted_count += 1

        filter_entry.bind('<KeyRelease>', lambda e: update_tree())
        update_tree()

        btn_bar = ttk.Frame(preview_window, padding="5")
        btn_bar.pack(fill=tk.X, pady=5)
        ttk.Button(btn_bar, text="Закрыть", command=preview_window.destroy).pack(side=tk.BOTTOM, pady=2)

        style_widget_tree(preview_window, "dark")

    # ========== Сохранение ==========
    def save_file(self):
        if self.df is None:
            messagebox.showwarning("Предупреждение", "Нет данных для сохранения.")
            return

        file_path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
        if not file_path:
            return

        try:
            self.df.to_excel(file_path, index=False)
            messagebox.showinfo("Успех", f"Файл сохранён:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")


# =============================================================================
# Основное приложение – создаёт Notebook с тремя вкладками
# =============================================================================
class BOMConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Унификация BOM — Нормализация названий SMD")
        self.root.geometry("1240x820")
        self.root.minsize(1000, 650)

        # Тема оформления
        self.current_theme = get_system_theme()
        self.style = ttk.Style()
        self._setup_icon()

        # Создаём менеджер базы данных (автозагрузка из database.txt)
        self.db_manager = DatabaseManager()

        # 1. Верхний современный Header
        self.header_frame = tk.Frame(self.root, height=60, padx=15, pady=8)
        self.header_frame.pack(fill=tk.X, side=tk.TOP)

        title_box = tk.Frame(self.header_frame, bg=self.header_frame["bg"])
        title_box.pack(side=tk.LEFT, fill=tk.Y)

        self.header_title = tk.Label(title_box, text="🗂️ Унификация BOM", font=("Segoe UI", 13, "bold"))
        self.header_title.pack(anchor="w")

        self.header_subtitle = tk.Label(
            title_box,
            text="Приведение описаний и кодов компонентов спецификации к единому складскому стандарту",
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
        ToolTip(self.btn_faq, "Открыть руководство по унификации компонентов")

        self.btn_feedback = tk.Button(btn_box, text="✉️ Обратная связь", font=("Segoe UI", 8),
                                      relief="flat", padx=10, pady=4, cursor="hand2",
                                      command=lambda: show_feedback_dialog(self.root, self.current_theme))
        self.btn_feedback.pack(side=tk.LEFT, padx=4)
        ToolTip(self.btn_feedback, "Написать автору проекта (kean5782@yandex.ru)")

        # 2. Основной Notebook с вкладками
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # Вкладка "Унификация по описанию"
        self.desc_tab = DescriptionTab(self.notebook, self.db_manager)
        self.notebook.add(self.desc_tab, text="📝 Унификация по описанию (русские параметры)")

        # Вкладка "Унификация по коду"
        self.code_tab = CodeTab(self.notebook, self.db_manager)
        self.notebook.add(self.code_tab, text="🔢 Унификация по коду (Samsung, Yageo, Murata...)")

        # Вкладка "База данных"
        self.db_tab = DatabaseTab(self.notebook, self.db_manager)
        self.notebook.add(self.db_tab, text="🗄️ База данных соответствий")

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


# =============================================================================
# Запуск приложения
# =============================================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = BOMConverterApp(root)
    root.mainloop()
