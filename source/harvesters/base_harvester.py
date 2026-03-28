"""
Base harvester class defining the interface for all paper harvesters.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import hashlib
import json
import os
import logging
import time
import requests
from datetime import datetime, date

logger = logging.getLogger(__name__)


class PartialFetchError(RuntimeError):
    """Raised when pagination fails after at least one successful batch."""

    def __init__(self, message: str, partial_items: List[Any]):
        super().__init__(message)
        self.partial_items = partial_items


class BaseHarvester(ABC):
    """Abstract base class for all paper harvesters."""
    
    def __init__(self, config: Dict[str, Any], db_manager, storage_path: str):
        """
        Initialize the harvester.
        
        Args:
            config: Configuration dictionary for this harvester
            db_manager: Database manager instance
            storage_path: Path to store downloaded papers
        """
        self.config = config
        self.db_manager = db_manager
        self.storage_path = storage_path
        self.source_name = self.__class__.__name__.lower().replace('harvester', '')
        self.last_error: Optional[str] = None
        self.request_timeout = int(config.get('request_timeout', 30))
        self.max_retries = int(config.get('max_retries', 3))
        self.retry_backoff_seconds = int(config.get('retry_backoff_seconds', 5))
        self.request_delay_seconds = int(config.get('request_delay_seconds', 1))
        self.api_key = config.get('api_key')
        self.session = requests.Session()
        
        # Create storage directory if it doesn't exist
        os.makedirs(storage_path, exist_ok=True)

    def _get_headers(self) -> Dict[str, str]:
        """Build default HTTP headers for source APIs."""
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'academic-paper-harvester/1.0'
        }
        if self.api_key:
            headers['x-api-key'] = self.api_key
        return headers

    def _get_retry_delay(self, response: requests.Response, attempt: int) -> float:
        """Get retry delay from response headers or configured backoff."""
        retry_after = response.headers.get('Retry-After')
        if retry_after:
            try:
                return max(float(retry_after), 1.0)
            except ValueError:
                logger.warning(f"Invalid Retry-After header received: {retry_after}")

        return float(self.retry_backoff_seconds * attempt)

    def _handle_rate_limit(
        self,
        response: requests.Response,
        params: Dict[str, Any],
        attempt: int,
        request_name: str,
        require_api_key_on_429: bool
    ) -> bool:
        """Handle HTTP 429 and return whether request should be retried."""
        if require_api_key_on_429 and not self.api_key:
            raise RuntimeError(
                f"{request_name} rejected an unauthenticated request with HTTP 429. "
                f"Configure sources.{self.source_name}.api_key or disable this source in config.yaml."
            )

        if attempt > self.max_retries:
            return False

        delay = self._get_retry_delay(response, attempt)
        logger.warning(
            "%s rate limit hit at offset %s. Retrying in %.1f seconds (%d/%d)",
            request_name,
            params.get('offset', params.get('start', 0)),
            delay,
            attempt,
            self.max_retries + 1
        )
        time.sleep(delay)
        return True

    def _handle_server_error(
        self,
        response: requests.Response,
        params: Dict[str, Any],
        attempt: int,
        request_name: str
    ) -> bool:
        """Handle retryable HTTP 5xx responses."""
        if not (500 <= response.status_code < 600) or attempt > self.max_retries:
            return False

        delay = float(self.retry_backoff_seconds * attempt)
        logger.warning(
            "%s server error %s at offset %s. Retrying in %.1f seconds (%d/%d)",
            request_name,
            response.status_code,
            params.get('offset', params.get('start', 0)),
            delay,
            attempt,
            self.max_retries + 1
        )
        time.sleep(delay)
        return True

    def _handle_transient_error(self, exc: Exception, attempt: int, request_name: str) -> bool:
        """Handle retryable connection and timeout failures."""
        if attempt > self.max_retries:
            return False

        delay = float(self.retry_backoff_seconds * attempt)
        logger.warning(
            "Transient %s network error: %s. Retrying in %.1f seconds (%d/%d)",
            request_name,
            exc,
            delay,
            attempt,
            self.max_retries + 1
        )
        time.sleep(delay)
        return True

    def request_with_retries(
        self,
        url: str,
        params: Dict[str, Any],
        request_name: str,
        require_api_key_on_429: bool = False
    ) -> requests.Response:
        """Perform HTTP GET with retry handling for 429/5xx/transient failures."""
        last_exception = None

        for attempt in range(2, self.max_retries + 2):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                    timeout=self.request_timeout
                )

                if response.status_code == 429 and self._handle_rate_limit(
                    response,
                    params,
                    attempt,
                    request_name,
                    require_api_key_on_429
                ):
                    continue

                if self._handle_server_error(response, params, attempt, request_name):
                    continue

                response.raise_for_status()
                return response

            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.SSLError,
            ) as exc:
                last_exception = exc
                if self._handle_transient_error(exc, attempt, request_name):
                    continue
                break
            except requests.exceptions.RequestException as exc:
                raise RuntimeError(f"{request_name} request failed: {exc}") from exc

        if last_exception is not None:
            raise RuntimeError(f"{request_name} request failed after retries: {last_exception}") from last_exception

        raise RuntimeError(f"{request_name} request failed after retries")
        
    @abstractmethod
    def fetch_papers(self) -> List[Dict[str, Any]]:
        """
        Fetch papers from the source.
        
        Returns:
            List of paper metadata dictionaries
        """
        pass
    
    @abstractmethod
    def parse_paper(self, raw_data: Any) -> Dict[str, Any]:
        """
        Parse raw paper data into standardized format.
        
        Args:
            raw_data: Raw data from the source
            
        Returns:
            Standardized paper metadata dictionary
        """
        pass
    
    def compute_content_hash(self, content: str) -> str:
        """
        Compute SHA-256 hash of content.
        
        Args:
            content: Content to hash
            
        Returns:
            Hexadecimal hash string
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    @staticmethod
    def _json_serializer(obj: Any) -> Any:
        """Convert non-JSON-native values to stable serializable forms."""
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")
    
    def save_paper(self, paper_data: Dict[str, Any], content: str) -> Optional[str]:
        """
        Save paper content to local storage.
        
        Args:
            paper_data: Paper metadata
            content: Paper content to save
            
        Returns:
            File path if successful, None otherwise
        """
        try:
            # Create filename from paper ID
            paper_id = paper_data['paper_id'].replace('/', '_').replace('\\', '_')
            filename = f"{paper_id}.json"
            filepath = os.path.join(self.storage_path, filename)
            
            # Prepare data to save
            save_data = {
                'metadata': paper_data,
                'content': content,
                'harvested_at': datetime.now().isoformat()
            }
            
            # Save to file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False, default=self._json_serializer)
            
            logger.info(f"Saved paper {paper_id} to {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Error saving paper {paper_data.get('paper_id')}: {e}")
            return None
    
    def apply_filters(self, paper: Dict[str, Any]) -> bool:
        """
        Apply configured filters to determine if paper should be harvested.
        
        Args:
            paper: Paper metadata dictionary
            
        Returns:
            True if paper passes filters, False otherwise
        """
        filters = self.config.get('filters', {})
        
        # Year filter
        if 'start_year' in filters or 'end_year' in filters:
            pub_year = paper.get('published_year')
            if pub_year:
                if 'start_year' in filters and pub_year < filters['start_year']:
                    return False
                if 'end_year' in filters and pub_year > filters['end_year']:
                    return False
        
        # Language filter
        if 'language' in filters:
            paper_lang = paper.get('language', 'en')
            if paper_lang.lower() != filters['language'].lower():
                return False
        
        return True
    
    def process_paper(self, raw_data: Any) -> bool:
        """
        Process a single paper: parse, filter, save, and record in database.
        
        Args:
            raw_data: Raw paper data from source
            
        Returns:
            True if successfully processed, False otherwise
        """
        try:
            # Parse paper data
            paper_data = self.parse_paper(raw_data)
            
            # Apply filters
            if not self.apply_filters(paper_data):
                logger.debug(f"Paper {paper_data.get('paper_id')} filtered out")
                return False
            
            # Compute content hash
            content_str = json.dumps(paper_data, sort_keys=True, default=self._json_serializer)
            content_hash = self.compute_content_hash(content_str)
            
            # Check if paper already exists
            existing = self.db_manager.paper_exists(
                self.source_name, 
                paper_data['paper_id'], 
                content_hash
            )
            
            if existing and existing['content_hash'] == content_hash:
                logger.debug(f"Paper {paper_data['paper_id']} already exists with same content")
                return False
            
            # Determine version number
            version = existing['version'] + 1 if existing else 1
            
            # Save paper to local storage
            filepath = self.save_paper(paper_data, content_str)
            if not filepath:
                return False
            
            # Prepare database record
            db_record = {
                'source': self.source_name,
                'paper_id': paper_data['paper_id'],
                'content_hash': content_hash,
                'title': paper_data.get('title'),
                'authors': paper_data.get('authors'),
                'published_date': paper_data.get('published_date'),
                'version': version,
                'status': 'active',
                'file_path': filepath,
                'metadata': {
                    'abstract': (paper_data.get('abstract') or '')[:500],  # Store truncated abstract
                    'categories': paper_data.get('categories') or [],
                    'url': paper_data.get('url') or '',
                    'doi': paper_data.get('doi') or ''
                }
            }
            
            # Insert into database
            success = self.db_manager.insert_paper(db_record)
            
            if success:
                logger.info(f"Successfully processed paper {paper_data['paper_id']} (version {version})")
            
            return success
            
        except Exception as e:
            logger.error(f"Error processing paper: {e}", exc_info=True)
            return False
    
    def harvest(self) -> Dict[str, int]:
        """
        Main harvest method to fetch and process papers.
        
        Returns:
            Dictionary with statistics (fetched, processed, errors)
        """
        logger.info(f"Starting harvest from {self.source_name}")
        
        stats = {
            'fetched': 0,
            'processed': 0,
            'filtered': 0,
            'errors': 0
        }
        self.last_error = None
        
        papers: List[Any] = []

        try:
            papers = self.fetch_papers()
            stats['fetched'] = len(papers)
        except PartialFetchError as e:
            papers = e.partial_items
            stats['fetched'] = len(papers)
            stats['errors'] += 1
            stats['error_message'] = str(e)
            self.last_error = str(e)
            logger.error(f"Error during fetch phase: {e}", exc_info=True)
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Error during harvest: {e}", exc_info=True)
            stats['errors'] += 1
            stats['error_message'] = str(e)
            return stats

        for paper in papers:
            try:
                if self.process_paper(paper):
                    stats['processed'] += 1
                else:
                    stats['filtered'] += 1
            except Exception as e:
                logger.error(f"Error processing individual paper: {e}")
                stats['errors'] += 1

        if self.last_error:
            logger.warning("Harvest completed with partial data: %s", self.last_error)
        else:
            logger.info(f"Harvest completed: {stats}")
        
        return stats
