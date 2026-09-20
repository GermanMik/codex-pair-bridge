import unittest
from unittest.mock import patch
import contextlib
import subprocess
import server
import management

class ManagementTests(unittest.TestCase):
    def scope(self, *_args, **_kwargs):
        return contextlib.nullcontext(object())

    def test_no_download_for_missing_model(self):
        with patch.object(management, 'models', return_value=[]), patch.object(management, 'request') as req:
            with self.assertRaisesRegex(ValueError, 'not installed'):
                management.find_model(object(), 'imaginary')
            req.assert_not_called()

    def test_weight_limit_preserves_other_loaded_models(self):
        loaded = {'key': 'other', 'size_bytes': 80, 'loaded_instances': [{'id': 'other-i'}]}
        candidate = {'key': 'new', 'size_bytes': 40, 'loaded_instances': []}
        with self.assertRaisesRegex(ValueError, 'limit would be exceeded'):
            management.ensure_capacity([loaded, candidate], candidate, 100)
        management.ensure_capacity([loaded, candidate], candidate, 120)

    def test_memory_preflight_uses_loaded_context_and_blocks_cap(self):
        loaded = {'key': 'running', 'loaded_instances': [{'id': 'i', 'config': {'context_length': 65536}}]}
        cold = {'key': 'new', 'loaded_instances': []}
        with patch.object(management, 'estimate_memory', side_effect=[
            {'total_bytes': 20, 'gpu_bytes': 20, 'context_length': 8192},
            {'total_bytes': 30, 'gpu_bytes': 30, 'context_length': 65536}]) as estimate:
            result = management.memory_preflight('pc', [loaded, cold], cold, 8192, 60)
        self.assertEqual(result['estimated_total_bytes'], 50)
        self.assertEqual(estimate.call_args_list[1].args, ('pc', 'running', 65536))
        with patch.object(management, 'estimate_memory', side_effect=[
            {'total_bytes': 20, 'gpu_bytes': 20}, {'total_bytes': 30, 'gpu_bytes': 30}]):
            with self.assertRaisesRegex(ValueError, 'estimated memory limit'):
                management.memory_preflight('pc', [loaded, cold], cold, 8192, 49)

    def test_memory_preflight_fails_closed_when_cap_and_context_unknown(self):
        loaded = {'key': 'running', 'loaded_instances': [{'id': 'i'}]}
        cold = {'key': 'new', 'loaded_instances': []}
        with patch.object(management, 'estimate_memory', return_value={'total_bytes': 20, 'gpu_bytes': 20}):
            with self.assertRaisesRegex(ValueError, 'context is unknown'):
                management.memory_preflight('pc', [loaded, cold], cold, 8192, 100)

    def test_estimator_accepts_cli_stderr_and_target_port(self):
        output = 'Estimated GPU Memory: 19.24 GiB\nEstimated Total Memory: 20.00 GiB\n'
        with patch.object(management, 'devices', return_value={'pc': {'base_url': 'http://127.0.0.1:1234'}}), \
             patch.object(management.shutil, 'which', return_value='/tmp/lms'), \
             patch.object(management.Path, 'is_file', return_value=True), \
             patch.object(management.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', output)) as run:
            result = management.estimate_memory('pc', 'installed-model', 8192)
        self.assertEqual(result['total_bytes'], 20 * 2**30)
        self.assertIn('1234', run.call_args.args[0])

    def test_reuse_loaded_without_mutation(self):
        model={'key':'m','loaded_instances':[{'id':'instance'}]}
        with patch.object(server, 'inference_lock', self.scope), patch.object(management, 'client', return_value=self.scope()), patch.object(management, 'models', return_value=[model]), patch.object(management, 'request') as req:
            self.assertEqual(server.pair_load('pc','m')['status'], 'already_loaded')
            req.assert_not_called()

    def test_unload_exact_instance_and_verify(self):
        before=[{'key':'m','loaded_instances':[{'id':'instance'}]}]
        with patch.object(server, 'inference_lock', self.scope), patch.object(management, 'client', return_value=self.scope()), patch.object(management, 'models', side_effect=[before, []]), patch.object(management, 'request', return_value={}) as req:
            self.assertEqual(server.pair_unload('pc','instance')['status'], 'unloaded')
            self.assertEqual(req.call_args.args[3], {'instance_id':'instance'})

    def test_unload_unknown_rejected(self):
        with patch.object(server, 'inference_lock', self.scope), patch.object(management, 'client', return_value=self.scope()), patch.object(management, 'models', return_value=[]), patch.object(management, 'request') as req:
            with self.assertRaisesRegex(ValueError, 'not loaded'):
                server.pair_unload('pc','missing')
            req.assert_not_called()

    @patch.object(management, 'memory_preflight', return_value={'status': 'estimated'})
    def test_load_not_confirmed(self, _preflight):
        m={'key':'m','type':'llm','loaded_instances':[],'max_context_length':8192}
        with patch.object(server, 'inference_lock', self.scope), patch.object(management, 'client', return_value=self.scope()), patch.object(management, 'models', return_value=[m]), patch.object(management, 'devices', return_value={'pc': {}}), patch.object(management, 'find_model', return_value=m), patch.object(management, 'request', return_value={}):
            self.assertEqual(server.pair_load('pc','m')['status'],'not_confirmed')

    @patch.object(management, 'memory_preflight', return_value={'status': 'estimated'})
    def test_load_reports_engine_eviction_without_unloading_itself(self, _preflight):
        other = {'key': 'other', 'type': 'llm', 'size_bytes': 10, 'loaded_instances': [{'id': 'other-i'}]}
        cold = {'key': 'm', 'type': 'llm', 'size_bytes': 20, 'loaded_instances': [], 'max_context_length': 8192}
        warm = dict(cold, loaded_instances=[{'id': 'new-i'}])
        with patch.object(server, 'inference_lock', self.scope), patch.object(management, 'client', return_value=self.scope()), \
             patch.object(management, 'models', side_effect=[[other, cold], [warm]]), \
             patch.object(management, 'devices', return_value={'pc': {}}), \
             patch.object(management, 'find_model', return_value=warm), \
             patch.object(management, 'request', return_value={'instance_id': 'new-i', 'load_time_seconds': 1.5}) as req:
            result = server.pair_load('pc', 'm')
        self.assertEqual(result['engine_evicted_instances'], ['other-i'])
        self.assertEqual(result['load_time_seconds'], 1.5)
        self.assertEqual(req.call_args.args[2], '/api/v1/models/load')

    def test_device_ask_uses_instance_not_router(self):
        m={'key':'m','type':'llm','loaded_instances':[{'id':'actual-instance'}]}
        with patch.object(server, 'inference_lock', self.scope), patch.object(management, 'client', return_value=self.scope()), patch.object(management, 'find_model', return_value=m), patch.object(management, 'request', return_value={'choices':[{'message':{'content':'ok'}}]}) as req, patch.object(server,'request') as router:
            r=server.pair_ask('m','test',device='pc')
            self.assertEqual(r['device'],'pc')
            self.assertEqual(req.call_args.args[3]['model'],'actual-instance')
            router.assert_not_called()

    def test_offline_device_does_not_hide_online(self):
        with patch.object(management,'devices',return_value={'offline':{},'online':{}}), patch.object(management,'client',side_effect=[ValueError('unreachable'),self.scope()]), patch.object(management,'models',return_value=[]):
            rows=server.pair_devices()['devices']
            self.assertFalse(rows[0]['online'])
            self.assertTrue(rows[1]['online'])

    def test_malformed_loaded_state_rejected(self):
        with patch.object(management,'request',return_value={'models':[{'key':'m'}]}):
            with self.assertRaisesRegex(ValueError,'loaded state'):
                management.models(object())
