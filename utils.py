#!/usr/bin/env python3
"""
Utility script for common Academic Paper Harvester operations.
"""

import argparse
import yaml
import json
from pathlib import Path
import sys


def view_paper(paper_id: str, source: str = None):
    """View details of a specific paper."""
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    storage = config.get('storage', {})
    root_dir = Path(storage.get('root_directory', './source'))
    subdirs = storage.get('subdirectories', {})
    
    # Search for paper
    search_dirs = []
    if source:
        subdir = subdirs.get(source)
        if subdir:
            search_dirs.append(root_dir / subdir)
    else:
        # Search all directories
        for subdir in subdirs.values():
            search_dirs.append(root_dir / subdir)
    
    found = False
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        
        # Try exact match
        paper_file = search_dir / f"{paper_id}.json"
        if paper_file.exists():
            with open(paper_file, 'r') as f:
                paper_data = json.load(f)
            
            print(f"\n{'='*80}")
            print(f"Paper found in: {search_dir.name}")
            print(f"{'='*80}")
            print(f"\nTitle: {paper_data['metadata'].get('title')}")
            print(f"Authors: {paper_data['metadata'].get('authors')}")
            print(f"Published: {paper_data['metadata'].get('published_date')}")
            print(f"Paper ID: {paper_data['metadata'].get('paper_id')}")
            print(f"Categories: {', '.join(paper_data['metadata'].get('categories', []))}")
            print(f"URL: {paper_data['metadata'].get('url')}")
            print(f"\nAbstract:\n{paper_data['metadata'].get('abstract', 'N/A')}")
            print(f"\nHarvested at: {paper_data.get('harvested_at')}")
            print(f"{'='*80}\n")
            found = True
            break
        
        # Try fuzzy match (contains paper_id)
        for paper_file in search_dir.glob('*.json'):
            if paper_id in paper_file.stem:
                with open(paper_file, 'r') as f:
                    paper_data = json.load(f)
                
                print(f"\n{'='*80}")
                print(f"Paper found (fuzzy match) in: {search_dir.name}")
                print(f"Filename: {paper_file.name}")
                print(f"{'='*80}")
                print(f"\nTitle: {paper_data['metadata'].get('title')}")
                print(f"Authors: {paper_data['metadata'].get('authors')}")
                print(f"Published: {paper_data['metadata'].get('published_date')}")
                print(f"Paper ID: {paper_data['metadata'].get('paper_id')}")
                print(f"Categories: {', '.join(paper_data['metadata'].get('categories', []))}")
                print(f"URL: {paper_data['metadata'].get('url')}")
                print(f"\nAbstract:\n{paper_data['metadata'].get('abstract', 'N/A')}")
                print(f"\nHarvested at: {paper_data.get('harvested_at')}")
                print(f"{'='*80}\n")
                found = True
                break
        
        if found:
            break
    
    if not found:
        print(f"Paper with ID '{paper_id}' not found.")


def list_papers(source: str = None, limit: int = 10):
    """List harvested papers."""
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    storage = config.get('storage', {})
    root_dir = Path(storage.get('root_directory', './source'))
    subdirs = storage.get('subdirectories', {})
    
    sources_to_check = [source] if source else list(subdirs.keys())
    
    for src in sources_to_check:
        subdir = subdirs.get(src)
        if not subdir:
            continue
        
        paper_dir = root_dir / subdir
        if not paper_dir.exists():
            continue
        
        paper_files = list(paper_dir.glob('*.json'))
        
        print(f"\n{'='*80}")
        print(f"Source: {src}")
        print(f"Total papers: {len(paper_files)}")
        print(f"{'='*80}")
        
        for i, paper_file in enumerate(sorted(paper_files, reverse=True)[:limit]):
            with open(paper_file, 'r') as f:
                paper_data = json.load(f)
            
            metadata = paper_data.get('metadata', {})
            print(f"\n{i+1}. {metadata.get('title', 'N/A')}")
            print(f"   ID: {metadata.get('paper_id', 'N/A')}")
            print(f"   Authors: {metadata.get('authors', 'N/A')}")
            print(f"   Published: {metadata.get('published_date', 'N/A')}")
        
        if len(paper_files) > limit:
            print(f"\n... and {len(paper_files) - limit} more papers")


def export_metadata(source: str = None, output_file: str = 'papers_export.json'):
    """Export paper metadata to JSON file."""
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    storage = config.get('storage', {})
    root_dir = Path(storage.get('root_directory', './source'))
    subdirs = storage.get('subdirectories', {})
    
    sources_to_export = [source] if source else list(subdirs.keys())
    
    all_papers = []
    
    for src in sources_to_export:
        subdir = subdirs.get(src)
        if not subdir:
            continue
        
        paper_dir = root_dir / subdir
        if not paper_dir.exists():
            continue
        
        for paper_file in paper_dir.glob('*.json'):
            with open(paper_file, 'r') as f:
                paper_data = json.load(f)
            
            all_papers.append({
                'source': src,
                'metadata': paper_data.get('metadata', {}),
                'harvested_at': paper_data.get('harvested_at')
            })
    
    with open(output_file, 'w') as f:
        json.dump(all_papers, f, indent=2, ensure_ascii=False)
    
    print(f"Exported {len(all_papers)} papers to {output_file}")


def clean_duplicates():
    """Find and report potential duplicate papers."""
    print("Scanning for duplicates...")
    
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    storage = config.get('storage', {})
    root_dir = Path(storage.get('root_directory', './source'))
    subdirs = storage.get('subdirectories', {})
    
    # Collect all papers by title hash
    papers_by_title = {}
    
    for src, subdir in subdirs.items():
        paper_dir = root_dir / subdir
        if not paper_dir.exists():
            continue
        
        for paper_file in paper_dir.glob('*.json'):
            with open(paper_file, 'r') as f:
                paper_data = json.load(f)
            
            title = paper_data.get('metadata', {}).get('title', '').lower().strip()
            if not title:
                continue
            
            if title not in papers_by_title:
                papers_by_title[title] = []
            
            papers_by_title[title].append({
                'source': src,
                'file': str(paper_file),
                'paper_id': paper_data.get('metadata', {}).get('paper_id'),
                'published_date': paper_data.get('metadata', {}).get('published_date')
            })
    
    # Find duplicates
    duplicates = {title: papers for title, papers in papers_by_title.items() if len(papers) > 1}
    
    if not duplicates:
        print("No duplicate papers found.")
        return
    
    print(f"\nFound {len(duplicates)} potential duplicates:")
    
    for i, (title, papers) in enumerate(duplicates.items(), 1):
        print(f"\n{i}. {title}")
        for paper in papers:
            print(f"   - Source: {paper['source']}, ID: {paper['paper_id']}, Published: {paper['published_date']}")


def main():
    parser = argparse.ArgumentParser(
        description='Utility script for Academic Paper Harvester',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # View command
    view_parser = subparsers.add_parser('view', help='View details of a specific paper')
    view_parser.add_argument('paper_id', help='Paper ID to view')
    view_parser.add_argument('--source', help='Source name (arxiv, semantic_scholar, s2orc)')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List harvested papers')
    list_parser.add_argument('--source', help='Filter by source')
    list_parser.add_argument('--limit', type=int, default=10, help='Number of papers to show')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export paper metadata to JSON')
    export_parser.add_argument('--source', help='Filter by source')
    export_parser.add_argument('--output', default='papers_export.json', help='Output file')
    
    # Clean command
    subparsers.add_parser('clean', help='Find and report duplicate papers')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == 'view':
        view_paper(args.paper_id, args.source)
    elif args.command == 'list':
        list_papers(args.source, args.limit)
    elif args.command == 'export':
        export_metadata(args.source, args.output)
    elif args.command == 'clean':
        clean_duplicates()


if __name__ == '__main__':
    main()
