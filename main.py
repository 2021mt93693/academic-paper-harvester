#!/usr/bin/env python3
"""
Academic Paper Harvester - Main Application Entry Point

This application harvests academic papers from multiple sources:
- ArXiv API
- Semantic Scholar API
- S2ORC (Semantic Scholar Open Research Corpus)

The harvester can run on a schedule (cron) or be triggered manually.
"""

import argparse
import logging
import yaml
import sys
import os
from pathlib import Path

from source.database import DatabaseManager
from source.harvest_manager import HarvestManager
from source.scheduler import HarvestScheduler


def setup_logging(config: dict):
    """
    Setup logging configuration.
    
    Args:
        config: Logging configuration dictionary
    """
    log_level = getattr(logging, config.get('level', 'INFO'))
    log_format = config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_file = config.get('file', 'harvester.log')
    
    # Create logs directory if it doesn't exist
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info("Logging initialized")


def load_config(config_path: str) -> dict:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configuration dictionary
    """
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        print(f"Error loading configuration: {e}")
        sys.exit(1)


def initialize_database(db_config: dict, schema_file: str):
    """
    Initialize database connection and schema.
    
    Args:
        db_config: Database configuration
        schema_file: Path to SQL schema file
        
    Returns:
        DatabaseManager instance
    """
    db_manager = DatabaseManager(db_config)
    db_manager.connect()
    
    # Initialize schema if schema file exists
    if os.path.exists(schema_file):
        db_manager.initialize_schema(schema_file)
    else:
        logging.warning(f"Schema file not found: {schema_file}")
    
    return db_manager


def run_immediate_harvest(config: dict, sources: list = None):
    """
    Run an immediate harvest without scheduling.
    
    Args:
        config: Application configuration
        sources: List of specific sources to harvest, or None for all
    """
    logger = logging.getLogger(__name__)
    logger.info("Starting immediate harvest")
    
    # Initialize database
    db_manager = initialize_database(
        config['database'],
        'schema.sql'
    )
    
    try:
        # Create harvest manager
        harvest_manager = HarvestManager(config, db_manager)
        
        # Run harvest
        results = harvest_manager.run_harvest(sources)
        
        # Display results
        logger.info("=" * 80)
        logger.info("HARVEST RESULTS:")
        logger.info("=" * 80)
        
        total_stats = {
            'fetched': 0,
            'processed': 0,
            'filtered': 0,
            'errors': 0
        }
        
        for source, stats in results.items():
            logger.info(f"\n{source.upper()}:")
            for key, value in stats.items():
                logger.info(f"  {key}: {value}")
                if key in total_stats:
                    total_stats[key] += value
        
        logger.info("\nTOTAL:")
        for key, value in total_stats.items():
            logger.info(f"  {key}: {value}")
        
        logger.info("=" * 80)
        
        # Display database statistics
        db_stats = harvest_manager.get_statistics()
        if db_stats:
            logger.info("\nDATABASE STATISTICS:")
            for stat in db_stats:
                logger.info(f"  {stat}")
        
    finally:
        db_manager.disconnect()


def run_scheduled_harvest(config: dict):
    """
    Run the harvester with scheduling enabled.
    
    Args:
        config: Application configuration
    """
    logger = logging.getLogger(__name__)
    logger.info("Starting scheduled harvester")
    
    # Initialize database
    db_manager = initialize_database(
        config['database'],
        'schema.sql'
    )
    
    try:
        # Create harvest manager
        harvest_manager = HarvestManager(config, db_manager)
        
        # Create and start scheduler
        scheduler = HarvestScheduler(
            config.get('scheduler', {}),
            harvest_manager
        )
        
        logger.info("Starting scheduler (press Ctrl+C to stop)")
        scheduler.start()
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"Error in scheduled mode: {e}", exc_info=True)
    finally:
        db_manager.disconnect()


def show_status(config: dict):
    """
    Show current system status.
    
    Args:
        config: Application configuration
    """
    logger = logging.getLogger(__name__)
    
    # Initialize database
    db_manager = initialize_database(
        config['database'],
        'schema.sql'
    )
    
    try:
        harvest_manager = HarvestManager(config, db_manager)
        
        print("\n" + "=" * 80)
        print("ACADEMIC PAPER HARVESTER - STATUS")
        print("=" * 80)
        
        # Show enabled sources
        enabled_sources = harvest_manager.get_enabled_sources()
        print(f"\nEnabled sources: {', '.join(enabled_sources) if enabled_sources else 'None'}")
        
        # Show scheduler status
        scheduler_config = config.get('scheduler', {})
        print(f"\nScheduler:")
        print(f"  Enabled: {scheduler_config.get('enabled', True)}")
        print(f"  Cron expression: {scheduler_config.get('cron_expression', '0 2 * * *')}")
        
        # Show database statistics
        print("\nDatabase Statistics:")
        stats = harvest_manager.get_statistics()
        if stats:
            for stat in stats:
                print(f"  Source: {stat.get('source')}")
                print(f"    Total papers: {stat.get('total_papers')}")
                print(f"    Unique papers: {stat.get('unique_papers')}")
                print(f"    Last updated: {stat.get('last_updated')}")
        else:
            print("  No papers harvested yet")
        
        print("=" * 80 + "\n")
        
    finally:
        db_manager.disconnect()


def main():
    """Main application entry point."""
    parser = argparse.ArgumentParser(
        description='Academic Paper Harvester',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run immediate harvest from all enabled sources
  python main.py --now
  
  # Run immediate harvest from specific sources
  python main.py --now --sources arxiv semantic_scholar
  
  # Start scheduled harvester
  python main.py --schedule
  
  # Show system status
  python main.py --status
  
  # Initialize database schema only
  python main.py --init-db
        """
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    
    parser.add_argument(
        '--now',
        action='store_true',
        help='Run harvest immediately without scheduling'
    )
    
    parser.add_argument(
        '--schedule',
        action='store_true',
        help='Start the scheduled harvester'
    )
    
    parser.add_argument(
        '--sources',
        nargs='+',
        help='Specific sources to harvest (arxiv, semantic_scholar, s2orc)'
    )
    
    parser.add_argument(
        '--status',
        action='store_true',
        help='Show system status and statistics'
    )
    
    parser.add_argument(
        '--init-db',
        action='store_true',
        help='Initialize database schema only'
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Setup logging
    setup_logging(config.get('logging', {}))
    
    logger = logging.getLogger(__name__)
    logger.info("Academic Paper Harvester started")
    logger.info(f"Configuration loaded from: {args.config}")
    
    # Execute requested action
    if args.init_db:
        logger.info("Initializing database schema...")
        db_manager = initialize_database(config['database'], 'schema.sql')
        db_manager.disconnect()
        logger.info("Database initialization complete")
        
    elif args.status:
        show_status(config)
        
    elif args.now:
        run_immediate_harvest(config, args.sources)
        
    elif args.schedule:
        run_scheduled_harvest(config)
        
    else:
        parser.print_help()
        print("\nNo action specified. Use --now, --schedule, --status, or --init-db")


if __name__ == '__main__':
    main()
