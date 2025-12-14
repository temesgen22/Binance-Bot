"""
Check if PostgreSQL is installed and accessible.
"""
import sys
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger


def check_postgresql_installed():
    """Check if PostgreSQL is installed on the system."""
    logger.info("Checking if PostgreSQL is installed...")
    
    # Check if psql command exists
    try:
        result = subprocess.run(
            ["psql", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            logger.info(f"✓ PostgreSQL found: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        logger.warning("✗ PostgreSQL 'psql' command not found")
    except Exception as e:
        logger.warning(f"✗ Error checking PostgreSQL: {e}")
    
    return False


def check_postgresql_service():
    """Check if PostgreSQL service is running (Windows)."""
    logger.info("Checking if PostgreSQL service is running...")
    
    try:
        result = subprocess.run(
            ["powershell", "-Command", "Get-Service -Name postgresql* -ErrorAction SilentlyContinue"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0 and result.stdout.strip():
            logger.info("✓ PostgreSQL service found:")
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    logger.info(f"  {line.strip()}")
            return True
        else:
            logger.warning("✗ No PostgreSQL service found")
    except Exception as e:
        logger.warning(f"✗ Error checking service: {e}")
    
    return False


def check_docker_postgresql():
    """Check if PostgreSQL is running in Docker."""
    logger.info("Checking if PostgreSQL is running in Docker...")
    
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=postgres", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0 and result.stdout.strip():
            containers = result.stdout.strip().split('\n')
            logger.info(f"✓ PostgreSQL container(s) found: {', '.join(containers)}")
            return True
        else:
            logger.info("ℹ No PostgreSQL containers running")
    except FileNotFoundError:
        logger.info("ℹ Docker not installed or not in PATH")
    except Exception as e:
        logger.warning(f"✗ Error checking Docker: {e}")
    
    return False


def main():
    """Run all checks."""
    logger.info("=" * 60)
    logger.info("PostgreSQL Installation Check")
    logger.info("=" * 60)
    logger.info("")
    
    installed = check_postgresql_installed()
    logger.info("")
    
    service_running = check_postgresql_service()
    logger.info("")
    
    docker_running = check_docker_postgresql()
    logger.info("")
    
    logger.info("=" * 60)
    logger.info("Summary")
    logger.info("=" * 60)
    
    if installed:
        logger.info("✓ PostgreSQL is installed on your system")
        if service_running:
            logger.info("✓ PostgreSQL service is running")
        else:
            logger.warning("⚠ PostgreSQL service is not running")
            logger.info("  Start it with: Start-Service postgresql-x64-<version>")
    elif docker_running:
        logger.info("✓ PostgreSQL is running in Docker")
    else:
        logger.warning("✗ PostgreSQL is not installed or not accessible")
        logger.info("")
        logger.info("Installation options:")
        logger.info("  1. Install PostgreSQL on Windows:")
        logger.info("     https://www.postgresql.org/download/windows/")
        logger.info("")
        logger.info("  2. Use Docker (recommended for quick setup):")
        logger.info("     docker-compose up -d postgres")
        logger.info("")
        logger.info("See docs/POSTGRESQL_INSTALLATION.md for detailed instructions")
    
    logger.info("")
    
    return 0 if (installed or docker_running) else 1


if __name__ == "__main__":
    sys.exit(main())

