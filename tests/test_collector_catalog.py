"""Verify every shipped collector remains visible without employer data."""

from job_radar.collector_catalog import list_collector_capabilities
from job_radar.config import SUPPORTED_SOURCE_TYPES


def test_collector_catalog_matches_supported_source_types() -> None:
    capabilities = list_collector_capabilities()

    assert {item.source_type for item in capabilities} == SUPPORTED_SOURCE_TYPES
    assert len(capabilities) == len(SUPPORTED_SOURCE_TYPES)
    assert all(item.name and item.setup and item.description for item in capabilities)
