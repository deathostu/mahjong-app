from engine.hand_validator import can_pon, can_chii, sort_mahjong_hand, is_tenpai, is_complete_hand
from engine.wall import MahjongWall

class MahjongGame:
    def __init__(self, game_id: int):
        self.game_id = game_id
        self.status = "waiting" # waiting, playing, finished
        self.players = []       # Список dict: [{"user_id": X, "username": Y, "seat": 0, "score": 25000, "hand": [], "discards": [], "melds": [], "riichi": False}]
        
        # Игровые параметры раунда
        self.wall = None
        self.current_round = "E1"  # E1-E4, S1-S4, W1-W4
        self.riichi_sticks = 0
        self.honba = 0
        self.active_player_seat = 0 # Чей сейчас ход (0: Восток, 1: Юг...)
        self.current_tsumo_tile = None
        self.dealer_seat = 0
        self.collected_calls = {}

    def add_player(self, user_id: int, username: str) -> bool:
        """Добавляет игрока в комнату, если есть свободные места."""
        if len(self.players) >= 4 or self.status != "waiting":
            return False
            
        # Проверяем, нет ли уже этого игрока в комнате
        if any(p["user_id"] == user_id for p in self.players):
            return False
            
        seat = len(self.players)
        self.players.append({
            "user_id": user_id,
            "username": username,
            "seat": seat,
            "score": 25000,
            "hand": [],
            "discards": [],
            "melds": [],
            "riichi": False,
            "riichi_pending": False,
            "available_actions": []
        })
        
        # Если набралось 4 игрока — автоматически стартуем игру
        if len(self.players) == 4:
            self.start_game()
            
        return True

    def get_player_seat(self, user_id: int) -> int:
        """Возвращает индекс сиденья (seat) для конкретного user_id."""
        for p in self.players:
            if p["user_id"] == user_id:
                return p["seat"]
        return 0 # Дефолтное сиденье, если игрок не найден

    def start_game(self):
        """Инициализирует начало матча (Ханчана)."""
        self.status = "playing"
        # Будем хранить числовой индекс раунда для простоты расчетов:
        # 0: E1, 1: E2, 2: E3, 3: E4, 4: S1, 5: S2 ...
        self.round_index = 0 
        self.riichi_sticks = 0
        self.honba = 0
        self.start_new_round()

    def start_new_round(self):
        """Запуск раунда (перемешивание стены, раздача рук)."""
        self.wall = MahjongWall()
        self.status = "playing"
        
        suits = ['E', 'S', 'W']
        current_suit = suits[self.round_index // 4]
        current_num = (self.round_index % 4) + 1
        self.current_round = f"{current_suit}{current_num}"
        
        self.dealer_seat = self.round_index % 4
        self.active_player_seat = self.dealer_seat # Дилер начинает раунд
        
        for player in self.players:
            player["hand"] = [self.wall.draw_tile() for _ in range(13)]
            player["hand"] = sort_mahjong_hand(player["hand"])
            player["discards"] = []
            player["melds"] = []
            player["riichi"] = False
            player["riichi_pending"] = False
            player["available_actions"] = []
            player["chii_choices"] = []
            player["forbidden_discards"] = []
            
        # ЖЕСТКАЯ ПРИВЯЗКА: Выдаем 14-й тайл СТРОГО текущему активному игроку (Дилеру)
        self.current_tsumo_tile = self.wall.draw_tile()
        
        # Очищаем временные экшены у всех перед стартовой проверкой
        for p in self.players:
            p["available_actions"] = []
            
        # Проверяем доступные кнопки СТРОГО для дилера
        self.check_my_turn_actions(self.players[self.active_player_seat])

    def advance_turn(self):
        """Передача обычного хода и выдача нового тайла."""
        self.status = "playing"
        
        # Полностью очищаем доступные объявления у всех игроков перед переходом хода
        for player in self.players:
            player["available_actions"] = []
            player["chii_choices"] = []
            
        # Сдвигаем ход на следующего игрока
        self.active_player_seat = (self.active_player_seat + 1) % 4
        
        next_tile = self.wall.draw_tile()
        if next_tile is None:
            print("--- СТЕНА ЗАКОНЧИЛАСЬ: РАУНД ЗАВЕРШЕН ВНИЧЬЮ ---")
            dealer_player = self.players[self.dealer_seat]
            from engine.hand_validator import is_tenpai
            dealer_has_tenpai = is_tenpai(dealer_player["hand"], dealer_player["melds"])
            
            if dealer_has_tenpai:
                self.honba += 1
            else:
                self.round_index += 1
                self.honba = 0
                
            if self.check_game_end():
                from database.db_manager import save_match_results
                save_match_results(self.game_id, self.current_round, self.players)
            else:
                self.start_new_round()
        else:
            # Назначаем тайл цумо текущему активному игроку
            self.current_tsumo_tile = next_tile
            
            active_player_obj = self.players[self.active_player_seat]
            active_player_obj["hand"] = sort_mahjong_hand(active_player_obj["hand"])
            
            # Проверяем доступные действия (Цумо, Риичи, Закрытый кан)
            self.check_my_turn_actions(active_player_obj)

    def perform_tsumogiri(self) -> bool:
        """Безопасно выполняет автоматический сброс тайла цумо для игрока в Риичи."""
        active_player_obj = self.players[self.active_player_seat]
        
        # Если игрок действительно в Риичи и у него на руках есть 14-й тайл
        if active_player_obj.get("riichi", False) and self.current_tsumo_tile:
            tsumo_to_discard = self.current_tsumo_tile
            print(f"[TSUMOGIRI SUCCESS] Автосброс тайла {tsumo_to_discard} для {active_player_obj['username']}")
            
            # Временно снимаем флаг Риичи, чтобы process_discard пропустил жесткую проверку Цумо
            # и возвращаем обратно сразу после вызова
            success = self.process_discard(active_player_obj["user_id"], tsumo_to_discard)
            return success
            
        return False

    def process_discard(self, user_id: int, tile: str) -> bool:
        if self.status != "playing":
            return False

        current_player = self.players[self.active_player_seat]
        if current_player["user_id"] != user_id:
            return False

        if tile in current_player.get("forbidden_discards", []):
            return False

        is_declaring_riichi = current_player.get("riichi_pending", False)

        if current_player.get("riichi", False) and not is_declaring_riichi:
            if tile != self.current_tsumo_tile:
                print(f"[RULES VIOLATION] Замок Риичи! Сброс только Цумо.")
                return False

        if is_declaring_riichi:
            valid_list = current_player.get("riichi_valid_discards", [])
            if tile not in valid_list:
                return False
            current_player["riichi_pending"] = False
            current_player["riichi"] = True

        current_player["discards"].append({
            "tile": tile,
            "is_riichi": is_declaring_riichi
        })
        
        full_hand = current_player["hand"].copy()
        if self.current_tsumo_tile:
            full_hand.append(self.current_tsumo_tile)
            
        if tile not in full_hand:
            return False
            
        if self.current_tsumo_tile == tile:
            self.current_tsumo_tile = None
        else:
            current_player["hand"].remove(tile)
            if self.current_tsumo_tile:
                current_player["hand"].append(self.current_tsumo_tile)
                self.current_tsumo_tile = None
            current_player["hand"] = sort_mahjong_hand(current_player["hand"])

        self.last_discard_tile = tile
        self.last_discard_seat = self.active_player_seat
        
        for p in self.players:
            p["available_actions"] = []
            p["chii_choices"] = []
        
        has_pending_actions = False
        for player in self.players:
            if player["seat"] == self.last_discard_seat:
                continue
                
            from engine.hand_validator import is_complete_hand
            potential_hand = player["hand"].copy()
            potential_hand.append(tile) 
            
            if is_complete_hand(potential_hand, player.get("melds", [])):
                player["available_actions"].append("ron")
                
            if player.get("riichi", False):
                if "ron" in player["available_actions"]:
                    player["available_actions"].append("skip")
                    has_pending_actions = True
                continue
                
            if player["hand"].count(tile) >= 2:
                player["available_actions"].append("pon")
            if player["hand"].count(tile) == 3:
                player["available_actions"].append("kan_open")
                
            next_seat = (self.last_discard_seat + 1) % 4
            if player["seat"] == next_seat and 'z' not in tile:
                rank = int(tile[:-1])
                suit = tile[-1]
                h = player["hand"]
                possible_chii_pairs = []
                if f"{rank+1}{suit}" in h and f"{rank+2}{suit}" in h: possible_chii_pairs.append([f"{rank+1}{suit}", f"{rank+2}{suit}"])
                if f"{rank-1}{suit}" in h and f"{rank+1}{suit}" in h: possible_chii_pairs.append([f"{rank-1}{suit}", f"{rank+1}{suit}"])
                if f"{rank-2}{suit}" in h and f"{rank-1}{suit}" in h: possible_chii_pairs.append([f"{rank-2}{suit}", f"{rank-1}{suit}"])
                if possible_chii_pairs:
                    player["chii_choices"] = possible_chii_pairs
                    for idx in range(len(possible_chii_pairs)):
                        player["available_actions"].append(f"chii_{idx}")
            
            if player["available_actions"]:
                player["available_actions"].append("skip")
                has_pending_actions = True

        if has_pending_actions:
            self.status = "waiting_for_calls"
            self.collected_calls = {} 
            return True
            
        self.advance_turn()
        return True

    def process_call(self, user_id: int, call_type: str) -> bool:
        """Собирает заявки объявлений и мгновенно разруливает автоприоритеты."""
        # 1. МГНОВЕННЫЙ ОТРЕЗ ДЛЯ ЗАКРЫТОГО КАНА (ИЗ-ПОД РИИЧИ)
        if call_type.startswith("kan_closed"):
            calling_player = next(p for p in self.players if p["user_id"] == user_id)
            choice_idx = int(call_type.split("_")[-1])
            kan_tile = calling_player["kan_choices"][choice_idx]
            
            if self.current_tsumo_tile == kan_tile: self.current_tsumo_tile = None
            calling_player["hand"] = [t for t in calling_player["hand"] if t != kan_tile]
            
            calling_player["melds"].append({
                "tiles": [f"{kan_tile}*", kan_tile, kan_tile, f"{kan_tile}*"],
                "rotate_index": -1
            })
            self.current_tsumo_tile = self.wall.draw_rinshan_tile()
            self.wall.open_next_dora()
            calling_player["available_actions"] = []
            self.check_my_turn_actions(calling_player)
            return True

        # 2. МГНОВЕННЫЙ ОТРЕЗ ДЛЯ ДОБАВЛЕННОГО КАНА (СЁМИНКАН)
        if call_type.startswith("kan_added"):
            calling_player = next(p for p in self.players if p["user_id"] == user_id)
            choice_idx = int(call_type.split("_")[-1])
            kan_tile = calling_player["kan_choices"][choice_idx]
            
            if self.current_tsumo_tile == kan_tile: self.current_tsumo_tile = None
            else: calling_player["hand"].remove(kan_tile)
            
            # Находим старый Пон в melds и превращаем его в Кан (добавляем 4-й тайл)
            for meld in calling_player["melds"]:
                m_tiles = meld.get("tiles", meld) if isinstance(meld, dict) else meld
                if len(m_tiles) == 3 and m_tiles[0] == kan_tile:
                    m_tiles.append(kan_tile) # Превращаем в квад
                    break
                    
            self.current_tsumo_tile = self.wall.draw_rinshan_tile()
            self.wall.open_next_dora()
            calling_player["available_actions"] = []
            self.check_my_turn_actions(calling_player)
            return True

        if self.status != "waiting_for_calls": return False
        calling_player = next(p for p in self.players if p["user_id"] == user_id)
        
        self.collected_calls[user_id] = call_type
        calling_player["available_actions"] = []

        # ВЫЧИСЛЯЕМ РЕАЛЬНЫЕ АВТОПРИОРИТЕТЫ
        def get_priority(call: str) -> int:
            if call == "ron": return 1
            if call in ["pon", "kan_open"]: return 2
            if call.startswith("chii"): return 3
            return 4

        highest_submitted_priority = 4
        for u_id, call in self.collected_calls.items():
            highest_submitted_priority = min(highest_submitted_priority, get_priority(call))

        players_with_actions = 0
        for p in self.players:
            if p["available_actions"] or p["user_id"] in self.collected_calls or len(p.get("chii_choices", [])) > 0:
                players_with_actions += 1

        # Проверяем, может ли КТО-ТО ИЗ ОСТАВШИХСЯ думающих реально перебить текущую лучшую ставку
        can_someone_overtake = False
        for p in self.players:
            if p["user_id"] not in self.collected_calls:
                # ВАЖНО: Проверяем Рон СТРОГО по его реальному присутствию в available_actions на бэкенде!
                has_real_ron = "ron" in p.get("available_actions", [])
                has_pon_or_kan = p["hand"].count(self.last_discard_tile) >= 2
                
                potential_best = 4
                if has_real_ron: potential_best = min(potential_best, 1)
                if has_pon_or_kan: potential_best = min(potential_best, 2)
                if len(p.get("chii_choices", [])) > 0: potential_best = min(potential_best, 3)

                if potential_best < highest_submitted_priority:
                    can_someone_overtake = True

        # Если все ответили ЛИБО если нажат Пон/Кан, а у остальных думающих нет Рона/Пона (только Чи) — закрываем опрос!
        if len(self.collected_calls) >= players_with_actions or not can_someone_overtake:
            print("[PRIORITY CHECK] Автоприоритет сработал! Конфликт исчерпан.")
            self.resolve_collected_calls()
            return True

        return True

    def resolve_collected_calls(self):
        """Выбирает и выполняет самое приоритетное объявление по правилам турниров EMA."""
        tile = self.last_discard_tile
        discarder_seat = self.last_discard_seat
        
        best_user_id = None
        best_call = "skip"
        
        # Ранг приоритета: Ron (1) > Pon/Kan (2) > Chii (3) > Skip (4)
        def get_call_priority(call: str) -> int:
            if call == "ron": return 1
            if call in ["pon", "kan_open"]: return 2
            if call.startswith("chii"): return 3
            return 4

        # Ищем заявку с наивысшим приоритетом в коллекторе
        for u_id, call in self.collected_calls.items():
            if get_call_priority(call) < get_call_priority(best_call):
                best_call = call
                best_user_id = u_id

        # Если наивысшим приоритетом оказался Пропустить (все нажали Skip)
        if best_call == "skip" or best_user_id is None:
            print("[PRIORITY] Все игроки пропустили объявление. Ход идет дальше.")
            # ОЧИЩАЕМ ВРЕМЕННЫЕ МАССИВЫ СТРОГО ТУТ
            self.collected_calls = {}
            for p in self.players:
                p["available_actions"] = []
                p["chii_choices"] = []
            self.advance_turn()
            return

        # Находим победителя приоритета
        winner = next(p for p in self.players if p["user_id"] == best_user_id)
        from_relative = (discarder_seat - winner["seat"] + 4) % 4
        print(f"[PRIORITY SUCCESS] Объявление {best_call} от {winner['username']} выполнено!")

        if best_call == "ron":
            self.collected_calls = {}
            for p in self.players:
                p["available_actions"] = []
                p["chii_choices"] = []
            self.process_win(best_user_id, "ron")
            return

        elif best_call == "pon":
            winner["hand"].remove(tile)
            winner["hand"].remove(tile)
            meld_tiles = [tile, tile, tile]
            rotate_idx = 0 if from_relative == 3 else (1 if from_relative == 2 else 2)
            winner["melds"].append({"tiles": meld_tiles, "rotate_index": rotate_idx})
            
            discarder = self.players[discarder_seat]
            if discarder["discards"]:
                stolen_tile_obj = discarder["discards"].pop()
                # ИСПРАВЛЕНИЕ 1: Если украли именно тайл объявления Риичи
                if stolen_tile_obj.get("is_riichi", False):
                    print(f"[RIICHI TRANSFER] Тайл Риичи игрока {discarder['username']} украден! Переносим поворот на следующий ход.")
                    discarder["riichi_pending"] = True # Взводим флаг отложенного поворота снова!
                    discarder["riichi"] = False

            self.active_player_seat = winner["seat"]
            self.current_tsumo_tile = None 
            self.status = "playing"

        # --- Находим этот блок внутри метода resolve_collected_calls в engine/manager.py ---
        elif best_call.startswith("chii"):
            choice_idx = int(best_call.split("_")[-1])
            chosen_pair = winner.get("chii_choices", [])[choice_idx]
            
            h = winner["hand"]
            h.remove(chosen_pair[0]) # ИСПРАВЛЕНИЕ: Удаляем первый конкретный тайл из пары
            h.remove(chosen_pair[1]) # ИСПРАВЛЕНИЕ: Удаляем второй конкретный тайл из пары
            
            # Формируем сет: украденный тайл идет самым первым (индекс 0), остальные два справа
            meld_tiles = [tile] + sorted(chosen_pair)
            
            # Записываем в melds объект со свойствами
            winner["melds"].append({
                "tiles": meld_tiles,
                "rotate_index": 0
            })
            
            discarder = self.players[discarder_seat]
            if discarder["discards"]: discarder["discards"].pop()

            # --- ИСПРАВЛЕНИЕ: ИСПРАВЛЕННЫЕ УСЛОВИЯ КУИКАЭ (ЗАПРЕТ СБРОСА) ---
            forbidden_discards = [tile] # Нельзя сбрасывать тот же тайл
            
            rank = int(tile[:-1])
            suit = tile[-1]
            
            # Сет отсортирован бэкендом, проверяем, где именно оказался украденный тайл 
            # внутри математической последовательности стрита
            full_set_sorted = sorted(meld_tiles)
            
            if full_set_sorted[0] == tile: 
                # Украденный тайл оказался самым маленьким (например, взяли 3m к 4-5m)
                # По правилам запрещено немедленно сбрасывать противоположный край стрита rank + 3 (6m)
                forbidden_discards.append(f"{rank+3}{suit}")
            elif full_set_sorted[-1] == tile: 
                # Украденный тайл оказался самым большим (например, взяли 5m к 3-4m)
                # Запрещено немедленно сбрасывать rank - 3 (2m)
                forbidden_discards.append(f"{rank-3}{suit}")
                
            winner["forbidden_discards"] = forbidden_discards

            self.active_player_seat = winner["seat"]
            self.current_tsumo_tile = None
            self.status = "playing"


        elif best_call == "kan_open":
            winner["hand"] = [t for t in winner["hand"] if t != tile]
            meld_tiles = [tile, tile, tile, tile]
            rotate_idx = 0 if from_relative == 3 else (1 if from_relative == 2 else 3)
            winner["melds"].append({"tiles": meld_tiles, "rotate_index": rotate_idx})
            
            discarder = self.players[discarder_seat]
            if discarder["discards"]: discarder["discards"].pop()
                    
            self.active_player_seat = winner["seat"]
            self.current_tsumo_tile = self.wall.draw_rinshan_tile()
            self.wall.open_next_dora()
            self.status = "playing"

        # ОЧИЩАЕМ ВСЕ СТРУКТУРЫ ПОСЛЕ УСПЕШНОГО ВЫПОЛНЕНИЯ ДЕЙСТВИЯ
        self.collected_calls = {}
        for p in self.players:
            p["available_actions"] = []
            p["chii_choices"] = []


    def process_win(self, winner_user_id: int, win_type: str):
        """Обрабатывает победу игрока (Рон или Цумо)."""
        winner = None
        for p in self.players:
            if p["user_id"] == winner_user_id:
                winner = p
                break
                
        if not winner: return
        
        base_win_points = 8000 # Фиксированная выплата за победу (Манган) [1]
        
        if win_type == "ron":
            # Забираем очки у сбросившего игрока
            loser = self.players[self.last_discard_seat]
            loser["score"] -= base_win_points
            winner["score"] += base_win_points
            print(f"Игрок {winner['username']} выиграл по РОНУ у {loser['username']}! +8000 очков.")
            
        elif win_type == "tsumo":
            # Распределяем выплату между всеми соперниками
            share = base_win_points // 3
            for p in self.players:
                if p["seat"] != winner["seat"]:
                    p["score"] -= share
                    winner["score"] += share
            print(f"Игрок {winner['username']} выиграл по ЦУМО со стены! +8000 очков.")
            
        # Забираем все палочки риичи со стола (каждая по 1000 очков)
        winner["score"] += self.riichi_sticks * 1000
        self.riichi_sticks = 0
        
        # Проверяем ТЗ: если дилер (Восток) выиграл — раунд не переходит (Ренчан)
        # Если выиграл кто-то другой — дилер сдвигается!
        if winner["seat"] == self.dealer_seat:
            print("Дилер выиграл раунд! Раунд сохраняется.")
            self.honba += 1
        else:
            print("Выиграл не дилер. Раунд сдвигается.")
            self.round_index += 1
            self.honba = 0
            
        # Проверяем условия конца игры (минус по очкам или финал 4-го Юга)
        if self.check_game_end():
            # Метод сохранения результатов матча в БД
            from database.db_manager import save_match_results
            save_match_results(self.game_id, self.current_round, self.players)
        else:
            self.start_new_round()


    def get_player_state(self, seat_index: int) -> dict:
        """Генерирует состояние игры для конкретного игрока (скрывает чужие карты)."""
        state_players = []
        wind_names = {0: "東", 1: "南", 2: "西", 3: "北"}
        wind_order = ["東", "南", "西", "北"]

        # Находим объект текущего игрока, который делает запрос
        me = None
        for p in self.players:
            if p["seat"] == seat_index:
                me = p
                
        for p in self.players:
            is_me = (p["seat"] == seat_index)
            
            # Если игра еще не началась, распределяем ветра просто по порядку мест
            if self.status == "waiting":
                player_wind = wind_order[p["seat"] % 4]
            else:
                # Если игра идет, вычисляем ветер относительно текущего дилера раунда
                wind_index = (p["seat"] - self.dealer_seat + 4) % 4
                player_wind = wind_order[wind_index]
            
            state_players.append({
                "seat": p["seat"],
                "username": p["username"],
                "score": p["score"],
                "player_wind": player_wind,
                "riichi_declared": p.get("riichi", False),
                "hand_size": len(p["hand"]),
                "discards": p.get("discards", []),
                # Поле melds должно отдаваться ВСЕГДА (открытая информация), 
                # скрывается (условие if is_me) только закрытая рука "hand"
                "melds": p.get("melds", []), 
                "hand": p["hand"] if is_me else None 
            })
            
        return {
            "game_id": self.game_id,
            "status": self.status,
            "current_round": self.current_round,
            "tiles_left_in_wall": self.wall.tiles_left if self.wall else 0,
            "dora_indicators": self.wall.dora_indicators if self.wall else [],
            "active_player_seat": self.active_player_seat,
            "your_seat": seat_index,
            "tsumo_tile": self.current_tsumo_tile if self.active_player_seat == seat_index else None,
            "players": state_players,
            "available_actions": me.get("available_actions", []) if me else [],
            "chii_choices": me.get("chii_choices", []) if me else [],
            "riichi_valid_discards": me.get("riichi_valid_discards", []) if me else [] 
        }

    def check_game_end(self) -> bool:
        """Проверяет условия завершения матча. 
        Возвращает True, если игра окончена."""
        # Условие 1: Кто-то ушел в минус
        for player in self.players:
            if player["score"] < 0:
                print(f"Игра окончена! Игрок {player['username']} ушел в минус ({player['score']}).")
                self.status = "finished"
                return True
                
        # Условие 2: Наступил конец Южного раунда (например, сыгран S4)
        # Если раунд должен перейти на Запад (W1), но у кого-то уже есть >= 30000, игра завершается
        if self.current_round == "S4":
            has_winner = any(player["score"] >= 30000 for player in self.players)
            if has_winner:
                print("Конец 4-го Юга, у игроков есть 30000+ очков. Игра завершена.")
                self.status = "finished"
                return True
            else:
                # Продлеваем игру на Западный раунд (Запад 1)
                print("Ни у кого нет 30000 к концу 4-го Юга. Начинается Западный раунд!")
                self.current_round = "W1"
                return False

        return False

    def check_my_turn_actions(self, player):
        """Проверяет доступные действия в свой ход (Риичи, Цумо, Закрытые и Добавленные Каны)."""
        player["available_actions"] = []
        player["riichi_valid_discards"] = []
        player["kan_choices"] = [] # Очищаем старый выбор канов
        
        full_hand = player["hand"].copy()
        if self.current_tsumo_tile and self.active_player_seat == player["seat"]:
            full_hand.append(self.current_tsumo_tile)
            
        from engine.hand_validator import is_complete_hand, can_riichi, is_tenpai
        is_closed_hand = (len(player.get("melds", [])) == 0)
        
        # 1. Проверка на Цумо
        if is_complete_hand(full_hand, player["melds"]):
            player["available_actions"].append("tsumo")
            
        # 2. Режим выбора карты для Риичи
        if player.get("riichi_pending", False):
            for tile in set(full_hand):
                test_hand = full_hand.copy()
                test_hand.remove(tile)
                if is_tenpai(test_hand, player["melds"]):
                    if tile not in player["riichi_valid_discards"]:
                        player["riichi_valid_discards"].append(tile)
            return

        # 3. Автоматическая проверка на доступность кнопки Риичи
        if is_closed_hand and not player.get("riichi", False) and player.get("score", 0) >= 1000:
            has_tenpai_now = False
            for tile in set(full_hand):
                test_hand = full_hand.copy()
                test_hand.remove(tile)
                if is_tenpai(test_hand, player["melds"]):
                    has_tenpai_now = True
                    break
            if has_tenpai_now:
                player["available_actions"].append("riichi")
            
        # 4. ПРОВЕРКА НА КАНЫ (Работает в том числе ИЗ-ПОД РИИЧИ!)
        # Проверяем Закрытый Кан (Анкан): 4 одинаковых тайла в закрытой части
        distinct_tiles = set(full_hand)
        for tile in distinct_tiles:
            if full_hand.count(tile) == 4:
                # По правилам Риичи: Анкан разрешен, только если не меняет ожидание. 
                # Разрешаем, если каре собралось полностью в руке
                if tile not in player["kan_choices"]:
                    player["kan_choices"].append(tile)
                idx = player["kan_choices"].index(tile)
                if f"kan_closed_{idx}" not in player["available_actions"]:
                    player["available_actions"].append(f"kan_closed_{idx}")

        # Проверяем Добавленный Открытый Кан (Сёминкан): 4-й тайл к уже открытому Пону
        # Доступно только если игрок НЕ в Риичи
        if not player.get("riichi", False):
            for meld in player.get("melds", []):
                # Проверяем, является ли объявление Поном (3 одинаковых тайла)
                meld_tiles = meld.get("tiles", meld) if isinstance(meld, dict) else meld
                if len(meld_tiles) == 3 and meld_tiles[0] == meld_tiles[1]:
                    base_tile = meld_tiles[0]
                    # Если у нас в закрытой руке или в цумо лежит 4-й такой же тайл
                    if base_tile in full_hand:
                        if base_tile not in player["kan_choices"]:
                            player["kan_choices"].append(base_tile)
                        idx = player["kan_choices"].index(base_tile)
                        if f"kan_added_{idx}" not in player["available_actions"]:
                            player["available_actions"].append(f"kan_added_{idx}")
                
        if player["available_actions"]:
            player["available_actions"].append("skip")


class GameManager:
    def __init__(self):
        self.active_games = {} # dict: {game_id: MahjongGame}

    def create_game(self, game_id: int) -> MahjongGame:
        game = MahjongGame(game_id)
        self.active_games[game_id] = game
        return game

    def get_game(self, game_id: int) -> MahjongGame:
        return self.active_games.get(game_id)

# Создаем глобальный объект менеджера, который импортируем в роуты
game_manager = GameManager()
