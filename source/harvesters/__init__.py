"""
Harvesters package for academic paper collection.
"""
from .base_harvester import BaseHarvester
from .arxiv_harvester import ArxivHarvester
from .semantic_scholar_harvester import SemanticScholarHarvester
from .s2orc_harvester import S2orcHarvester

__all__ = [
    'BaseHarvester',
    'ArxivHarvester',
    'SemanticScholarHarvester',
    'S2orcHarvester'
]
