"""
Database manager for handling PostgreSQL operations.
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Dict, Any, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and operations for the paper harvesting system."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize database manager with configuration.
        
        Args:
            config: Database configuration dictionary
        """
        self.config = config
        self.connection = None
        
    def connect(self):
        """Establish database connection."""
        try:
            self.connection = psycopg2.connect(
                host=self.config['host'],
                port=self.config['port'],
                dbname=self.config['dbname'],
                user=self.config['user'],
                password=self.config['password']
            )
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def disconnect(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")
    
    def initialize_schema(self, schema_file: str):
        """
        Initialize database schema from SQL file.
        
        Args:
            schema_file: Path to the SQL schema file
        """
        try:
            with open(schema_file, 'r') as f:
                schema_sql = f.read()
            
            with self.connection.cursor() as cursor:
                cursor.execute(schema_sql)
                self.connection.commit()
                logger.info("Database schema initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            self.connection.rollback()
            raise
    
    def paper_exists(self, source: str, paper_id: str, content_hash: str) -> Optional[Dict[str, Any]]:
        """
        Check if a paper already exists in the database.
        
        Args:
            source: Source of the paper
            paper_id: Paper identifier
            content_hash: Hash of the paper content
            
        Returns:
            Existing paper record if found, None otherwise
        """
        query = """
            SELECT * FROM harvested_papers 
            WHERE source = %s AND paper_id = %s 
            ORDER BY version DESC LIMIT 1
        """
        
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, (source, paper_id))
                result = cursor.fetchone()
                
                if result and result['content_hash'] == content_hash:
                    logger.debug(f"Paper {paper_id} already exists with same content")
                    return dict(result)
                elif result:
                    logger.debug(f"Paper {paper_id} exists but content has changed")
                    return dict(result)
                else:
                    return None
        except Exception as e:
            logger.error(f"Error checking paper existence: {e}")
            return None
    
    def insert_paper(self, paper_data: Dict[str, Any]) -> bool:
        """
        Insert a new paper record into the database.
        
        Args:
            paper_data: Dictionary containing paper information
            
        Returns:
            True if successful, False otherwise
        """
        query = """
            INSERT INTO harvested_papers 
            (source, paper_id, content_hash, title, authors, published_date, 
             updated_datetime, version, status, file_path, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (
                    paper_data['source'],
                    paper_data['paper_id'],
                    paper_data['content_hash'],
                    paper_data.get('title'),
                    paper_data.get('authors'),
                    paper_data.get('published_date'),
                    datetime.now(),
                    paper_data.get('version', 1),
                    paper_data.get('status', 'active'),
                    paper_data.get('file_path'),
                    psycopg2.extras.Json(paper_data.get('metadata', {}))
                ))
                paper_id = cursor.fetchone()[0]
                self.connection.commit()
                logger.info(f"Inserted paper {paper_data['paper_id']} with database id {paper_id}")
                return True
        except Exception as e:
            logger.error(f"Error inserting paper: {e}")
            self.connection.rollback()
            return False
    
    def update_paper_status(self, source: str, paper_id: str, status: str) -> bool:
        """
        Update the status of a paper.
        
        Args:
            source: Source of the paper
            paper_id: Paper identifier
            status: New status value
            
        Returns:
            True if successful, False otherwise
        """
        query = """
            UPDATE harvested_papers 
            SET status = %s, updated_datetime = %s
            WHERE source = %s AND paper_id = %s
        """
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (status, datetime.now(), source, paper_id))
                self.connection.commit()
                logger.info(f"Updated status for paper {paper_id} to {status}")
                return True
        except Exception as e:
            logger.error(f"Error updating paper status: {e}")
            self.connection.rollback()
            return False
    
    def get_papers_by_source(self, source: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieve papers from a specific source.
        
        Args:
            source: Source to filter by
            limit: Maximum number of records to return
            
        Returns:
            List of paper records
        """
        query = """
            SELECT * FROM harvested_papers 
            WHERE source = %s 
            ORDER BY updated_datetime DESC 
            LIMIT %s
        """
        
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, (source, limit))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error retrieving papers: {e}")
            return []
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about harvested papers.
        
        Returns:
            Dictionary with statistics
        """
        query = """
            SELECT 
                source,
                COUNT(*) as total_papers,
                COUNT(DISTINCT paper_id) as unique_papers,
                MAX(updated_datetime) as last_updated
            FROM harvested_papers
            WHERE status = 'active'
            GROUP BY source
        """
        
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error retrieving statistics: {e}")
            return []
