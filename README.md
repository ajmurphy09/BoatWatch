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


## Feature upgrade

This version adds:
- plain-English vessel type when CESARops supplies type metadata
- vessel length, call sign, and IMO when available
- likely / may / unlikely visible labels based on distance and vessel size
- plain-English movement / closest-approach explanations
- special-purpose badges (tug, pilot, rescue, Coast Guard, law enforcement,
  research, dredging, fishing, passenger, pleasure craft, etc.) when supported
  by AIS metadata/name
- expandable details on the primary visible vessel
- same-name vessel disambiguation using MMSI and other available metadata

Visibility labels are estimates only and do not account for current haze,
weather, terrain, or obstructions.


## Dummy traffic test mode

The production vessel feed remains untouched.

To render test vessels in the browser, append:

    ?test=1

to the normal GitHub Pages URL.

Example:

    https://YOUR-USERNAME.github.io/BoatWatch/?test=1

Test mode supplies:
- 2 Visible Now vessels
- 2 Coming Up vessels
- 2 Background vessels
- cargo, pleasure craft, tug, Coast Guard, research, and sailing examples
- duplicate SELAH names for identity testing
- visibility badges, movement explanations, CPA values, and metadata

Remove `?test=1` to immediately return to real CESARops data.


## UX upgrade

This version makes each section answer a distinct question:

- Visible Now: every visible vessel gets a useful identification card and a
  prominent direction to look.
- Coming Up: emphasizes estimated time to the 15-mile visible zone instead of
  showing an "unlikely visible" badge.
- Background: starts collapsed and can be expanded for situational awareness.
- Every vessel can expose identifying details such as MMSI, call sign, IMO,
  type, length, destination, AIS age, and source when the source provides them.

The ETA to the visible-zone boundary is an approximation based on current
distance, current speed, and an approaching status.
