from datetime import datetime, timedelta
from app.utils.weather import fetch_weathercode_using_meteo

def test_fetch_weather_data_real_request():
    # Known coordinates for testing, e.g., Norman, OK
    latitude, longitude = 35.2226, -97.4395
    # Use a fixed date known to have weather data (using the date in api website)
    test_date = ('2024-03-28')
    # Choose an hour known to be within the data range, e.g., 12 PM UTC
    test_hour = 12

    
    weather_code = fetch_weathercode_using_meteo(latitude, longitude, test_date, test_hour)
    assert weather_code == 0
    