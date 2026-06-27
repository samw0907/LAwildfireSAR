# scripts/sync_to_s3.py
# Syncs final pipeline outputs to versioned AWS S3 prefix.
# Run after all pipeline stages are complete.
# Usage:
#   python -m scripts.sync_to_s3               # upload all outputs
#   python -m scripts.sync_to_s3 --dry-run     # list what would be uploaded

import os
import sys
import hashlib
import argparse
import boto3
from botocore.exceptions import ClientError
from src.utils.config import load_config, get_aws_credentials


def get_s3_client(region):
    """Create and return an S3 client using credentials from environment."""
    key, secret, _ = get_aws_credentials()
    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=key,
        aws_secret_access_key=secret,
    )


def md5_of_file(path):
    """Compute MD5 hash of a local file for ETag comparison."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def s3_etag_matches(s3_client, bucket, key, local_path):
    """
    Check if the S3 object ETag matches the local file MD5.
    Returns True if the file is already uploaded and unchanged.
    Note: ETag matching is exact only for files uploaded without multipart.
    For large files uploaded via multipart, we skip the check and re-upload.
    """
    try:
        response = s3_client.head_object(Bucket=bucket, Key=key)
        etag = response["ETag"].strip('"')
        # Multipart ETags contain a dash — skip comparison
        if "-" in etag:
            return False
        return etag == md5_of_file(local_path)
    except ClientError:
        return False


def upload_file(s3_client, local_path, bucket, s3_key, dry_run=False):
    """
    Upload a single file to S3 using multipart for files over 100 MB.
    Skips if the file already exists on S3 with a matching ETag.
    """
    file_size_mb = os.path.getsize(local_path) / (1024 * 1024)

    if not dry_run and s3_etag_matches(s3_client, bucket, s3_key, local_path):
        print(f"  Unchanged, skipping: {s3_key}")
        return False

    if dry_run:
        print(f"  [dry-run] Would upload: {s3_key} ({file_size_mb:.1f} MB)")
        return True

    print(f"  Uploading: {s3_key} ({file_size_mb:.1f} MB)")

    if file_size_mb > 100:
        # Multipart upload for large files
        config = boto3.s3.transfer.TransferConfig(
            multipart_threshold=100 * 1024 * 1024,
            multipart_chunksize=50 * 1024 * 1024,
        )
        s3_client.upload_file(local_path, bucket, s3_key, Config=config)
    else:
        s3_client.upload_file(local_path, bucket, s3_key)

    return True


def collect_outputs(include_analysis=False):
    """
    Collect output files to sync to S3.
    By default excludes large analysis rasters (composites, change rasters).
    Pass include_analysis=True to include them.
    Returns list of (local_path, s3_relative_key) tuples.
    """
    outputs = []

    # Figures
    figures_dir = os.path.join("outputs", "figures")
    if os.path.exists(figures_dir):
        for f in os.listdir(figures_dir):
            if f.endswith(".png"):
                outputs.append((
                    os.path.join(figures_dir, f),
                    f"figures/{f}"
                ))

    # Vectors
    vectors_dir = os.path.join("data", "vectors")
    if os.path.exists(vectors_dir):
        for f in os.listdir(vectors_dir):
            if f.endswith(".geojson"):
                outputs.append((
                    os.path.join(vectors_dir, f),
                    f"vectors/{f}"
                ))

    # Validation
    validation_dir = os.path.join("data", "validation")
    if os.path.exists(validation_dir):
        for f in os.listdir(validation_dir):
            if f.endswith(".json"):
                outputs.append((
                    os.path.join(validation_dir, f),
                    f"validation/{f}"
                ))

    # Analysis rasters — large files, excluded by default
    if include_analysis:
        analysis_dir = os.path.join("data", "analysis")
        if os.path.exists(analysis_dir):
            for f in os.listdir(analysis_dir):
                if f.endswith(".tif"):
                    outputs.append((
                        os.path.join(analysis_dir, f),
                        f"analysis/{f}"
                    ))

    return outputs

def run_sync(dry_run=False, include_analysis=False):
    """
    Main sync function. Uploads all outputs to versioned S3 prefix.
    """
    config = load_config()
    bucket = config["aws"]["bucket"]
    prefix = config["aws"]["prefix"]
    region = config["aws"]["region"]

    print(f"Target: s3://{bucket}/{prefix}/")
    print(f"Mode: {'dry-run' if dry_run else 'upload'}\n")

    s3_client = get_s3_client(region)

    # Verify bucket exists and is accessible
    try:
        s3_client.head_bucket(Bucket=bucket)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "404":
            print(f"ERROR: Bucket '{bucket}' does not exist.")
            print("Create it in the AWS console or with:")
            print(f"  aws s3 mb s3://{bucket} --region {region}")
            sys.exit(1)
        elif error_code == "403":
            print(f"ERROR: Access denied to bucket '{bucket}'. Check AWS credentials.")
            sys.exit(1)
        raise

    outputs = collect_outputs(include_analysis=include_analysis)

    if not outputs:
        print("No output files found to sync.")
        return

    print(f"Found {len(outputs)} files to sync:\n")

    uploaded = 0
    skipped = 0
    total_size_mb = 0

    for local_path, relative_key in outputs:
        s3_key = f"{prefix}/{relative_key}"
        size_mb = os.path.getsize(local_path) / (1024 * 1024)
        total_size_mb += size_mb
        result = upload_file(s3_client, local_path, bucket, s3_key, dry_run=dry_run)
        if result:
            uploaded += 1
        else:
            skipped += 1

    print(f"\nSync complete.")
    print(f"  {'Would upload' if dry_run else 'Uploaded'}: {uploaded} files")
    print(f"  Skipped (unchanged): {skipped} files")
    print(f"  Total size: {total_size_mb:.1f} MB")
    print(f"  S3 prefix: s3://{bucket}/{prefix}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sync pipeline outputs to AWS S3"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be uploaded without uploading"
    )
    parser.add_argument(
        "--include-analysis",
        action="store_true",
        help="Also upload large analysis rasters (composites, change rasters, ~3.5 GB)"
    )
    args = parser.parse_args()
    run_sync(dry_run=args.dry_run, include_analysis=args.include_analysis)