import unittest
import tempfile
import os
from pathlib import Path
from utils.helpers import calculate_file_hash, get_video_metadata

class TestHelpers(unittest.TestCase):
    def setUp(self):
        # Create a temporary file to test hashing
        self.test_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        self.test_file.write(b"hello world")
        self.test_file.close()

    def tearDown(self):
        if os.path.exists(self.test_file.name):
            os.remove(self.test_file.name)

    def test_calculate_file_hash(self):
        # MD5 of "hello world" is "5eb63bbbe01eeed093cb22bb8f5acdc3"
        expected_hash = "5eb63bbbe01eeed093cb22bb8f5acdc3"
        calculated = calculate_file_hash(self.test_file.name)
        self.assertEqual(calculated, expected_hash)

    def test_get_video_metadata_invalid_file(self):
        # Testing metadata fetch for a non-existent file
        result = get_video_metadata("non_existent_file.mp4")
        self.assertIsNone(result)
