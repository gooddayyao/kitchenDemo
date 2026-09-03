"""Tests for ingredient catalog."""

from __future__ import annotations

import unittest

from src.ingredient_catalog import detectable_items, label_for, yolo_class_names


class IngredientCatalogTests(unittest.TestCase):
    def test_detectable_includes_cucumber_and_yolo_foods(self) -> None:
        ids = {i["id"] for i in detectable_items()}
        self.assertIn("cucumber", ids)
        self.assertIn("banana", ids)
        self.assertIn("carrot", ids)
        self.assertIn("broccoli", ids)

    def test_labels_zh(self) -> None:
        self.assertEqual(label_for("cucumber"), "小黃瓜")
        self.assertEqual(label_for("banana"), "香蕉")
        self.assertEqual(label_for("hot dog"), "熱狗")

    def test_id_for_label(self) -> None:
        from src.ingredient_catalog import id_for_label

        self.assertEqual(id_for_label("小黃瓜"), "cucumber")
        self.assertEqual(id_for_label("cucumber"), "cucumber")

    def test_yolo_names(self) -> None:
        names = yolo_class_names()
        self.assertIn("banana", names)
        self.assertIn("hot dog", names)
        self.assertIn("cucumber", names)


if __name__ == "__main__":
    unittest.main()
