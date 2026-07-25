"""Task L/2: dispatch()'s generic catch-all must never leak str(exc) to the
caller (potential internal-detail leak -- paths, hostnames, connection
strings) -- it should log the detail server-side (logger.exception) and
return a generic error message instead."""
import logging
import pytest
from unittest.mock import AsyncMock
from hiris.app.tools.dispatcher import ToolDispatcher


def _dispatcher(ha):
    return ToolDispatcher(ha_client=ha, notify_config={})


@pytest.mark.asyncio
async def test_dispatch_catch_all_does_not_leak_exception_text(caplog):
    ha = AsyncMock()
    sensitive = "connection refused to 10.0.0.5:5432 at /opt/hiris/secret/db.sock"
    ha.get_states = AsyncMock(side_effect=RuntimeError(sensitive))
    d = _dispatcher(ha)

    with caplog.at_level(logging.ERROR):
        res = await d.dispatch("get_entity_states", {"ids": ["light.living"]})

    assert "error" in res
    assert sensitive not in res["error"]
    # the detail must still be logged server-side for debugging
    assert any(sensitive in rec.getMessage() or sensitive in str(rec.exc_info)
               for rec in caplog.records)
