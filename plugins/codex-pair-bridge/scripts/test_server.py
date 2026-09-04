import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import httpx
import server


class BridgeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch.object(server, "user_cache_path", return_value=Path(temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_http_error_does_not_echo_prompt_or_retry(self):
        with patch.object(server.httpx, 'Client') as factory:
            client = factory.return_value.__enter__.return_value
            client.request.return_value = httpx.Response(400, json={'error': 'PRIVATE PROMPT'})
            with self.assertRaisesRegex(ValueError, '^PAIR returned HTTP 400') as error:
                server.request('POST', '/chat/completions', {'private': 'data'})
            self.assertNotIn('PRIVATE', str(error.exception))
            self.assertEqual(client.request.call_count, 1)

    def test_timeout_no_retry(self):
        with patch.object(server.httpx, 'Client') as factory:
            client = factory.return_value.__enter__.return_value
            client.request.side_effect = httpx.ReadTimeout('timeout')
            with self.assertRaisesRegex(ValueError, 'may still be running'):
                server.request('POST', '/chat/completions', {})
            self.assertEqual(client.request.call_count, 1)

    def test_lock_rejects_overlap(self):
        with server.inference_lock():
            with self.assertRaisesRegex(ValueError, 'Another Codex PAIR request'):
                with server.inference_lock():
                    self.fail('lock was not held')

    def test_content_parts_and_truncation(self):
        with patch.object(server, 'catalog', return_value=[{'id': 'model', 'kind_hint': 'chat_candidate'}]), patch.object(server, 'request', return_value={'model': 'model', 'choices': [{'message': {'content': [{'type': 'text', 'text': 'answer'}]}, 'finish_reason': 'length'}]}):
            result = server.pair_ask('model', 'test')
            self.assertEqual(result['answer'], 'answer')
            self.assertTrue(result['truncated'])

    def test_empty_answer_is_failure(self):
        with patch.object(server, 'catalog', return_value=[{'id': 'model', 'kind_hint': 'chat_candidate'}]), patch.object(server, 'request', return_value={'choices': [{'message': {'content': None, 'reasoning_content': 'private reasoning'}, 'finish_reason': 'length'}]}):
            with self.assertRaisesRegex(ValueError, 'no final text'):
                server.pair_ask('model', 'test')

class ConfigTests(unittest.TestCase):
    def test_config_file(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(server.Path, 'home', return_value=Path(tmp)), patch.dict(server.os.environ, {}, clear=True):
            (Path(tmp)/'.codex-pair-bridge.json').write_text('{"base_url":"http://localhost:7777/v1/"}')
            self.assertEqual(server.load_config(), ('http://localhost:7777/v1', None))

    def test_reject_embedded_credentials(self):
        with patch.dict(server.os.environ, {'PAIR_BASE_URL':'https://user:secret@example.com/v1'}):
            with self.assertRaisesRegex(ValueError, 'without credentials'):
                server.load_config()

    def test_env_override(self):
        with patch.dict(server.os.environ, {'PAIR_BASE_URL':'https://example.com/v1','PAIR_API_KEY':'test'}):
            self.assertEqual(server.load_config(), ('https://example.com/v1', 'test'))


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_handshake_and_schema(self):
        import sys
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(command=sys.executable, args=[str(Path(server.__file__))])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                self.assertEqual({t.name for t in tools}, {'pair_list', 'pair_ask'})
                result = await session.call_tool('pair_ask', {'model':'model','prompt':'hello','max_tokens':-1})
                self.assertTrue(result.isError)


if __name__ == '__main__':
    unittest.main()
