"""
smd_db.py — Модуль управления базой данных пользовательских соответствий на базе SQLite.
Поддерживает метаданные (категория, комментарий на русском, автор, дата),
экспорт/импорт в TXT и Excel, автомиграцию из database.txt и разрешение конфликтов.
"""

import os
import sys
import sqlite3
import shutil
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any, Callable

# Стандартный список категорий компонентов
COMPONENT_CATEGORIES = [
    "Резисторы",
    "Конденсаторы",
    "Микросхемы",
    "Диоды",
    "Индуктивности",
    "Разъемы",
    "Транзисторы",
    "Светодиоды",
    "Алюминиевые конденсаторы",
    "Танталовые конденсаторы",
]


def get_default_db_path() -> str:
    """Возвращает путь к database.db в %APPDATA%\\SMD_Hub."""
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    db_dir = os.path.join(appdata, "SMD_Hub")
    try:
        os.makedirs(db_dir, exist_ok=True)
    except Exception:
        pass
    return os.path.join(db_dir, "database.db")


class DatabaseManager:
    """
    Менеджер базы данных соответствий на SQLite.
    Обеспечивает 100% обратную совместимость со старым API на базе словаря (self.data).
    """

    def __init__(self, filename: Optional[str] = None):
        if not filename:
            filename = get_default_db_path()
        elif not filename.endswith(".db"):
            # Если передали старый путь к database.txt, преобразуем в database.db в той же папке
            base_dir = os.path.dirname(filename)
            filename = os.path.join(base_dir, "database.db") if base_dir else get_default_db_path()

        self.filename = os.path.abspath(filename)
        self.backup_filename = self.filename + ".bak"
        self._init_db()
        self._check_auto_migration()

    def _get_connection(self) -> sqlite3.Connection:
        """Создает подключение к базе SQLite с поддержкой многопоточности и WAL."""
        conn = sqlite3.connect(self.filename, timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            pass
        return conn

    def _init_db(self):
        """Инициализирует таблицу replacements и индексы."""
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS replacements (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    category TEXT DEFAULT 'Резисторы',
                    comment TEXT DEFAULT '',
                    author TEXT DEFAULT 'Технолог',
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_replacements_key ON replacements(key);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_replacements_cat ON replacements(category);")
            conn.commit()

    def _check_auto_migration(self):
        """Если база пуста, проверяет наличие старого database.txt и импортирует его."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM replacements;")
            count = cur.fetchone()[0]
            if count > 0:
                return

        # Ищем возможные места расположения database.txt
        possible_paths = [
            os.path.join(os.path.dirname(self.filename), "database.txt"),
            os.path.join(os.getcwd(), "database.txt"),
            os.path.join(os.getcwd(), "BarcodeDecoder", "database.txt"),
            os.path.join(os.path.dirname(__file__), "database.txt"),
            os.path.join(os.path.dirname(__file__), "Unification", "database.txt"),
        ]
        for p in possible_paths:
            if os.path.exists(p):
                try:
                    self.import_from_txt(p)
                    break
                except Exception:
                    pass

    # =========================================================================
    # Свойство self.data для 100% совместимости с модулями унификации
    # =========================================================================
    @property
    def data(self) -> Dict[str, str]:
        """Возвращает словарь {key: value} для обратной совместимости."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT key, value FROM replacements;")
            return {row["key"]: row["value"] for row in cur.fetchall()}

    @data.setter
    def data(self, new_data: Dict[str, str]):
        """Сеттер для полной замены данных (если вызывается устаревшим кодом)."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM replacements;")
            for k, v in new_data.items():
                conn.execute(
                    "INSERT OR REPLACE INTO replacements (key, value, category, comment, author) VALUES (?, ?, ?, ?, ?);",
                    (k, v, "Резисторы", "", "Технолог")
                )
            conn.commit()

    # =========================================================================
    # Базовые CRUD методы
    # =========================================================================
    def get(self, key: str) -> Optional[str]:
        """Возвращает унифицированное значение по ключу."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM replacements WHERE key = ?;", (key,))
            row = cur.fetchone()
            return row["value"] if row else None

    def get_record(self, key: str) -> Optional[Dict[str, Any]]:
        """Возвращает полную запись со всеми метаданными."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT key, value, category, comment, author, created_at FROM replacements WHERE key = ?;", (key,))
            row = cur.fetchone()
            return dict(row) if row else None

    def contains(self, key: str) -> bool:
        """Проверяет наличие ключа в базе."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM replacements WHERE key = ? LIMIT 1;", (key,))
            return cur.fetchone() is not None

    def add_or_update(
        self,
        key: str,
        value: str,
        category: str = "Резисторы",
        comment: str = "",
        author: str = "Технолог",
        created_at: Optional[str] = None
    ):
        """Добавляет или обновляет запись с сохранением метаданных."""
        now_str = created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO replacements (key, value, category, comment, author, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    category = excluded.category,
                    comment = excluded.comment,
                    author = excluded.author,
                    created_at = excluded.created_at;
            """, (key.strip(), value.strip(), category.strip(), comment.strip(), author.strip(), now_str))
            conn.commit()

    def delete(self, key: str) -> bool:
        """Удаляет запись по ключу."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM replacements WHERE key = ?;", (key,))
            conn.commit()
            return cur.rowcount > 0

    def delete_multiple(self, keys: List[str]) -> int:
        """Удаляет несколько записей."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.executemany("DELETE FROM replacements WHERE key = ?;", [(k,) for k in keys])
            conn.commit()
            return cur.rowcount

    def get_all(self) -> List[Tuple[str, str]]:
        """Возвращает список пар (key, value) для обратной совместимости."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT key, value FROM replacements ORDER BY key ASC;")
            return [(row["key"], row["value"]) for row in cur.fetchall()]

    def get_all_full(self) -> List[Dict[str, Any]]:
        """Возвращает список всех записей со всеми метаданными."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT key, value, category, comment, author, created_at FROM replacements ORDER BY key ASC;")
            return [dict(row) for row in cur.fetchall()]

    def add_multiple(self, items: List[Tuple[str, str]], overwrite: bool = False, author: str = "Технолог") -> Tuple[List[str], List[str]]:
        """Пакетное добавление пар (key, value) для обратной совместимости."""
        added = []
        skipped = []
        for key, value in items:
            key_str = key.strip()
            val_str = value.strip()
            if not key_str or not val_str:
                continue
            if self.contains(key_str):
                if overwrite:
                    self.add_or_update(key_str, val_str, author=author)
                    added.append(key_str)
                else:
                    skipped.append(key_str)
            else:
                self.add_or_update(key_str, val_str, author=author)
                added.append(key_str)
        return added, skipped

    def save(self):
        """Заглушка для совместимости со старым кодом (в SQLite изменения сохраняются сразу)."""
        pass

    def load(self):
        """Заглушка для совместимости со старым кодом."""
        pass

    # =========================================================================
    # Экспорт базы данных
    # =========================================================================
    def export_to_txt(self, filepath: str):
        """
        Экспортирует базу данных в файл .txt с табуляцией:
        Ключ\tЗначение\tКатегория\tКомментарий\tАвтор\tДата
        """
        records = self.get_all_full()
        with open(filepath, "w", encoding="utf-8") as f:
            for r in records:
                k = str(r.get("key", "")).replace("\t", " ").replace("\n", " ").replace("\r", " ")
                v = str(r.get("value", "")).replace("\t", " ").replace("\n", " ").replace("\r", " ")
                cat = str(r.get("category", "")).replace("\t", " ").replace("\n", " ").replace("\r", " ")
                comm = str(r.get("comment", "")).replace("\t", " ").replace("\n", " ").replace("\r", " ")
                author = str(r.get("author", "")).replace("\t", " ").replace("\n", " ").replace("\r", " ")
                created = str(r.get("created_at", "")).replace("\t", " ").replace("\n", " ").replace("\r", " ")
                f.write(f"{k}\t{v}\t{cat}\t{comm}\t{author}\t{created}\n")

    def export_to_excel(self, filepath: str):
        """Экспортирует базу данных в Excel (.xlsx)."""
        import pandas as pd
        records = self.get_all_full()
        df = pd.DataFrame(records)
        df.rename(columns={
            "key": "Название в BOM (Ключ)",
            "value": "Унифицированное наименование",
            "category": "Категория",
            "comment": "Комментарий",
            "author": "Автор",
            "created_at": "Дата добавления"
        }, inplace=True)
        df.to_excel(filepath, index=False)

    # =========================================================================
    # Импорт базы данных с разрешением конфликтов
    # =========================================================================
    def import_from_txt(
        self,
        filepath: str,
        conflict_callback: Optional[Callable[[Dict[str, Any], Dict[str, Any]], str]] = None
    ) -> Dict[str, int]:
        """
        Импортирует базу из файла .txt.
        Поддерживает:
        - 6-колоночный формат: key \t value \t category \t comment \t author \t created_at
        - 2-колоночный формат: key \t value

        Правила:
        - Если ключа нет -> добавляется в базу (автор, комментарий и категория берутся из файла).
        - Если ключ есть и значения совпадают -> пропускается без изменений.
        - Если ключ есть и значения отличаются:
          - Если передан conflict_callback, вызывается callback(current_record, new_record),
            возвращающий: 'keep' (оставить текущее), 'replace' (заменить на импортируемое),
            'keep_all' (оставить текущее для всех последующих), 'replace_all' (заменить все последующие).
          - Если callback не передан, по умолчанию пропускается (оставляется текущее).

        Возвращает: {"added": N, "updated": N, "skipped": N}
        """
        stats = {"added": 0, "updated": 0, "skipped": 0}
        conflict_decision_all = None  # 'keep_all' или 'replace_all'

        if not os.path.exists(filepath):
            return stats

        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            parts = line_str.split("\t")
            if len(parts) < 2:
                continue

            k = parts[0].strip()
            v = parts[1].strip()
            if not k or not v:
                continue

            cat = parts[2].strip() if len(parts) > 2 and parts[2].strip() else "Резисторы"
            comm = parts[3].strip() if len(parts) > 3 else ""
            author = parts[4].strip() if len(parts) > 4 and parts[4].strip() else "Импорт"
            created = parts[5].strip() if len(parts) > 5 and parts[5].strip() else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            new_rec = {
                "key": k,
                "value": v,
                "category": cat,
                "comment": comm,
                "author": author,
                "created_at": created
            }

            existing_rec = self.get_record(k)
            if not existing_rec:
                # Новая запись: добавляем
                self.add_or_update(k, v, category=cat, comment=comm, author=author, created_at=created)
                stats["added"] += 1
            else:
                # Ключ уже существует
                if existing_rec["value"].strip() == v:
                    # Идентичные значения: пропускаем
                    stats["skipped"] += 1
                else:
                    # Конфликт значений
                    decision = conflict_decision_all
                    if not decision and conflict_callback:
                        decision = conflict_callback(existing_rec, new_rec)
                        if decision in ("keep_all", "replace_all"):
                            conflict_decision_all = decision

                    if decision in ("replace", "replace_all"):
                        self.add_or_update(k, v, category=cat, comment=comm, author=author, created_at=created)
                        stats["updated"] += 1
                    else:
                        stats["skipped"] += 1

        return stats
