import time
import datetime
import re

from util import get_link_data, post_data, build_data, cancel_import, get_user_yn, flip_pages, ImportLogger
from config import JIRA_URL, JIRA_HEADERS, SOURCE_API_URL, SOURCE_HEADERS, IMPORT_NAME

LOGGER = ImportLogger("main", re.sub(r'\s+', '-', IMPORT_NAME.lower())).get_logger()

jira_status = ""
jira_start = ""
jira_mapping = ""

start_time = time.time()

# Initialize relevant links and connections to both Jira and the source API. Returns true if initialization was successful,
# and false if it was not.
def init():
    LOGGER.info(f"Starting import [{IMPORT_NAME}]")

    jira_links = get_link_data(JIRA_URL, JIRA_HEADERS, LOGGER)
    source_links = get_link_data(SOURCE_API_URL, SOURCE_HEADERS, LOGGER)

    if (not jira_links or not source_links):
        return False

    if (not jira_links.ok):
        LOGGER.error(f"Jira connection failed: Response {jira_links.status_code}")
        return False

    if (not source_links.ok):
        LOGGER.error(f"Source connection failed: Response {source_links.status_code}")
        return False

    global jira_status, jira_start, jira_mapping, data_list

    # Save relevant links from the Jira connection
    jira_json = jira_links.json()

    jira_status = jira_json["links"].get("getStatus")
    jira_start = jira_json["links"].get("start")
    jira_mapping = jira_json["links"].get("mapping")

    LOGGER.info(f"Jira connection successful: Response {jira_links.status_code}")

    # Save JSON from source API
    source_json = source_links.json()

    data_list = flip_pages(source_json, LOGGER)

    if not data_list:
        LOGGER.error("Source connection was successful, but no data was found.")
        return False
    
    LOGGER.info(f"Successfully loaded {len(data_list)} entries from {SOURCE_API_URL}.")
    LOGGER.info(f"Source connection successful: Response {source_links.status_code}")

    return True

def main():
    if (init()):

        status = get_link_data(jira_status, JIRA_HEADERS, LOGGER)
        status = status.json()

        if (status.get("status") == "IDLE"):
            entries = len(data_list)
            LOGGER.info(f"Starting {entries} imports.")

            # Main loop to import each entry into CMDB
            for key, entry in enumerate(data_list, start = 1):
                LOGGER.info(f"* Preparing import {key} of {entries}...")
                if (not post_data(jira_start, build_data(entry, LOGGER), LOGGER)):
                    LOGGER.error(f"Remaining {entries - key} imports have been cancelled.")
                    break

        else:
            LOGGER.error(f"Jira is currently busy! Current import status: {status.get('status')}")

            exec_status = get_link_data(status.get("links").get("getExecutionStatus"), JIRA_HEADERS, LOGGER)
            execution_id = exec_status.json().get("executionId")

            LOGGER.warning(f"Current import status: {exec_status.json().get('status')}")

            if(execution_id):
                LOGGER.warning(f"Import [{execution_id}] is currently in progress. Would you like to cancel it?")

                cancel = get_user_yn("Cancel current import?")

                if (not cancel):
                    LOGGER.info(f"Import [{execution_id}] will not be cancelled. To get this prompt again, rerun main().")
                else:
                    cancel_import(f"{jira_start.replace('/assets/', '/insight/')}/{execution_id}", execution_id, LOGGER)
            
    else:
        LOGGER.error("Initialization failed, aborting.")

    LOGGER.info(f"Finished running in {datetime.timedelta(seconds = time.time() - start_time)}.")

if __name__ == "__main__":
    main()