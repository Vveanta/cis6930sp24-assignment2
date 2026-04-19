# Norman PD Incident Data Visualizer

## Project Overview
This project provides a web platform that processes and visualizes incident data from the Norman, Oklahoma Police Department's daily incident reports. Users can upload reports in CSV, PDF, or URL formats, and the application extracts, augments, and visualizes the data to reveal insights about incident patterns. The visualizations aid in identifying trends such as peak times, high-incident areas, and weather conditions associated with incidents. The platform also enables users to download an augmented dataset with additional analytical fields.

> **Note**: This application is designed to analyze and visualize Norman PD incident reports found on the [Norman PD website](https://www.normanok.gov/public-safety/police-department/crime-prevention-data/department-activity-reports).

### Key Features
- **Multi-Format Upload Support**: Users can upload files in CSV, PDF, or as URLs linking to incident reports.
- **Data Augmentation**: Each incident is enriched with additional fields, including Weather, Location Rank, and Incident Rank.
- **Visual Analytics**: Displays 7 key visualizations, including incident trends, weather patterns, and hotspot maps.
- **Data Download**: Users can download the augmented dataset for further analysis in CSV format.

---

## Project Structure and File Overview
- **/app**: Contains the core web app code, templates, and utilities.
  - **templates/**: HTML templates for the frontend pages.
  - **utils/**: Helper scripts for data processing, including geocoding, ranking, weather lookups, and data augmentation.
  - **resources/**: Stores the SQLite database and augmented CSV files.
- **/tests**: Includes test cases for verifying data processing functions.
- **run.py**: The main entry point for running the Flask application.
- **Pipfile**: Manages dependencies using Pipenv.

---

## Installation and Setup
Ensure Python 3.11 or later is installed on your system.

### Step 1: Clone the Repository
```bash
git clone https://github.com/Vveanta/norman-incident-vis.git
cd norman-incident-vis
```

### Step 2: Install Dependencies
From the project root, install everything declared in the `Pipfile` (this creates or uses the project virtualenv and installs Flask, PyMuPDF, etc.):

```bash
pipenv install
```

If you do not use Pipenv, install the pinned set from `requirements.txt` **into the same environment** you will use to run the app (for example, after activating your venv):

```bash
pip install -r requirements.txt
```

### Step 3: Configure `.env`

Copy the example environment file and update it with your actual Google Maps API key:

```bash
cp .example_env .env
```

Then, open `.env` and replace the placeholder with your API key:

```env
GOOGLE_API_KEY=YOUR_ACTUAL_API_KEY_HERE
```

### Step 4: Run the application locally

Run everything from the **project root**. Use **`pipenv run`** (or `pipenv shell` first) so you use this project’s Python—not a global/Homebrew `flask` (which often causes missing packages such as `fitz`).

#### Option A — Simple (no Redis)

Augmentation runs inside the web process. **Do not** set `REDIS_URL` in `.env` (or comment it out).

```bash
export FLASK_APP=run
pipenv run python -m flask run --port 5200
```

Then open **http://localhost:5200**.

With an activated shell:

```bash
pipenv shell
export FLASK_APP=run
python -m flask run --port 5200
```

Sanity checks: `which python` should point under `.local/share/virtualenvs/...`; `python -c "import fitz"` should work.

#### Option B — With Celery + Redis (same as production)

For the **processing page** and background augmentation:

1. Start Redis: `docker compose up -d redis` (see `docker-compose.yml`).
2. In `.env`: `REDIS_URL=redis://localhost:6379/0` and `GOOGLE_API_KEY=...`.
3. **Terminal 1 — worker:**

   ```bash
   pipenv run celery -A app.celery_app worker --loglevel=info
   ```

4. **Terminal 2 — web:**

   ```bash
   export FLASK_APP=run
   pipenv run python -m flask run --port 5200
   ```

#### Optional: Gunicorn locally

```bash
pipenv run gunicorn run:app -c gunicorn.conf.py
```

Render sets `PORT`; locally the config falls back to port **8000** unless you set `PORT`.

#### Troubleshooting: `ModuleNotFoundError` (e.g. `No module named 'fitz'`)

Use **`pipenv run python -m flask ...`** or **`python -m flask ...`** after `pipenv shell`, not a bare **`flask`** from Homebrew.

---

### Deployment (cloud)

Step-by-step for **Render and other hosts** (build/start commands, environment variables, Redis, worker) is in **`deployment_readme.md`**.

---

## File Upload Methods and Requirements
Users can upload incident data in multiple formats. Each file should follow the data structure specified by the Norman PD, containing fields such as Date/Time, Incident Number, Location, Nature, and Incident ORI.

### Supported Upload Types
1. **CSV Files**: Direct upload of CSV files containing URLs to incident PDFs hosted on the Norman PD website.
2. **PDF Files**: Upload PDFs from the Norman PD’s incident summary reports.
3. **URLs**: Provide URLs directly to the PDF incident reports hosted on the Norman PD website.
4. **Default PDFs**: Select from a set of pre-loaded default PDFs available on the platform.

### Usage Limits
The platform processes up to three incident reports at a time. For further processing, please contact the project owner.

---

## Data Processing and Augmentation
The initial data includes the following fields extracted from the Norman PD reports:
- **Date/Time**: Timestamp of the incident.
- **Incident Number**: Unique identifier for each incident.
- **Location**: Place where the incident occurred.
- **Nature**: Type/category of the incident.
- **Incident ORI**: Identifier indicating the originating agency or unit.

The application augments this data with additional fields to enable comprehensive analysis:

### Augmented Data Fields
1. **Day of the Week**: Numeric value from 1 (Sunday) to 7 (Saturday).
2. **Time of Day**: Hour of the incident in 24-hour format.
3. **Weather**: WMO (World Meteorological Organization) code indicating weather conditions at the time of the incident.
4. **Location Rank**: Rank of the location based on incident frequency.
5. **Location**: Name of the incident location from the original data.
6. **Side of Town**: Directional classification (e.g., N, S, E) relative to Norman’s town center.
7. **Incident Rank**: Rank of the incident type based on frequency.
8. **Nature**: Category or type of the incident (from the original data).
9. **EMSSTAT**: Boolean indicating if the incident ORI is "EMSSTAT" or if related incidents occur at the same time/location.

---

## Data Augmentation Details
The main goal of this project is to enhance the structured dataset extracted from Norman PD reports by adding attributes to each record. Below is a breakdown of each attribute, including how it is calculated and integrated into the dataset.

### Day of the Week and Time of Day
The "Day of the Week" and "Time of Day" attributes are derived using Python's `datetime` module. By converting the `incident_time` field to a `datetime` object, we extract both the day of the week and the hour of the incident. The `isoweekday()` method provides the day as an integer (1 for Monday, 7 for Sunday), while the `hour` attribute gives the hour of the incident.

### Weather
The "Weather" attribute is determined by querying the Open-Meteo API using the latitude, longitude, and date of each incident. The API response includes historical weather data, from which we extract the WMO weather code for the specific hour of the incident. This process is handled in the `fetch_weather_data` function.

### Location Rank and Incident Rank
Both "Location Rank" and "Incident Rank" are based on the frequency of each unique location and incident type, respectively. The `calculate_frequencies` function counts occurrences, while `assign_ranks` assigns a rank based on frequency, accounting for ties.

### Side of Town
To categorize each incident's "Side of Town," we first geocode the location to obtain latitude and longitude (using the Google Maps API). The bearing from the town center (35.220833, -97.443611) is calculated, and based on this angle, the `determine_side_of_town` function classifies each incident as being in one of eight directional categories (N, S, E, W, NW, NE, SW, SE).

### Nature
The "Nature" field is a direct copy from the original data, representing the type or category of the incident.

### EMSSTAT
The "EMSSTAT" field is a boolean indicating whether the incident ORI is `EMSSTAT` or if the two following records share the same time and location with an ORI of `EMSSTAT`. This check is implemented in the `check_emsstat` function.

### Augmentation Process Implementation
The `augment_data` function coordinates the data augmentation process. It retrieves incidents from the database, augments each record with the new attributes, and saves the results as a new dataset for visualization and download.

---

## Data Visualizations
The platform provides a comprehensive visualization dashboard to explore incident trends and patterns. Each visualization leverages `Plotly` for interactive graphs and `Leaflet` for maps.

### Visualization Types
1. **Incidents by Day of the Week**:
   - **Chart Type**: Bar Chart
   - **Description**: Shows the frequency of incidents by day of the week to highlight weekly trends.
   
2. **Incidents by Time of Day**:
   - **Chart Type**: Line Chart
   - **Description**: Visualizes incident frequency by hour, identifying peak times.

3. **Weather Conditions**:
   - **Chart Type**: Bar Chart with Icons
   - **Description**: Displays incident frequency by WMO weather codes. Each weather type includes a descriptive icon from the WMO Code Table.

4. **Incident Hotspots Map**:
   - **Visualization Tool**: Leaflet
   - **Description**: Geographical map showing the distribution of incidents across the city. Color intensity indicates incident density, with red as the highest frequency.

5. **Top Incident Types**:
   - **Chart Type**: Horizontal Bar Chart
   - **Description**: Lists the top 20 incident types, with the option to adjust the number of types displayed.

6. **Side of Town Distribution**:
   - **Chart Type**: Pie Chart
   - **Description**: Depicts the proportion of incidents across different areas (e.g., N, S, E) within Norman, Oklahoma.

7. **EMSSTAT Incidents**:
   - **Chart Type**: Pie Chart
   - **Description**: Shows the proportion of incidents categorized as EMSSTAT (emergency medical service) versus non-emergency incidents.

---

## Augmented Data Download
After processing, users can download the augmented dataset from the results page. The CSV file includes all original fields plus the newly added fields, offering a rich dataset for further analysis.

---

## Known Issues and Assumptions
- **Geocoding Accuracy**: Accuracy depends on the Google Maps API, which has rate limits that may affect response times.
- **Weather Data Efficiency**: Weather data retrieval can be slow, especially for large datasets. Caching mechanisms could improve efficiency.
- **File Processing Limit**: Only three files are processed per session to manage API calls and processing load.

---

## External Resources
- **Google Maps API**: Used for geocoding locations.
- **Open-Meteo API**: Provides historical weather data by location.
- **WMO Code Table**: Used for interpreting weather conditions.

---


## Contact
- **Name**: Vedansh Maheshwari
- **LinkedIn**: [Vedansh Maheshwari](https://www.linkedin.com/in/vedansh-mahe)
