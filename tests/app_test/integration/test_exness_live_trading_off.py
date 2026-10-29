# Two independent locks: BrokerFactory refuses the exness broker, and the client refuses
# every order call before any network use.

from __future__ import annotations

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import SecretStr

from pocketquant.app.di import create_container
from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.data_provider_port import IDataProviderPort
from pocketquant.core.infra.brokers.broker_factory import BrokerFactory
from pocketquant.core.infra.exness.exness_adapter import ExnessAdapter
from pocketquant.core.infra.exness.exness_client import ExnessApiError, ExnessClient

pytestmark = pytest.mark.integration


def _secret_hex() -> str:
    key = Ed25519PrivateKey.generate()
    return (key.private_bytes_raw() + key.public_key().public_bytes_raw()).hex()


async def test_live_trading_off_blocks_every_exness_order_path(settings: Settings) -> None:
    configured = settings.model_copy(
        update={
            "exness_api_base_url": "https://api.exness.com",
            "exness_account_id": "1",
            "exness_api_key": SecretStr("test-api-key"),
            "exness_secret_key": SecretStr(_secret_hex()),
            "exness_live_trading": False,
        }
    )
    container = create_container(configured)
    try:
        client = await container.get(ExnessClient)
        requests: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(500)

        client._http = httpx.AsyncClient(transport=httpx.MockTransport(record))

        assert client.is_configured
        router = await container.get(IDataProviderPort)
        assert isinstance(router._providers["exness"], ExnessAdapter)  # type: ignore[attr-defined]
        with pytest.raises(ValueError, match="EXNESS_LIVE_TRADING is false"):
            (await container.get(BrokerFactory)).create("exness", {})

        with pytest.raises(ExnessApiError) as raised:
            await client.call("openPosition", json_body={}, idempotency_key="order-00001")
        assert raised.value.code == "LIVE_TRADING_DISABLED"
        assert not any("/positions" in r.url.path for r in requests)
    finally:
        await container.close()
