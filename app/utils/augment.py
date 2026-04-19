import csv
import datetime
import os
import sqlite3
from .geocoding import geocode_address
from .weather import fetch_weathercode_using_meteo
from .side import calculate_street_position
from .rank import calculate_frequencies, assign_ranks
from .emstat import check_emsstat
def create_geocode_table(geocode_db_path="resources/normanpd.db"):
    conn = sqlite3.connect(geocode_db_path)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS geocodes (
            location TEXT PRIMARY KEY,
            latitude REAL,
            longitude REAL
        );
    ''')
    conn.commit()
    conn.close()
def augment_data(db_path):
    create_geocode_table(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM incidents')
    incidents = cursor.fetchall()
    # Convert tuple to dict for easier manipulation
    incidents_dicts = [{'Incident_time': i[0], 'Incident Number': i[1], 'Location': i[2], 'Nature': i[3], 'Incident ORI': i[4]} for i in incidents]
    # Calculate frequencies and then ranks for locations and natures
    location_frequencies = calculate_frequencies(incidents_dicts, 'Location')
    nature_frequencies = calculate_frequencies(incidents_dicts, 'Nature')
    location_ranks = assign_ranks(location_frequencies)
    nature_ranks = assign_ranks(nature_frequencies)

    # Placeholder for augmented data
    augmented_incidents = []
    for index, incident in enumerate(incidents_dicts):
        incident_time = datetime.datetime.strptime(incident['Incident_time'], "%m/%d/%Y %H:%M")
        # Day of the Week (1=Sunday, 7=Saturday)
        dow = incident_time.isoweekday()
        adow = (dow % 7) + 1
        incident['Day Of The Week'] = adow
        # Time of Day (hour)
        incident['Time Of Day'] = incident_time.hour
        # latitude, longitude = geocode_location(location)  # Assuming implementation
        latitude, longitude = geocode_address(incident['Location'], db_path)
        
        if latitude is not None and longitude is not None:
            incident['Weather'] = fetch_weathercode_using_meteo(latitude, longitude, incident_time.strftime("%Y-%m-%d"), incident_time.hour)
            incident['Side of Town'] = calculate_street_position(latitude, longitude)
        else:
            incident['Weather'] = 'Unknown'
            incident['Side of Town'] = 'Unknown'

        incident['Location Rank'] = location_ranks[incident['Location']]
        incident['Nature Rank'] = nature_ranks[incident['Nature']]
        incident['EMSSTAT'] = check_emsstat(incidents_dicts, index)
        augmented_incidents.append(incident)

    resources_dir = os.path.join('app', 'resources')
    if not os.path.exists(resources_dir):
        os.makedirs(resources_dir)
    csv_file_path = os.path.join(resources_dir, 'augmented_data.csv')
    with open(csv_file_path, 'w', newline='') as file:
        writer = csv.writer(file, delimiter=',')
        writer.writerow(["Day of the Week", "Time of Day", "Weather", "Location Rank", "Location", "Side of Town", "Incident Rank", "Nature", "EMSSTAT"])
        for incident in augmented_incidents:
            writer.writerow([
                incident['Day Of The Week'],
                incident['Time Of Day'],
                incident['Weather'],
                incident['Location Rank'],
                incident['Location'],
                incident['Side of Town'],
                incident['Nature Rank'],
                incident['Nature'],
                incident['EMSSTAT']
            ])
    return csv_file_path
