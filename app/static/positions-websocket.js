/**
 * Real-time position updates via WebSocket /ws/positions.
 * Connect when authenticated; store latest per-strategy updates; dispatch 'position-update' event.
 */
(function() {
    const TOKEN_KEY = 'binance_bot_token';

    function getToken() {
        if (typeof window !== 'undefined' && window.Auth && typeof window.Auth.getToken === 'function') {
            return window.Auth.getToken();
        }
        return localStorage.getItem(TOKEN_KEY);
    }

    function isAuthenticated() {
        return !!getToken();
    }

    window.PositionUpdates = {
        _ws: null,
        _updates: {},
        _reconnectAttempts: 0,
        _maxReconnectAttempts: 10,

        get(strategyId) {
            return this._updates[strategyId] || null;
        },

        /** Latest update for account + strategy (matches server composite key). */
        getComposite(accountId, strategyId) {
            const acc = accountId && String(accountId).trim() !== '' ? String(accountId) : 'default';
            const sid = strategyId != null && String(strategyId).trim() !== '' ? String(strategyId) : '';
            const key = acc + '|' + sid;
            return this._updates[key] || null;
        },

        getAll() {
            return Object.assign({}, this._updates);
        },

        /** Remove a key (e.g. after position closed) so merge does not keep filtering out a future reopen. */
        deleteKey(strategyId) {
            if (strategyId != null && strategyId !== '') {
                delete this._updates[strategyId];
            }
        },

        /** Call after rendering strategy table so Unrealized PnL shows latest WebSocket data immediately */
        applyStoredToDOM() {
            const all = this.getAll();
            for (const sid in all) {
                if (Object.prototype.hasOwnProperty.call(all, sid)) {
                    window.dispatchEvent(new CustomEvent('position-update', { detail: all[sid] }));
                }
            }
        },

        connect() {
            if (!isAuthenticated()) return;
            const token = getToken();
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = window.location.host;
            const url = `${protocol}//${host}/api/ws/positions?token=${encodeURIComponent(token)}`;
            if (this._ws && (this._ws.readyState === WebSocket.OPEN || this._ws.readyState === WebSocket.CONNECTING)) return;
            try {
                this._ws = new WebSocket(url);
                this._ws.onopen = () => {
                    this._reconnectAttempts = 0;
                    console.info('[positions-ws] Connected to /api/ws/positions');
                };
                this._ws.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        if (data.type === 'position_update') {
                            const sid = data.strategy_id ?? data.strategyId;
                            const stratPart = (sid != null && sid !== '') ? sid : ('manual_' + (data.symbol || 'unknown'));
                            const accId = data.account_id || 'default';
                            const key = accId + '|' + stratPart;
                            const row = {
                                strategy_id: sid ?? null,
                                strategy_name: data.strategy_name ?? null,
                                symbol: data.symbol,
                                account_id: accId,
                                position_size: data.position_size,
                                entry_price: data.entry_price,
                                unrealized_pnl: data.unrealized_pnl,
                                position_side: data.position_side,
                                current_price: data.current_price,
                                leverage: data.leverage,
                                liquidation_price: data.liquidation_price,
                                initial_margin: data.initial_margin,
                                margin_type: data.margin_type
                            };
                            if (data.position_size <= 0) {
                                // Flat: keep key so strategy details can show "no position" while REST lags.
                                this._updates[key] = {
                                    ...row,
                                    position_size: 0,
                                    position_side: null,
                                    entry_price: null,
                                    unrealized_pnl: null
                                };
                            } else {
                                this._updates[key] = row;
                            }
                            window.dispatchEvent(new CustomEvent('position-update', { detail: this._updates[key] }));
                        }
                    } catch (e) {
                        console.warn('[positions-ws] Parse error', e);
                    }
                };
                this._ws.onclose = (event) => {
                    this._ws = null;
                    if (event.code === 4001 && this._reconnectAttempts < this._maxReconnectAttempts) {
                        this._reconnectAttempts++;
                        console.warn('[positions-ws] Auth rejected (4001), reconnecting in 2s…');
                        setTimeout(() => this.connect(), 2000);
                    } else if (event.code !== 1000) {
                        console.warn('[positions-ws] Closed', event.code, event.reason || '');
                    }
                };
                this._ws.onerror = () => {
                    console.warn('[positions-ws] Connection error');
                };
            } catch (e) {
                console.debug('[positions-ws] Connect error', e);
            }
        },

        disconnect() {
            if (this._ws) {
                this._ws.close(1000, 'Client disconnect');
                this._ws = null;
            }
        }
    };

    function maybeConnect() {
        if (isAuthenticated()) window.PositionUpdates.connect();
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', maybeConnect);
    } else {
        maybeConnect();
    }
    // Reconnect when page becomes visible (e.g. tab focus) in case connection dropped
    if (typeof document.addEventListener === 'function') {
        document.addEventListener('visibilitychange', function() {
            if (document.visibilityState === 'visible' && isAuthenticated()) {
                if (!window.PositionUpdates._ws || window.PositionUpdates._ws.readyState !== WebSocket.OPEN) {
                    window.PositionUpdates.connect();
                }
            }
        });
    }
})();
