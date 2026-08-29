# Green Bay Ship Watch — Cloud Edition

This is the cloud conversion of the existing local CESARops vessel watcher.

It preserves:
- CESARops AIS source
- 50-mile collection radius
- 15-mile visible radius
- moving/stationary freshness rules
- navigation-aid and fixed-infrastructure filtering
- approaching / passing / departing classification
- closest-point-of-approach calculations
- Visible Now / Coming Up / Background dashboard

## Privacy change

The exact watch coordinates are NOT stored in this public repository and are
NOT sent to the browser. They are supplied to the GitHub Action using repository
secrets named:

- SITE_LATITUDE
- SITE_LONGITUDE

## Install over the existing BoatWatch demo repo

Replace the demo repo contents with the contents of this package.

Then in GitHub:
Settings → Secrets and variables → Actions → New repository secret

Create SITE_LATITUDE and SITE_LONGITUDE using the coordinates from the existing
local config/locations.json file.

Do not upload the original .env file or config/locations.json.

Settings → Pages → Source should remain GitHub Actions.

Then open Actions → Update Green Bay Ship Watch → Run workflow.

The Action fetches live CESARops data, runs the existing watch logic, generates
data/vessels.json, and deploys the static dashboard to GitHub Pages.

The scheduled workflow requests a new cloud snapshot every 5 minutes. GitHub
scheduled workflows can occasionally run later than the nominal schedule.
The web page checks for newly deployed data every 60 seconds.
