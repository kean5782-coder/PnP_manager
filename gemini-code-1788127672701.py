import pandas as pd
import openpyxl

# Создаем тестовую таблицу
data = {
    "Имя": ["Алексей", "Мария", "Иван"],
    "Возраст": [25, 30, 28],
    "Город": ["Москва", "Санкт-Петербург", "Казань"],
}
df = pd.DataFrame(data)

# Сохраняем в Excel с использованием движка openpyxl
excel_file = "test_output.xlsx"
df.to_excel(excel_file, index=False, engine="openpyxl")

# Читаем обратно
df_read = pd.read_excel(excel_file)
print("Файл успешно создан и прочитан:")
print(df_read)