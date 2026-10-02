import asyncio
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from database.db_manager import init_db, register_user, check_user_credentials, get_user_stats
from engine.manager import game_manager
from pydantic import BaseModel

app = FastAPI()

# Хранилище активных WebSocket-соединений: { game_id: { user_id: WebSocket } }
active_connections = {}

async def broadcast_game_state(game_id: int):
    """Рассылает текущее состояние игры всем подключенным игрокам в комнате."""
    game = game_manager.get_game(game_id)
    if not game:
        return

    if game_id in active_connections:
        # 1. Сначала рассылаем стейт абсолютно всем вкладкам стола
        for user_id, websocket in active_connections[game_id].items():
            try:
                player_state = game.get_player_state(game.get_player_seat(user_id))
                await websocket.send_json({
                    "event": "game_state",
                    "data": player_state
                })
            except Exception as e:
                print(f"Ошибка отправки стейта игроку {user_id}: {e}")

        # 2. ИСПРАВЛЕНИЕ: Автосброс для Риичи запускается ИЗОЛИРОВАННО после рассылки пакетов
        active_player = game.players[game.active_player_seat]
        if game.status == "playing" and active_player.get("riichi", False) and game.current_tsumo_tile:
            # Проверяем, нет ли у игрока в Риичи экшена Цумо со стены
            real_options = [a for a in active_player.get("available_actions", []) if a != "skip"]
            
            if not real_options:
                # Даем задержку в 0.8 сек, чтобы игроки успели увидеть прилетевший тайл Цумо
                await asyncio.sleep(0.8)
                
                # Запускаем автосброс
                success = game.perform_tsumogiri()
                if success:
                    # Рекурсивно вызываем broadcast для следующего хода
                    await broadcast_game_state(game_id)


@app.on_event("startup")
def startup_event():
    init_db()
    # Создаем одну тестовую игру с ID=1
    game_manager.create_game(1)
    print("Создана тестовая игра с ID=1")

@app.get("/")
async def get_index():
    return FileResponse(os.path.join("static", "index.html"))

@app.get("/game")
async def get_game():
    return FileResponse(os.path.join("static", "game.html"))

@app.get("/api/stats/{user_id}")
async def api_get_stats(user_id: int):
    return get_user_stats(user_id)

# Подключаем статику
app.mount("/static", StaticFiles(directory="static"), name="static")


# --- WEB SOCKET LOGIC ---

@app.websocket("/ws/{game_id}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: int, user_id: int, username: str = "Игрок"):
    await websocket.accept()
    
    if game_id not in active_connections:
        active_connections[game_id] = {}
        
    active_connections[game_id][user_id] = websocket
    
    game = game_manager.get_game(game_id)
    if game:
        # Сажаем игрока под его РЕАЛЬНЫМ именем из авторизации
        game.add_player(user_id, username)
        
    await broadcast_game_state(game_id)
    
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            
            if action == "discard":
                tile = data.get("tile")
                game = game_manager.get_game(game_id)
                if game:
                    success = game.process_discard(user_id, tile)
                    if success:
                        await broadcast_game_state(game_id)
            
            elif action == "call_action":
                call_type = data.get("call_type")
                game = game_manager.get_game(game_id)
                
                if game:
                    if call_type == "skip":
                        if game.status == "waiting_for_calls":
                            game.process_call(user_id, "skip")
                        else:
                            # ИСПРАВЛЕНИЕ: Если игрок отменил ставку Риичи в свой собственный ход
                            p = game.players[game.active_player_seat]
                            p["riichi_pending"] = False
                            p["riichi_valid_discards"] = [] # Очищаем список, чтобы снять затемнение тайлов!
                            p["available_actions"] = []
                        await broadcast_game_state(game_id)
                        
                    elif call_type in ["ron", "tsumo"]:
                        game.process_win(user_id, call_type)
                        await broadcast_game_state(game_id)
                        
                    # --- Находим этот блок внутри main.py ---
                    elif call_type == "riichi":
                        game = game_manager.get_game(game_id)
                        if game:
                            p = game.players[game.active_player_seat]
                            
                            p["score"] -= 1000
                            game.riichi_sticks += 1
                            
                            # Взводим флаг: игра переходит в фазу выбора карты для Риичи
                            p["riichi_pending"] = True 
                            
                            # Очищаем кнопку Риичи с экрана
                            p["available_actions"] = []
                            
                            # ГАРАНТИЯ: Жестко возвращаем статус обычной игры, чтобы активировать клики по картам руки!
                            game.status = "playing"
                            
                            # Пересчитываем белый список дискардов перед отправкой пакета
                            game.check_my_turn_actions(p)
                            
                            await broadcast_game_state(game_id)

                        
                    # Передаем строку объявления 
                    # --- Находим этот блок внутри main.py под elif action == "call_action": ---
                    elif call_type in ["pon", "kan_open"] or call_type.startswith("chii") or call_type.startswith("kan_closed") or call_type.startswith("kan_added"):
                        success = game.process_call(user_id, call_type)
                        if success:
                            await broadcast_game_state(game_id)
                        else:
                            print(f"[WS ERROR] Ошибка вызова {call_type}")

            elif action == "debug_trigger":
                mode = data.get("mode")
                game = game_manager.get_game(game_id)
                
                if game:
                    # Находим игрока, который нажал отладочную кнопку
                    current_p = None
                    for p in game.players:
                        if p["user_id"] == user_id:
                            current_p = p
                            break
                    
                    if current_p:
                        if mode == "force_riichi":
                            # Принудительно включаем режим выбора тайла для Риичи
                            current_p["available_actions"] = ["riichi", "skip"]
                            # Виртуально разрешаем сбросить вообще любой тайл из его текущей руки
                            current_p["riichi_valid_discards"] = current_p["hand"].copy()
                            if game.current_tsumo_tile and game.active_player_seat == current_p["seat"]:
                                current_p["riichi_valid_discards"].append(game.current_tsumo_tile)
                            
                            # Взводим флаг ожидания
                            current_p["riichi_pending"] = True
                            print(f"[DEBUG CHEAT] Игроку {username} принудительно выдана кнопка РИИЧИ")
                            
                        elif mode == "force_ron":
                            # Принудительно выводим кнопку победы по Рону
                            game.status = "waiting_for_calls"
                            current_p["available_actions"] = ["ron", "skip"]
                            print(f"[DEBUG CHEAT] Игроку {username} принудительно выдана кнопка РОН")
                            
                        # Сразу рассылаем обновленный стейт, чтобы кнопки мгновенно выскочили на экране
                        await broadcast_game_state(game_id)


            
    except WebSocketDisconnect:
        if game_id in active_connections and user_id in active_connections[game_id]:
            del active_connections[game_id][user_id]
        print(f"Игрок {user_id} отключился от игры {game_id}")


# Схема данных для запросов
class UserAuth(BaseModel):
    username: str
    password: str

@app.post("/api/register")
async def api_register(user: UserAuth):
    success = register_user(user.username, user.password)
    if not success:
        raise HTTPException(status_code=400, detail="Это имя пользователя уже занято")
    
    # После регистрации сразу авторизуем
    credentials = check_user_credentials(user.username, user.password)
    return credentials

@app.post("/api/login")
async def api_login(user: UserAuth):
    credentials = check_user_credentials(user.username, user.password)
    if not credentials:
        raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")
    return credentials
