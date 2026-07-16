# BFT Spring Route Profile Dashboard

A public-facing Streamlit dashboard that reads route-profile CSV files directly from the repository.

## Repository structure

```text
bft-spring-route-dashboard/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
└── data/
    ├── RouteProfile_Spring_Rt 1.csv
    ├── RouteProfile_Spring_Rt 2.csv
    └── ...
```

## Required CSV columns

Each route CSV should include:

```text
Day
Trip
AverageDailyBoardings
MedianPassengerLoad
Early
OnTime
Late
TotalFareCounts
```

Example `Trip` value:

```text
2 - 2W - 08:30
```

## Create the GitHub repository

1. Sign in to GitHub.
2. Select **New repository**.
3. Name it, for example, `bft-spring-route-dashboard`.
4. Set the repository to **Public**.
5. Upload `app.py`, `requirements.txt`, `README.md`, `.gitignore`, and the `data` folder.
6. Commit the files.

## Deploy on Streamlit Community Cloud

1. Sign in to Streamlit Community Cloud with GitHub.
2. Select **Create app**.
3. Choose your public repository.
4. Set the main file path to:

```text
app.py
```

5. Deploy the app.

## Adding or replacing route data

Upload the new CSV to the `data` folder and commit the change. The app scans every CSV in that folder automatically.

Recommended file names:

```text
RouteProfile_Spring_Rt 1.csv
RouteProfile_Spring_Rt 2.csv
RouteProfile_Spring_Rt 26S.csv
```

## Data privacy

Only upload data that are approved for public release. Do not include personally identifiable information, internal credentials, database connection information, or restricted operational data.
