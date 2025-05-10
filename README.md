# GCS Downloader

This script provides a high-performance command-line tool for downloading files and folders from Google Cloud Storage (GCS). It utilizes `gsutil` for the core download operations and enhances it with features like parallel downloads, progress bars, and an interactive mode.

## Features

- **Interactive Mode:** Easily browse and select files/folders to download from a GCS bucket.
- **Command-Line Mode:** Directly specify a bucket, file, or folder to download.
- **Parallel Downloads:** Download multiple files/folders simultaneously (configurable).
- **Threaded Downloads:** Utilize multiple threads for a single large file download (configurable).
- **Progress Bars:** Visual feedback on download progress for individual files and overall batch operations.
- **`gsutil` Integration:**
  - Checks if `gsutil` is installed and provides installation instructions if not.
  - Attempts to apply performance optimizations to the `gsutil` configuration.
- **Dependency Management:** Automatically checks for and installs required Python packages (e.g., `tqdm`).
- **Flexible Destination:** Specify a download destination, or use a default (tries `~/Desktop/Canva`, then `~`).
- **Resumable & Overwrite Protection:** Leverages `gsutil cp -n` to skip already existing files, making downloads somewhat resumable and preventing accidental overwrites.

## Prerequisites

1.  **Python 3:** Ensure you have Python 3 installed.
2.  **Google Cloud SDK (`gsutil`):**
    - The script requires `gsutil` to be installed and configured for access to your GCS buckets.
    - If not installed, the script will prompt you with a link to the installation guide: [Google Cloud SDK Installation](https://cloud.google.com/sdk/docs/install)
    - After installation, make sure you have authenticated and set up your project:
      ```bash
      gcloud auth login
      gcloud config set project YOUR_PROJECT_ID
      ```

## Installation

1.  Clone this repository or download the `main.py` script.
2.  Make the script executable:
    ```bash
    chmod +x main.py
    ```

## Usage

You can run the script in interactive mode or by providing command-line arguments.

### Interactive Mode

To run in interactive mode, simply execute the script without any arguments or with the `--interactive` flag:

```bash
./main.py
```

or

```bash
python3 main.py
```

or

```bash
./main.py --interactive
```

The script will then guide you through:

1.  Entering the GCS bucket name (e.g., `gs://your-bucket-name`).
2.  Listing the bucket contents.
3.  Choosing what to download (single file, multiple files, single folder, multiple folders, or everything).
4.  Specifying a local destination directory.

### Command-Line Mode

Use command-line arguments for direct downloads.

**Syntax:**

```bash
./main.py --bucket gs://<your-bucket-name> [--destination <local-path>] [--file <file-in-bucket>] [--folder <folder-in-bucket>] [--max-parallel <N>] [--threads <M>]
```

**Arguments:**

- `--bucket <bucket-path>`: (Required unless in interactive mode) The GCS bucket path (e.g., `gs://your-bucket`).
- `--destination <local-path>`: (Optional) Local directory to download files to.
  - Defaults to `~/Desktop/Canva` if it exists, otherwise `~` (your home directory).
  - The script will create the directory if it doesn't exist.
- `--file <file-name>`: (Optional) Specific file to download from the bucket (relative to the bucket root).
- `--folder <folder-name>`: (Optional) Specific folder to download from the bucket (relative to the bucket root).
- `--interactive`: (Optional) Force run in interactive mode.
- `--max-parallel <N>`: (Optional) Maximum number of parallel downloads. Default: 16.
- `--threads <M>`: (Optional) Number of threads per download for `gsutil`. Default: 8.

**Examples:**

1.  **Download a specific file:**

    ```bash
    ./main.py --bucket gs://my-data-bucket --file logs/january.txt --destination ~/Downloads/logs
    ```

2.  **Download a specific folder:**

    ```bash
    ./main.py --bucket gs://my-assets-bucket --folder images/products --destination ~/Work/product-images
    ```

3.  **Download the entire bucket:**

    ```bash
    ./main.py --bucket gs://my-backup-bucket --destination /mnt/backups/gcs
    ```

4.  **Download with custom parallelism:**
    ```bash
    ./main.py --bucket gs://my-large-files --max-parallel 4 --threads 16 --destination ~/BigDownloads
    ```

## How it Works

The script performs the following steps:

1.  **Checks Python Dependencies:** Verifies if `tqdm` (for progress bars) is installed. If not, it attempts to install it using `pip`.
2.  **Checks `gsutil`:** Ensures `gsutil` is installed and accessible in the system's PATH.
3.  **Optimizes `gsutil` (Optional):** Tries to set performance-related configurations in the `~/.boto` file if they aren't already present. These include `parallel_thread_count`, `parallel_process_count`, and settings for sliced object downloads.
4.  **Parses Arguments:** Reads command-line arguments or defaults to interactive mode.
5.  **Handles Downloads:**
    - **Interactive Mode:** Lists bucket contents using `gsutil ls` and prompts the user for selections.
    - **Direct Download:** Uses `gsutil -m cp -r -n` for downloading.
      - `-m`: Enables parallel operations.
      - `cp`: Copy command.
      - `-r`: Recursive, for folders.
      - `-n`: No-clobber, skips files that already exist in the destination.
    - For individual files/folders or batches, it uses a `ThreadPoolExecutor` to manage parallel downloads.
    - A separate thread monitors the size of the downloading file(s) to update a `tqdm` progress bar.

## Notes

- The script creates the destination directory if it does not exist.
- Error handling is included for common issues like missing buckets, network problems during download, or inability to create directories.
- The `gsutil` optimization step might require user interaction or might fail if there are permission issues with the `~/.boto` file, but the downloads will still proceed without these specific optimizations.
