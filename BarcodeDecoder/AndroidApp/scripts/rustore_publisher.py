#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RuStore Publishing Automation Script for BarcodeDecoder
Автоматизирует создание черновика версии, загрузку APK, обновление списка изменений и отправку на модерацию в RuStore.
"""

import os
import sys
import json
import base64
import argparse
from datetime import datetime, timezone
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

API_BASE_URL = "https://public-api.rustore.ru"


def get_auth_signature(key_id: str, timestamp_str: str, private_key_pem: bytes) -> str:
    """
    Формирует RSA-подпись строки (keyId + timestamp) по алгоритму SHA512withRSA (PKCS#1 v1.5).
    
    Args:
        key_id (str): Идентификатор ключа RuStore API Console.
        timestamp_str (str): Строка времени в формате ISO 8601 UTC.
        private_key_pem (bytes): Содержимое приватного RSA ключа в формате PEM.
        
    Returns:
        str: Base64-строка сгенерированной цифровой подписи.
    """
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    data_to_sign = f"{key_id}{timestamp_str}".encode("utf-8")
    signature = private_key.sign(
        data_to_sign,
        padding.PKCS1v15(),
        hashes.SHA512()
    )
    return base64.b64encode(signature).decode("utf-8")


def get_rustore_token(key_id: str, key_path: str) -> str:
    """
    Выполняет аутентификацию в RuStore Public API и возвращает временный токен JWE.
    
    Args:
        key_id (str): Идентификатор ключа RuStore API.
        key_path (str): Путь к файлу приватного RSA-ключа (*.pem).
        
    Returns:
        str: JWE токен для авторизации последующих запросов.
    """
    if not os.path.exists(key_path):
        raise FileNotFoundError(f"Файл приватного RSA ключа не найден по пути: {key_path}")

    with open(key_path, "rb") as f:
        key_pem = f.read()

    # RuStore требует формат ISO 8601 с указанием таймзоны UTC (Z)
    now_utc = datetime.now(timezone.utc)
    timestamp_str = now_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    signature = get_auth_signature(key_id, timestamp_str, key_pem)

    payload = {
        "keyId": str(key_id),
        "timestamp": timestamp_str,
        "signature": signature
    }

    resp = requests.post(f"{API_BASE_URL}/public/auth", json=payload, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Ошибка аутентификации RuStore ({resp.status_code}): {resp.text}")

    data = resp.json()
    if data.get("code") != "OK":
        raise RuntimeError(f"Ответ с ошибкой от RuStore Auth: {data}")

    jwe_token = data["body"]["jwe"]
    return jwe_token


def get_headers(token: str) -> dict:
    """Формирует стандартные HTTP-заголовки авторизации RuStore."""
    return {
        "public-token": token,
        "Accept": "application/json"
    }


def list_versions(token: str, package_name: str) -> None:
    """
    Запрашивает и выводит список всех версий приложения в RuStore.
    
    Args:
        token (str): JWE токен авторизации.
        package_name (str): Имя пакета Android-приложения.
    """
    url = f"{API_BASE_URL}/public/v1/application/{package_name}/version"
    resp = requests.get(url, headers=get_headers(token), timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Не удалось получить список версий ({resp.status_code}): {resp.text}")

    data = resp.json()
    if data.get("code") != "OK":
        raise RuntimeError(f"Ошибка получения версий: {data}")

    body = data.get("body", {})
    if isinstance(body, dict):
        versions_list = body.get("content", [])
    elif isinstance(body, list):
        versions_list = body
    else:
        versions_list = []

    print(f"\n=== Список версий приложения {package_name} ===")
    if not versions_list:
        print("Версии не найдены.")
    else:
        for v in versions_list:
            v_id = v.get("versionId") or v.get("id")
            v_name = v.get("versionName", "—")
            v_code = v.get("versionCode", "—")
            v_status = v.get("versionStatus", "—")
            print(f"• ID: {v_id} | Версия: {v_name} (Код: {v_code}) | Статус: {v_status}")
    print("===================================================\n")


def create_version_draft(token: str, package_name: str, publish_type: str = "MANUAL") -> int:
    """
    Создает черновик новой версии приложения.
    
    Args:
        token (str): JWE токен авторизации.
        package_name (str): Имя пакета Android-приложения.
        publish_type (str): Тип публикации ('MANUAL' или 'AUTOMATIC').
        
    Returns:
        int: Идентификатор созданного черновика версии (versionId).
    """
    url = f"{API_BASE_URL}/public/v1/application/{package_name}/version"
    payload = {
        "publishType": publish_type
    }
    resp = requests.post(url, headers=get_headers(token), json=payload, timeout=30)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Не удалось создать черновик версии ({resp.status_code}): {resp.text}")

    data = resp.json()
    if data.get("code") != "OK":
        raise RuntimeError(f"Ошибка создания черновика: {data}")

    version_id = data["body"]
    print(f"Черновик версии успешно создан с ID: {version_id}")
    return version_id


def upload_apk(token: str, package_name: str, version_id: int, apk_path: str) -> None:
    """
    Загружает бинарный APK-файл в созданный черновик версии.
    
    Args:
        token (str): JWE токен авторизации.
        package_name (str): Имя пакета Android-приложения.
        version_id (int): Идентификатор версии.
        apk_path (str): Путь к загружаемому файлу .apk.
    """
    if not os.path.exists(apk_path):
        raise FileNotFoundError(f"APK файл не найден по пути: {apk_path}")

    apk_size_mb = os.path.getsize(apk_path) / (1024 * 1024)
    print(f"Загрузка APK ({apk_size_mb:.2f} МБ): {apk_path}...")

    url = f"{API_BASE_URL}/public/v1/application/{package_name}/version/{version_id}/apk"
    params = {"isMainApk": "true"}
    headers = get_headers(token)

    with open(apk_path, "rb") as f:
        files = {
            "file": (os.path.basename(apk_path), f, "application/vnd.android.package-archive")
        }
        resp = requests.post(url, headers=headers, params=params, files=files, timeout=300)

    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Не удалось загрузить APK ({resp.status_code}): {resp.text}")

    data = resp.json()
    if data.get("code") != "OK":
        raise RuntimeError(f"Ошибка загрузки APK: {data}")

    print("APK успешно загружен в RuStore!")


def update_whats_new(token: str, package_name: str, version_id: int, whats_new_text: str) -> None:
    """
    Обновляет описание изменений ('Что нового') для указанной версии.
    """
    if not whats_new_text:
        return

    url = f"{API_BASE_URL}/public/v1/application/{package_name}/version/{version_id}"
    payload = {
        "whatsNew": whats_new_text
    }
    resp = requests.post(url, headers=get_headers(token), json=payload, timeout=30)
    if resp.status_code not in (200, 201):
        print(f"Предупреждение: не удалось обновить список изменений ({resp.status_code}): {resp.text}")
    else:
        print("Список изменений (whatsNew) успешно обновлен!")


def commit_version(token: str, package_name: str, version_id: int) -> None:
    """
    Отправляет версию на проверку модерацией RuStore.
    """
    url = f"{API_BASE_URL}/public/v1/application/{package_name}/version/{version_id}/commit"
    params = {"priorityUpdate": 0}
    resp = requests.post(url, headers=get_headers(token), params=params, timeout=30)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Не удалось отправить версию на модерацию ({resp.status_code}): {resp.text}")

    data = resp.json()
    if data.get("code") != "OK":
        raise RuntimeError(f"Ошибка подтверждения версии: {data}")

    print(f"Версия {version_id} успешно отправлена на модерацию в RuStore!")


def load_config() -> dict:
    """Загружает локальную конфигурацию из rustore_config.json, если файл существует."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "rustore_config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    parser = argparse.ArgumentParser(description="Утилита публикации BarcodeDecoder в RuStore")
    parser.add_argument("action", choices=["test-auth", "publish", "list-versions"], help="Действие для выполнения")
    parser.add_argument("--key-id", help="Идентификатор ключа RuStore (из консоли разработчика)")
    parser.add_argument("--key-path", default="rustore_key.pem", help="Путь к файлу приватного RSA ключа PEM")
    parser.add_argument("--package-name", default="com.barcodedecoder", help="Имя пакета Android-приложения")
    parser.add_argument("--apk-path", default="app/build/outputs/apk/release/BarcodeDecoderForSmdResistorsAndCondensators_kean5782.apk", help="Путь к файлу release APK")
    parser.add_argument("--publish-type", default="MANUAL", choices=["MANUAL", "AUTOMATIC"], help="Тип публикации: MANUAL или AUTOMATIC после прохождения модерации")
    parser.add_argument("--whats-new", default="", help="Текст списка изменений для релиза")
    parser.add_argument("--draft-only", action="store_true", help="Сохранить как черновик без отправки на модерацию")

    args = parser.parse_args()
    config = load_config()

    key_id = args.key_id or config.get("key_id")
    key_path = args.key_path or config.get("key_path", "rustore_key.pem")
    package_name = args.package_name or config.get("package_name", "com.barcodedecoder")

    if not key_id:
        print("ОШИБКА: Требуется указать Key ID RuStore! Передайте аргумент --key-id или укажите 'key_id' в rustore_config.json", file=sys.stderr)
        sys.exit(1)

    print(f"Подключение к RuStore API (Key ID: {key_id})...")
    token = get_rustore_token(key_id, key_path)
    print("Аутентификация успешна! Токен получен.")

    if args.action == "test-auth":
        print("Проверка связи с RuStore API выполнена успешно!")
        return

    if args.action == "list-versions":
        list_versions(token, package_name)
        return

    if args.action == "publish":
        version_id = create_version_draft(token, package_name, args.publish_type)
        upload_apk(token, package_name, version_id, args.apk_path)
        if args.whats_new:
            update_whats_new(token, package_name, version_id, args.whats_new)
        
        if args.draft_only:
            print(f"\n[УСПЕХ] Версия {version_id} сохранена как ЧЕРНОВИК в RuStore (без отправки на модерацию).")
        else:
            commit_version(token, package_name, version_id)
            print("\nВсе этапы завершены! Новая версия передана на модерацию в RuStore.")


if __name__ == "__main__":
    main()
