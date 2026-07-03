"""Elasticsearch async client factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from elasticsearch import AsyncElasticsearch, AuthenticationException, ConnectionError
from loguru import logger

from cipher.datastores.elasticsearch.config import ElasticsearchConfig


def get_client(config: ElasticsearchConfig, **kwargs) -> AsyncElasticsearch:
    """Construct an AsyncElasticsearch client from config."""
    client_args = {
        "hosts": f"https://{config.host}:{config.port}/",
        "basic_auth": (config.username, config.password),
        "verify_certs": False,
        "ssl_show_warn": False,
        "connections_per_node": 5,
        "max_retries": 3,
        "retry_on_timeout": True,
        **kwargs,
    }

    if config.ca_cert:
        client_args["ca_certs"] = config.ca_cert.expanduser().as_posix()
        client_args["verify_certs"] = True

    return AsyncElasticsearch(**client_args)


@asynccontextmanager
async def get_async_client(
    config: ElasticsearchConfig,
) -> AsyncGenerator[AsyncElasticsearch, None]:
    """Async context manager that yields a connected AsyncElasticsearch client.

    Performs a health check on entry and always closes the client on exit.
    """
    client = get_client(config)
    try:
        await client.info()
    except AuthenticationException as exc:
        await client.close()
        raise RuntimeError("Elasticsearch authentication failed") from exc
    except ConnectionError as exc:
        await client.close()
        raise RuntimeError(
            f"Could not connect to Elasticsearch at {config.host}:{config.port}"
        ) from exc
    except Exception as exc:
        await client.close()
        raise RuntimeError(f"Elasticsearch client error: {exc}") from exc

    try:
        await client.ping()
        logger.success(
            f"Connected to Elasticsearch cluster at {config.host}:{config.port}"
        )
        yield client
    finally:
        await client.close()
        logger.debug("Elasticsearch client closed")
