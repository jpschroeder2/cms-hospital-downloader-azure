import azure.functions as func
import logging
import json
import re
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import requests
from tqdm import tqdm
from azure.storage.blob import BlobServiceClient, ContentSettings

app = func.FunctionApp()

CONTAINER_NAME = "hospital-data"
METADATA_BLOB_NAME = "metadata.json"

def get_blob_service_client():
    connection_string = os.environ.get("STORAGE_CONNECTION_STRING") or os.environ.get("AzureWebJobsStorage")
    if not connection_string:
        raise ValueError("STORAGE_CONNECTION_STRING or AzureWebJobsStorage is required")
    return BlobServiceClient.from_connection_string(connection_string)

def ensure_container(client: BlobServiceClient):
    container_client = client.get_container_client(CONTAINER_NAME)
    try:
        container_client.get_container_properties()
    except Exception:
        container_client.create_container()
    return container_client

def to_snake_case(name: str) -> str:
    if not name:
        return "unnamed_column"
    name = re.sub(r"['’]", "", name)
    name = re.sub(r"[^a-zA-Z0-9]+", " ", name)
    name = name.strip().lower()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"^_+|_+$", "", name)
    return name

def load_metadata(container_client) -> dict:
    blob_client = container_client.get_blob_client(METADATA_BLOB_NAME)
    try:
        download_stream = blob_client.download_blob()
        return json.loads(download_stream.readall().decode('utf-8'))
    except Exception:
        return {}

def save_metadata(container_client, metadata: dict):
    blob_client = container_client.get_blob_client(METADATA_BLOB_NAME)
    data = json.dumps(metadata, indent=2, ensure_ascii=False).encode('utf-8')
    blob_client.upload_blob(data, overwrite=True)

def get_hospital_datasets() -> list:
    logging.info("Fetching dataset list from CMS metastore...")
    try:
        response = requests.get("https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items", timeout=30)
        response.raise_for_status()
        datasets = response.json()
    except Exception as e:
        logging.error(f"Failed to fetch dataset list: {e}")
        return []

    hospital_datasets = []
    for ds in datasets:
        themes = ds.get("theme", [])
        if isinstance(themes, list) and any("Hospitals" in theme for theme in themes):
            for dist in ds.get("distribution", []):
                if dist.get("mediaType") == "text/csv" and dist.get("downloadURL"):
                    hospital_datasets.append({
                        "identifier": ds.get("identifier"),
                        "title": ds.get("title", "Unknown"),
                        "modified": ds.get("modified"),
                        "download_url": dist["downloadURL"],
                    })
                    break
    logging.info(f"Found {len(hospital_datasets)} hospital-related datasets.")
    return hospital_datasets

def process_dataset(dataset: dict, metadata: dict, container_client) -> str:
    ds_id = dataset["identifier"]
    last_modified = dataset.get("modified")
    if ds_id in metadata and metadata[ds_id] == last_modified:
        return f"Skipped (unchanged): {dataset['title'][:60]}"

    try:
        logging.info(f"Downloading: {dataset['title'][:70]}...")
        df = pd.read_csv(dataset["download_url"], dtype=str, low_memory=False)
        df.columns = [to_snake_case(col) for col in df.columns]

        timestamp = int(time.time())
        filename = f"raw/{ds_id}_{timestamp}.csv"

        blob_client = container_client.get_blob_client(filename)
        csv_data = df.to_csv(index=False).encode('utf-8')
        blob_client.upload_blob(csv_data, overwrite=True, content_settings=ContentSettings(content_type='text/csv'))

        metadata[ds_id] = last_modified
        return f"Success: {filename} ({len(df):,} rows)"
    except Exception as e:
        logging.error(f"Failed {ds_id}: {type(e).__name__} - {e}")
        return f"Failed {ds_id}: {type(e).__name__} - {e}"

def run_hospital_data_fetch() -> list:
    start_time = time.time()
    max_workers = int(os.getenv("MAX_WORKERS", 12))

    blob_client = get_blob_service_client()
    container_client = ensure_container(blob_client)
    metadata = load_metadata(container_client)
    hospital_datasets = get_hospital_datasets()

    if not hospital_datasets:
        logging.warning("No hospital datasets found.")
        return ["No datasets found"]

    logging.info(f"Starting parallel processing with {max_workers} workers...")

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ds = {executor.submit(process_dataset, ds, metadata, container_client): ds for ds in hospital_datasets}

        for future in tqdm(as_completed(future_to_ds), total=len(future_to_ds), desc="Processing datasets"):
            result = future.result()
            results.append(result)
            if "Success" in result or "Skipped" in result:
                save_metadata(container_client, metadata)

    save_metadata(container_client, metadata)
    elapsed = time.time() - start_time
    logging.info(f"\nJOB COMPLETED in {elapsed/60:.1f} minutes\n" + "\n".join(results))
    return results

@app.timer_trigger(schedule="%TIMER_SCHEDULE%", arg_name="mytimer", run_on_startup=False, use_monitor=False)
def download_hospital_data_timer(mytimer: func.TimerRequest):
    if mytimer.past_due:
        logging.warning("The timer is past due!")
    logging.info("🚀 Timer-triggered CMS Hospital Data fetch started.")
    run_hospital_data_fetch()
    logging.info("✅ Timer-triggered fetch completed.")

@app.route(route="download-hospital-data", methods=["GET", "POST"], auth_level=func.AuthLevel.FUNCTION)
def download_hospital_data_http(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("🚀 HTTP-triggered CMS Hospital Data fetch started.")
    results = run_hospital_data_fetch()
    return func.HttpResponse(
        body=f"✅ CMS Hospital Data fetch completed!\nProcessed {len(results)} datasets.\nCheck Function Logs for details.",
        status_code=200
    )