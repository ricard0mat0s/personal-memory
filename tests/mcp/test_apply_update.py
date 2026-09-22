import subprocess
from pathlib import Path

import pytest
from mcp.types import TextContent

from personal_memory._git_recording import GitRecordingError

from .support import (
    DIRECTION_MARKDOWN,
    authenticated_client,
    connected_client,
    create_test_server,
    write_memory_page,
)


class RecordingUpdateRecorder:
    def __init__(self) -> None:
        self.prepared_page_ids: list[str] = []
        self.recorded_updates: list[tuple[str, str]] = []

    def prepare(self, page_id: str) -> None:
        self.prepared_page_ids.append(page_id)

    def record(self, page_id: str, version_token: str) -> None:
        self.recorded_updates.append((page_id, version_token))


class FailOnceUpdateRecorder(RecordingUpdateRecorder):
    def __init__(self) -> None:
        super().__init__()
        self._should_fail = True

    def record(self, page_id: str, version_token: str) -> None:
        if self._should_fail:
            self._should_fail = False
            raise GitRecordingError("Synthetic Git failure.")
        super().record(page_id, version_token)


def initialize_repository(workspace_root: Path) -> None:
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=workspace_root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Personal Memory test"],
        cwd=workspace_root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=workspace_root,
        check=True,
    )
    subprocess.run(
        ["git", "add", "memory/direction.md"],
        cwd=workspace_root,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "memory: baseline"],
        cwd=workspace_root,
        check=True,
    )


@pytest.mark.anyio
async def test_authenticated_application_approves_applies_and_records_one_commit(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    initialize_repository(tmp_path)
    replacement = DIRECTION_MARKDOWN.replace("small", "focused")
    (tmp_path / "operator-notes.md").write_text("Keep this staged.\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "operator-notes.md"],
        cwd=tmp_path,
        check=True,
    )
    server = create_test_server(tmp_path)

    async with authenticated_client(server) as client:
        proposal = await client.call_tool(
            "propose_update",
            {"page_id": "direction.md", "markdown": replacement},
        )
        assert proposal.structured_content is not None

        result = await client.call_tool(
            "apply_update",
            {"proposal_id": proposal.structured_content["proposal_id"]},
        )

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["page_id"] == "direction.md"
    assert result.structured_content["previous_version_token"]
    assert result.structured_content["version_token"]
    assert (tmp_path / "memory" / "direction.md").read_text(encoding="utf-8") == replacement

    changed_files = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert changed_files == ["memory/direction.md"]
    subject = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert subject == "memory: update direction.md"
    staged_files = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert staged_files == ["operator-notes.md"]


@pytest.mark.anyio
async def test_application_uses_the_injected_recording_adapter(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    recorder = RecordingUpdateRecorder()
    replacement = DIRECTION_MARKDOWN.replace("small", "focused")
    server = create_test_server(tmp_path, update_recorder=recorder)

    async with authenticated_client(server) as client:
        proposal = await client.call_tool(
            "propose_update",
            {"page_id": "direction.md", "markdown": replacement},
        )
        assert proposal.structured_content is not None
        result = await client.call_tool(
            "apply_update",
            {"proposal_id": proposal.structured_content["proposal_id"]},
        )

    assert not result.is_error
    assert result.structured_content is not None
    assert recorder.prepared_page_ids == ["direction.md"]
    assert recorder.recorded_updates == [
        ("direction.md", result.structured_content["version_token"])
    ]
    assert (tmp_path / "memory" / "direction.md").read_text(encoding="utf-8") == replacement


@pytest.mark.anyio
async def test_application_rolls_back_and_keeps_the_proposal_for_a_recording_retry(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    recorder = FailOnceUpdateRecorder()
    replacement = DIRECTION_MARKDOWN.replace("small", "focused")
    server = create_test_server(tmp_path, update_recorder=recorder)
    target = tmp_path / "memory" / "direction.md"

    async with authenticated_client(server) as client:
        proposal = await client.call_tool(
            "propose_update",
            {"page_id": "direction.md", "markdown": replacement},
        )
        assert proposal.structured_content is not None
        proposal_id = proposal.structured_content["proposal_id"]
        failed = await client.call_tool("apply_update", {"proposal_id": proposal_id})
        retried = await client.call_tool("apply_update", {"proposal_id": proposal_id})

    assert failed.is_error
    assert failed.structured_content is None
    assert len(failed.content) == 1
    assert isinstance(failed.content[0], TextContent)
    assert "Current Memory was restored" in failed.content[0].text
    assert not retried.is_error
    assert target.read_text(encoding="utf-8") == replacement
    assert recorder.prepared_page_ids == ["direction.md", "direction.md"]
    assert len(recorder.recorded_updates) == 1


@pytest.mark.anyio
async def test_application_refuses_an_already_applied_proposal_without_a_second_commit(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    initialize_repository(tmp_path)
    server = create_test_server(tmp_path)

    async with authenticated_client(server) as client:
        proposal = await client.call_tool(
            "propose_update",
            {
                "page_id": "direction.md",
                "markdown": DIRECTION_MARKDOWN.replace("small", "focused"),
            },
        )
        assert proposal.structured_content is not None
        proposal_id = proposal.structured_content["proposal_id"]
        first = await client.call_tool("apply_update", {"proposal_id": proposal_id})
        second = await client.call_tool("apply_update", {"proposal_id": proposal_id})

    assert not first.is_error
    assert second.is_error
    assert second.structured_content is None
    assert len(second.content) == 1
    assert isinstance(second.content[0], TextContent)
    assert second.content[0].text.endswith("Proposed Update is unavailable.")
    count = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert count == "2"


@pytest.mark.anyio
async def test_application_refuses_a_proposal_owned_by_another_principal(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    initialize_repository(tmp_path)
    target = tmp_path / "memory" / "direction.md"
    server = create_test_server(tmp_path)
    app = server.streamable_http_app()

    async with server.session_manager.run():
        async with connected_client(app, "valid-test-token") as owner:
            proposal = await owner.call_tool(
                "propose_update",
                {
                    "page_id": "direction.md",
                    "markdown": DIRECTION_MARKDOWN.replace("small", "focused"),
                },
            )
        assert proposal.structured_content is not None
        async with connected_client(app, "other-user-test-token") as other_principal:
            result = await other_principal.call_tool(
                "apply_update",
                {"proposal_id": proposal.structured_content["proposal_id"]},
            )

    assert result.is_error
    assert result.structured_content is None
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text.endswith("Proposed Update is unavailable.")
    assert target.read_text(encoding="utf-8") == DIRECTION_MARKDOWN
    count = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert count == "1"


@pytest.mark.anyio
async def test_application_refuses_a_dirty_proposal_target_before_writing(
    tmp_path: Path,
) -> None:
    write_memory_page(tmp_path)
    initialize_repository(tmp_path)
    replacement = DIRECTION_MARKDOWN.replace("small", "focused")
    server = create_test_server(tmp_path)

    async with authenticated_client(server) as client:
        proposal = await client.call_tool(
            "propose_update",
            {"page_id": "direction.md", "markdown": replacement},
        )
        assert proposal.structured_content is not None
        target = tmp_path / "memory" / "direction.md"
        target.write_text(
            DIRECTION_MARKDOWN.replace("small", "locally changed"), encoding="utf-8"
        )
        result = await client.call_tool(
            "apply_update",
            {"proposal_id": proposal.structured_content["proposal_id"]},
        )

    assert result.is_error
    assert result.structured_content is None
    assert target.read_text(encoding="utf-8") == DIRECTION_MARKDOWN.replace(
        "small", "locally changed"
    )
