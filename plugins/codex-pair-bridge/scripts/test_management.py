import unittest
from unittest.mock import patch
import contextlib
import server
import management

class ManagementTests(unittest.TestCase):
    def scope(self):
        return contextlib.nullcontext(object())

    def test_no_download_for_missing_model(self):
        with patch.object(management, 'models', return_value=[]), patch.object(management, 'request') as req:
            with self.assertRaisesRegex(ValueError, 'not installed'):
                management.find_model(object(), 'imaginary')
            req.assert_not_called()

    def test_reuse_loaded_without_mutation(self):
        model={'key':'m','loaded_instances':[{'id':'instance'}]}
        with patch.object(server, 'inference_lock', self.scope), patch.object(management, 'client', return_value=self.scope()), patch.object(management, 'find_model', return_value=model), patch.object(management, 'request') as req:
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

    def test_load_not_confirmed(self):
        m={'key':'m','type':'llm','loaded_instances':[],'max_context_length':8192}
        with patch.object(server, 'inference_lock', self.scope), patch.object(management, 'client', return_value=self.scope()), patch.object(management, 'find_model', return_value=m), patch.object(management, 'request', return_value={}):
            self.assertEqual(server.pair_load('pc','m')['status'],'not_confirmed')

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
