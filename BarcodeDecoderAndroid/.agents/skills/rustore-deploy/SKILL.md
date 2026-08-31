---
name: rustore-deploy
description: Automates building and publishing new Android app versions to RuStore using the RuStore Publishing API. Use whenever the user asks to publish, upload, release, or deploy a new version to RuStore.
---

# RuStore Deployment Skill

This skill guides the automated workflow for building, packaging, and publishing Android APK releases to RuStore via the RuStore Publishing API.

## Workflow

When the user asks to release or upload a new version to RuStore:

### 1. Versioning & Building
1. Check `version.properties` and ensure `versionCode` and `versionName` are appropriate for the new release.
2. Build the signed release APK using Gradle:
   ```powershell
   .\gradlew.bat assembleRelease
   ```
3. Verify the generated APK is present at `app/build/outputs/apk/release/BarcodeDecoderForSmdResistorsAndCondensators_kean5782.apk`.

### 2. Testing Authentication & Uploading to RuStore
Run the deployment script using the virtual environment:
```powershell
.\.venv\Scripts\python scripts/rustore_publisher.py publish --whats-new "<Changelog description in Russian>"
```

Options:
- `--key-id <KEY_ID>`: Overrides key ID from `rustore_config.json`.
- `--publish-type MANUAL`: Draft is sent to moderation and published manually after approval (or `AUTOMATIC` to auto-publish upon approval).
- `--whats-new "<text>"`: Description of what is new in this release.

### 3. Test Authentication Only
To verify API connectivity and private key validity:
```powershell
.\.venv\Scripts\python scripts/rustore_publisher.py test-auth
```
