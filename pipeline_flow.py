import subprocess
from prefect import flow, task
from prefect.schedules import Cron

# Reuse the exact same functions from ingest.py — no duplicate logic
from ingest import (fetch_recently_played, transform, load, get_unique_artists,
                    fetch_and_load_artist_genres, fetch_and_load_audio_features)

@task(retries=2, retry_delay_seconds=30)
def ingest_task():
    raw_tracks = fetch_recently_played()
    rows = transform(raw_tracks)
    load(rows)
    fetch_and_load_artist_genres(get_unique_artists(raw_tracks))
    fetch_and_load_audio_features([item["track"]["id"] for item in raw_tracks])

@task(retries=1)
def dbt_run_task():
    result = subprocess.run(
        ["dbt", "run"],
        cwd="spotify_dbt",
        capture_output=True,
        text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        raise Exception(f"dbt run failed:\n{result.stderr}")

@task(retries=1)
def dbt_test_task():
    result = subprocess.run(
        ["dbt", "test"],
        cwd="spotify_dbt",
        capture_output=True,
        text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        raise Exception(f"dbt test failed:\n{result.stderr}")

@flow(name="spotify-daily-pipeline")
def spotify_pipeline():
    ingest_task()
    dbt_run_task()
    dbt_test_task()

if __name__ == "__main__":
    spotify_pipeline.serve(
        name="spotify-daily-deployment",
        schedule=Cron("0 20 * * *", timezone="Asia/Kolkata"),
    )