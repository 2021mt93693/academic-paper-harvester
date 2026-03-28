#!/usr/bin/env python3
"""
Test script to verify Academic Paper Harvester installation.
"""

import sys
import os
from pathlib import Path


def check_python_version():
    """Check if Python version is 3.12+"""
    print("Checking Python version...", end=" ")
    version = sys.version_info
    if version.major == 3 and version.minor >= 12:
        print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"✗ Python {version.major}.{version.minor}.{version.micro}")
        print(f"  Required: Python 3.12+")
        return False


def check_dependencies():
    """Check if required packages are installed"""
    print("\nChecking dependencies...")
    
    required_packages = [
        'requests',
        'psycopg2',
        'yaml',
        'apscheduler',
        'feedparser'
    ]
    
    missing = []
    for package in required_packages:
        try:
            if package == 'yaml':
                __import__('yaml')
            elif package == 'psycopg2':
                __import__('psycopg2')
            else:
                __import__(package)
            print(f"  ✓ {package}")
        except ImportError:
            print(f"  ✗ {package}")
            missing.append(package)
    
    if missing:
        print(f"\nMissing packages: {', '.join(missing)}")
        print("Install with: pip install -r requirements.txt")
        return False
    
    return True


def check_config_file():
    """Check if config file exists"""
    print("\nChecking configuration...")
    
    if Path('config.yaml').exists():
        print("  ✓ config.yaml exists")
        
        # Try to load it
        try:
            import yaml
            with open('config.yaml', 'r') as f:
                config = yaml.safe_load(f)
            
            # Check if password is set
            password = config.get('database', {}).get('password', '')
            if password == 'your_password_here' or password == 'CHANGE_THIS_PASSWORD':
                print("  ⚠ Database password not configured in config.yaml")
                return False
            else:
                print("  ✓ Database password configured")
            
            # Check if at least one source is enabled
            sources = config.get('sources', {})
            enabled_sources = [name for name, cfg in sources.items() if cfg.get('enabled', False)]
            
            if enabled_sources:
                print(f"  ✓ Enabled sources: {', '.join(enabled_sources)}")
            else:
                print("  ⚠ No sources enabled")
                return False
            
            return True
            
        except Exception as e:
            print(f"  ✗ Error loading config.yaml: {e}")
            return False
    else:
        print("  ✗ config.yaml not found")
        print("  Run: cp config.template.yaml config.yaml")
        return False


def check_database_connection():
    """Check if database connection works"""
    print("\nChecking database connection...")
    
    try:
        import yaml
        import psycopg2
        
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        db_config = config.get('database', {})
        
        conn = psycopg2.connect(
            host=db_config.get('host', 'localhost'),
            port=db_config.get('port', 5432),
            dbname=db_config.get('dbname', 'academic_papers'),
            user=db_config.get('user', 'postgres'),
            password=db_config.get('password', '')
        )
        
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        
        print(f"  ✓ Database connection successful")
        print(f"  PostgreSQL version: {version.split(',')[0]}")
        
        # Check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'harvested_papers'
            );
        """)
        table_exists = cursor.fetchone()[0]
        
        if table_exists:
            print("  ✓ harvested_papers table exists")
            
            # Check row count
            cursor.execute("SELECT COUNT(*) FROM harvested_papers;")
            count = cursor.fetchone()[0]
            print(f"  Papers in database: {count}")
        else:
            print("  ⚠ harvested_papers table not found")
            print("  Run: python main.py --init-db")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"  ✗ Database connection failed: {e}")
        return False


def check_storage_directories():
    """Check if storage directories exist"""
    print("\nChecking storage directories...")
    
    try:
        import yaml
        
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        storage = config.get('storage', {})
        root_dir = storage.get('root_directory', '../data/harvested')
        subdirs = storage.get('subdirectories', {})
        
        if Path(root_dir).exists():
            print(f"  ✓ Root directory exists: {root_dir}")
        else:
            print(f"  ⚠ Root directory not found: {root_dir}")
            Path(root_dir).mkdir(parents=True, exist_ok=True)
            print(f"  Created: {root_dir}")
        
        for source, subdir in subdirs.items():
            full_path = Path(root_dir) / subdir
            if full_path.exists():
                # Count files
                json_files = list(full_path.glob('*.json'))
                print(f"  ✓ {source}: {full_path} ({len(json_files)} papers)")
            else:
                print(f"  ⚠ {source}: {full_path} not found")
                full_path.mkdir(parents=True, exist_ok=True)
                print(f"  Created: {full_path}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Error checking directories: {e}")
        return False


def check_schema_file():
    """Check if schema.sql exists"""
    print("\nChecking schema file...")
    
    if Path('schema.sql').exists():
        print("  ✓ schema.sql exists")
        return True
    else:
        print("  ✗ schema.sql not found")
        return False


def main():
    """Run all checks"""
    print("=" * 60)
    print("Academic Paper Harvester - Installation Verification")
    print("=" * 60)
    
    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("Configuration", check_config_file),
        ("Schema File", check_schema_file),
        ("Storage Directories", check_storage_directories),
        ("Database Connection", check_database_connection),
    ]
    
    results = []
    
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ Unexpected error in {name}: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 All checks passed! You're ready to start harvesting.")
        print("\nNext steps:")
        print("  1. Run a test harvest: python main.py --now --sources arxiv")
        print("  2. Check status: python main.py --status")
        print("  3. Start scheduler: python main.py --schedule")
    else:
        print("\n⚠ Some checks failed. Please address the issues above.")
        print("Refer to QUICKSTART.md or README.md for help.")
    
    print("=" * 60)
    
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
