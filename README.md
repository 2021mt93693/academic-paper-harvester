# Academic Paper Harvester

A robust, scalable system for harvesting academic papers from multiple sources with scheduling, filtering, and database tracking capabilities.

## Features

- **Multiple Sources**: ArXiv (Computer science and related fields), Semantic Scholar (Cross-disciplinary coverage), and S2ORC (Large-scale corpus support)
- **Cron-Based Scheduling**: Automated harvesting on configurable schedules
- **Flexible Filtering**: Filter by year, language, subject areas, and more
- **Source Control**: Enable/disable individual sources as needed
- **Database Tracking**: PostgreSQL-based tracking with content hashing
- **Deduplication**: Automatic detection of duplicate papers via SHA-256 hashing
- **Version Tracking**: Maintains version history when papers are updated
- **Organized Storage**: Papers stored in source-specific directories
- **Comprehensive Logging**: Detailed logs for monitoring and debugging

## System Requirements

- Python 3.12+
- PostgreSQL 12+
- 2GB+ RAM recommended
- Network access to academic APIs

## Project Structure

```
academic-paper-harvester/
├── main.py                               # Main entry point
├── config.yaml                           # Configuration
├── schema.sql                            # Database schema
├── requirements.txt                      # Dependencies
├── setup.sh                              # Setup script
├── test_installation.py                  # Verification
├── utils.py                              # Utilities
├── README.md                             # Full documentation
├── QUICKSTART.md                         # Quick start guide
├── STRUCTURE.md                          # Project structure details
├── EXAMPLES.md                           # Usage examples
└── source/
    ├── __init__.py
    ├── harvest_manager.py                # Coordinator
    ├── database/
    │   └── db_manager.py                 # PostgreSQL manager
    ├── harvesters/
    │   ├── base_harvester.py             # Abstract base
    │   ├── arxiv_harvester.py            # ArXiv impl
    │   ├── semantic_scholar_harvester.py #Semantic Scholar impl
    │   └── s2orc_harvester.py
    └── scheduler/
        └── harvest_scheduler.py          # Cron scheduler
```

## Usage

### Setup Project
Run the following setup script.

```bash
sh setup.sh
```

### Edit config.yaml
Edit this file according to your requirements. Refer the Configuration guide below to get an overview.

### Initialize Database

Either run the sql commands from schema.sql for creation of tables and indexes. Or initialize schema using following commands.

```bash
python main.py --init-db
```

### Run Immediate Harvest

Harvest from all enabled sources:
```bash
python main.py --now
```

Harvest from specific sources:
```bash
python main.py --now --sources arxiv semantic_scholar
```

### Start Scheduled Harvester

```bash
python main.py --schedule
```

Press `Ctrl+C` to stop the scheduler.

### Check System Status

```bash
python main.py --status
```

### View Help

```bash
python main.py --help
```

### Utilities
```bash
# View paper
python utils.py view 2301.12345

# List papers
python utils.py list --source arxiv --limit 20

# Export to JSON
python utils.py export --output papers.json

# Find duplicates
python utils.py clean
```

## Testing & Verification

```bash
# Run verification
python test_installation.py

# Checks:
✓ Python version (3.12+)
✓ Dependencies installed
✓ Configuration valid
✓ Database connection
✓ Schema initialized
✓ Storage directories
```

## Automation Examples

### Systemd Service (Linux)

Create `/etc/systemd/system/paper-harvester.service`:

```ini
[Unit]
Description=Academic Paper Harvester
After=network.target postgresql.service

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/academic-paper-harvester
ExecStart=/path/to/academic-paper-harvester/venv/bin/python main.py --schedule
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable paper-harvester
sudo systemctl start paper-harvester
sudo systemctl status paper-harvester
```

View logs:

```bash
sudo journalctl -u paper-harvester -f
```

### Cron Job (Alternative to Built-in Scheduler)

```bash
# Edit crontab
crontab -e

# Add entry (runs daily at 2 AM)
0 2 * * * cd /path/to/academic-paper-harvester && /path/to/venv/bin/python main.py --now >> /path/to/cron.log 2>&1
```

### Docker Container (Example Dockerfile)

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install PostgreSQL client
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create storage directories
RUN mkdir -p source/arxiv_papers source/semantic_scholar_papers source/s2orc_papers

# Run the application
CMD ["python", "main.py", "--schedule"]
```

Build and run:

```bash
docker build -t paper-harvester .
docker run -d --name harvester \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -v $(pwd)/source:/app/source \
  paper-harvester
```

### Monitoring Script

Create `monitor.sh`:

```bash
#!/bin/bash

# Check if harvester is running
if pgrep -f "main.py --schedule" > /dev/null; then
    echo "Harvester is running"
else
    echo "Harvester is NOT running!"
    # Optionally restart or send alert
fi

# Check disk space
USAGE=$(df -h /path/to/source | awk 'NR==2 {print $5}' | sed 's/%//')
if [ $USAGE -gt 80 ]; then
    echo "WARNING: Disk usage is at ${USAGE}%"
fi

# Check log for errors
ERROR_COUNT=$(tail -n 100 harvester.log | grep -c "ERROR")
if [ $ERROR_COUNT -gt 0 ]; then
    echo "WARNING: Found $ERROR_COUNT errors in recent logs"
fi

# Display statistics
python main.py --status
```

Run periodically:

```bash
# Add to crontab
0 */6 * * * /path/to/monitor.sh | mail -s "Harvester Status" admin@example.com
```

## Advanced Examples

### Custom Filter Extension

Create `custom_filters.py`:

```python
from source.harvesters.arxiv_harvester import ArxivHarvester

class CustomArxivHarvester(ArxivHarvester):
    def apply_filters(self, paper):
        # Call parent filter first
        if not super().apply_filters(paper):
            return False
        
        # Custom filter: Only papers with "neural" in title
        title = paper.get('title', '').lower()
        if 'neural' not in title:
            return False
        
        # Custom filter: Minimum abstract length
        abstract = paper.get('abstract', '')
        if len(abstract) < 200:
            return False
        
        return True
```

### Parallel Source Harvesting

```python
from concurrent.futures import ThreadPoolExecutor
from source.harvest_manager import HarvestManager

def harvest_source(source_name, harvest_manager):
    return harvest_manager.run_harvest([source_name])

# In your custom script
harvest_manager = HarvestManager(config, db_manager)
sources = harvest_manager.get_enabled_sources()

with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(harvest_source, source, harvest_manager) 
               for source in sources]
    results = [f.result() for f in futures]
```

### Integration with Data Analysis Pipeline

```python
import pandas as pd
import json
from pathlib import Path

# Load all papers into DataFrame
papers = []
for paper_file in Path('source/arxiv_papers').glob('*.json'):
    with open(paper_file) as f:
        data = json.load(f)
        papers.append(data['metadata'])

df = pd.DataFrame(papers)

# Analyze
print(df['published_year'].value_counts())
print(df['categories'].value_counts())

# Export to CSV
df.to_csv('papers_analysis.csv', index=False)
```

## Configuration Guide

### Database Configuration

```yaml
database:
  host: localhost         # PostgreSQL host
  port: 5432              # PostgreSQL port
  dbname: academic_papers # Database name
  user: postgres          # Database user
  password: your_password # Database password
```

### Source Configuration

Each source has the following structure:

```yaml
source_name:
  enabled: true/false          # Enable/disable this source
  base_url: "..."              # API endpoint (optional)
  api_key: "..."               # API key if required (optional)
  filters:
    start_year: 2023           # Filter papers from this year
    end_year: 2024             # Filter papers until this year
    max_results: 100           # Maximum papers to fetch per harvest
    language: en               # Language filter (optional)
    categories: [...]          # Source-specific categories
```

### ArXiv-Specific Filters

```yaml
arxiv:
  filters:
    categories:
      - cs.AI      # Artificial Intelligence
      - cs.LG      # Machine Learning
      - cs.CL      # Computation and Language
      - cs.CV      # Computer Vision
      - cs.NE      # Neural and Evolutionary Computing
```

Common ArXiv categories:
- `cs.*`: Computer Science
- `math.*`: Mathematics
- `physics.*`: Physics
- `stat.*`: Statistics

### Semantic Scholar Filters

```yaml
semantic_scholar:
  filters:
    fields_of_study:
      - Computer Science
      - Artificial Intelligence
      - Machine Learning
      - Natural Language Processing
```

### Scheduler Configuration

```yaml
scheduler:
  enabled: true                # Enable/disable scheduling
  cron_expression: "0 2 * * *" # Cron format: min hour day month dow
```

Cron expression format:
```
* * * * *
│ │ │ │ │
│ │ │ │ └─── Day of week (0-6, 0=Sunday)
│ │ │ └───── Month (1-12)
│ │ └─────── Day of month (1-31)
│ └───────── Hour (0-23)
└─────────── Minute (0-59)
```

Common schedules:
- `0 2 * * *` - Daily at 2 AM
- `0 */6 * * *` - Every 6 hours
- `0 0 * * 0` - Weekly on Sunday at midnight
- `0 0 1 * *` - Monthly on the 1st at midnight

### Storage Configuration

```yaml
storage:
  root_directory: ../data/harvested
  subdirectories:
    arxiv: arxiv_papers
    semantic_scholar: semantic_scholar_papers
    s2orc: s2orc_papers
```

Papers will be stored in JSON format:
```
../data/harvested/
├── arxiv_papers/
│   ├── 2301.12345.json
│   └── 2302.67890.json
├── semantic_scholar_papers/
│   └── abc123def456.json
└── s2orc_papers/
    └── s2orc_xyz789.json
```

### Log Configuration

```yaml
logging:
  level: INFO          # DEBUG, INFO, WARNING, ERROR, CRITICAL
  file: harvester.log  # Log file path
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

## Database Schema

The system creates a `harvested_papers` table with the following structure:

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| source | VARCHAR(50) | Source name (arxiv, semantic_scholar, s2orc) |
| paper_id | VARCHAR(255) | Source-specific paper identifier |
| content_hash | VARCHAR(64) | SHA-256 hash for deduplication |
| title | TEXT | Paper title |
| authors | TEXT | Comma-separated author names |
| published_date | DATE | Publication date |
| updated_datetime | TIMESTAMP | Last update timestamp |
| version | INTEGER | Version number (for tracking updates) |
| status | VARCHAR(20) | Status (active, archived, deleted, error) |
| file_path | TEXT | Local file path |
| metadata | JSONB | Additional metadata |
| created_at | TIMESTAMP | Record creation time |

## File Format

Each harvested paper is stored as a JSON file:

```json
{
  "metadata": {
    "paper_id": "2301.12345",
    "title": "Example Paper Title",
    "authors": "John Doe, Jane Smith",
    "abstract": "This paper presents...",
    "published_date": "2023-01-15",
    "categories": ["cs.AI", "cs.LG"],
    "url": "https://arxiv.org/abs/2301.12345"
  },
  "content": "{...}",
  "harvested_at": "2024-02-24T10:30:00"
}
```

## Data Flow

```
1. Scheduler triggers → 2. HarvestManager → 3. Individual Harvesters
                                                    ↓
4. API Requests ← 5. Parse & Filter ← 6. Save to Disk
        ↓
7. Compute Hash → 8. Check DB for Duplicates → 9. Insert/Update DB
```


## Filtering Mechanism

The system applies filters at multiple stages:

1. **API Query Filters**: Filters applied when querying the API (year, categories)
2. **Post-Fetch Filters**: Additional filters applied after fetching (language, custom rules)
3. **Deduplication**: Content hashing to prevent duplicate storage

### Deduplication
- SHA-256 hash of paper content
- Checks before insertion
- Version increment on updates
- Prevents duplicate storage

### Error Handling
- Try-catch blocks throughout
- Logging at all levels
- Graceful degradation
- Connection retry logic

### Rate Limiting
- ArXiv: 3 second delay between requests
- Semantic Scholar: 1 second delay
- Respectful API usage
- API key support for higher limits

## Monitoring and Logs

Logs are written to `harvester.log` by default. Configure in `config.yaml`.

## Troubleshooting

### Connection Issues

**Problem**: Cannot connect to PostgreSQL
```
Solution: Check database credentials in config.yaml
         Verify PostgreSQL is running: sudo systemctl status postgresql
         Check PostgreSQL allows connections: pg_hba.conf
```

**Problem**: API rate limiting
```
Solution: For Semantic Scholar, add API key to config.yaml for higher limits
         The harvester retries HTTP 429 responses with backoff automatically
         Reduce max_results if you are still running into sustained throttling
```

### Data Issues

**Problem**: Papers not being saved
```
Solution: Check file permissions on storage directories
         Verify disk space: df -h
         Review logs for error messages
```

**Problem**: Duplicate papers in database
```
Solution: Content hashing should prevent this
         Check if paper content changed (version should increment)
         Verify database unique constraints are in place
```

## Performance Optimization

### For Large-Scale Harvesting

1. **Batch Processing**: Increase `max_results` but be mindful of API limits
2. **Parallel Harvesting**: Modify to use multiprocessing for different sources
3. **Database Indexing**: Indexes are pre-configured in schema.sql
4. **Storage**: Use SSD for better I/O performance
5. **API Keys**: Obtain API keys for higher rate limits

### Rate Limits

- **ArXiv**: 1 request per 3 seconds (implemented in code)
- **Semantic Scholar**: 100 requests per 5 minutes (free tier)
  - With API key: 5000 requests per 5 minutes

## Extending the System

### Adding a New Source

1. Create a new harvester class in `source/harvesters/`:

```python
from .base_harvester import BaseHarvester

class NewSourceHarvester(BaseHarvester):
    def fetch_papers(self) -> List[Dict[str, Any]]:
        # Implement API fetching
        pass
    
    def parse_paper(self, raw_data: Any) -> Dict[str, Any]:
        # Implement parsing logic
        pass
```

2. Register in `harvest_manager.py`:

```python
if sources_config.get('new_source', {}).get('enabled', False):
    self.harvesters['new_source'] = NewSourceHarvester(...)
```

3. Add configuration to `config.yaml`:

```yaml
sources:
  new_source:
    enabled: true
    filters:
      # Your filters
```

### Adding Custom Filters

You can extend the `apply_filters` method in `base_harvester.py`:

```python
def apply_filters(self, paper: Dict[str, Any]) -> bool:
    # Your custom filter logic
    if paper.get('citation_count', 0) < 10:
        return False
    return super().apply_filters(paper)
```

## API Documentation

### ArXiv API
- Documentation: https://arxiv.org/help/api/
- Rate limit: 1 request per 3 seconds
- No authentication required

### Semantic Scholar API
- Documentation: https://api.semanticscholar.org/
- Rate limits: See website for current limits
- API key: Optional but recommended

### S2ORC
- Information: https://allenai.org/data/s2orc
- Access: Bulk download or Semantic Scholar API
- Note: Full corpus is 8TB+ compressed

## Security Considerations

1. **Database Credentials**: Never commit `config.yaml` with real credentials
2. **API Keys**: Store securely, consider environment variables
3. **File Permissions**: Ensure proper permissions on storage directories
4. **Input Validation**: System validates and sanitizes all inputs
5. **SQL Injection**: Uses parameterized queries throughout

## Contributing

To contribute:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

[Your License Here]

## Support

For issues and questions:
- Check logs in `harvester.log`
- Review this documentation
- Open an issue on the project repository

## Changelog

### Version 1.0.0
- Initial release
- ArXiv, Semantic Scholar, and S2ORC support
- Cron-based scheduling
- PostgreSQL database integration
- Content deduplication
- Configurable filtering
