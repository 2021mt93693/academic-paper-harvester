"""
Academic Paper Harvesting System

A comprehensive system for harvesting academic papers from multiple sources:
- ArXiv
- Semantic Scholar
- S2ORC

Features:
- Cron-based scheduling
- Configurable filters (year, language, subject)
- Enable/disable individual sources
- PostgreSQL database for tracking
- Content deduplication using hashing
- Local file storage with organized directory structure
"""

__version__ = '1.0.0'
__author__ = 'Academic Paper Harvester Team'
