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

        getAll() {
            return Object.assign({}, this._updates);
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
            const url = `${protocol}//${host}/ws/positions?token=${encodeURIComponent(token)}`;
            if (this._ws && (this._ws.readyState === WebSocket.OPEN || this._ws.readyState === WebSocket.CONNECTING)) return;
            try {
                this._ws = new WebSocket(url);
                this._ws.onopen = () => {
                    this._reconnectAttempts = 0;
                    console.debug('[positions-ws] Connected');
                };
                this._ws.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        if (data.type === 'position_update') {
                            const sid = data.strategy_id || data.strategyId;
                            if (sid) {
                                this._updates[sid] = {
                                    strategy_id: sid,
                                    symbol: data.symbol,
                                    account_id: data.account_id || 'default',
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
                                // Keep closed (position_size <= 0) in store so merge can remove from Open Positions tab
                                if (data.position_size <= 0) {
                                    this._updates[sid] = { ...this._updates[sid], position_size: 0 };
                                }
                                window.dispatchEvent(new CustomEvent('position-update', { detail: this._updates[sid] }));
                            }
                        }
                    } catch (e) {
                        console.debug('[positions-ws] Parse error', e);
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
