"""
Semantic Scholar paper harvester implementation.
"""
from typing import List, Dict, Any
from datetime import datetime
import logging
import time
from .base_harvester import BaseHarvester, PartialFetchError

logger = logging.getLogger(__name__)


class SemanticScholarHarvester(BaseHarvester):
    """Harvester for Semantic Scholar papers."""
    
    def __init__(self, config: Dict[str, Any], db_manager, storage_path: str):
        super().__init__(config, db_manager, storage_path)
        self.base_url = config.get('base_url', 'https://api.semanticscholar.org/graph/v1')
        self.source_name = 'semantic_scholar'
        # Semantic Scholar API enforces hard limits: 100 per request with key, 25 without
        self.authenticated_page_size_limit = 100
        self.unauthenticated_page_size_limit = 25

    def _build_base_params(self, query: str, year_filter: str) -> Dict[str, Any]:
        """Build the shared request parameters for Semantic Scholar search."""
        params = {
            'query': query,
            'fields': 'paperId,title,abstract,authors,year,publicationDate,citationCount,referenceCount,fieldsOfStudy,s2FieldsOfStudy,publicationTypes,url,externalIds'
        }

        if year_filter:
            params['year'] = year_filter

        return params

    def _build_page_params(
        self,
        base_params: Dict[str, Any],
        offset: int,
        remaining: int,
        page_size: int
    ) -> Dict[str, Any]:
        """Build a single paged search request."""
        return {
            **base_params,
            'limit': min(page_size, remaining),
            'offset': offset
        }

    def _should_continue_fetching(
        self,
        batch: List[Dict[str, Any]],
        limit: int,
        offset: int,
        total_available: Any,
        fetched_count: int,
        max_results: int
    ) -> bool:
        """Determine whether another page should be requested."""
        if not batch:
            return False

        if total_available is not None and offset >= total_available:
            return False

        if len(batch) < limit:
            return False

        return fetched_count < max_results

    def fetch_papers(self) -> List[Dict[str, Any]]:
        """
        Fetch papers from Semantic Scholar API.
        
        Returns:
            List of raw paper data from Semantic Scholar
        """
        filters = self.config.get('filters', {})
        max_results = max(int(filters.get('max_results', 100)), 0)
        fields_of_study = filters.get('categories', ['Computer Science'])
        start_year = filters.get('start_year')
        end_year = filters.get('end_year')

        if max_results == 0:
            logger.info("Semantic Scholar max_results is 0; skipping fetch")
            return []
        
        # Build query
        query = ' '.join(fields_of_study)
        
        # Construct year filter
        year_filter = ''
        if start_year or end_year:
            year_filter = f"{start_year or '1900'}-{end_year or '2100'}"
        
        # Use paper search endpoint
        url = f"{self.base_url}/paper/search"
        # Semantic Scholar API enforces hard limits per request
        api_limit = self.authenticated_page_size_limit if self.api_key else self.unauthenticated_page_size_limit
        configured_batch_size = int(filters.get('batch_size', api_limit))
        page_size = min(configured_batch_size, api_limit)

        if page_size < configured_batch_size:
            logger.info(
                "Semantic Scholar batch_size clamped to API limit: %d (configured: %d)",
                page_size,
                configured_batch_size
            )

        base_params = self._build_base_params(query, year_filter)

        papers: List[Dict[str, Any]] = []
        offset = 0
        batch_num = 0

        logger.info(f"Fetching papers from Semantic Scholar with query: {query}")

        while len(papers) < max_results:
            remaining = max_results - len(papers)
            params = self._build_page_params(base_params, offset, remaining, page_size)

            try:
                response = self.request_with_retries(
                    url,
                    params,
                    request_name="Semantic Scholar",
                    require_api_key_on_429=True
                )
            except Exception as exc:
                if papers:
                    raise PartialFetchError(
                        f"Semantic Scholar fetch stopped at offset {offset}: {exc}",
                        partial_items=papers,
                    ) from exc
                raise
            data = response.json()
            batch = data.get('data', [])

            papers.extend(batch)
            batch_num += 1
            offset += len(batch)

            logger.info(
                f"Batch {batch_num}: offset={offset - len(batch)}, fetched={len(batch)}, "
                f"total so far={len(papers)}"
            )

            total_available = data.get('total')
            if not self._should_continue_fetching(
                batch,
                params['limit'],
                offset,
                total_available,
                len(papers),
                max_results
            ):
                break

            time.sleep(self.request_delay_seconds)

        logger.info(f"Fetch complete: {len(papers)} total papers retrieved in {batch_num} batch(es)")
        return papers
    
    def parse_paper(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Semantic Scholar paper data into standardized format.
        
        Args:
            raw_data: JSON data from Semantic Scholar API
            
        Returns:
            Standardized paper metadata dictionary
        """
        # Extract paper ID
        paper_id = raw_data.get('paperId', '')
        
        # Extract title
        title = raw_data.get('title', 'Unknown Title')
        
        # Extract authors
        authors = []
        for author in raw_data.get('authors', []):
            if 'name' in author:
                authors.append(author['name'])
        authors_str = ', '.join(authors) if authors else 'Unknown'
        
        # Extract abstract
        abstract = raw_data.get('abstract', '')
        
        # Extract publication date
        pub_date_str = raw_data.get('publicationDate')
        published_date = None
        published_year = raw_data.get('year')
        
        if pub_date_str:
            try:
                published_date = datetime.strptime(pub_date_str, '%Y-%m-%d').date()
                if not published_year:
                    published_year = published_date.year
            except ValueError:
                logger.warning(f"Could not parse date: {pub_date_str}")
        
        # Extract fields of study
        fields = []
        if 's2FieldsOfStudy' in raw_data:
            fields = [f['category'] for f in raw_data['s2FieldsOfStudy']]
        elif 'fieldsOfStudy' in raw_data:
            fields = raw_data['fieldsOfStudy'] or []
        
        # Extract external IDs
        external_ids = raw_data.get('externalIds', {})
        doi = external_ids.get('DOI')
        arxiv_id = external_ids.get('ArXiv')
        
        # Extract URL
        url = raw_data.get('url', f"https://www.semanticscholar.org/paper/{paper_id}")
        
        # Extract citation and reference counts
        citation_count = raw_data.get('citationCount', 0)
        reference_count = raw_data.get('referenceCount', 0)
        
        paper_data = {
            'paper_id': paper_id,
            'title': title,
            'authors': authors_str,
            'abstract': abstract,
            'published_date': published_date,
            'published_year': published_year,
            'categories': fields,
            'url': url,
            'doi': doi,
            'arxiv_id': arxiv_id,
            'citation_count': citation_count,
            'reference_count': reference_count,
            'publication_types': raw_data.get('publicationTypes', []),
            'language': 'en'  # Most papers in Semantic Scholar are in English
        }
        
        return paper_data
    
    def harvest(self) -> Dict[str, int]:
        """Run harvest with a status header."""
        logger.info("=" * 80)
        logger.info("SEMANTIC SCHOLAR HARVESTER — fetching papers")
        logger.info("=" * 80)
        return super().harvest()
