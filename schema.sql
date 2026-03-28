-- Database schema for academic paper harvesting system

CREATE TABLE IF NOT EXISTS harvested_papers (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50) NOT NULL,
    paper_id VARCHAR(255) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    title TEXT,
    authors TEXT,
    published_date DATE,
    updated_datetime TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    file_path TEXT,
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, paper_id, version)
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_source ON harvested_papers(source);
CREATE INDEX IF NOT EXISTS idx_paper_id ON harvested_papers(paper_id);
CREATE INDEX IF NOT EXISTS idx_content_hash ON harvested_papers(content_hash);
CREATE INDEX IF NOT EXISTS idx_status ON harvested_papers(status);
CREATE INDEX IF NOT EXISTS idx_published_date ON harvested_papers(published_date);
CREATE INDEX IF NOT EXISTS idx_updated_datetime ON harvested_papers(updated_datetime);

-- Create a composite index for common queries
CREATE INDEX IF NOT EXISTS idx_source_paper_id ON harvested_papers(source, paper_id);

COMMENT ON TABLE harvested_papers IS 'Stores metadata and tracking information for harvested academic papers';
COMMENT ON COLUMN harvested_papers.source IS 'Source of the paper (arxiv, semantic_scholar, s2orc)';
COMMENT ON COLUMN harvested_papers.paper_id IS 'Unique identifier from the source system';
COMMENT ON COLUMN harvested_papers.content_hash IS 'SHA-256 hash of the paper content for deduplication';
COMMENT ON COLUMN harvested_papers.version IS 'Version number for tracking updates to the same paper';
COMMENT ON COLUMN harvested_papers.status IS 'Status of the paper record (active, archived, deleted, error)';
COMMENT ON COLUMN harvested_papers.file_path IS 'Local file system path where the paper is stored';
COMMENT ON COLUMN harvested_papers.metadata IS 'Additional metadata in JSON format';
