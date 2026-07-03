"""
===============================================================================
Unit Tests: utils/visual_regression.py
===============================================================================
Tests compare_images() pixel-diff logic with generated images — no browser
or screenshot capture involved.

Author: PMAC
===============================================================================
"""

from PIL import Image

from utils.visual_regression import compare_images


def make_image(path, color, size=(50, 50)):
    """Create a solid-color RGB image on disk and return its path as str."""
    Image.new("RGB", size, color).save(path)
    return str(path)


class TestCompareImages:
    def test_identical_images_match(self, tmp_path):
        baseline = make_image(tmp_path / "baseline.png", "red")
        current = make_image(tmp_path / "current.png", "red")
        diff_path = tmp_path / "diff.png"

        matches, ratio = compare_images(baseline, current, str(diff_path))

        assert matches is True
        assert ratio == 0.0
        assert not diff_path.exists()

    def test_completely_different_images_fail_and_write_diff(self, tmp_path):
        baseline = make_image(tmp_path / "baseline.png", "red")
        current = make_image(tmp_path / "current.png", "blue")
        diff_path = tmp_path / "diff.png"

        matches, ratio = compare_images(baseline, current, str(diff_path))

        assert matches is False
        assert ratio == 1.0
        assert diff_path.exists()

    def test_partial_difference_ratio(self, tmp_path):
        baseline = make_image(tmp_path / "baseline.png", "red", size=(100, 100))
        # Current: top half red (same), bottom half blue (different)
        img = Image.new("RGB", (100, 100), "red")
        img.paste(Image.new("RGB", (100, 50), "blue"), (0, 50))
        current = tmp_path / "current.png"
        img.save(current)
        diff_path = tmp_path / "diff.png"

        matches, ratio = compare_images(baseline, str(current), str(diff_path))

        assert matches is False
        assert abs(ratio - 0.5) < 0.01

    def test_difference_within_tolerance_passes(self, tmp_path):
        baseline = make_image(tmp_path / "baseline.png", "red", size=(100, 100))
        img = Image.new("RGB", (100, 100), "red")
        img.putpixel((0, 0), (0, 0, 255))  # one differing pixel = 0.01%
        current = tmp_path / "current.png"
        img.save(current)
        diff_path = tmp_path / "diff.png"

        matches, ratio = compare_images(
            baseline, str(current), str(diff_path), tolerance=0.01
        )

        assert matches is True
        assert 0 < ratio <= 0.01
        assert not diff_path.exists()

    def test_size_mismatch_resizes_current_to_baseline(self, tmp_path):
        baseline = make_image(tmp_path / "baseline.png", "red", size=(50, 50))
        current = make_image(tmp_path / "current.png", "red", size=(100, 100))
        diff_path = tmp_path / "diff.png"

        matches, ratio = compare_images(baseline, current, str(diff_path))

        assert matches is True
        assert ratio == 0.0

    def test_missing_file_returns_complete_difference(self, tmp_path):
        baseline = make_image(tmp_path / "baseline.png", "red")

        matches, ratio = compare_images(
            baseline, str(tmp_path / "does_not_exist.png"), str(tmp_path / "diff.png")
        )

        assert matches is False
        assert ratio == 1.0
