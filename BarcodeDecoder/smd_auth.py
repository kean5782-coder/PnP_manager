"""
smd_auth.py — Модуль управления учетными записями пользователей и правами доступа.
Хранит аккаунты в %APPDATA%\\SMD_Hub\\users.json.
Предустановленные пользователи:
- Технолог (логин 'user', без пароля, активен по умолчанию)
- Администратор (логин 'admin', пароль 'admin', права на добавление/удаление аккаунтов)
"""

import os
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any


def get_default_users_path() -> str:
    """Возвращает путь к users.json в %APPDATA%\\SMD_Hub."""
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    users_dir = os.path.join(appdata, "SMD_Hub")
    try:
        os.makedirs(users_dir, exist_ok=True)
    except Exception:
        pass
    return os.path.join(users_dir, "users.json")


def hash_password(password: str) -> str:
    """Хеширует пароль по алгоритму SHA-256."""
    if not password:
        return ""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


class AccountManager:
    """Управляет пользователями, ролями и активной сессией."""

    def __init__(self, filepath: Optional[str] = None):
        self.filepath = filepath or get_default_users_path()
        self.users: Dict[str, Dict[str, Any]] = {}
        self.active_username: str = "user"  # По умолчанию всегда "Технолог"
        self.load()

    def _get_initial_users(self) -> Dict[str, Dict[str, Any]]:
        """Создает стартовую структуру пользователей."""
        return {
            "user": {
                "username": "user",
                "display_name": "Технолог",
                "password_hash": "",  # Вход без пароля
                "role": "operator",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            "admin": {
                "username": "admin",
                "display_name": "Администратор",
                "password_hash": hash_password("admin"),  # Пароль 'admin'
                "role": "admin",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }

    def load(self):
        """Загружает пользователей из файла или инициализирует стартовыми."""
        if not os.path.exists(self.filepath):
            self.users = self._get_initial_users()
            self.active_username = "user"
            self.save()
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.users = data.get("users", {})
                # По требованию пользователя при каждом открытии программы
                # по умолчанию ВСЕГДА выбирается аккаунт 'user' (Технолог)
                if "user" in self.users:
                    self.active_username = "user"
                elif self.users:
                    self.active_username = list(self.users.keys())[0]
                else:
                    self.users = self._get_initial_users()
                    self.active_username = "user"
        except Exception:
            self.users = self._get_initial_users()
            self.active_username = "user"
            self.save()

    def save(self):
        """Сохраняет пользователей в JSON-файл."""
        try:
            dir_name = os.path.dirname(self.filepath)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            data = {
                "active_username": self.active_username,
                "users": self.users
            }
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Warning: Could not save users.json: {e}")

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Возвращает список всех зарегистрированных пользователей."""
        return list(self.users.values())

    def get_active_user(self) -> Dict[str, Any]:
        """Возвращает данные текущего вошедшего пользователя."""
        return self.users.get(self.active_username, {
            "username": "user",
            "display_name": "Технолог",
            "role": "operator"
        })

    def get_active_display_name(self) -> str:
        """Возвращает отображаемое имя текущего пользователя (для поля author)."""
        user = self.get_active_user()
        return user.get("display_name", "Технолог")

    def is_current_admin(self) -> bool:
        """Проверяет, является ли текущий вошедший пользователь Администратором."""
        return self.get_active_user().get("role") == "admin"

    def requires_password(self, username: str) -> bool:
        """Проверяет, установлен ли пароль у пользователя."""
        user = self.users.get(username)
        if not user:
            return False
        return bool(user.get("password_hash"))

    def login(self, username: str, password: str = "") -> Tuple[bool, str]:
        """
        Выполняет вход под пользователем.
        Если пароль не задан, вход происходит мгновенно без пароля.
        """
        user = self.users.get(username)
        if not user:
            return False, "Пользователь не найден."

        expected_hash = user.get("password_hash", "")
        if not expected_hash:
            # Пароля нет -> вход без пароля
            self.active_username = username
            self.save()
            return True, f"Успешный вход: {user.get('display_name', username)}"

        # Пароль задан -> проверяем хеш
        input_hash = hash_password(password)
        if input_hash == expected_hash:
            self.active_username = username
            self.save()
            return True, f"Успешный вход: {user.get('display_name', username)}"
        else:
            return False, "Неверный пароль."

    def create_user(
        self,
        username: str,
        display_name: str,
        password: str = "",
        role: str = "operator"
    ) -> Tuple[bool, str]:
        """
        Создает нового пользователя.
        Право на создание аккаунта есть ТОЛЬКО у Администратора!
        """
        if not self.is_current_admin():
            return False, "Права на добавление аккаунта есть только у Администратора.\nПожалуйста, выполните вход под учетной записью администратора."

        username = username.strip().lower()
        display_name = display_name.strip()

        if not username:
            return False, "Логин не может быть пустым."
        if not display_name:
            return False, "Имя пользователя не может быть пустым."

        if username in self.users:
            return False, f"Пользователь с логином '{username}' уже существует."

        self.users[username] = {
            "username": username,
            "display_name": display_name,
            "password_hash": hash_password(password) if password else "",
            "role": role if role in ("admin", "operator") else "operator",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.save()
        return True, f"Пользователь '{display_name}' успешно создан."

    def delete_user(self, username: str) -> Tuple[bool, str]:
        """
        Удаляет пользователя.
        Право на удаление есть только у Администратора.
        Нельзя удалить самого себя или последнего администратора.
        """
        if not self.is_current_admin():
            return False, "Права на удаление аккаунта есть только у Администратора."

        if username not in self.users:
            return False, "Пользователь не найден."

        if username == self.active_username:
            return False, "Нельзя удалить текущего активного пользователя."

        # Проверка на последнего администратора
        admins = [u for u in self.users.values() if u.get("role") == "admin"]
        if self.users[username].get("role") == "admin" and len(admins) <= 1:
            return False, "Нельзя удалить единственного администратора системы."

        del self.users[username]
        self.save()
        return True, "Пользователь успешно удален."
