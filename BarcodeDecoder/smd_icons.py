"""
smd_icons.py - Модуль цветных векторных/растровых иконок для SMD Hub.
Обеспечивает нативную отрисовку цветных иконок высокого разрешения (PNG 32-bit RGBA)
в интерфейсе Tkinter взамен системных черно-белых монохромных глифов Windows GDI.
"""

import os
import sys
import tkinter as tk
from typing import Optional, Dict

# Определение директории ресурсов с поддержкой сборщика PyInstaller (_MEIPASS)
BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
ICONS_DIR = os.path.join(BASE_DIR, "assets", "icons")

# Глобальный кэш PhotoImage объектов (предотвращает сборку мусора Tkinter)
_ICON_CACHE: Dict[str, tk.PhotoImage] = {}

# Маппинг логических имен
ICON_ALIASES = {
    "dashboard": "dashboard",
    "step1": "step1",
    "step2": "step2",
    "step3": "step3",
    "compare_pnp": "compare_pnp",
    "compare_bom": "compare_bom",
    "database": "database",
    "user": "user",
    "admin": "admin",
    "status_green": "status_green",
    "import": "import",
    "export": "export",
    "add": "add",
    "trash": "trash",
    "edit": "edit",
    "reset": "reset",
    "lightning": "lightning",
    "rocket": "rocket",
    "tools": "tools",
    "book": "book",
    "faq": "book",
    "mail": "mail",
    "feedback": "mail",
    "check": "check"
}

def get_icon(name: str, size: int = 22) -> Optional[tk.PhotoImage]:
    """
    Возвращает цветную иконку заданного размера в формате tk.PhotoImage.
    Результат кэшируется для исключения сборки мусора и ускорения отрисовки.
    """
    canonical_name = ICON_ALIASES.get(name, name)
    cache_key = f"{canonical_name}_{size}"

    if cache_key in _ICON_CACHE:
        cached = _ICON_CACHE[cache_key]
        try:
            cached.tk.call('image', 'type', str(cached))
            return cached
        except Exception:
            _ICON_CACHE.pop(cache_key, None)

    # Поиск файла в assets/icons
    # Пробуем запрошенный размер, либо ближайший доступный
    sizes_to_try = [size, 22, 24, 28, 32, 18]
    img = None

    for sz in sizes_to_try:
        path = os.path.join(ICONS_DIR, f"{canonical_name}_{sz}.png")
        if os.path.exists(path):
            try:
                img = tk.PhotoImage(file=path)
                break
            except Exception:
                continue

    if img is not None:
        _ICON_CACHE[cache_key] = img
        return img

    return None

def clear_icon_cache():
    """Очищает кэш иконок при перезапуске интерпретатора Tk."""
    _ICON_CACHE.clear()

def apply_label_icon(label: tk.Label, icon_name: str, text: str, size: int = 18, padx: int = 6):
    """
    Устанавливает цветную иконку на tk.Label с текстом слева или по центру.
    """
    img = get_icon(icon_name, size)
    if img:
        label.configure(image=img, text=f" {text}" if text else "", compound=tk.LEFT if text else tk.CENTER)
        label.image = img # Сохраняем ссылку
    else:
        label.configure(text=text)

def apply_button_icon(button: tk.Button, icon_name: str, text: str = "", size: int = 18):
    """
    Устанавливает цветную иконку на tk.Button.
    """
    img = get_icon(icon_name, size)
    if img:
        button.configure(image=img, text=f" {text}" if text else "", compound=tk.LEFT if text else tk.CENTER)
        button.image = img
    else:
        if text:
            button.configure(text=text)
