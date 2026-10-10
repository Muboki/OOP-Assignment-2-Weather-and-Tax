# OOP Assignment 2: Weather Forecast and Uganda Tax Engine

This repository contains my work for the Advent 2026 Python assignment.

## Project status

- Mini-Project 1: Weather Forecast — implemented and tested.
- Mini-Project 2: Uganda Tax Engine — not yet implemented.

## Folder structure

- `notebooks/`: executable notebooks, explanations and results.
- `src/`: reusable Python functions and classes.
- `tests/`: automated tests.
- `data/`: saved API responses for offline testing.

## Setup on Windows

Run these commands in PowerShell from the repository's main folder:

```powershell
# Create a local Python environment.
py -m venv .venv

# Install the recorded dependencies.
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Configure your own university email for identifying weather API requests:

```powershell
# Read your email without embedding it in shared source code.
$email = Read-Host "Enter your university email"

# Save the setting for your Windows user account.
[Environment]::SetEnvironmentVariable(
    "WEATHER_CONTACT_EMAIL",
    $email,
    "User"
)
```

Close all VS Code windows and reopen VS Code from the Start menu
after setting the environment variable.

## Run the weather notebook

Open `notebooks/project1_weather.ipynb` in VS Code and select the
project's `.venv` Python environment as the notebook kernel.

The configuration cell controls the location name, forecast length
and candidate number. When changing locations, run the candidate
lookup first, inspect the displayed choices and update
`location_choice` before continuing.

Use **Restart**, followed by **Run All**, to check execution from
a fresh kernel. Live API requests require an internet connection.
Expected failures in the error demonstrations are caught and displayed.

## Run the offline tests

```powershell
# Run the weather tests without contacting the APIs.
.\.venv\Scripts\python.exe -m pytest tests/test_weather.py -q
```

The six weather tests passed. They check selected parsing behaviours
using saved JSON, rather than proving forecast accuracy.


## Weather project findings

The application uses Open-Meteo to find candidate locations and
retrieve daily forecasts. It displays temperatures, precipitation,
wind speeds and readable weather descriptions in a table, chart
and text summary.

The recorded Kampala forecast for 10–14 October 2026 had temperatures
ranging from 17.9°C to 27.2°C, total precipitation of 32.5 mm and
a highest daily maximum wind speed of 13.3 km/h. These are forecast
snapshot values, not observed weather. Later requests may differ.

MET Norway provides a second-source snapshot. Its timestamps are
converted to the selected location's time zone, and wind speeds
are converted from m/s to km/h. Temperature comparisons use its
available time steps, which do not necessarily capture full daily
minimum and maximum temperatures.

The notebook demonstrates an unknown city, invalid latitude,
simulated network failure and a tiny timeout. Request functions
limit retries and report failures through a custom WeatherError.

## Saved samples and limitations

Files in `data/` support offline tests and reproducible examples.
Existing samples are preserved rather than overwritten on each run.

The MET Norway sample is reused without automatic refreshing.
Open-Meteo's live forecast can therefore have a different issue
time, and eventually the two sources may have no overlapping dates.

Parsing checks cover required fields and list lengths, but do not
validate every measurement's type, range or physical consistency.
Passing tests does not guarantee that all possible errors are covered.

## Data sources and licences

- Open-Meteo forecasts: https://open-meteo.com/
- Open-Meteo geocoding, based on GeoNames:
  https://open-meteo.com/en/docs/geocoding-api
- Open-Meteo licence: https://open-meteo.com/en/licence
- Open-Meteo service terms: https://open-meteo.com/en/terms
- MET Norway: https://api.met.no/
- MET Norway licensing: https://api.met.no/doc/License
- MET Norway service terms: https://api.met.no/doc/TermsOfService
- CC BY 4.0: https://creativecommons.org/licenses/by/4.0/

Provider documentation was checked on 10 October 2026.
Open-Meteo API data use CC BY 4.0, while its free hosted service is
restricted to non-commercial use. MET Norway lists NLOD 2.0 and
CC BY 4.0 unless otherwise specified.

Displayed results involve formatting, code interpretation,
unit and time-zone conversion, and summarisation. Provider credit
does not imply endorsement of this project.

## Additional library justification

Jinja2 supports pandas' formatted notebook tables. Standard-library
pathlib handles file paths, unittest.mock simulates failures, and
re supports the report word-count check. Pytest provides automated
tests, while ipykernel enables notebook execution in VS Code.

## AI assistance

I used ChatGPT for step-by-step guidance on code structure,
HTTP requests, error handling, testing and interpretation.
I ran the code and tests locally, checked the outputs and used
the explanations to revise the implementation.