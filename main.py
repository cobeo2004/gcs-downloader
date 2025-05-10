#!/usr/bin/env python3
import sys
import subprocess
import importlib.util

# Check if required packages are installed
def check_package(package_name):
    spec = importlib.util.find_spec(package_name)
    if spec is None:
        print(f"Package {package_name} not found. Installing...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
            print(f"Successfully installed {package_name}")
            return True
        except subprocess.CalledProcessError:
            print(f"Failed to install {package_name}")
            return False
    return True

# Check for required packages
required_packages = ["tqdm"]
for package in required_packages:
    if not check_package(package):
        sys.exit(1)

import argparse
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import re

# Maximum number of parallel downloads
MAX_PARALLEL_DOWNLOADS = 16
# Maximum number of threads for a single download
MAX_THREADS_PER_DOWNLOAD = 8

def get_size_of_object(bucket_path):
    """Get the size of a single object or total size of objects in a directory in GCS."""
    try:
        # Use gsutil du to get the size
        result = subprocess.run(
            ["gsutil", "-q", "du", "-s", bucket_path],
            capture_output=True,
            text=True,
            check=True
        )
        # Extract the size from the output (first value)
        size_str = result.stdout.strip().split()[0]
        return int(size_str)
    except subprocess.CalledProcessError:
        return 0

def list_objects(bucket_path):
    """List all objects in a bucket or bucket path."""
    try:
        result = subprocess.run(
            ["gsutil", "ls", bucket_path],
            capture_output=True,
            text=True,
            check=True
        )
        items = result.stdout.strip().split('\n')
        return [item for item in items if item]  # Filter out empty strings
    except subprocess.CalledProcessError as e:
        print(f"Error listing objects: {e}")
        return []

def download_with_progress(source, destination, total_size=None):
    """Download files with optimized performance and progress bar."""
    global MAX_THREADS_PER_DOWNLOAD
    # If total_size is not provided, try to get it
    if total_size is None:
        total_size = get_size_of_object(source)

    # Create progress bar
    progress_bar = tqdm(total=total_size, unit='B', unit_scale=True, desc=f"Downloading {os.path.basename(source)}")

    # Flag to signal download completion
    download_complete = threading.Event()

    # Monitor file size growth for progress updates
    def update_progress():
        previous_size = 0
        while not download_complete.is_set():
            try:
                # For folders we need a different approach
                if os.path.isdir(destination):
                    current_size = sum(os.path.getsize(os.path.join(dirpath, filename))
                                      for dirpath, _, filenames in os.walk(destination)
                                      for filename in filenames)
                else:
                    current_size = os.path.getsize(destination) if os.path.exists(destination) else 0

                # Update progress bar with the difference
                if current_size > previous_size:
                    progress_bar.update(current_size - previous_size)
                    previous_size = current_size

                # Prevent CPU overuse
                time.sleep(0.1)

            except OSError:
                # File might be being written to or not exist yet
                time.sleep(0.1)

    # Start progress monitoring in a separate thread
    progress_thread = threading.Thread(target=update_progress)
    progress_thread.daemon = True
    progress_thread.start()

    # Start download process with optimized parameters
    try:
        # Use -m for parallel composite uploads and downloads
        # Use -o for setting options to optimize performance
        process = subprocess.run(
            [
                "gsutil",
                "-m",
                "-o", f"GSUtil:parallel_thread_count={MAX_THREADS_PER_DOWNLOAD}",
                "-o", "GSUtil:parallel_process_count=1",  # Use threading instead of processes
                "-o", "GSUtil:sliced_object_download_threshold=64M",
                "-o", "GSUtil:sliced_object_download_max_components=8",
                "cp",
                "-r",  # Recursive
                "-n",  # Skip files that already exist
                source,
                destination
            ],
            check=True
        )
        success = True
    except subprocess.CalledProcessError:
        success = False

    # Signal download completion
    download_complete.set()

    # Wait for progress thread to finish updates
    progress_thread.join(timeout=1.0)

    # Close progress bar
    progress_bar.close()

    return success

def batch_download(items, destination, is_folders=False, max_workers=None):
    """Download multiple items in parallel batches."""
    global MAX_PARALLEL_DOWNLOADS
    if max_workers is None:
        max_workers = MAX_PARALLEL_DOWNLOADS

    total_items = len(items)
    print(f"Starting download of {total_items} {'folders' if is_folders else 'files'} in parallel")

    # Function to download a single item
    def download_item(item):
        if is_folders:
            # Create destination folder
            folder_name = os.path.basename(item.rstrip('/'))
            folder_dest = os.path.join(destination, folder_name)
            if not os.path.exists(folder_dest):
                os.makedirs(folder_dest)
            success = download_with_progress(item, folder_dest)
        else:
            # Download single file
            file_name = os.path.basename(item)
            file_dest = os.path.join(destination, file_name)
            success = download_with_progress(item, file_dest)

        return item, success

    # Use ThreadPoolExecutor to download in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(download_item, items))

    # Print results
    successful = [item for item, success in results if success]
    failed = [item for item, success in results if not success]

    if successful:
        print(f"Successfully downloaded {len(successful)} items")

    if failed:
        print(f"Failed to download {len(failed)} items:")
        for item in failed:
            print(f"  - {item}")

def check_gsutil_installed():
    """Check if gsutil is installed and available in PATH."""
    try:
        result = subprocess.run(["gsutil", "version"], capture_output=True, check=True)
        print(f"Using {result.stdout.decode().splitlines()[0].strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: gsutil is not installed or not in your PATH.")
        print("Please install the Google Cloud SDK and ensure gsutil is working.")
        print("Installation guide: https://cloud.google.com/sdk/docs/install")
        return False

def optimize_gsutil_config():
    """Apply performance optimizations to gsutil config."""
    global MAX_THREADS_PER_DOWNLOAD
    print("Applying gsutil performance optimizations...")
    try:
        # Check if boto config exists and has parallelism settings
        has_optimizations = False
        boto_config = os.path.expanduser("~/.boto")
        if os.path.exists(boto_config):
            with open(boto_config, 'r') as f:
                content = f.read()
                if "parallel_thread_count" in content:
                    has_optimizations = True

        # If optimizations don't exist, add them
        if not has_optimizations:
            subprocess.run([
                "gsutil",
                "config",
                "-o", f"GSUtil:parallel_thread_count={MAX_THREADS_PER_DOWNLOAD}",
                "-o", "GSUtil:parallel_process_count=1",
                "-o", "GSUtil:sliced_object_download_threshold=64M",
                "-o", "GSUtil:sliced_object_download_max_components=8",
                "-o", "GSUtil:use_magicfile=False"
            ], check=True)
            print("Applied performance optimizations to gsutil configuration")
    except Exception as e:
        print(f"Note: Could not optimize gsutil config: {e}")
        print("Downloads will still work but might not be at peak performance")

def get_default_destination():
    """Get the default destination (Canva folder)."""
    home_dir = os.path.expanduser("~")
    desktop_dir = os.path.join(home_dir, "Desktop/Canva")

    # Check if Desktop directory exists
    if os.path.isdir(desktop_dir):
        return desktop_dir
    return home_dir

def prompt_for_destination():
    """Prompt the user for a destination directory."""
    default_dest = get_default_destination()
    dest = input(f"Enter destination directory [default: {default_dest}]: ")

    if not dest:
        dest = default_dest

    # Expand user directory notation (e.g., ~)
    dest = os.path.expanduser(dest)

    # Create directory if it doesn't exist
    if not os.path.exists(dest):
        try:
            os.makedirs(dest)
            print(f"Created directory: {dest}")
        except OSError as e:
            print(f"Error creating directory {dest}: {e}")
            return None

    return dest

def interactive_download():
    """Interactive mode for downloading files/folders from GCS."""
    # Get bucket information
    bucket = input("Enter the GCS bucket name (e.g., gs://your-bucket): ")
    if not bucket.startswith("gs://"):
        bucket = f"gs://{bucket}"

    # List the contents of the bucket
    print(f"Listing contents of {bucket}...")
    items = list_objects(bucket)

    if not items:
        print("No items found in the bucket or bucket does not exist.")
        return

    # Display bucket contents
    print("\nBucket contents:")
    for i, item in enumerate(items, 1):
        print(f"{i}. {item}")

    # Ask user what they want to download
    print("\nWhat would you like to download?")
    print("1. Single file")
    print("2. Multiple files")
    print("3. Single folder")
    print("4. Multiple folders")
    print("5. Everything in this bucket")

    choice = input("Enter your choice (1-5): ")

    # Get destination
    destination = prompt_for_destination()
    if not destination:
        return

    # Process based on user choice
    if choice == "1":
        # Single file
        file_index = int(input("Enter the number of the file to download: ")) - 1
        if 0 <= file_index < len(items):
            file_path = items[file_index]
            file_name = os.path.basename(file_path)
            file_dest = os.path.join(destination, file_name)
            download_with_progress(file_path, file_dest)
        else:
            print("Invalid file selection.")

    elif choice == "2":
        # Multiple files
        indices = input("Enter the numbers of files to download (comma-separated): ")
        try:
            indices = [int(idx.strip()) - 1 for idx in indices.split(",")]
            files_to_download = [items[idx] for idx in indices if 0 <= idx < len(items)]
            if files_to_download:
                batch_download(files_to_download, destination, is_folders=False)
            else:
                print("No valid files selected.")
        except ValueError:
            print("Invalid input. Please enter comma-separated numbers.")

    elif choice == "3":
        # Single folder
        folder_index = int(input("Enter the number of the folder to download: ")) - 1
        if 0 <= folder_index < len(items):
            folder_path = items[folder_index]
            folder_name = os.path.basename(folder_path.rstrip('/'))
            folder_dest = os.path.join(destination, folder_name)

            if not os.path.exists(folder_dest):
                os.makedirs(folder_dest)

            download_with_progress(folder_path, folder_dest)
        else:
            print("Invalid folder selection.")

    elif choice == "4":
        # Multiple folders
        indices = input("Enter the numbers of folders to download (comma-separated): ")
        try:
            indices = [int(idx.strip()) - 1 for idx in indices.split(",")]
            folders_to_download = [items[idx] for idx in indices if 0 <= idx < len(items)]
            if folders_to_download:
                batch_download(folders_to_download, destination, is_folders=True)
            else:
                print("No valid folders selected.")
        except ValueError:
            print("Invalid input. Please enter comma-separated numbers.")

    elif choice == "5":
        # Everything in bucket
        print(f"Downloading everything from {bucket} to {destination}")
        # For efficiency, download the entire bucket with a single command
        download_with_progress(bucket, destination)

    else:
        print("Invalid choice. Please run the program again and select a valid option.")

def main():
    global MAX_PARALLEL_DOWNLOADS, MAX_THREADS_PER_DOWNLOAD
    """Main function to run the GCS downloader CLI."""
    parser = argparse.ArgumentParser(description="High-performance download tool for Google Cloud Storage")
    parser.add_argument("--bucket", help="GCS bucket path (e.g., gs://your-bucket)")
    parser.add_argument("--destination", help="Local destination directory")
    parser.add_argument("--file", help="Specific file to download from the bucket")
    parser.add_argument("--folder", help="Specific folder to download from the bucket")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode")
    parser.add_argument("--max-parallel", type=int, default=MAX_PARALLEL_DOWNLOADS,
                        help=f"Maximum number of parallel downloads (default: {MAX_PARALLEL_DOWNLOADS})")
    parser.add_argument("--threads", type=int, default=MAX_THREADS_PER_DOWNLOAD,
                        help=f"Number of threads per download (default: {MAX_THREADS_PER_DOWNLOAD})")

    args = parser.parse_args()

    # Update global variables with command line arguments
    # Use the current module's globals

    MAX_PARALLEL_DOWNLOADS = args.max_parallel
    MAX_THREADS_PER_DOWNLOAD = args.threads

    # Check if gsutil is installed
    if not check_gsutil_installed():
        sys.exit(1)

    # Try to optimize gsutil config
    optimize_gsutil_config()

    # Run in interactive mode if specified or if no arguments are provided
    if args.interactive or len(sys.argv) == 1:
        interactive_download()
        return

    # Get destination directory
    destination = args.destination if args.destination else get_default_destination()
    destination = os.path.expanduser(destination)  # Expand ~ if present

    if not os.path.exists(destination):
        try:
            os.makedirs(destination)
            print(f"Created directory: {destination}")
        except OSError as e:
            print(f"Error creating destination directory: {e}")
            sys.exit(1)

    # Check if bucket is provided
    if not args.bucket:
        print("Error: Bucket path is required unless using interactive mode.")
        parser.print_help()
        sys.exit(1)

    # Add gs:// prefix if missing
    bucket = args.bucket
    if not bucket.startswith("gs://"):
        bucket = f"gs://{bucket}"

    # Download specific file
    if args.file:
        file_path = f"{bucket}/{args.file}"
        file_name = os.path.basename(args.file)
        file_dest = os.path.join(destination, file_name)

        print(f"Downloading file {file_path} to {file_dest}")
        success = download_with_progress(file_path, file_dest)

        if success:
            print(f"Successfully downloaded {file_path}")
        else:
            print(f"Failed to download {file_path}")

    # Download specific folder
    elif args.folder:
        folder_path = f"{bucket}/{args.folder}"
        folder_name = os.path.basename(args.folder.rstrip('/'))
        folder_dest = os.path.join(destination, folder_name)

        if not os.path.exists(folder_dest):
            os.makedirs(folder_dest)

        print(f"Downloading folder {folder_path} to {folder_dest}")
        success = download_with_progress(folder_path, folder_dest)

        if success:
            print(f"Successfully downloaded {folder_path}")
        else:
            print(f"Failed to download {folder_path}")

    # Download entire bucket
    else:
        print(f"Downloading entire bucket {bucket} to {destination}")
        success = download_with_progress(bucket, destination)

        if success:
            print(f"Successfully downloaded {bucket}")
        else:
            print(f"Failed to download {bucket}")

if __name__ == "__main__":
    main()
