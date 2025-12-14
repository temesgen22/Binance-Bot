# Redis and Database Integration Test

## Overview

This test suite (`test_redis_database_integration.py`) provides comprehensive end-to-end testing for Redis and Database working together using the cache-aside pattern.

## Test Coverage

### 1. Cache-Aside Pattern Tests
- ✅ **Read from Redis cache** (cache hit)
- ✅ **Fallback to database** (cache miss)
- ✅ **Cache population** after database read

### 2. Write-Through Pattern Tests
- ✅ **Create strategy** (write to DB, cache in Redis)
- ✅ **Update strategy** (update DB, invalidate cache)
- ✅ **Data persistence** across operations

### 3. Cache Invalidation Tests
- ✅ **Cache deletion** on strategy update
- ✅ **Fresh data fetch** after invalidation
- ✅ **Re-caching** after invalidation

### 4. Redis Disabled Tests
- ✅ **Fallback to database only** when Redis disabled
- ✅ **No errors** when Redis unavailable

### 5. Trade Service Integration Tests
- ✅ **Trade creation** with Redis and Database
- ✅ **Trade caching** in Redis sorted set
- ✅ **Trade persistence** in database

### 6. End-to-End Lifecycle Tests
- ✅ **Complete strategy lifecycle**: Create → Read → Update → Delete
- ✅ **Data consistency** across all operations
- ✅ **Cache performance** with multiple reads

## Running the Tests

### Prerequisites

1. **Install test dependencies:**
   ```bash
   pip install pytest pytest-asyncio
   ```

2. **No external services required:**
   - Uses in-memory SQLite database (no PostgreSQL needed)
   - Uses mocked Redis (no Redis server needed)
   - All tests are isolated and self-contained

### Run All Tests

```bash
# Run all Redis/Database integration tests
pytest tests/test_redis_database_integration.py -v

# Run with coverage
pytest tests/test_redis_database_integration.py --cov=app.services.strategy_service --cov=app.services.trade_service -v
```

### Run Specific Test Classes

```bash
# Test cache-aside pattern
pytest tests/test_redis_database_integration.py::TestRedisDatabaseIntegration -v

# Test end-to-end lifecycle
pytest tests/test_redis_database_integration.py::TestRedisDatabaseEndToEnd -v
```

### Run Specific Tests

```bash
# Test cache-aside read from Redis
pytest tests/test_redis_database_integration.py::TestRedisDatabaseIntegration::test_cache_aside_pattern_read_from_redis -v

# Test write-through pattern
pytest tests/test_redis_database_integration.py::TestRedisDatabaseIntegration::test_write_through_pattern_create_strategy -v

# Test cache invalidation
pytest tests/test_redis_database_integration.py::TestRedisDatabaseIntegration::test_cache_invalidation_on_update -v
```

## Test Structure

### Fixtures

- `test_db_session`: In-memory SQLite database session
- `test_user`: Test user in database
- `test_account`: Test account in database
- `mock_redis_enabled`: Mock Redis storage (enabled)
- `mock_redis_disabled`: Mock Redis storage (disabled)
- `strategy_service_with_redis`: StrategyService with Redis enabled
- `strategy_service_no_redis`: StrategyService without Redis
- `trade_service_with_redis`: TradeService with Redis enabled

### Test Classes

1. **TestRedisDatabaseIntegration**
   - Tests individual patterns and behaviors
   - Verifies cache-aside, write-through, and invalidation
   - Tests Redis disabled scenarios

2. **TestRedisDatabaseEndToEnd**
   - Tests complete workflows
   - Verifies data consistency across operations
   - Tests real-world usage scenarios

## What the Tests Verify

### ✅ Correct Behavior

1. **Cache-Aside Pattern:**
   - Redis checked first for reads
   - Database queried on cache miss
   - Results cached in Redis after DB read

2. **Write-Through Pattern:**
   - Database updated first (source of truth)
   - Redis cache updated after DB write
   - Both storage systems synchronized

3. **Cache Invalidation:**
   - Cache deleted on updates
   - Fresh data fetched from DB on next read
   - New data re-cached in Redis

4. **Redis Disabled:**
   - System works without Redis
   - Database used as primary storage
   - No errors or exceptions

5. **Data Persistence:**
   - Data survives across operations
   - Updates reflected correctly
   - Consistency maintained

### ❌ What Would Fail

- If Redis cache is not checked first
- If database is not updated on writes
- If cache is not invalidated on updates
- If data is inconsistent between Redis and DB
- If system fails when Redis is disabled

## Expected Test Results

All tests should pass with the following output:

```
tests/test_redis_database_integration.py::TestRedisDatabaseIntegration::test_cache_aside_pattern_read_from_redis PASSED
tests/test_redis_database_integration.py::TestRedisDatabaseIntegration::test_cache_aside_pattern_fallback_to_database PASSED
tests/test_redis_database_integration.py::TestRedisDatabaseIntegration::test_write_through_pattern_create_strategy PASSED
tests/test_redis_database_integration.py::TestRedisDatabaseIntegration::test_cache_invalidation_on_update PASSED
tests/test_redis_database_integration.py::TestRedisDatabaseIntegration::test_redis_disabled_fallback_to_database_only PASSED
tests/test_redis_database_integration.py::TestRedisDatabaseIntegration::test_trade_service_redis_database_integration PASSED
tests/test_redis_database_integration.py::TestRedisDatabaseIntegration::test_data_persistence_across_operations PASSED
tests/test_redis_database_integration.py::TestRedisDatabaseIntegration::test_concurrent_reads_cache_performance PASSED
tests/test_redis_database_integration.py::TestRedisDatabaseEndToEnd::test_complete_strategy_lifecycle PASSED

======================== 9 passed in X.XXs ========================
```

## Troubleshooting

### Test Failures

1. **Import Errors:**
   - Ensure all dependencies are installed: `pip install -r requirements.txt`
   - Check that `app` package is in Python path

2. **Database Errors:**
   - Tests use in-memory SQLite, no setup needed
   - If errors occur, check SQLAlchemy version compatibility

3. **Mock Errors:**
   - Tests use `unittest.mock`, ensure Python 3.8+
   - Check that mock objects are properly configured

### Debugging

Run tests with verbose output and print statements:

```bash
pytest tests/test_redis_database_integration.py -v -s
```

Add breakpoints in test code to inspect state:

```python
import pdb; pdb.set_trace()  # Add this in test
```

## Integration with CI/CD

These tests are designed to run in CI/CD pipelines:

- ✅ No external dependencies (mocked Redis, in-memory DB)
- ✅ Fast execution (isolated tests)
- ✅ Deterministic results (no flaky tests)
- ✅ Comprehensive coverage (all patterns tested)

Add to your CI pipeline:

```yaml
- name: Run Redis/Database Integration Tests
  run: |
    pytest tests/test_redis_database_integration.py -v --cov=app.services.strategy_service --cov=app.services.trade_service
```

## Next Steps

After running these tests:

1. ✅ Verify all tests pass
2. ✅ Review test coverage report
3. ✅ Check for any warnings or errors
4. ✅ Document any test failures
5. ✅ Update tests if code changes

## Related Documentation

- `REDIS_AND_DATABASE_TOGETHER.md` - How Redis and Database work together
- `REDIS_DISABLED_BEHAVIOR.md` - Behavior when Redis is disabled
- `app/services/strategy_service.py` - StrategyService implementation
- `app/services/trade_service.py` - TradeService implementation

