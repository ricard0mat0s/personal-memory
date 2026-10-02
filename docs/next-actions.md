# Next action

Write one failing **process-level HTTP test**: launch the server as a separate process with a temporary workspace passed on the command line and offline test settings in the environment. Send a valid MCP request over a real local socket without a token and assert HTTP `401`. This test proves that the new launcher serves the protected MCP endpoint. The existing `test_unauthorized_search_is_refused_before_memory_is_opened` already covers the adapter's `401` behavior in-process, so do not add another in-process denial test. Then make the smallest implementation change that passes the new test.

Follow the agreed sequence in [authenticated-retrieval-design.md](authenticated-retrieval-design.md). The project owner will write the implementation as a learning exercise.
