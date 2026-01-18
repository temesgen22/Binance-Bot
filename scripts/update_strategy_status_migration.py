#!/usr/bin/env python3
"""
Migration script to update strategy status in database:
- "paused_by_risk" -> "stopped_by_risk"
- "paused" -> "stopped"

This script updates existing database records to match the new status naming convention.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger
from app.core.config import get_settings


def update_strategy_statuses(db_session: Session, dry_run: bool = False) -> dict:
    """
    Update strategy statuses in database.
    
    Args:
        db_session: Database session
        dry_run: If True, only shows what would be changed without making changes
    
    Returns:
        Dictionary with update statistics
    """
    stats = {
        "paused_by_risk_to_stopped_by_risk": 0,
        "paused_to_stopped": 0,
        "total_updated": 0
    }
    
    try:
        # Count strategies with old statuses first
        paused_by_risk_count = db_session.execute(
            text("SELECT COUNT(*) FROM strategies WHERE status = 'paused_by_risk'")
        ).scalar()
        
        paused_count = db_session.execute(
            text("SELECT COUNT(*) FROM strategies WHERE status = 'paused'")
        ).scalar()
        
        logger.info(f"Found {paused_by_risk_count} strategies with status 'paused_by_risk'")
        logger.info(f"Found {paused_count} strategies with status 'paused'")
        
        if dry_run:
            logger.info("DRY RUN MODE - No changes will be made")
            stats["paused_by_risk_to_stopped_by_risk"] = paused_by_risk_count
            stats["paused_to_stopped"] = paused_count
            stats["total_updated"] = paused_by_risk_count + paused_count
            return stats
        
        # CRITICAL: Update constraint and data in correct order
        # We need to: 1) Drop constraint, 2) Update data, 3) Recreate constraint
        try:
            logger.info("Step 1: Dropping old constraint...")
            # Drop the old constraint (allows both old and new statuses temporarily)
            db_session.execute(text("ALTER TABLE strategies DROP CONSTRAINT IF EXISTS strategies_status_check"))
            db_session.commit()
            logger.info("Constraint dropped successfully")
            
            # Update paused_by_risk -> stopped_by_risk
            if paused_by_risk_count > 0:
                logger.info(f"Step 2: Updating {paused_by_risk_count} strategies from 'paused_by_risk' to 'stopped_by_risk'...")
                result = db_session.execute(
                    text("UPDATE strategies SET status = 'stopped_by_risk' WHERE status = 'paused_by_risk'")
                )
                db_session.commit()
                stats["paused_by_risk_to_stopped_by_risk"] = result.rowcount
                logger.info(f"Updated {result.rowcount} strategies: 'paused_by_risk' -> 'stopped_by_risk'")
            
            # Update paused -> stopped
            if paused_count > 0:
                logger.info(f"Step 3: Updating {paused_count} strategies from 'paused' to 'stopped'...")
                result = db_session.execute(
                    text("UPDATE strategies SET status = 'stopped' WHERE status = 'paused'")
                )
                db_session.commit()
                stats["paused_to_stopped"] = result.rowcount
                logger.info(f"Updated {result.rowcount} strategies: 'paused' -> 'stopped'")
            
            # Recreate constraint with new status values
            logger.info("Step 4: Recreating constraint with new status values...")
            db_session.execute(
                text("ALTER TABLE strategies ADD CONSTRAINT strategies_status_check "
                     "CHECK (status IN ('stopped', 'running', 'error', 'stopped_by_risk'))")
            )
            db_session.commit()
            logger.info("Constraint recreated successfully with 'stopped_by_risk'")
            
        except Exception as update_error:
            logger.error(f"Error during update: {update_error}")
            db_session.rollback()
            raise
        
        stats["total_updated"] = stats["paused_by_risk_to_stopped_by_risk"] + stats["paused_to_stopped"]
        
        # Verify the updates
        remaining_paused_by_risk = db_session.execute(
            text("SELECT COUNT(*) FROM strategies WHERE status = 'paused_by_risk'")
        ).scalar()
        
        remaining_paused = db_session.execute(
            text("SELECT COUNT(*) FROM strategies WHERE status = 'paused'")
        ).scalar()
        
        stopped_by_risk_count = db_session.execute(
            text("SELECT COUNT(*) FROM strategies WHERE status = 'stopped_by_risk'")
        ).scalar()
        
        stopped_count = db_session.execute(
            text("SELECT COUNT(*) FROM strategies WHERE status = 'stopped'")
        ).scalar()
        
        logger.info(f"\n📊 Status Summary:")
        logger.info(f"  - stopped_by_risk: {stopped_by_risk_count}")
        logger.info(f"  - stopped: {stopped_count}")
        
        if remaining_paused_by_risk > 0:
            logger.warning(f"⚠️  {remaining_paused_by_risk} strategies still have 'paused_by_risk' status (update may have failed)")
        
        if remaining_paused > 0:
            logger.warning(f"⚠️  {remaining_paused} strategies still have 'paused' status (update may have failed)")
        
        return stats
        
    except Exception as e:
        logger.error(f"Error updating strategy statuses: {e}", exc_info=True)
        db_session.rollback()
        raise


def main():
    """Main function to run the migration."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Update strategy statuses: 'paused_by_risk' -> 'stopped_by_risk', 'paused' -> 'stopped'"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without making any changes"
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Database URL (overrides .env settings). Example: postgresql://user:pass@localhost/dbname"
    )
    args = parser.parse_args()
    
    try:
        # Get database URL
        if args.database_url:
            database_url = args.database_url
            logger.info(f"Using provided database URL: {database_url.split('@')[0]}@...")
        else:
            settings = get_settings()
            database_url = settings.database_url
            logger.info(f"Using database URL from config: {database_url.split('@')[0] if '@' in database_url else 'sqlite'}")
        
        # Create database connection
        engine = create_engine(database_url, echo=False)
        SessionLocal = sessionmaker(bind=engine)
        db_session = SessionLocal()
        
        logger.info("Starting strategy status migration...")
        logger.info(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE UPDATE'}\n")
        
        # Run the migration
        stats = update_strategy_statuses(db_session, dry_run=args.dry_run)
        
        if args.dry_run:
            logger.info(f"\nDRY RUN COMPLETE")
            logger.info(f"Would update {stats['total_updated']} strategies:")
            logger.info(f"  - {stats['paused_by_risk_to_stopped_by_risk']} from 'paused_by_risk' to 'stopped_by_risk'")
            logger.info(f"  - {stats['paused_to_stopped']} from 'paused' to 'stopped'")
            logger.info(f"\nRun without --dry-run to apply changes")
        else:
            logger.info(f"\nMIGRATION COMPLETE")
            logger.info(f"Updated {stats['total_updated']} strategies:")
            logger.info(f"  - {stats['paused_by_risk_to_stopped_by_risk']} from 'paused_by_risk' to 'stopped_by_risk'")
            logger.info(f"  - {stats['paused_to_stopped']} from 'paused' to 'stopped'")
        
        db_session.close()
        
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

