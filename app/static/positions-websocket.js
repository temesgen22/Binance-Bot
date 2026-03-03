/**
 * Real-time position updates via WebSocket /ws/positions.
 * Connect when authenticated; store latest per-strategy updates; dispatch 'position-update' event.
 */
(function() {
    const STORAGE_KEY = 'binance_bot_auth';
    const TOKEN_KEY = 'binance_bot_token';

    function getToken() {
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
                                    current_price: data.current_price
                                };
                                if (data.position_size <= 0) delete this._updates[sid];
                                window.dispatchEvent(new CustomEvent('position-update', { detail: this._updates[sid] || { strategy_id: sid, position_size: 0 } }));
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
                        setTimeout(() => this.connect(), 2000);
                    }
                };
                this._ws.onerror = () => {};
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

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            if (isAuthenticated()) window.PositionUpdates.connect();
        });
    } else if (isAuthenticated()) {
        window.PositionUpdates.connect();
    }
})();
