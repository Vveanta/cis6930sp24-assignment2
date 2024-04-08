from unittest.mock import patch
import pytest # type: ignore

from assignment2 import geocode_address  
@pytest.fixture
def mock_gmaps_geocode():
    # Fixture to mock the gmaps.geocode method
    with patch('assignment2.gmaps.geocode') as mock:
        yield mock

def test_geocode_address_without_cache_and_api_call(mock_gmaps_geocode):
    test_address = "1600 Amphitheatre Parkway, Mountain View, CA"
    expected_latitude, expected_longitude = 37.4223096, -122.0846244  # Googleplex coordinates

    # Set up the mock to return the expected response structure
    mock_gmaps_geocode.return_value = [
        {
            'geometry': {
                'location': {'lat': expected_latitude, 'lng': expected_longitude}
            }
        }
    ]

    # Call the function with an address that's not in the cache
    latitude, longitude = geocode_address(test_address)

    # Verify that the mock was called with the expected address
    mock_gmaps_geocode.assert_called_once_with(f"{test_address}, Norman, Oklahoma, USA")

    # Assert that the function returns the expected coordinates
    assert latitude == expected_latitude, "Latitude does not match the expected value"
    assert longitude == expected_longitude, "Longitude does not match the expected value"