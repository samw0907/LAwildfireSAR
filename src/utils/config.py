# src/utils/config.py
import os
import yaml
from dotenv import load_dotenv

# Load environment variables from config/.env
load_dotenv(dotenv_path="config/.env")


def load_config(path="config/pipeline_config.yaml"):
    """Load and return the pipeline config as a dictionary."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


def get_cdse_credentials():
    """Return CDSE credentials from environment."""
    user = os.getenv("CDSE_USER")
    password = os.getenv("CDSE_PASSWORD")
    if not user or not password:
        raise EnvironmentError("CDSE_USER or CDSE_PASSWORD not set in environment")
    return user, password


def get_aws_credentials():
    """Return AWS credentials from environment."""
    key = os.getenv("AWS_ACCESS_KEY_ID")
    secret = os.getenv("AWS_SECRET_ACCESS_KEY")
    region = os.getenv("AWS_DEFAULT_REGION")
    if not key or not secret:
        raise EnvironmentError("AWS credentials not set in environment")
    return key, secret, region