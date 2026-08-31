# PnP_manager (Pick and Place Manager)

**PnP_manager** — экосистема инструментов и приложений для оптимизации процессов SMD-монтажа, учета радиодеталей, работы с катушками и автоматизации линий поверхностного монтажа (Pick and Place).

---

## 📁 Состав экосистемы

Репозиторий организован по модульному принципу:

```text
PnP_manager/
├── BarcodeDecoder/                   # Сканер и декодер маркировок SMD катушек
│   ├── BarcodeDecoderAndroid/        # Android-приложение (CameraX, ML Kit, RuStore)
│   ├── BarcodeDecoder_1.1.py         # Десктопное приложение (Python / Tkinter)
│   ├── CHANGELOG.md                  # История версий BarcodeDecoder
│   └── README.md                     # Документация модуля BarcodeDecoder
│
├── [Приложение 2]                    # Модуль управления питателями (в разработке)
├── [Приложение 3]                    # Модуль учета и инвентаризации (в разработке)
└── [Launcher]                        # Единый лаунчер экосистемы (в разработке)
```

---

## 📥 Скачать приложение

### 📱 BarcodeDecoder (Android)
- 🚀 **[Скачать релизный APK (GitHub Releases)](https://github.com/kean5782-coder/BarcodeDecoder/releases/latest)** — прямая загрузка последней версии `.apk`.
- 🛍️ **[Страница приложения в RuStore](https://www.rustore.ru/catalog/app/com.barcodedecoder)** — официальный каталог RuStore.
- 📦 **[Все версии и архивы релизов](https://github.com/kean5782-coder/BarcodeDecoder/releases)**

---

## 🚀 Текущие модули

### 1. [BarcodeDecoder](BarcodeDecoder/README.md)
Интеллектуальный декодер штрихкодов и Data Matrix кодов с этикеток катушек SMD конденсаторов (MLCC) и резисторов.
- **Поддержка производителей:** Murata, Samsung, Vishay, Panasonic, Bourns, KOA Speer, Royal Ohm, ROHM, Viking, AVX, TDK, Walsin, CCTC, HOTTECH, а также российские резисторы Р1-12 и Р1-16.
- **Автоматическая очистка префиксов:** удаление префиксов катушек (1P, Q, 1T, суффиксов упаковок/партий).
- **Платформы:** Android (Kotlin) и Desktop (Python 3 / Tkinter).
- **[Скачать APK](https://github.com/kean5782-coder/BarcodeDecoder/releases/latest)** / **[История версий](BarcodeDecoder/CHANGELOG.md)**

---

## 🛠️ Разработка и сборка

### Android-приложение:
```powershell
cd BarcodeDecoder/BarcodeDecoderAndroid
.\gradlew.bat assembleRelease
```

### Десктопный декодер (Python):
```powershell
python BarcodeDecoder/BarcodeDecoder_1.1.py
```

### Проверка статуса синхронизации с GitHub:
```powershell
.\check_github.ps1
```

---

## 📜 Лицензия
Проект распространяется под лицензией MIT. Подробнее см. файл [LICENSE](LICENSE).
