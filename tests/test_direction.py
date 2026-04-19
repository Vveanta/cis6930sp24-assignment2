from app.utils.side import calculate_street_position

def test_calculate_street_position():
    # Assuming CENTER_OF_TOWN_LAT, CENTER_OF_TOWN_LON = 35.220833, -97.443611
    assert calculate_street_position(35.1817934, -97.4162307) == "SE"  
    assert calculate_street_position(35.215, -97.45) == "SW"  