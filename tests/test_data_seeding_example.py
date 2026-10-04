"""
===============================================================================
Example: API-seeded setup -> test -> automatic teardown
===============================================================================
Demonstrates the data setup & teardown pattern (docs/USAGE.md). Skipped unless
SEED_API_BASE_URL (and optionally SEED_API_TOKEN) point at a REST API that
supports POST /<collection> and DELETE /<collection>/<id>.

    SEED_API_BASE_URL=https://api.example.test pytest -m seeding

Author: PMAC
===============================================================================
"""
import pytest


@pytest.fixture
def seeded_item(api_seed):
    """Setup: create an entity. Teardown: api_seed deletes it automatically."""
    return api_seed.create("/items", {"name": "seeded-by-test"})


@pytest.mark.seeding
@pytest.mark.api
@pytest.mark.positive
@pytest.mark.p2
def test_seeded_item_exists(seeded_item, api_seed):
    assert seeded_item["id"] is not None
    assert api_seed._client.get(f"/items/{seeded_item['id']}").status_code == 200
