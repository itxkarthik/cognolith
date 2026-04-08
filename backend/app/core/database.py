import asyncio
import logging
from sqlmodel import SQLModel, create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

logger = logging.getLogger(__name__)

connect_args: dict = {}
if settings.DATABASE_SSL_MODE != "disable":
    connect_args["sslmode"] = settings.DATABASE_SSL_MODE

# Connection pool configuration for production resilience
engine = create_engine(
    settings.get_database_url(),
    echo=settings.DEBUG,
    connect_args=connect_args,
    # Pool configuration for better resilience
    pool_size=10,  # Number of connections to keep in pool
    max_overflow=20,  # Allow up to 20 overflow connections
    pool_pre_ping=True,  # Test connections before using them
    pool_recycle=3600,  # Recycle connections after 1 hour
)

def create_db_and_tables():
    """Create database tables"""
    SQLModel.metadata.create_all(engine)
    logger.info("Database tables created successfully")


async def test_db_connection() -> bool:
    """
    Test database connection without creating tables.
    Used for retry logic in startup.
    
    Returns:
        bool: True if connection successful, False otherwise
    """
    try:
        with engine.connect() as connection:
            connection.execute(__import__('sqlalchemy').text("SELECT 1"))
            logger.debug("Database connection test passed")
            return True
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False


async def create_db_and_tables_with_retry(
    max_retries: int = 5,
    initial_delay: int = 1,
) -> bool:
    """
    Create database tables with connection retry logic.
    Used during application startup to handle cases where database
    is not immediately available (e.g., in Docker Compose).
    
    Args:
        max_retries: Maximum number of connection attempts
        initial_delay: Initial delay in seconds between retries
        
    Returns:
        bool: True if successful, False if all retries failed
        
    Raises:
        Exception: If all retries are exhausted
    """
    retry_delay = initial_delay
    
    for attempt in range(max_retries):
        try:
            logger.info(
                f"Attempting database connection (attempt {attempt + 1}/{max_retries})"
            )
            
            # Test connection first
            if not await test_db_connection():
                raise ConnectionError("Database connection test failed")
            
            # Create tables
            create_db_and_tables()
            logger.info("✓ Database connected and tables created successfully")
            return True
            
        except Exception as e:
            logger.warning(
                f"Database connection attempt {attempt + 1} failed: {e}"
            )
            
            # If this was the last attempt, raise the error
            if attempt == max_retries - 1:
                logger.error(
                    f"Failed to connect to database after {max_retries} attempts"
                )
                raise
            
            # Calculate exponential backoff
            # delay = initial_delay * (2 ^ attempt)
            wait_time = retry_delay * (2 ** attempt)
            logger.info(
                f"Retrying in {wait_time} seconds... "
                f"(next attempt {attempt + 2}/{max_retries})"
            )
            
            await asyncio.sleep(wait_time)
    
    # This should never be reached
    raise RuntimeError("Database initialization failed")


if __name__ == "__main__":
    create_db_and_tables()
