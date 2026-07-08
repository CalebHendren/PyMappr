import math

import pytest

from pymappr.coords import CoordinateError, parse_latitude, parse_longitude


def close(a, b):
    return math.isclose(a, b, abs_tol=1e-9)


class TestDecimal:
    def test_plain(self):
        assert close(parse_longitude("-122.4194"), -122.4194)
        assert close(parse_latitude("37.7749"), 37.7749)

    def test_numeric_input(self):
        assert close(parse_longitude(-122.4194), -122.4194)
        assert close(parse_latitude(45), 45.0)

    def test_positive_sign(self):
        assert close(parse_longitude("+122.5"), 122.5)

    def test_comma_decimal_separator(self):
        assert close(parse_latitude("37,7749"), 37.7749)

    def test_hemisphere_suffix(self):
        assert close(parse_longitude("122.4194 W"), -122.4194)
        assert close(parse_longitude("122.4194E"), 122.4194)
        assert close(parse_latitude("37.7749 S"), -37.7749)

    def test_hemisphere_prefix(self):
        assert close(parse_longitude("W122.4194"), -122.4194)
        assert close(parse_latitude("n 37.7749"), 37.7749)


class TestDMS:
    def test_full_dms_symbols(self):
        assert close(parse_longitude("122°25'10.5\"W"),
                     -(122 + 25 / 60 + 10.5 / 3600))
        assert close(parse_latitude("37°46'29.6\"N"),
                     37 + 46 / 60 + 29.6 / 3600)

    def test_unicode_marks(self):
        assert close(parse_latitude("37º46′29.6″N"),
                     37 + 46 / 60 + 29.6 / 3600)

    def test_letter_markers(self):
        assert close(parse_longitude("122d 25m 10.5s W"),
                     -(122 + 25 / 60 + 10.5 / 3600))

    def test_bare_numbers(self):
        assert close(parse_longitude("122 25 10.5 W"),
                     -(122 + 25 / 60 + 10.5 / 3600))

    def test_colon_separated(self):
        assert close(parse_latitude("37:46:29.6N"),
                     37 + 46 / 60 + 29.6 / 3600)

    def test_degrees_minutes_only(self):
        assert close(parse_latitude("37°46.493'N"), 37 + 46.493 / 60)

    def test_negative_dms(self):
        assert close(parse_longitude("-122 25 10.5"),
                     -(122 + 25 / 60 + 10.5 / 3600))

    def test_south_prefix(self):
        assert close(parse_latitude("S 33 51 54"), -(33 + 51 / 60 + 54 / 3600))


class TestErrors:
    def test_empty(self):
        with pytest.raises(CoordinateError):
            parse_longitude("")

    def test_nan(self):
        with pytest.raises(CoordinateError):
            parse_latitude(float("nan"))

    def test_garbage(self):
        with pytest.raises(CoordinateError):
            parse_longitude("not a coordinate")

    def test_longitude_out_of_range(self):
        with pytest.raises(CoordinateError):
            parse_longitude("181")
        with pytest.raises(CoordinateError):
            parse_longitude("-180.1")

    def test_latitude_out_of_range(self):
        with pytest.raises(CoordinateError):
            parse_latitude("90.5")

    def test_wrong_hemisphere_letter(self):
        with pytest.raises(CoordinateError):
            parse_longitude("122.4 N")
        with pytest.raises(CoordinateError):
            parse_latitude("37.7 E")

    def test_sign_and_hemisphere_conflict(self):
        with pytest.raises(CoordinateError):
            parse_longitude("-122.4 W")

    def test_minutes_over_60(self):
        with pytest.raises(CoordinateError):
            parse_latitude("37 65 10 N")

    def test_boundary_values_ok(self):
        assert close(parse_longitude("180"), 180.0)
        assert close(parse_longitude("-180"), -180.0)
        assert close(parse_latitude("90"), 90.0)
        assert close(parse_latitude("-90"), -90.0)
