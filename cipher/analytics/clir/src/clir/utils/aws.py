from clir import settings
from loguru import logger

try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError
except ImportError:
    logger.error("Failed to import boto3 and/or botocore. Please install them with `pip install boto3 botocore`")
    exit(1)


def generate_presigned_url(bucket: str, key: str, expiration: int = settings.aws_presigned_url_expiration) -> str:
    """Generate a presigned URL to share an S3 object."""
    config = Config(signature_version="s3v4")
    s3_client = boto3.client("s3", region_name=settings.aws_default_region, config=config)
    try:
        response = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expiration,
        )
    except ClientError as exc:
        logger.error(exc)
        return None

    return response


def download_file(bucket: str, key: str, file_path: str) -> bool:
    """Download a file from S3."""
    s3_client = boto3.client("s3", region_name=settings.aws_default_region)
    try:
        s3_client.download_file(bucket, key, file_path)
    except ClientError as exc:
        logger.error(exc)
        return False
    return True


def download_file_contents(bucket: str, key: str) -> bytes:
    """Download the contents of a file from S3."""
    s3_client = boto3.client("s3", region_name=settings.aws_default_region)
    try:
        content = s3_client.get_object(Bucket=bucket, Key=key)
        return content["Body"].read()
    except ClientError as exc:
        logger.error(exc)
        return None
