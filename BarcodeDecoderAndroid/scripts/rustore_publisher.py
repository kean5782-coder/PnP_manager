#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RuStore Publishing Automation Script for BarcodeDecoder
Automates version creation, APK uploading, changelog updating, and moderation submission.
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
    """Signs keyId + timestamp using SHA512withRSA and returns base64 string."""
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    data_to_sign = f"{key_id}{timestamp_str}".encode("utf-8")
    signature = private_key.sign(
        data_to_sign,
        padding.PKCS1v15(),
        hashes.SHA512()
    )
    return base64.b64encode(signature).decode("utf-8")

def get_rustore_token(key_id: str, key_path: str) -> str:
    """Requests JWE authentication token from RuStore Public API."""
    if not os.path.exists(key_path):
        raise FileNotFoundError(f"RSA Private key file not found at: {key_path}")

    with open(key_path, "rb") as f:
        key_pem = f.read()

    # RuStore requires ISO 8601 with timezone (e.g. 2026-08-31T06:20:00+00:00 or Z)
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
        raise RuntimeError(f"RuStore Auth Failed ({resp.status_code}): {resp.text}")

    data = resp.json()
    if data.get("code") != "OK":
        raise RuntimeError(f"RuStore Auth Error: {data}")

    jwe_token = data["body"]["jwe"]
    return jwe_token

def get_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "auth-token": token,
        "Accept": "application/json"
    }

def create_version_draft(token: str, package_name: str, publish_type: str = "MANUAL") -> int:
    """Creates a new version draft on RuStore."""
    url = f"{API_BASE_URL}/public/v1/application/{package_name}/version"
    payload = {
        "publishType": publish_type  # MANUAL or AUTOMATIC
    }
    resp = requests.post(url, headers=get_headers(token), json=payload, timeout=30)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Failed to create version draft ({resp.status_code}): {resp.text}")

    data = resp.json()
    if data.get("code") != "OK":
        raise RuntimeError(f"Create draft response error: {data}")

    version_id = data["body"]
    print(f"Created version draft with ID: {version_id}")
    return version_id

def upload_apk(token: str, package_name: str, version_id: int, apk_path: str) -> None:
    """Uploads APK binary file to the created version draft."""
    if not os.path.exists(apk_path):
        raise FileNotFoundError(f"APK file not found at: {apk_path}")

    apk_size_mb = os.path.getsize(apk_path) / (1024 * 1024)
    print(f"Uploading APK ({apk_size_mb:.2f} MB): {apk_path}...")

    url = f"{API_BASE_URL}/public/v1/application/{package_name}/version/{version_id}/apk"
    params = {"isMainApk": "true"}
    
    headers = get_headers(token)

    with open(apk_path, "rb") as f:
        files = {
            "file": (os.path.basename(apk_path), f, "application/vnd.android.package-archive")
        }
        resp = requests.post(url, headers=headers, params=params, files=files, timeout=300)

    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Failed to upload APK ({resp.status_code}): {resp.text}")

    data = resp.json()
    if data.get("code") != "OK":
        raise RuntimeError(f"Upload APK response error: {data}")

    print("APK successfully uploaded to RuStore!")

def update_whats_new(token: str, package_name: str, version_id: int, whats_new_text: str) -> None:
    """Updates the changelog/what's new description for the version."""
    if not whats_new_text:
        return

    url = f"{API_BASE_URL}/public/v1/application/{package_name}/version/{version_id}"
    payload = {
        "whatsNew": whats_new_text
    }
    resp = requests.post(url, headers=get_headers(token), json=payload, timeout=30)
    if resp.status_code not in (200, 201):
        print(f"Warning: Could not update whatsNew ({resp.status_code}): {resp.text}")
    else:
        print("Changelog (whatsNew) updated successfully!")

def commit_version(token: str, package_name: str, version_id: int) -> None:
    """Submits the version to moderation / publishing."""
    url = f"{API_BASE_URL}/public/v1/application/{package_name}/version/{version_id}/commit"
    params = {"priorityUpdate": 0}
    resp = requests.post(url, headers=get_headers(token), params=params, timeout=30)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Failed to commit version ({resp.status_code}): {resp.text}")

    data = resp.json()
    if data.get("code") != "OK":
        raise RuntimeError(f"Commit version error: {data}")

    print(f"Version {version_id} successfully submitted to RuStore moderation!")

def load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "rustore_config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def main():
    parser = argparse.ArgumentParser(description="RuStore Deployment Tool")
    parser.add_argument("action", choices=["test-auth", "publish", "list-versions"], help="Action to perform")
    parser.add_argument("--key-id", help="RuStore Key ID (from Console)")
    parser.add_argument("--key-path", default="rustore_key.pem", help="Path to RSA private key PEM file")
    parser.add_argument("--package-name", default="com.barcodedecoder", help="Android application package name")
    parser.add_argument("--apk-path", default="app/build/outputs/apk/release/BarcodeDecoderForSmdResistorsAndCondensators_kean5782.apk", help="Path to release APK")
    parser.add_argument("--publish-type", default="MANUAL", choices=["MANUAL", "AUTOMATIC"], help="MANUAL or AUTOMATIC publication after moderation")
    parser.add_argument("--whats-new", default="Исправление выравнивания иконок и оптимизация интерфейса шторки результатов.", help="Release changelog text")

    args = parser.parse_args()
    config = load_config()

    key_id = args.key_id or config.get("key_id")
    key_path = args.key_path or config.get("key_path", "rustore_key.pem")
    package_name = args.package_name or config.get("package_name", "com.barcodedecoder")

    if not key_id:
        print("ERROR: RuStore Key ID is required! Pass --key-id or set 'key_id' in rustore_config.json", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to RuStore API with Key ID: {key_id}...")
    token = get_rustore_token(key_id, key_path)
    print("Authentication successful! Token obtained.")

    if args.action == "test-auth":
        print("RuStore API authentication test passed successfully!")
        return

    if args.action == "publish":
        version_id = create_version_draft(token, package_name, args.publish_type)
        upload_apk(token, package_name, version_id, args.apk_path)
        if args.whats_new:
            update_whats_new(token, package_name, version_id, args.whats_new)
        commit_version(token, package_name, version_id)
        print("\nAll steps completed! Version is sent to RuStore.")

if __name__ == "__main__":
    main()
