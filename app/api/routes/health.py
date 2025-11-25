from fastapi import APIRouter, Depends

from app.api.deps import get_binance_client
from app.core.my_binance_client import BinanceClient


router = APIRouter(tags=["health"])


@router.get("/health")
def health(client: BinanceClient = Depends(get_binance_client)) -> dict[str, str | float]:
    price = client.get_price("BTCUSDT")
    return {"status": "ok", "btc_price": price}

