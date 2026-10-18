"""Basic tests for the PostgreSQL placeholder helper."""
import unittest
from postgres_sql import placeholders

class PlaceholdersTest(unittest.TestCase):
    def test_bind_parameters(self):
        self.assertEqual(placeholders("SELECT * FROM users WHERE id=? AND school_id=?"),
                         "SELECT * FROM users WHERE id=%s AND school_id=%s")

    def test_literal_question_mark(self):
        self.assertEqual(placeholders("SELECT '?' AS symbol WHERE id=?"),
                         "SELECT '?' AS symbol WHERE id=%s")

if __name__ == "__main__":
    unittest.main()
