import unittest
from unittest.mock import patch

import download_review
import server


class DownloadReviewTests(unittest.TestCase):
    def test_one_exact_hugging_face_quantization(self):
        info = {'sha': 'revision123', 'siblings': [
            {'rfilename': 'model-Q4_K_M.gguf', 'size': 1000},
            {'rfilename': 'model-Q8_0.gguf', 'size': 2000}]}
        with patch.object(download_review.httpx, 'Client') as factory:
            factory.return_value.__enter__.return_value.get.return_value.json.return_value = info
            result = download_review.model_files('https://huggingface.co/owner/repo', 'Q4_K_M')
        self.assertEqual(result['status'], 'verified_file')
        self.assertEqual(result['size_bytes'], 1000)
        self.assertEqual(result['revision'], 'revision123')

    def test_ambiguous_repository_does_not_claim_exact_size(self):
        info = {'sha': 'revision123', 'siblings': [
            {'rfilename': 'a.gguf', 'size': 1000}, {'rfilename': 'b.gguf', 'size': 2000}]}
        with patch.object(download_review.httpx, 'Client') as factory:
            factory.return_value.__enter__.return_value.get.return_value.json.return_value = info
            result = download_review.model_files('https://huggingface.co/owner/repo', None)
        self.assertEqual(result['status'], 'ambiguous')

    def test_download_plan_uses_verified_size_and_rejects_low_space(self):
        metadata = {'status': 'verified_file', 'size_bytes': 1000, 'revision': 'sha'}
        with patch.object(server.management, 'devices', return_value={'mac': {}}), \
             patch.object(server.download_review, 'model_files', return_value=metadata), \
             patch.object(server.download_review, 'destination_space', return_value={'status': 'enough'}) as space:
            result = server.pair_download_plan('mac', 'https://huggingface.co/owner/repo',
                                               destination='/models', quantization='Q4_K_M')
        self.assertEqual(result['size_source'], 'huggingface_file_metadata')
        self.assertEqual(result['estimated_disk_and_network_bytes'], 1000)
        self.assertEqual(space.call_args.args[-1], 1100)
        with patch.object(server.management, 'devices', return_value={'mac': {}}), \
             patch.object(server.download_review, 'model_files', return_value=metadata), \
             patch.object(server.download_review, 'destination_space', return_value={'status': 'insufficient'}):
            with self.assertRaisesRegex(ValueError, 'less than'):
                server.pair_download_plan('mac', 'https://huggingface.co/owner/repo', destination='/models')

    def test_download_rechecks_revision_before_start(self):
        metadata = {'status': 'verified_file', 'size_bytes': 1000, 'revision': 'old', 'file': 'q4.gguf'}
        with patch.object(server.management, 'devices', return_value={'mac': {}}), \
             patch.object(server.download_review, 'model_files', return_value=metadata), \
             patch.object(server.download_review, 'destination_space', return_value={'status': 'enough'}):
            plan = server.pair_download_plan('mac', 'https://huggingface.co/owner/repo', destination='/models')
        with patch.object(server.download_review, 'model_files', return_value=dict(metadata, revision='new')), \
             patch.object(server.management, 'request') as request:
            with self.assertRaisesRegex(ValueError, 'metadata changed'):
                server.pair_download(plan['plan_id'], plan['model'])
            request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
