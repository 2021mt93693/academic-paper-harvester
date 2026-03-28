"""
S2ORC (Semantic Scholar Open Research Corpus) paper harvester implementation.

Supports two fetch modes controlled by ``sources.s2orc.mode`` in config.yaml:

* ``proxy`` (default) — queries the Semantic Scholar Graph API (/paper/search)
  page-by-page.  Fast to set up; limited to ~10k results per query window.

* ``bulk`` — downloads signed S3 shard files from the Semantic Scholar Datasets
  API, decompresses them in-memory shard-by-shard, and streams JSONL records.
  Gives access to the full S2ORC corpus.  Controlled by ``max_results`` in both
  modes — bulk mode stops reading at the line boundary once the cap is reached,
  so you never have to download the entire corpus.
"""
import gzip
import io
import json
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import time
from .base_harvester import BaseHarvester, PartialFetchError

logger = logging.getLogger(__name__)


class S2orcHarvester(BaseHarvester):
    """
    Harvester for the S2ORC dataset (Lo et al. 2020,
    "S2ORC: The Semantic Scholar Open Research Corpus").

    Two modes are supported (see module docstring).  In both modes
    ``filters.max_results`` caps total papers returned; 0 means no cap.
    """

    def __init__(self, config: Dict[str, Any], db_manager, storage_path: str):
        super().__init__(config, db_manager, storage_path)
        self.base_url = config.get('base_url', 'https://api.semanticscholar.org/datasets/v1/release')
        self.source_name = 's2orc'
        # 'proxy' or 'bulk'
        self.mode = config.get('mode', 'proxy')
        # Release tag for bulk mode; 'latest' resolves to the newest available snapshot
        self.bulk_release = config.get('bulk_release', 'latest')

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _get_current_batch_size(self, max_results: int, fetched_count: int, batch_size: int) -> Optional[int]:
        """Return the page size for the next proxy request, or None when the cap is reached."""
        if max_results > 0:
            remaining = max_results - fetched_count
            if remaining <= 0:
                logger.info(f"Reached max_results cap of {max_results}. Stopping pagination.")
                return None
            return min(batch_size, remaining)
        return batch_size

    # ------------------------------------------------------------------
    # Proxy mode
    # ------------------------------------------------------------------

    def _fetch_proxy_papers(self) -> List[Dict[str, Any]]:
        """
        Fetch papers via the Semantic Scholar Graph API (/paper/search).

        Suitable for small-to-medium harvests (up to ~10k results per query
        window).  Pages through results in batches of up to 100 records.

        Returns:
            List of raw paper dicts from the Graph API ``data`` array.
        """
        filters = self.config.get('filters', {})
        max_results = filters.get('max_results', 0)
        batch_size = min(int(filters.get('batch_size', 100)), 100)
        start_year = filters.get('start_year')
        end_year = filters.get('end_year')
        categories = filters.get('categories', ['Computer Science'])

        if max_results == 0:
            logger.info("S2ORC proxy: max_results is 0; skipping fetch")
            return []

        api_url = 'https://api.semanticscholar.org/graph/v1/paper/search'
        year_filter = f"{start_year or '2020'}-{end_year or '2024'}"
        query = ' '.join(categories)
        base_params = {
            'query': query,
            'fields': 'paperId,title,abstract,authors,year,publicationDate,'
                      'citationCount,referenceCount,fieldsOfStudy,url,externalIds',
            'year': year_filter,
        }

        papers: List[Dict[str, Any]] = []
        offset = 0
        batch_num = 0

        logger.info("S2ORC proxy: fetching via Semantic Scholar Graph API")

        while True:
            current_batch = self._get_current_batch_size(max_results, len(papers), batch_size)
            if current_batch is None:
                break

            params = {**base_params, 'limit': current_batch, 'offset': offset}

            try:
                response = self.request_with_retries(
                    api_url, params, request_name="S2ORC proxy"
                )
                batch = response.json().get('data', [])
            except RuntimeError as exc:
                if papers:
                    raise PartialFetchError(
                        f"S2ORC proxy fetch stopped at offset {offset}: {exc}",
                        list(papers)
                    ) from exc
                raise

            papers.extend(batch)
            batch_num += 1
            logger.info(
                f"Batch {batch_num}: offset={offset}, fetched={len(batch)}, "
                f"total so far={len(papers)}"
            )

            if len(batch) < current_batch:
                logger.info("Last proxy page reached. Pagination complete.")
                break

            offset += len(batch)
            time.sleep(self.request_delay_seconds)

        logger.info(f"S2ORC proxy fetch complete: {len(papers)} papers in {batch_num} batch(es)")
        return papers

    # ------------------------------------------------------------------
    # Bulk mode
    # ------------------------------------------------------------------

    def _fetch_bulk_shard_urls(self) -> List[str]:
        """
        Retrieve signed S3 download URLs for all S2ORC paper shard files.

        Uses the Semantic Scholar Datasets API endpoint:
        GET /datasets/v1/release/{release}/dataset/papers

        Args:
            (uses self.bulk_release and self.base_url)

        Returns:
            List of HTTPS URLs, each pointing to a gzipped JSONL shard file.
        """
        url = f"{self.base_url}/{self.bulk_release}/dataset/papers"
        logger.info(f"S2ORC bulk: fetching shard URLs from {url}")
        response = self.request_with_retries(url, {}, request_name="S2ORC datasets API")
        return response.json().get('files', [])

    def _stream_shard(
        self,
        shard_url: str,
        papers: List[Dict[str, Any]],
        max_results: int,
        start_year: Optional[int],
        end_year: Optional[int],
    ) -> bool:
        """
        Download, decompress, and stream one gzipped JSONL shard.

        Records are filtered by year and appended to ``papers`` in-place.
        Stops mid-shard as soon as ``max_results`` is reached.

        Args:
            shard_url: Signed S3 URL for the shard.
            papers: Accumulator list; mutated in-place.
            max_results: Stop appending when ``len(papers) >= max_results`` (0 = no cap).
            start_year: Inclusive lower year bound (None = no lower bound).
            end_year: Inclusive upper year bound (None = no upper bound).

        Returns:
            True if the cap was reached and no further shards should be fetched.

        Example:
            >>> capped = self._stream_shard(url, papers, max_results=500, ...)
        """
        # Use a 5-minute timeout for shard downloads; shards can be ~100 MB compressed
        # Signed S3 URLs are already authenticated by query params; do not send API headers.
        resp = self.session.get(shard_url, timeout=300, stream=True)
        resp.raise_for_status()

        # Buffer the shard in memory so gzip can seek if needed
        buf = io.BytesIO()
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                buf.write(chunk)
        buf.seek(0)

        cap_reached = False
        with gzip.open(buf, 'rt', encoding='utf-8') as gz:
            for line in gz:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                year = record.get('year')
                if start_year and year and year < start_year:
                    continue
                if end_year and year and year > end_year:
                    continue

                papers.append(record)

                if max_results > 0 and len(papers) >= max_results:
                    logger.info(f"Reached max_results cap of {max_results}. Stopping bulk fetch.")
                    cap_reached = True
                    break

        return cap_reached

    @staticmethod
    def _is_status_code(exc: Exception, status_code: int) -> bool:
        """Return True when ``exc`` is an HTTPError with the requested status code."""
        if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
            return exc.response.status_code == status_code
        return False

    def _fetch_bulk_papers(self) -> List[Dict[str, Any]]:
        """
        Download S2ORC bulk shard files and stream records up to ``max_results``.

        Each shard is a gzipped JSONL file (~100 MB compressed).  Shards are
        processed sequentially; fetching stops as soon as the ``max_results``
        cap is reached, so only the minimum number of shards are downloaded.

        Returns:
            List of raw S2ORC paper dicts from the Datasets API bulk files.
        """
        filters = self.config.get('filters', {})
        max_results = filters.get('max_results', 0)
        start_year = filters.get('start_year')
        end_year = filters.get('end_year')

        shard_urls = self._fetch_bulk_shard_urls()
        logger.info(f"S2ORC bulk: found {len(shard_urls)} shard file(s) for release '{self.bulk_release}'")

        papers: List[Dict[str, Any]] = []

        for shard_num, url in enumerate(shard_urls, 1):
            if max_results > 0 and len(papers) >= max_results:
                break

            logger.info(f"S2ORC bulk: downloading shard {shard_num}/{len(shard_urls)}")
            attempts = 0
            max_attempts = 2

            while True:
                try:
                    cap_reached = self._stream_shard(url, papers, max_results, start_year, end_year)
                    break
                except Exception as exc:
                    attempts += 1

                    # Signed shard URLs can occasionally be stale/invalid (HTTP 403).
                    # Refresh the URL list and retry this shard once before failing.
                    if self._is_status_code(exc, 403) and attempts < max_attempts:
                        logger.warning(
                            "S2ORC bulk: shard %s returned 403; refreshing signed URLs and retrying (%s/%s)",
                            shard_num,
                            attempts,
                            max_attempts,
                        )
                        refreshed_urls = self._fetch_bulk_shard_urls()
                        if len(refreshed_urls) < shard_num:
                            raise RuntimeError(
                                f"S2ORC bulk refresh returned {len(refreshed_urls)} shard URLs; "
                                f"cannot retry shard {shard_num}."
                            ) from exc
                        shard_urls = refreshed_urls
                        url = shard_urls[shard_num - 1]
                        continue

                    if papers:
                        raise PartialFetchError(
                            f"S2ORC bulk shard {shard_num} failed after {len(papers)} papers: {exc}",
                            list(papers)
                        ) from exc
                    raise RuntimeError(f"S2ORC bulk shard {shard_num} failed: {exc}") from exc

            logger.info(f"S2ORC bulk: shard {shard_num} done, total so far={len(papers)}")

            if cap_reached:
                break

        logger.info(f"S2ORC bulk fetch complete: {len(papers)} papers from {shard_num} shard(s)")
        return papers

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_papers(self) -> List[Dict[str, Any]]:
        """
        Dispatch to proxy or bulk fetch based on ``sources.s2orc.mode``.

        Returns:
            List of raw paper dicts; schema differs slightly between modes
            but is normalised by ``parse_paper``.
        """
        if self.mode == 'bulk':
            logger.info("S2ORC harvester running in BULK mode")
            return self._fetch_bulk_papers()

        logger.info("S2ORC harvester running in PROXY mode")
        logger.warning(
            "S2ORC proxy mode uses the Semantic Scholar Graph API as a stand-in. "
            "Switch to mode: bulk for full corpus access."
        )
        return self._fetch_proxy_papers()

    def parse_paper(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalise a raw S2ORC record (proxy or bulk format) to the shared schema.

        Proxy records (Graph API) use camelCase keys (``paperId``, ``externalIds``).
        Bulk records (Datasets API) use lowercase keys (``corpusid``, ``externalids``).
        Both are handled transparently here.

        Args:
            raw_data: Raw dict from either the proxy or bulk fetch path.

        Returns:
            Standardised paper metadata dictionary.
        """
        # Bulk records use 'corpusid'; proxy records use 'paperId'
        if 'corpusid' in raw_data:
            paper_id = f"s2orc_{raw_data['corpusid']}"
            external_ids = raw_data.get('externalids', {}) or {}
        else:
            paper_id = f"s2orc_{raw_data.get('paperId', '')}"
            external_ids = raw_data.get('externalIds', {}) or {}

        title = raw_data.get('title') or 'Unknown Title'

        authors = []
        for author in raw_data.get('authors', []):
            if isinstance(author, dict) and 'name' in author:
                authors.append(author['name'])
        authors_str = ', '.join(authors) if authors else 'Unknown'

        abstract = raw_data.get('abstract') or ''

        pub_date_str = raw_data.get('publicationDate') or raw_data.get('publicationdate')
        published_date = None
        published_year = raw_data.get('year')

        if pub_date_str:
            try:
                published_date = datetime.strptime(pub_date_str, '%Y-%m-%d').date()
                if not published_year:
                    published_year = published_date.year
            except ValueError:
                logger.warning(f"Could not parse date: {pub_date_str}")

        # Bulk: s2fieldsofstudy is a list of {category, source}; proxy: fieldsOfStudy is a list of strings
        if 's2fieldsofstudy' in raw_data:
            fields = [f['category'] for f in (raw_data['s2fieldsofstudy'] or []) if 'category' in f]
        else:
            fields = raw_data.get('fieldsOfStudy') or []

        doi = external_ids.get('DOI') or external_ids.get('doi')
        arxiv_id = external_ids.get('ArXiv') or external_ids.get('arxiv')

        url = raw_data.get('url') or f"https://www.semanticscholar.org/paper/{paper_id}"

        return {
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
            'citation_count': raw_data.get('citationCount', 0),
            'reference_count': raw_data.get('referenceCount', 0),
            'language': 'en',
        }

    def harvest(self) -> Dict[str, int]:
        """Run harvest with an S2ORC mode note."""
        logger.info("=" * 80)
        logger.info(f"S2ORC HARVESTER — mode: {self.mode.upper()}")
        if self.mode == 'bulk':
            logger.info(f"Using Datasets API bulk shards (release: {self.bulk_release})")
        else:
            logger.info("Using Semantic Scholar Graph API as proxy")
            logger.info("For full corpus access, switch to mode: bulk in config.yaml")
        logger.info("=" * 80)
        return super().harvest()
