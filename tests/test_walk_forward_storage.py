"""
Tests for walk-forward analysis database storage functionality.

Tests:
- Database models creation
- Saving walk-forward analysis
- Retrieving analysis with ownership check
- Listing analyses with filters
- Deleting analysis
- User isolation (users can only see their own data)
"""
import pytest
pytestmark = pytest.mark.slow  # Walk-forward storage tests are slow and excluded from CI
import os
from datetime import datetime, timezone, timedelta
from uuid import uuid4, UUID
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import (
    User, WalkForwardAnalysis, WalkForwardWindow, WalkForwardEquityPoint
)
from app.services.database_service import DatabaseService
from app.services.walk_forward import WalkForwardRequest, WalkForwardResult, WalkForwardWindow as WFWindow
from app.api.routes.backtesting import BacktestResult


@pytest.fixture
def db_session():
    """Create a database session for testing."""
    from app.core.database import get_db_session
    
    # Skip if DATABASE_URL is not set
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set - skipping database test")
    
    # Get a database session
    session_gen = get_db_session()
    session = next(session_gen)
    
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def mock_walk_forward_result():
    """Create a mock WalkForwardResult for testing."""
    from app.services.walk_forward import WalkForwardResult, WalkForwardWindow as WFWindow
    from app.api.routes.backtesting import BacktestResult
    
    # Create mock backtest results
    training_result = BacktestResult(
        symbol="BTCUSDT",
        strategy_type="scalping",
        start_time=datetime.now(timezone.utc) - timedelta(days=30),
        end_time=datetime.now(timezone.utc) - timedelta(days=7),
        initial_balance=1000.0,
        final_balance=1050.0,
        total_pnl=50.0,
        total_return_pct=5.0,
        total_trades=10,
        completed_trades=10,
        open_trades=0,
        winning_trades=6,
        losing_trades=4,
        win_rate=60.0,
        total_fees=2.0,
        avg_profit_per_trade=5.0,
        largest_win=20.0,
        largest_loss=-10.0,
        max_drawdown=15.0,
        max_drawdown_pct=1.5,
        trades=[]
    )
    
    test_result = BacktestResult(
        symbol="BTCUSDT",
        strategy_type="scalping",
        start_time=datetime.now(timezone.utc) - timedelta(days=7),
        end_time=datetime.now(timezone.utc),
        initial_balance=1050.0,
        final_balance=1100.0,
        total_pnl=50.0,
        total_return_pct=4.76,
        total_trades=8,
        completed_trades=8,
        open_trades=0,
        winning_trades=5,
        losing_trades=3,
        win_rate=62.5,
        total_fees=1.5,
        avg_profit_per_trade=6.25,
        largest_win=25.0,
        largest_loss=-8.0,
        max_drawdown=12.0,
        max_drawdown_pct=1.14,
        trades=[]
    )
    
    # Create mock window
    window = WFWindow(
        window_number=1,
        training_start=datetime.now(timezone.utc) - timedelta(days=30),
        training_end=datetime.now(timezone.utc) - timedelta(days=7),
        test_start=datetime.now(timezone.utc) - timedelta(days=7),
        test_end=datetime.now(timezone.utc),
        training_result=training_result,
        test_result=test_result,
        optimized_params={"ema_fast": 8, "ema_slow": 21},
        optimization_results=[
            {"params": {"ema_fast": 8, "ema_slow": 21}, "score": 1.5, "status": "PASSED"},
            {"params": {"ema_fast": 5, "ema_slow": 11}, "score": 0.8, "status": "FAILED", "failure_reason": "Insufficient trades"}
        ],
        training_sharpe=1.2,
        test_sharpe=1.5,
        training_return_pct=5.0,
        test_return_pct=4.76,
        training_win_rate=60.0,
        test_win_rate=62.5
    )
    
    # Create mock result
    result = WalkForwardResult(
        symbol="BTCUSDT",
        strategy_type="scalping",
        overall_start_time=datetime.now(timezone.utc) - timedelta(days=30),
        overall_end_time=datetime.now(timezone.utc),
        training_period_days=23,
        test_period_days=7,
        step_size_days=7,
        window_type="rolling",
        total_windows=1,
        windows=[window],
        total_return_pct=10.0,
        avg_window_return_pct=10.0,
        consistency_score=100.0,
        sharpe_ratio=1.35,
        max_drawdown_pct=1.5,
        total_trades=18,
        avg_win_rate=61.25,
        return_std_dev=0.24,
        best_window=1,
        worst_window=1,
        equity_curve=[
            {"time": int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp()), "balance": 1000.0},
            {"time": int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp()), "balance": 1050.0},
            {"time": int(datetime.now(timezone.utc).timestamp()), "balance": 1100.0}
        ],
        initial_balance=1000.0
    )
    
    return result


@pytest.fixture
def mock_walk_forward_request():
    """Create a mock WalkForwardRequest for testing."""
    from app.services.walk_forward import WalkForwardRequest
    
    return WalkForwardRequest(
        symbol="BTCUSDT",
        strategy_type="scalping",
        start_time=datetime.now(timezone.utc) - timedelta(days=30),
        end_time=datetime.now(timezone.utc),
        training_period_days=23,
        test_period_days=7,
        step_size_days=7,
        window_type="rolling",
        leverage=5,
        risk_per_trade=0.01,
        initial_balance=1000.0,
        params={"ema_fast": 8, "ema_slow": 21},
        optimize_params={"ema_fast": [5, 8, 9], "ema_slow": [11, 21, 30]},
        optimization_method="grid_search",
        optimization_metric="robust_score",
        min_trades_guardrail=5,
        max_drawdown_cap=50.0,
        lottery_trade_threshold=0.5
    )


def test_walk_forward_analysis_model_creation(db_session: Session):
    """Test that WalkForwardAnalysis model can be created."""
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    
    analysis = WalkForwardAnalysis(
        user_id=user.id,
        symbol="BTCUSDT",
        strategy_type="scalping",
        overall_start_time=datetime.now(timezone.utc) - timedelta(days=30),
        overall_end_time=datetime.now(timezone.utc),
        training_period_days=23,
        test_period_days=7,
        step_size_days=7,
        window_type="rolling",
        total_windows=1,
        leverage=5,
        risk_per_trade=Decimal("0.01"),
        initial_balance=Decimal("1000.0"),
        params={},
        optimization_enabled=True,
        total_return_pct=Decimal("10.0"),
        avg_window_return_pct=Decimal("10.0"),
        consistency_score=Decimal("100.0"),
        total_trades=18,
        avg_win_rate=Decimal("61.25")
    )
    
    db_session.add(analysis)
    db_session.commit()
    
    assert analysis.id is not None
    assert analysis.user_id == user.id
    assert analysis.symbol == "BTCUSDT"
    assert analysis.total_windows == 1


def test_save_walk_forward_analysis_sync(db_session: Session, mock_walk_forward_result, mock_walk_forward_request):
    """Test saving walk-forward analysis (sync)."""
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    
    db_service = DatabaseService(db_session)
    
    analysis_id = db_service._sync_save_walk_forward_analysis(
        user_id=user.id,
        result=mock_walk_forward_result,
        request=mock_walk_forward_request,
        execution_time_ms=5000,
        candles_processed=1000,
        name="Test Analysis",
        label="Test",
        keep_details=True
    )
    
    assert analysis_id is not None
    
    # Verify analysis was saved
    analysis = db_session.query(WalkForwardAnalysis).filter(
        WalkForwardAnalysis.id == analysis_id
    ).first()
    
    assert analysis is not None
    assert analysis.user_id == user.id
    assert analysis.name == "Test Analysis"
    assert analysis.symbol == "BTCUSDT"
    assert analysis.total_windows == 1
    assert analysis.total_return_pct == Decimal("10.0")
    
    # Verify windows were saved
    windows = db_session.query(WalkForwardWindow).filter(
        WalkForwardWindow.analysis_id == analysis_id
    ).all()
    assert len(windows) == 1
    assert windows[0].window_number == 1
    
    # Verify equity points were saved
    equity_points = db_session.query(WalkForwardEquityPoint).filter(
        WalkForwardEquityPoint.analysis_id == analysis_id
    ).all()
    assert len(equity_points) == 3


def test_get_walk_forward_analysis_with_ownership(db_session: Session):
    """Test that get_walk_forward_analysis enforces ownership."""
    # Create two users
    user1 = User(
        username="user1",
        email="user1@example.com",
        password_hash="hash1",
        is_active=True
    )
    user2 = User(
        username="user2",
        email="user2@example.com",
        password_hash="hash2",
        is_active=True
    )
    db_session.add_all([user1, user2])
    db_session.commit()
    
    # Create analysis for user1
    analysis = WalkForwardAnalysis(
        user_id=user1.id,
        symbol="BTCUSDT",
        strategy_type="scalping",
        overall_start_time=datetime.now(timezone.utc) - timedelta(days=30),
        overall_end_time=datetime.now(timezone.utc),
        training_period_days=23,
        test_period_days=7,
        step_size_days=7,
        window_type="rolling",
        total_windows=1,
        leverage=5,
        risk_per_trade=Decimal("0.01"),
        initial_balance=Decimal("1000.0"),
        params={},
        optimization_enabled=False,
        total_return_pct=Decimal("10.0"),
        avg_window_return_pct=Decimal("10.0"),
        consistency_score=Decimal("100.0"),
        total_trades=18,
        avg_win_rate=Decimal("61.25")
    )
    db_session.add(analysis)
    db_session.commit()
    
    db_service = DatabaseService(db_session)
    
    # User1 should be able to get their analysis
    result1 = db_service.get_walk_forward_analysis(analysis.id, user1.id)
    assert result1 is not None
    assert result1.id == analysis.id
    
    # User2 should NOT be able to get user1's analysis
    result2 = db_service.get_walk_forward_analysis(analysis.id, user2.id)
    assert result2 is None  # Should return None due to ownership check


def test_list_walk_forward_analyses_user_isolation(db_session: Session):
    """Test that list_walk_forward_analyses only returns current user's analyses."""
    # Create two users
    user1 = User(
        username="user1",
        email="user1@example.com",
        password_hash="hash1",
        is_active=True
    )
    user2 = User(
        username="user2",
        email="user2@example.com",
        password_hash="hash2",
        is_active=True
    )
    db_session.add_all([user1, user2])
    db_session.commit()
    
    # Create analyses for both users
    analysis1 = WalkForwardAnalysis(
        user_id=user1.id,
        symbol="BTCUSDT",
        strategy_type="scalping",
        overall_start_time=datetime.now(timezone.utc) - timedelta(days=30),
        overall_end_time=datetime.now(timezone.utc),
        training_period_days=23,
        test_period_days=7,
        step_size_days=7,
        window_type="rolling",
        total_windows=1,
        leverage=5,
        risk_per_trade=Decimal("0.01"),
        initial_balance=Decimal("1000.0"),
        params={},
        optimization_enabled=False,
        total_return_pct=Decimal("10.0"),
        avg_window_return_pct=Decimal("10.0"),
        consistency_score=Decimal("100.0"),
        total_trades=18,
        avg_win_rate=Decimal("61.25")
    )
    
    analysis2 = WalkForwardAnalysis(
        user_id=user2.id,
        symbol="ETHUSDT",
        strategy_type="scalping",
        overall_start_time=datetime.now(timezone.utc) - timedelta(days=30),
        overall_end_time=datetime.now(timezone.utc),
        training_period_days=23,
        test_period_days=7,
        step_size_days=7,
        window_type="rolling",
        total_windows=1,
        leverage=5,
        risk_per_trade=Decimal("0.01"),
        initial_balance=Decimal("1000.0"),
        params={},
        optimization_enabled=False,
        total_return_pct=Decimal("5.0"),
        avg_window_return_pct=Decimal("5.0"),
        consistency_score=Decimal("50.0"),
        total_trades=10,
        avg_win_rate=Decimal("50.0")
    )
    
    db_session.add_all([analysis1, analysis2])
    db_session.commit()
    
    db_service = DatabaseService(db_session)
    
    # User1 should only see their analysis
    analyses1, total1 = db_service._sync_list_walk_forward_analyses(
        user_id=user1.id,
        limit=50,
        offset=0
    )
    assert total1 == 1
    assert len(analyses1) == 1
    assert analyses1[0].id == analysis1.id
    assert analyses1[0].symbol == "BTCUSDT"
    
    # User2 should only see their analysis
    analyses2, total2 = db_service._sync_list_walk_forward_analyses(
        user_id=user2.id,
        limit=50,
        offset=0
    )
    assert total2 == 1
    assert len(analyses2) == 1
    assert analyses2[0].id == analysis2.id
    assert analyses2[0].symbol == "ETHUSDT"


def test_delete_walk_forward_analysis_with_ownership(db_session: Session):
    """Test that delete_walk_forward_analysis enforces ownership."""
    # Create two users
    user1 = User(
        username="user1",
        email="user1@example.com",
        password_hash="hash1",
        is_active=True
    )
    user2 = User(
        username="user2",
        email="user2@example.com",
        password_hash="hash2",
        is_active=True
    )
    db_session.add_all([user1, user2])
    db_session.commit()
    
    # Create analysis for user1
    analysis = WalkForwardAnalysis(
        user_id=user1.id,
        symbol="BTCUSDT",
        strategy_type="scalping",
        overall_start_time=datetime.now(timezone.utc) - timedelta(days=30),
        overall_end_time=datetime.now(timezone.utc),
        training_period_days=23,
        test_period_days=7,
        step_size_days=7,
        window_type="rolling",
        total_windows=1,
        leverage=5,
        risk_per_trade=Decimal("0.01"),
        initial_balance=Decimal("1000.0"),
        params={},
        optimization_enabled=False,
        total_return_pct=Decimal("10.0"),
        avg_window_return_pct=Decimal("10.0"),
        consistency_score=Decimal("100.0"),
        total_trades=18,
        avg_win_rate=Decimal("61.25")
    )
    db_session.add(analysis)
    db_session.commit()
    analysis_id = analysis.id
    
    db_service = DatabaseService(db_session)
    
    # User2 should NOT be able to delete user1's analysis
    success = db_service.delete_walk_forward_analysis(analysis_id, user2.id)
    assert success is False
    
    # Verify analysis still exists
    analysis_still_exists = db_session.query(WalkForwardAnalysis).filter(
        WalkForwardAnalysis.id == analysis_id
    ).first()
    assert analysis_still_exists is not None
    
    # User1 should be able to delete their own analysis
    success = db_service.delete_walk_forward_analysis(analysis_id, user1.id)
    assert success is True
    
    # Verify analysis was deleted
    analysis_deleted = db_session.query(WalkForwardAnalysis).filter(
        WalkForwardAnalysis.id == analysis_id
    ).first()
    assert analysis_deleted is None


def test_list_walk_forward_analyses_with_filters(db_session: Session):
    """Test that list_walk_forward_analyses filters work correctly."""
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    
    # Create multiple analyses with different symbols
    analysis1 = WalkForwardAnalysis(
        user_id=user.id,
        symbol="BTCUSDT",
        strategy_type="scalping",
        overall_start_time=datetime.now(timezone.utc) - timedelta(days=30),
        overall_end_time=datetime.now(timezone.utc),
        training_period_days=23,
        test_period_days=7,
        step_size_days=7,
        window_type="rolling",
        total_windows=1,
        leverage=5,
        risk_per_trade=Decimal("0.01"),
        initial_balance=Decimal("1000.0"),
        params={},
        optimization_enabled=False,
        total_return_pct=Decimal("10.0"),
        avg_window_return_pct=Decimal("10.0"),
        consistency_score=Decimal("100.0"),
        total_trades=18,
        avg_win_rate=Decimal("61.25")
    )
    
    analysis2 = WalkForwardAnalysis(
        user_id=user.id,
        symbol="ETHUSDT",
        strategy_type="scalping",
        overall_start_time=datetime.now(timezone.utc) - timedelta(days=30),
        overall_end_time=datetime.now(timezone.utc),
        training_period_days=23,
        test_period_days=7,
        step_size_days=7,
        window_type="rolling",
        total_windows=1,
        leverage=5,
        risk_per_trade=Decimal("0.01"),
        initial_balance=Decimal("1000.0"),
        params={},
        optimization_enabled=False,
        total_return_pct=Decimal("5.0"),
        avg_window_return_pct=Decimal("5.0"),
        consistency_score=Decimal("50.0"),
        total_trades=10,
        avg_win_rate=Decimal("50.0")
    )
    
    db_session.add_all([analysis1, analysis2])
    db_session.commit()
    
    db_service = DatabaseService(db_session)
    
    # Filter by symbol
    analyses, total = db_service._sync_list_walk_forward_analyses(
        user_id=user.id,
        limit=50,
        offset=0,
        symbol="BTCUSDT"
    )
    assert total == 1
    assert len(analyses) == 1
    assert analyses[0].symbol == "BTCUSDT"
    
    # No filter - should get all
    analyses, total = db_service._sync_list_walk_forward_analyses(
        user_id=user.id,
        limit=50,
        offset=0
    )
    assert total == 2
    assert len(analyses) == 2


def test_get_walk_forward_equity_curve_with_ownership(db_session: Session):
    """Test that get_walk_forward_equity_curve enforces ownership."""
    user1 = User(
        username="user1",
        email="user1@example.com",
        password_hash="hash1",
        is_active=True
    )
    user2 = User(
        username="user2",
        email="user2@example.com",
        password_hash="hash2",
        is_active=True
    )
    db_session.add_all([user1, user2])
    db_session.commit()
    
    # Create analysis for user1
    analysis = WalkForwardAnalysis(
        user_id=user1.id,
        symbol="BTCUSDT",
        strategy_type="scalping",
        overall_start_time=datetime.now(timezone.utc) - timedelta(days=30),
        overall_end_time=datetime.now(timezone.utc),
        training_period_days=23,
        test_period_days=7,
        step_size_days=7,
        window_type="rolling",
        total_windows=1,
        leverage=5,
        risk_per_trade=Decimal("0.01"),
        initial_balance=Decimal("1000.0"),
        params={},
        optimization_enabled=False,
        total_return_pct=Decimal("10.0"),
        avg_window_return_pct=Decimal("10.0"),
        consistency_score=Decimal("100.0"),
        total_trades=18,
        avg_win_rate=Decimal("61.25")
    )
    db_session.add(analysis)
    db_session.commit()
    
    # Add equity points
    point1 = WalkForwardEquityPoint(
        analysis_id=analysis.id,
        time=datetime.now(timezone.utc) - timedelta(days=30),
        balance=Decimal("1000.0")
    )
    point2 = WalkForwardEquityPoint(
        analysis_id=analysis.id,
        time=datetime.now(timezone.utc),
        balance=Decimal("1100.0")
    )
    db_session.add_all([point1, point2])
    db_session.commit()
    
    db_service = DatabaseService(db_session)
    
    # User1 should be able to get equity curve
    equity_curve1 = db_service.get_walk_forward_equity_curve(analysis.id, user1.id)
    assert len(equity_curve1) == 2
    
    # User2 should NOT be able to get equity curve (returns empty list)
    equity_curve2 = db_service.get_walk_forward_equity_curve(analysis.id, user2.id)
    assert len(equity_curve2) == 0  # Returns empty list due to ownership check

