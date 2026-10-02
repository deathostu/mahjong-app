def get_tile_weight(tile: str) -> int:
    """Числовой вес тайла для правильного порядка сортировки."""
    if not tile or len(tile) < 2:
        return 999
    clean = tile[:-1] if tile.endswith('*') else tile
    rank = int(clean[:-1])
    suit = clean[-1]
    suit_offsets = {'m': 0, 'p': 10, 's': 20, 'z': 30}
    return suit_offsets.get(suit, 100) + rank

def sort_mahjong_hand(hand: list) -> list:
    """Сортирует массив тайлов по правилам маджонга."""
    return sorted(hand, key=get_tile_weight)

def _is_four_sets_valid(tiles: list) -> bool:
    """Рекурсивный разбор остатка закрытой части руки на чистые сеты по 3 тайла."""
    if not tiles:
        return True

    first = tiles[0]

    # Вариант А: Пробуем собрать Триплет (3 одинаковых тайла)
    if tiles.count(first) >= 3:
        remain = tiles.copy()
        for _ in range(3):
            remain.remove(first)
        if _is_four_sets_valid(remain):
            return True

    # Вариант Б: Пробуем собрать Стрит (последовательность из 3 тайлов)
    # Стриты собираются ТОЛЬКО для числовых мастей (m, p, s), но НЕ для z
    if first[-1] != 'z':
        rank = int(first[:-1])
        suit = first[-1]
        next1 = f"{rank+1}{suit}"
        next2 = f"{rank+2}{suit}"

        if next1 in tiles and next2 in tiles:
            remain = tiles.copy()
            remain.remove(first)
            remain.remove(next1)
            remain.remove(next2)
            if _is_four_sets_valid(remain):
                return True

    return False

def is_complete_hand(hand: list, melds: list) -> bool:
    """Проверяет маджонг на комбинацию сетов и 1 пару с учетом открытых объявлений.
    Математически адаптировано под любую длину руки."""
    # Суммарное количество тайлов (в закрытой руке + в melds) обязано быть 14
    # На бэкенде melds хранится как список объектов [{"tiles": [...]}, ...]
    total_meld_tiles = sum(len(m.get("tiles", m)) if isinstance(m, dict) else len(m) for m in melds)
    total_tiles = len(hand) + total_meld_tiles
    
    if total_tiles != 14:
        return False

    sorted_closed = sort_mahjong_hand(hand)
    unique_tiles = set(sorted_closed)
    
    # Ищем потенциальные пары для "глаз" в закрытой части руки
    possible_pairs = [t for t in unique_tiles if sorted_closed.count(t) >= 2]

    # Если закрытая часть пуста (например, все 4 сета открыты в melds), а пара осталась в руке
    if not sorted_closed and total_meld_tiles == 12:
        return False

    for pair in possible_pairs:
        remain_hand = sorted_closed.copy()
        remain_hand.remove(pair)
        remain_hand.remove(pair)

        # Проверяем, раскладывается ли остаток закрытой руки на чистые тройки
        if _is_four_sets_valid(remain_hand):
            return True

    return False

def is_tenpai(hand: list, melds: list) -> bool:
    """Проверяет, находится ли рука в тэнпае (не хватает 1 тайла до победы)."""
    total_meld_tiles = sum(len(m.get("tiles", m)) if isinstance(m, dict) else len(m) for m in melds)
    if len(hand) + total_meld_tiles != 13:
        return False

    all_possible_tiles = []
    for suit in ['m', 'p', 's']:
        for rank in range(1, 10):
            all_possible_tiles.append(f"{rank}{suit}")
    for rank in range(1, 8):
        all_possible_tiles.append(f"{rank}z")

    for mock_tile in all_possible_tiles:
        test_hand = hand.copy()
        test_hand.append(mock_tile)
        if is_complete_hand(test_hand, melds):
            return True

    return False

def can_riichi(hand: list, melds: list, score: int) -> bool:
    """Условия объявления Риичи (только Menzenchin — полностью закрытая рука)."""
    if len(melds) > 0:
        return False
    if score < 1000:
        return False
    return is_tenpai(hand, melds)

def can_pon(hand: list, discard_tile: str) -> bool:
    """Проверяет, можно ли объявить Пон (в руке уже есть 2 таких же тайла)."""
    return hand.count(discard_tile) >= 2

def can_chii(hand: list, discard_tile: str) -> bool:
    """Проверяет, можно ли объявить Чи (только для следующего по ходу игрока).
    Работает только для мастей (m, p, s). Благородные тайлы (z) в Чи не собираются."""
    if 'z' in discard_tile:
        return False
        
    rank = int(discard_tile[:-1])
    suit = discard_tile[-1]
    
    # Возможные варианты последовательностей с участием сброшенного тайла:
    opt1 = (f"{rank+1}{suit}" in hand) and (f"{rank+2}{suit}" in hand)
    opt2 = (f"{rank-1}{suit}" in hand) and (f"{rank+1}{suit}" in hand)
    opt3 = (f"{rank-2}{suit}" in hand) and (f"{rank-1}{suit}" in hand)
    
    return opt1 or opt2 or opt3