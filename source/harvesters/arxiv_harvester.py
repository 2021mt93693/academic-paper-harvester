"""
ArXiv paper harvester implementation.
"""
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from datetime import datetime
import logging
import time
from .base_harvester import BaseHarvester, PartialFetchError

logger = logging.getLogger(__name__)


class ArxivHarvester(BaseHarvester):
    """Harvester for arXiv papers."""
    
    def __init__(self, config: Dict[str, Any], db_manager, storage_path: str):
        super().__init__(config, db_manager, storage_path)
        self.base_url = config.get('base_url', 'http://export.arxiv.org/api/query')
        self.source_name = 'arxiv'
        # ArXiv requires a proper User-Agent header; see https://arxiv.org/help/api/basics
        self.headers = {
            'User-Agent': 'academic-paper-harvester/1.0 (https://github.com/)'
        }
        # ArXiv uses faster exponential backoff by default than JSON APIs.
        self.retry_backoff_seconds = int(config.get('retry_backoff_seconds', 2))
    
    def _request_with_retries(self, params: Dict[str, Any]) -> requests.Response:
        """
        Request from ArXiv API with exponential backoff on transient errors.
        
        Retries on HTTP 429/5xx and transient network errors with exponential
        backoff. Treats non-retryable HTTP status errors as permanent failures.
        
        Args:
            params: Query parameters for the API request
            
        Returns:
            requests.Response object (after HTTP validation)
            
        Raises:
            RuntimeError: On non-retryable HTTP errors or after max retries exceeded
        """
        last_exception = None
        
        for attempt in range(1, self.max_retries + 2):
            try:
                response = self.session.get(
                    self.base_url,
                    params=params,
                    headers=self.headers,
                    timeout=self.request_timeout
                )

                if response.status_code == 429 and self._handle_rate_limit(
                    response,
                    params,
                    attempt,
                    "ArXiv API",
                    require_api_key_on_429=False,
                ):
                    continue

                if self._handle_server_error(response, params, attempt, "ArXiv API"):
                    continue

                response.raise_for_status()
                return response
                
            except requests.exceptions.HTTPError as e:
                # Remaining HTTP errors are treated as permanent
                raise RuntimeError(f"ArXiv API request failed: {e}") from e
                
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.Timeout,
                    requests.exceptions.SSLError) as e:
                # Transient network errors (including mid-stream IncompleteRead) — retry with backoff
                last_exception = e
                if attempt <= self.max_retries:
                    delay = self.retry_backoff_seconds ** (attempt - 1)
                    logger.warning(
                        f"Transient network error on attempt {attempt}/{self.max_retries + 1}. "
                        f"Retrying in {delay}s: {type(e).__name__}"
                    )
                    time.sleep(delay)
                    continue
                break
                
            except Exception as e:
                # Other unexpected errors — surface immediately
                raise RuntimeError(f"Unexpected error fetching from ArXiv: {e}") from e
        
        # Max retries exhausted
        raise RuntimeError(
            f"ArXiv request failed after {self.max_retries} retries: {last_exception}"
        ) from last_exception
    
    def fetch_papers(self) -> List[Dict[str, Any]]:
        """
        Fetch papers from arXiv using start-offset pagination.

        Returns:
            List of raw XML entry elements from the arXiv Atom feed
        """
        papers = []
        filters = self.config.get('filters', {})
        # max_results is the overall cap across all batches; 0 means no cap
        max_results = filters.get('max_results', 0)
        # batch_size is the per-request limit; ArXiv enforces a maximum of 2000
        batch_size = filters.get('batch_size', 2000)
        categories = filters.get('categories', ['cs.AI'])

        # Build category query
        category_query = ' OR '.join([f'cat:{cat}' for cat in categories])

        # Build date range filter honouring both start_year and end_year
        year_filter = ''
        if 'start_year' in filters:
            start_year = filters['start_year']
            end_year = filters.get('end_year', 9999)
            year_filter = f' AND submittedDate:[{start_year}01010000 TO {end_year}12312359]'

        search_query = f'({category_query}){year_filter}'
        logger.info(f"Fetching papers from arXiv with query: {search_query}")

        ns = {'atom': 'http://www.w3.org/2005/Atom',
              'arxiv': 'http://arxiv.org/schemas/atom'}

        start = 0
        batch_num = 0

        while True:
            # Respect overall cap: shrink final batch if needed
            if max_results > 0:
                remaining = max_results - len(papers)
                if remaining <= 0:
                    logger.info(f"Reached max_results cap of {max_results}. Stopping pagination.")
                    break
                current_batch_size = min(batch_size, remaining)
            else:
                current_batch_size = batch_size

            request_batch_size = current_batch_size

            batch_attempt = 0
            while True:
                try:
                    params = {
                        'search_query': search_query,
                        'start': start,
                        'max_results': request_batch_size,
                        'sortBy': 'submittedDate',
                        'sortOrder': 'descending'
                    }

                    response = self._request_with_retries(params)

                    # response.content triggers body download; IncompleteRead can happen here
                    root = ET.fromstring(response.content)
                    batch = root.findall('atom:entry', ns)
                    break  # success — exit retry loop

                except requests.exceptions.ChunkedEncodingError as e:
                    # Connection dropped while streaming the response body.
                    # Retry the whole batch request up to max_retries times.
                    batch_attempt += 1
                    if batch_attempt <= self.max_retries:
                        delay = self.retry_backoff_seconds ** (batch_attempt - 1)
                        logger.warning(
                            f"ArXiv response body truncated (IncompleteRead) on batch "
                            f"{batch_num + 1} attempt {batch_attempt}/{self.max_retries}. "
                            f"Retrying in {delay}s: {e}"
                        )
                        time.sleep(delay)
                        continue
                    # Retries exhausted — raise PartialFetchError so base harvest() records the error
                    if papers:
                        raise PartialFetchError(
                            f"ArXiv fetch stopped at start={start} after {self.max_retries} retries: {e}",
                            partial_items=papers,
                        ) from e
                    raise RuntimeError(
                        f"ArXiv fetch failed at start={start} after {self.max_retries} retries: {e}"
                    ) from e

                except Exception as e:
                    error_text = str(e).lower()
                    # ArXiv occasionally returns 5xx for deep offsets and large pages.
                    # Retry the same offset with a smaller page size before aborting.
                    if (
                        (" 5" in error_text or "500" in error_text or "server error" in error_text)
                        and request_batch_size > 200
                    ):
                        reduced_batch_size = max(200, request_batch_size // 2)
                        if reduced_batch_size < request_batch_size:
                            logger.warning(
                                "ArXiv request failed at start=%s with batch_size=%s. "
                                "Retrying same offset with reduced batch_size=%s.",
                                start,
                                request_batch_size,
                                reduced_batch_size,
                            )
                            request_batch_size = reduced_batch_size
                            continue

                    # On any other error, raise PartialFetchError if we have data, else propagate
                    if papers:
                        raise PartialFetchError(
                            f"ArXiv fetch stopped at start={start}: {e}",
                            partial_items=papers,
                        ) from e
                    raise

            papers.extend(batch)
            batch_num += 1
            logger.info(
                f"Batch {batch_num}: start={start}, fetched={len(batch)}, "
                f"total so far={len(papers)}"
            )

            # ArXiv returns fewer than requested only on the last page
            if len(batch) < request_batch_size:
                logger.info("Last page reached. Pagination complete.")
                break

            start += request_batch_size

            # Be respectful to the ArXiv API between batches
            time.sleep(self.request_delay_seconds)

        logger.info(f"Fetch complete: {len(papers)} total papers retrieved in {batch_num} batch(es)")
        return papers
    
    def parse_paper(self, raw_data: ET.Element) -> Dict[str, Any]:
        """
        Parse arXiv XML entry into standardized format.
        
        Args:
            raw_data: XML Element from arXiv
            
        Returns:
            Standardized paper metadata dictionary
        """
        ns = {'atom': 'http://www.w3.org/2005/Atom',
              'arxiv': 'http://arxiv.org/schemas/atom'}
        
        # Extract paper ID from URL
        id_url = raw_data.find('atom:id', ns).text
        paper_id = id_url.split('/')[-1]
        
        # Extract title
        title = raw_data.find('atom:title', ns).text.strip().replace('\n', ' ')
        
        # Extract authors
        authors = []
        for author in raw_data.findall('atom:author', ns):
            name = author.find('atom:name', ns).text
            authors.append(name)
        authors_str = ', '.join(authors)
        
        # Extract abstract
        abstract = raw_data.find('atom:summary', ns).text.strip().replace('\n', ' ')
        
        # Extract published date
        published = raw_data.find('atom:published', ns).text
        published_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
        
        # Extract updated date
        updated = raw_data.find('atom:updated', ns).text
        updated_date = datetime.fromisoformat(updated.replace('Z', '+00:00'))
        
        # Extract categories
        categories = []
        for category in raw_data.findall('atom:category', ns):
            categories.append(category.get('term'))
        
        # Additional arXiv-specific fields
        comment = raw_data.find('arxiv:comment', ns)
        journal_ref = raw_data.find('arxiv:journal_ref', ns)
        doi = raw_data.find('arxiv:doi', ns)
        
        # Extract PDF link
        pdf_url = None
        for link in raw_data.findall('atom:link', ns):
            if link.get('title') == 'pdf':
                pdf_url = link.get('href')
                break
        
        paper_data = {
            'paper_id': paper_id,
            'title': title,
            'authors': authors_str,
            'abstract': abstract,
            'published_date': published_date.date(),
            'published_year': published_date.year,
            'updated_date': updated_date.date(),
            'categories': categories,
            'url': id_url,
            'pdf_url': pdf_url,
            'doi': doi.text if doi is not None else None,
            'journal_ref': journal_ref.text if journal_ref is not None else None,
            'comment': comment.text if comment is not None else None,
            'language': 'en'  # arXiv papers are predominantly in English
        }
        
        return paper_data
    
    def harvest(self) -> Dict[str, int]:
        """Run harvest with a status header."""
        logger.info("=" * 80)
        logger.info("ARXIV HARVESTER — fetching papers")
        logger.info("=" * 80)
        return super().harvest()
