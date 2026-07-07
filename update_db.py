import pandas as pd

# Читаем текущую базу
df = pd.read_csv('database.csv')

# Функция для определения категории по названию
def get_category(name):
    name_lower = str(name).lower()
    # Если в названии есть слова, относящиеся к арматуре и сеткам
    if any(word in name_lower for word in ['арматур', 'сетка', 'проволок', 'углепластик', 'базальтопластик']):
        return 'arm'
    # Остальное считаем слоями стены
    return 'wall'

# Добавляем новую колонку
df['category'] = df['material_name'].apply(get_category)

# Сохраняем обратно
df.to_csv('database.csv', index=False)
print("База данных успешно разделена на категории!")
print(f"Слоев стены: {len(df[df['category']=='wall'])}")
print(f"Арматуры: {len(df[df['category']=='arm'])}")