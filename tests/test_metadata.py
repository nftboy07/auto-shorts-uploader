import unittest
from youtube.metadata_generator import clean_title, generate_shorts_metadata

class TestMetadataGenerator(unittest.TestCase):
    def test_clean_title_normal(self):
        title = "Incredible Street Food Skills!"
        cleaned = clean_title(title)
        self.assertTrue(cleaned.endswith("#shorts"))
        self.assertIn("Incredible Street Food Skills", cleaned)

    def test_clean_title_long(self):
        # Title longer than 80 chars should be truncated
        long_title = "This is an extremely long title that describes something amazing that happened on the street today with lots of details!"
        cleaned = clean_title(long_title)
        self.assertTrue(len(cleaned) <= 100)
        self.assertTrue(cleaned.endswith("#shorts"))

    def test_clean_title_emoji_removal(self):
        title = "Yummy Food 😱🔥! Best ever"
        cleaned = clean_title(title)
        # Should remove emoji special chars but retain text and #shorts
        self.assertNotIn("😱", cleaned)
        self.assertIn("Yummy Food ! Best ever", cleaned)

    def test_generate_shorts_metadata_fallback(self):
        creator = "chef_john"
        caption = "Cooking delicious pasta tonight. Full instructions inside."
        
        metadata = generate_shorts_metadata(creator, caption)
        
        self.assertIn("Cooking delicious pasta tonight", metadata["title"])
        self.assertIn("#shorts", metadata["title"])
        self.assertIn("Credit to original creator: @chef_john", metadata["description"])
        self.assertIn("chef_john", metadata["tags"])
