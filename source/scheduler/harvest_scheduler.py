"""
Scheduler module for managing cron-based paper harvesting.
"""
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class HarvestScheduler:
    """Manages scheduled execution of paper harvesting tasks."""
    
    def __init__(self, config: Dict[str, Any], harvest_manager):
        """
        Initialize the scheduler.
        
        Args:
            config: Scheduler configuration
            harvest_manager: HarvestManager instance to run harvests
        """
        self.config = config
        self.harvest_manager = harvest_manager
        self.scheduler = BlockingScheduler()
        self.is_enabled = config.get('enabled', True)
        
    def parse_cron_expression(self, cron_expr: str) -> Dict[str, str]:
        """
        Parse cron expression into APScheduler format.
        
        Args:
            cron_expr: Cron expression (e.g., "0 2 * * *")
            
        Returns:
            Dictionary with cron fields
        """
        parts = cron_expr.split()
        
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {cron_expr}. Expected 5 fields.")
        
        return {
            'minute': parts[0],
            'hour': parts[1],
            'day': parts[2],
            'month': parts[3],
            'day_of_week': parts[4]
        }
    
    def scheduled_harvest(self):
        """Execute the harvest job."""
        try:
            logger.info("=" * 80)
            logger.info(f"Scheduled harvest started at {datetime.now()}")
            logger.info("=" * 80)
            
            results = self.harvest_manager.run_harvest()
            
            logger.info("=" * 80)
            logger.info("Scheduled harvest completed")
            logger.info(f"Results: {results}")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"Error during scheduled harvest: {e}", exc_info=True)

    def _safe_next_run_time(self, job):
        """Return next run time for a job when available."""
        return getattr(job, 'next_run_time', None)
    
    def start(self):
        """Start the scheduler."""
        if not self.is_enabled:
            logger.warning("Scheduler is disabled in configuration")
            return
        
        cron_expr = self.config.get('cron_expression', '0 2 * * *')
        
        try:
            cron_fields = self.parse_cron_expression(cron_expr)
            
            # Add the job to scheduler
            self.scheduler.add_job(
                self.scheduled_harvest,
                CronTrigger(**cron_fields),
                id='paper_harvest_job',
                name='Academic Paper Harvest',
                replace_existing=True
            )
            
            logger.info(f"Scheduler configured with cron expression: {cron_expr}")
            logger.info("Scheduled jobs:")
            for job in self.scheduler.get_jobs():
                logger.info(
                    f"  - {job.name} (ID: {job.id}) - Next run: {self._safe_next_run_time(job)}"
                )
            
            logger.info("Starting scheduler...")
            self.scheduler.start()
            
        except Exception as e:
            logger.error(f"Error starting scheduler: {e}", exc_info=True)
            raise
    
    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            logger.info("Stopping scheduler...")
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")
    
    def run_now(self):
        """Run harvest immediately without waiting for scheduled time."""
        logger.info("Running immediate harvest (bypassing schedule)")
        self.scheduled_harvest()
    
    def get_next_run_time(self):
        """Get the next scheduled run time."""
        jobs = self.scheduler.get_jobs()
        if jobs:
            return self._safe_next_run_time(jobs[0])
        return None
    
    def list_jobs(self):
        """List all scheduled jobs."""
        jobs = self.scheduler.get_jobs()
        return [(job.id, job.name, self._safe_next_run_time(job)) for job in jobs]
