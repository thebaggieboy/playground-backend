#!/usr/bin/env python3
"""
Django Migration Cleaner Script
Removes all migration files except __init__.py from Django apps

Usage:
    python clean_migrations.py [--dry-run] [--apps app1,app2,...]

Options:
    --dry-run       Show what would be deleted without actually deleting
    --apps          Comma-separated list of specific apps to clean (optional)
    --help          Show this help message

Examples:
    python clean_migrations.py --dry-run
    python clean_migrations.py --apps myapp,otherapp
    python clean_migrations.py
"""

import os
import sys
import argparse
from pathlib import Path


def find_migration_files(project_root, specific_apps=None):
    """
    Find all migration files in Django apps
    
    Args:
        project_root (str): Path to Django project root
        specific_apps (list): List of specific app names to target (optional)
    
    Returns:
        list: List of migration file paths to delete
    """
    migration_files = []
    
    # Look for Django apps (directories containing models.py or apps.py)
    for item in os.listdir(project_root):
        item_path = os.path.join(project_root, item)
        
        # Skip if not a directory
        if not os.path.isdir(item_path):
            continue
            
        # Skip common non-app directories
        if item in ['venv', 'env', '.git', '__pycache__', '.vscode', 'static', 'media', 'templates']:
            continue
            
        # If specific apps are specified, only process those
        if specific_apps and item not in specific_apps:
            continue
            
        # Check if this looks like a Django app
        has_models = os.path.exists(os.path.join(item_path, 'models.py'))
        has_apps = os.path.exists(os.path.join(item_path, 'apps.py'))
        has_migrations = os.path.exists(os.path.join(item_path, 'migrations'))
        
        if (has_models or has_apps) and has_migrations:
            migrations_dir = os.path.join(item_path, 'migrations')
            
            # Find all .py files in migrations directory except __init__.py
            for migration_file in os.listdir(migrations_dir):
                if migration_file.endswith('.py') and migration_file != '__init__.py':
                    migration_path = os.path.join(migrations_dir, migration_file)
                    migration_files.append(migration_path)
                    
    return migration_files


def delete_migration_files(migration_files, dry_run=False):
    """
    Delete migration files
    
    Args:
        migration_files (list): List of file paths to delete
        dry_run (bool): If True, only show what would be deleted
    """
    if not migration_files:
        print("✅ No migration files found to delete.")
        return
        
    print(f"Found {len(migration_files)} migration files:")
    print("-" * 50)
    
    # Group files by app for better display
    files_by_app = {}
    for file_path in migration_files:
        app_name = os.path.basename(os.path.dirname(os.path.dirname(file_path)))
        if app_name not in files_by_app:
            files_by_app[app_name] = []
        files_by_app[app_name].append(os.path.basename(file_path))
    
    for app_name, files in files_by_app.items():
        print(f"\n📁 {app_name}/migrations/:")
        for file in sorted(files):
            print(f"   - {file}")
    
    print("-" * 50)
    
    if dry_run:
        print("🔍 DRY RUN: No files were actually deleted.")
        print("Run without --dry-run to actually delete these files.")
        return
    
    # Confirm deletion
    confirm = input("\n⚠️  Are you sure you want to delete these files? (y/N): ").lower().strip()
    if confirm not in ['y', 'yes']:
        print("❌ Operation cancelled.")
        return
    
    # Delete files
    deleted_count = 0
    failed_count = 0
    
    for file_path in migration_files:
        try:
            os.remove(file_path)
            deleted_count += 1
            print(f"✅ Deleted: {file_path}")
        except Exception as e:
            failed_count += 1
            print(f"❌ Failed to delete {file_path}: {str(e)}")
    
    print(f"\n📊 Summary:")
    print(f"   ✅ Successfully deleted: {deleted_count} files")
    if failed_count > 0:
        print(f"   ❌ Failed to delete: {failed_count} files")
    
    if deleted_count > 0:
        print(f"\n💡 Don't forget to:")
        print(f"   1. Run 'python manage.py makemigrations' to create new initial migrations")
        print(f"   2. Run 'python manage.py migrate' to apply them")


def main():
    parser = argparse.ArgumentParser(
        description="Remove Django migration files (except __init__.py)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python clean_migrations.py --dry-run
  python clean_migrations.py --apps myapp,otherapp
  python clean_migrations.py
        """
    )
    
    parser.add_argument(
        '--dry-run', 
        action='store_true', 
        help='Show what would be deleted without actually deleting'
    )
    
    parser.add_argument(
        '--apps', 
        type=str, 
        help='Comma-separated list of specific apps to clean (e.g., myapp,otherapp)'
    )
    
    args = parser.parse_args()
    
    # Get project root (current directory)
    project_root = os.getcwd()
    
    # Check if this looks like a Django project
    if not os.path.exists(os.path.join(project_root, 'manage.py')):
        print("❌ Error: This doesn't appear to be a Django project root.")
        print("   Make sure you're running this script from the directory containing manage.py")
        sys.exit(1)
    
    # Parse specific apps if provided
    specific_apps = None
    if args.apps:
        specific_apps = [app.strip() for app in args.apps.split(',')]
        print(f"🎯 Targeting specific apps: {', '.join(specific_apps)}")
    
    print(f"🔍 Searching for migration files in: {project_root}")
    
    # Find migration files
    migration_files = find_migration_files(project_root, specific_apps)
    
    # Delete or show files
    delete_migration_files(migration_files, args.dry_run)


if __name__ == "__main__":
    main()