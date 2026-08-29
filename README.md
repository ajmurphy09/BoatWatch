# BoatWatch cloud starter

A zero-hardware BoatWatch prototype using GitHub Pages + GitHub Actions.

## First deployment

1. Create a new **public** GitHub repository, for example `boatwatch`.
2. Upload all files in this package, including the hidden `.github` folder.
3. Commit them to the `main` branch.
4. Open **Settings → Pages**.
5. Under **Build and deployment → Source**, choose **GitHub Actions**.
6. Open **Actions → Update BoatWatch and deploy** and run it once if it did not run automatically.
7. Return to **Settings → Pages** and use **Visit site**.

The first version intentionally displays DEMO DATA. Once the cloud deployment works,
the next step is connecting `scripts/update_vessels.py` to a live vessel/AIS data source.

## Privacy

Do not put a home address or exact home coordinates in `index.html`, JSON, workflow files,
or the public repository. When live tracking is added, use a broader watch region or keep
sensitive API credentials in GitHub repository secrets.
