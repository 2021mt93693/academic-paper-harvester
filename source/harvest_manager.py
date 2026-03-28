"""
Harvest manager to coordinate multiple paper harvesters.
"""
import logging
from typing import Dict, Any, List
from source.database import DatabaseManager
from source.harvesters import ArxivHarvester, SemanticScholarHarvester, S2orcHarvester

logger = logging.getLogger(__name__)


class HarvestManager:
    """Manages and coordinates multiple paper harvesters."""
    
    def __init__(self, config: Dict[str, Any], db_manager: DatabaseManager):
        """
        Initialize the harvest manager.
        
        Args:
            config: Full application configuration
            db_manager: Database manager instance
        """
        self.config = config
        self.db_manager = db_manager
        self.harvesters = {}
        
        # Initialize harvesters based on configuration
        self._initialize_harvesters()
    
    def _initialize_harvesters(self):
        """Initialize all configured harvesters."""
        sources_config = self.config.get('sources', {})
        storage_config = self.config.get('storage', {})
        root_dir = storage_config.get('root_directory', '../data/harvested')
        subdirs = storage_config.get('subdirectories', {})
        
        # ArXiv harvester
        if sources_config.get('arxiv', {}).get('enabled', False):
            arxiv_storage = f"{root_dir}/{subdirs.get('arxiv', 'arxiv_papers')}"
            self.harvesters['arxiv'] = ArxivHarvester(
                sources_config['arxiv'],
                self.db_manager,
                arxiv_storage
            )
            logger.info("ArXiv harvester initialized")
        
        # Semantic Scholar harvester
        if sources_config.get('semantic_scholar', {}).get('enabled', False):
            ss_storage = f"{root_dir}/{subdirs.get('semantic_scholar', 'semantic_scholar_papers')}"
            self.harvesters['semantic_scholar'] = SemanticScholarHarvester(
                sources_config['semantic_scholar'],
                self.db_manager,
                ss_storage
            )
            logger.info("Semantic Scholar harvester initialized")
        
        # S2ORC harvester
        if sources_config.get('s2orc', {}).get('enabled', False):
            s2orc_storage = f"{root_dir}/{subdirs.get('s2orc', 's2orc_papers')}"
            self.harvesters['s2orc'] = S2orcHarvester(
                sources_config['s2orc'],
                self.db_manager,
                s2orc_storage
            )
            logger.info("S2ORC harvester initialized")
        
        if not self.harvesters:
            logger.warning("No harvesters are enabled! Check your configuration.")
    
    def run_harvest(self, sources: List[str] = None) -> Dict[str, Dict[str, int]]:
        """
        Run harvest for specified sources or all enabled sources.
        
        Args:
            sources: List of source names to harvest. If None, harvest all enabled sources.
            
        Returns:
            Dictionary mapping source names to their harvest statistics
        """
        if sources is None:
            sources = list(self.harvesters.keys())
        
        results = {}
        
        for source_name in sources:
            if source_name not in self.harvesters:
                logger.warning(f"Source '{source_name}' is not available or not enabled")
                continue
            
            logger.info(f"Starting harvest for {source_name}")
            
            try:
                harvester = self.harvesters[source_name]
                stats = harvester.harvest()
                results[source_name] = stats
                
                logger.info(f"Completed harvest for {source_name}: {stats}")
                
            except Exception as e:
                logger.error(f"Error harvesting from {source_name}: {e}", exc_info=True)
                results[source_name] = {
                    'fetched': 0,
                    'processed': 0,
                    'filtered': 0,
                    'errors': 1,
                    'error_message': str(e)
                }
        
        return results
    
    def get_enabled_sources(self) -> List[str]:
        """
        Get list of enabled source names.
        
        Returns:
            List of enabled source names
        """
        return list(self.harvesters.keys())
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics from the database.
        
        Returns:
            Database statistics
        """
        try:
            return self.db_manager.get_statistics()
        except Exception as e:
            logger.error(f"Error retrieving statistics: {e}")
            return {}
