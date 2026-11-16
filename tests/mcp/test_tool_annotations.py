import pytest

from pathlib import Path

from .support import authenticated_client, create_test_server


@pytest.mark.anyio
async def test_tools_declare_their_effect_so_clients_can_confirm_writes(
    tmp_path: Path,
) -> None:
    async with authenticated_client(create_test_server(tmp_path)) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    hints = {
        name: (
            tool.annotations.read_only_hint,
            tool.annotations.destructive_hint,
            tool.annotations.open_world_hint,
        )
        for name, tool in tools.items()
        if tool.annotations is not None
    }
    assert hints == {
        "search_memory": (True, None, False),
        "read_memory": (True, None, False),
        "propose_update": (False, False, False),
        "apply_update": (False, True, False),
    }
