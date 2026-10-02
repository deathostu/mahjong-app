import random

class MahjongWall:
    def __init__(self):
        self.tiles = []
        self.dead_wall = []
        self.dora_indicators = []
        self.ura_dora_indicators = []
        
        self.reset()

    def reset(self):
        """Создает новую колоду из 136 тайлов и подготавливает стену."""
        # Собираем все 136 тайлов (каждый тайл дублируется 4 раза)
        suits = ['m', 'p', 's']  # Манзу, Пинзу, Созу
        ranks = [str(i) for i in range(1, 10)] # 1-9
        
        # 1z-4z: Ветра (Восток, Юг, Запад, Север)
        # 5z-7z: Драконы (Белый, Зеленый, Красный)
        honors = [f"{i}z" for i in range(1, 8)] 
        
        base_tiles = []
        # Добавляем масти
        for suit in suits:
            for rank in ranks:
                base_tiles.append(rank + suit)
        # Добавляем благородные (ветра/драконы)
        for honor in honors:
            base_tiles.append(honor)
            
        # Умножаем на 4, так как каждого тайла ровно четыре в игре
        self.tiles = base_tiles * 4
        
        # Перемешиваем стену (Алгоритм Фишера-Йетса встроен в random.shuffle)
        random.shuffle(self.tiles)
        
        # Формируем мертвую стену (последние 14 тайлов стены)
        # В реальном маджонге она отсчитывается с конца
        self.dead_wall = self.tiles[-14:]
        self.tiles = self.tiles[:-14] # Остается 122 тайла в живой стене
        
        # Открываем первый индикатор доры
        # В мертвой стене индикаторы обычно занимают фиксированные места
        # Для простоты возьмем 5-й тайл мертвой стены как дору, а 6-й как ура-дору
        self.dora_indicators = [self.dead_wall[4]]
        self.ura_dora_indicators = [self.dead_wall[5]]

    def draw_tile(self):
        """Берет один тайл из начала живой стены. 
        Если стена пуста, возвращает None (наступает ничья)."""
        if len(self.tiles) > 0:
            return self.tiles.pop(0)
        return None

    def draw_rinshan_tile(self):
        """Берет тайл с конца мертвой стены (при объявлении Кана).
        Взамен берется один тайл из живой стены и переносится в мертвую."""
        if len(self.dead_wall) > 0 and len(self.tiles) > 0:
            rinshan = self.dead_wall.pop(0) # Берем тайл для игрока
            # Компенсируем мертвую стену тайлом из конца живой стены
            self.dead_wall.append(self.tiles.pop())
            return rinshan
        return None

    def open_next_dora(self):
        """Открывает следующий индикатор доры (при Кане)."""
        # Всего может быть открыто до 5 дор (индексы 4, 2, 0, 8, 6 в классике)
        # Для простоты просто берем еще не открытый тайл из мертвой стены
        current_opened = len(self.dora_indicators)
        if current_opened < 5:
            # Берем следующий условный тайл из мертвой стены
            next_index = 4 + current_opened * 2
            if next_index < len(self.dead_wall):
                self.dora_indicators.append(self.dead_wall[next_index])
                self.ura_dora_indicators.append(self.dead_wall[next_index + 1])

    @property
    def tiles_left(self):
        """Возвращает количество оставшихся тайлов в живой стене."""
        return len(self.tiles)
