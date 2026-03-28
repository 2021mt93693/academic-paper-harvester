#!/bin/bash
# Setup script for Academic Paper Harvester

set -e  # Exit on error

echo "=========================================="
echo "Academic Paper Harvester - Setup"
echo "=========================================="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Found Python $python_version"

# Create virtual environment
echo ""
echo "Creating virtual environment..."
if [ -d "venv" ]; then
    echo "Virtual environment already exists. Skipping..."
else
    python3 -m venv venv
    echo "Virtual environment created."
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Copy configuration template if config.yaml doesn't exist
echo ""
if [ -f "config.yaml" ]; then
    echo "config.yaml already exists. Skipping template copy..."
else
    echo "Creating config.yaml from template..."
    cp config.template.yaml config.yaml
    echo "⚠️  IMPORTANT: Edit config.yaml and set your database password!"
fi

# Create necessary directories
echo ""
echo "Creating storage directories..."
mkdir -p ../data/harvested/arxiv_papers
mkdir -p ../data/harvested/semantic_scholar_papers
mkdir -p ../data/harvested/s2orc_papers
echo "Directories created."

# Database setup instructions
echo ""
echo "=========================================="
echo "Next Steps:"
echo "=========================================="
echo ""
echo "1. Configure PostgreSQL:"
echo "   sudo -u postgres psql"
echo "   CREATE DATABASE academic_papers;"
echo "   \\q"
echo ""
echo "2. Edit config.yaml and set your database credentials"
echo ""
echo "3. Initialize the database schema:"
echo "   python main.py --init-db"
echo ""
echo "4. Run your first harvest:"
echo "   python main.py --now"
echo ""
echo "5. Or start the scheduler:"
echo "   python main.py --schedule"
echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
