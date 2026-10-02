let socket = null;

if (window.location.pathname === '/game') {
    // Уникальный ID для тестирования в разных вкладках
    const userId = Math.floor(Math.random() * 100000) + Date.now() % 10000;
    const savedName = localStorage.getItem('username') || `Игрок_${userId}`;
    const gameId = 1; 
    
    const wsUrl = `ws://${window.location.host}/ws/${gameId}/${userId}?username=${encodeURIComponent(savedName)}`;
    socket = new WebSocket(wsUrl);
    
    socket.onopen = function(e) {
        console.log("[WebSocket] Соединение установлено! Наш ID:", userId);
    };
    
    socket.onmessage = function(event) {
        try {
            const message = JSON.parse(event.data);
            if (message.event === 'game_state') {
                renderTable(message.data);
            }
        } catch (err) {
            console.error("[WebSocket] Ошибка при обработке сообщения или рендере:", err);
        }
    };
    
    socket.onerror = function(error) {
        console.error(`[WebSocket] Ошибка: ${error.message}`);
    };
    
    socket.onclose = function(event) {
        console.log("[WebSocket] Соединение закрыто.");
    };

    window.discardTile = function(tile) {
        if (socket && socket.readyState === WebSocket.OPEN) {
            console.log("Отправляем сброс тайла:", tile);
            socket.send(JSON.stringify({
                "action": "discard",
                "tile": tile
            }));
        }
    };

    window.sendAction = function(action) {
        if (socket && socket.readyState === WebSocket.OPEN) {
            console.log("Отправляем объявление:", action);
            socket.send(JSON.stringify({
                "action": "call_action",
                "call_type": action
            }));
        }
    };

    window.debugAction = function(mode) {
        if (socket && socket.readyState === WebSocket.OPEN) {
            console.log("[DEBUG] Отправляем чит-команду на сервер:", mode);
            socket.send(JSON.stringify({
                "action": "debug_trigger",
                "mode": mode
            }));
        }
    };
}

function renderTable(gameState) {
    // 1. Обновляем параметры центра стола
    document.getElementById('round-name').innerText = gameState.current_round || 'E1';
    document.getElementById('wall-count').innerText = gameState.tiles_left_in_wall || 0;
    document.getElementById('riichi-count').innerText = gameState.riichi_sticks || 0;
    
    const dora = gameState.dora_indicators || [];
    const doraContainer = document.getElementById('dora-indicator');
    if (doraContainer) {
        doraContainer.innerHTML = '';
        
        // Маджонг-лимит: в стене доры всегда ровно 5 позиций
        for (let i = 0; i < 5; i++) {
            const tileEl = document.createElement('div');
            
            if (i < dora.length) {
                // Если дора уже открыта — рендерим её каллиграфию
                tileEl.className = 'tile';
                tileEl.innerHTML = translateTile(dora[i]);
            } else {
                // Если дора ещё закрыта — рендерим её рубашкой вверх
                tileEl.className = 'tile tile-back';
            }
            doraContainer.appendChild(tileEl);
        }
    }

    const mySeat = gameState.your_seat;
    const players = gameState.players || [];

    // Находим имя текущего ходящего игрока
    const activePlayer = players.find(p => p.seat === gameState.active_player_seat);
    const activePlayerName = activePlayer ? activePlayer.username : `Игрок ${gameState.active_player_seat}`;

    // Обновляем статус центральной панели
    const statusEl = document.getElementById('game-status');
    if (statusEl) {
        if (gameState.status === 'playing') {
            statusEl.innerText = "Ход игрока: " + activePlayerName;
            statusEl.style.color = "#2ecc71";
        } else if (gameState.status === 'waiting_for_calls') {
            statusEl.innerText = "ПАУЗА: Ожидание объявлений";
            statusEl.style.color = "#e67e22";
        } else {
            statusEl.innerText = "Статус: " + gameState.status;
        }
    }

    // 2. Отрисовываем зоны и заполняем Центральный Компас
    players.forEach(player => {
        const relativePosition = (player.seat - mySeat + 4) % 4;
        
        let zoneId = '';
        let centerNameId = '';
        if (relativePosition === 0) { zoneId = 'zone-bottom'; centerNameId = 'c-name-bottom'; }
        else if (relativePosition === 1) { zoneId = 'zone-right'; centerNameId = 'c-name-right'; }
        else if (relativePosition === 2) { zoneId = 'zone-top'; centerNameId = 'c-name-top'; }
        else if (relativePosition === 3) { zoneId = 'zone-left'; centerNameId = 'c-name-left'; }

        const zoneEl = document.getElementById(zoneId);
        if (!zoneEl) return;

        // Вывод имени и очков в компас центральной панели
        const windMarker = player.player_wind ? ` [${player.player_wind}]` : '';
        const riichiMarker = player.riichi_declared ? ' [R]' : '';
        const centerNameEl = document.getElementById(centerNameId);
        if (centerNameEl) {
            centerNameEl.innerText = `${player.username}${windMarker}${riichiMarker} (${player.score})`;
        }

        // Рендерим сбросы (дискарды)
        const discardsGrid = zoneEl.querySelector('.discards-grid');
        if (discardsGrid) {
            discardsGrid.innerHTML = '';
            if (player.discards) {
                player.discards.forEach(tileObj => {
                    const tileEl = document.createElement('div');
                    // Если у тайла стоит флаг is_riichi, добавляем ему класс поворота
                    tileEl.className = 'tile' + (tileObj.is_riichi ? ' tile-rotated' : '');
                    tileEl.innerHTML = translateTile(tileObj.tile);
                    discardsGrid.appendChild(tileEl);
                });
            }
        }

        // Синхронная отрисовка мелдсов (объявлений) по ID контейнеров для ВСЕХ в лобби
        let currentMeldsId = '';
        if (relativePosition === 0) currentMeldsId = 'melds-bottom';
        else if (relativePosition === 1) currentMeldsId = 'melds-right';
        else if (relativePosition === 2) currentMeldsId = 'melds-top';
        else if (relativePosition === 3) currentMeldsId = 'melds-left';

        const meldsContainer = document.getElementById(currentMeldsId);
        if (meldsContainer) {
            meldsContainer.innerHTML = '';
            if (player.melds && player.melds.length > 0) {
                // Разворачиваем только порядок самих сетов (чтобы последний взятый был левее остальных)
                const reversedMelds = [...player.melds].reverse();
                
                reversedMelds.forEach(meldObj => {
                    if (meldObj.tiles) {
                        meldObj.tiles.forEach((t, tIdx) => {
                            const mTile = document.createElement('div');
                            
                            // Проверяем, совпадает ли текущий индекс тайла с rotate_index от сервера
                            const isRotated = (tIdx === meldObj.rotate_index);
                            mTile.className = 'tile' + (isRotated ? ' tile-rotated' : '');
                            
                            mTile.innerHTML = translateTile(t);
                            meldsContainer.appendChild(mTile);
                        });
                    }
                });
            }
        }

        // Рендерим закрытые руки
        if (relativePosition === 0) {
            const validList = gameState.riichi_valid_discards || [];
            
            // Рука полностью блокируется (затемняется), если мы УЖЕ в Риичи, 
            // ЛИБО если мы находимся в режиме выбора легального тайла ставки Риичи
            const isHandTotallyLocked = player.riichi_declared; 
            const isChoosingRiichi = (gameState.status === 'playing' && validList.length > 0);

            const handEl = document.getElementById('my-hand');
            if (handEl) {
                handEl.innerHTML = '';
                if (player.hand) {
                    player.hand.forEach(tile => {
                        const tileEl = document.createElement('div');
                        
                        // ИСПРАВЛЕНИЕ: если рука залочена риичи, то ВСЕ тайлы закрытой руки получают класс tile-disabled
                        let isInvalid = isHandTotallyLocked || (isChoosingRiichi && validList.indexOf(tile) === -1);
                        
                        tileEl.className = 'tile' + (isInvalid ? ' tile-disabled' : '');
                        tileEl.innerHTML = translateTile(tile);
                        
                        if (!isInvalid) {
                            tileEl.onclick = () => window.discardTile(tile);
                        }
                        handEl.appendChild(tileEl);
                    });
                }
            }

            // Тайл цумо остается ярким и доступным для сброса (если мы не в тотальном автосбросе)
            const tsumoEl = document.getElementById('tsumo-tile');
            if (tsumoEl) {
                tsumoEl.innerHTML = '';
                if (gameState.tsumo_tile && gameState.active_player_seat === mySeat) {
                    const tileEl = document.createElement('div');
                    
                    let isInvalid = isChoosingRiichi && (validList.indexOf(gameState.tsumo_tile) === -1);
                    
                    tileEl.className = 'tile' + (isInvalid ? ' tile-disabled' : '');
                    tileEl.innerHTML = translateTile(gameState.tsumo_tile);
                    
                    if (!isInvalid) {
                        tileEl.onclick = () => window.discardTile(gameState.tsumo_tile);
                    }
                    tsumoEl.appendChild(tileEl);
                }
            }
        } else {
            // Закрытые руки соперников (рубашки)
            let opponentHandId = '';
            if (relativePosition === 1) opponentHandId = 'hand-right';
            else if (relativePosition === 2) opponentHandId = 'hand-top';
            else if (relativePosition === 3) opponentHandId = 'hand-left';

            const oppHandEl = document.getElementById(opponentHandId);
            if (oppHandEl) {
                oppHandEl.innerHTML = '';
                const size = player.hand_size || 13;
                for (let i = 0; i < size; i++) {
                    const tileEl = document.createElement('div');
                    tileEl.className = 'tile tile-back'; 
                    oppHandEl.appendChild(tileEl);
                }
            }
        }
    });

    // 3. ГЕНЕРАЦИЯ КНОПОК ДЕЙСТВИЙ ИГРОКА (С ПРЕВЬЮ)
    const buttonsContainer = document.getElementById('action-buttons');
    if (buttonsContainer) {
        buttonsContainer.innerHTML = ''; 
        if (gameState.available_actions && gameState.available_actions.length > 0) {
            gameState.available_actions.forEach(action => {
                const btn = document.createElement('button');
                
                if (action === 'pon') {
                    btn.innerText = 'ПОН (Триплет)';
                } else if (action.startsWith('chii')) {
                    const parts = action.split('_');
                    const choiceIdx = parseInt(parts[1], 10);
                    
                    btn.innerText = 'ЧИ с парой: ';
                    
                    if (gameState.chii_choices && gameState.chii_choices[choiceIdx]) {
                        const pair = gameState.chii_choices[choiceIdx];
                        
                        const preview1 = document.createElement('span');
                        preview1.className = 'tile btn-tile-preview';
                        preview1.innerHTML = translateTile(pair[0]);
                        
                        const preview2 = document.createElement('span');
                        preview2.className = 'tile btn-tile-preview';
                        preview2.innerHTML = translateTile(pair[1]);
                        
                        btn.appendChild(preview1);
                        btn.appendChild(preview2);
                    }
                }
                else if (action.startsWith('kan_added')) btn.innerText = 'ДОБАВИТЬ КАН (Сёминкан)';
                else if (action === 'kan_open') btn.innerText = 'ОТКРЫТЫЙ КАН';
                else if (action.startsWith('kan_closed')) btn.innerText = 'ЗАКРЫТЫЙ КАН';
                else if (action === 'ron') btn.innerText = '💥 РОН (Победа)';
                else if (action === 'tsumo') btn.innerText = '🏆 ЦУМО (Победа)';
                else if (action === 'riichi') btn.innerText = '⚡ РИИЧИ';
                else if (action === 'skip') { 
                    btn.innerText = 'Пропустить'; 
                    btn.style.backgroundColor = '#7f8c8d'; 
                }
                
                btn.onclick = () => window.sendAction(action);
                buttonsContainer.appendChild(btn);
            });
        }
    }
}

function translateTile(tileStr) {
    if (!tileStr || typeof tileStr !== 'string' || tileStr.length < 2) return '';
    
    const isClosedKanMarker = tileStr.endsWith('*');
    const cleanTile = isClosedKanMarker ? tileStr.slice(0, -1) : tileStr;

    const rank = cleanTile.slice(0, -1);
    const suit = cleanTile.slice(-1).toLowerCase();
    
    const baseUrl = '/static/img/';
    let fileName = '';
    
    if (suit === 'm') {
        fileName = `Man${rank}`;
    } else if (suit === 'p') {
        fileName = `Pin${rank}`;
    } else if (suit === 's') {
        fileName = `Sou${rank}`;
    } else if (suit === 'z') {
        const honors = {
            '1': 'Ton',
            '2': 'Nan',
            '3': 'Shaa',
            '4': 'Pei',
            '5': 'Haku',
            '6': 'Hatsu',
            '7': 'Chun'
        };
        fileName = honors[rank];
    }

    if (tileStr === '?' || isClosedKanMarker) {
        return `
            <div style="position: relative; width: 100%; height: 100%;">
                <img src="${baseUrl}Front.svg" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 1;">
                <img src="${baseUrl}Back.svg" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 2; padding: 6%; box-sizing: border-box;" alt="Back">
            </div>
        `;
    }

    if (!fileName) return '';
    
    return `
        <div style="position: relative; width: 100%; height: 100%;">
            <img src="${baseUrl}Front.svg" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 1;">
            <img src="${baseUrl}${fileName}.svg" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 2; padding: 10% 5% 15% 5%; box-sizing: border-box;" alt="${tileStr}">
        </div>
    `;
}
