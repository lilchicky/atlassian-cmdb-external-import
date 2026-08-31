import requests
import uuid
import logging
import os
import glob

from pathlib import Path
from config import (
    TIMEOUT, 
    JIRA_HEADERS, 
    DATA_MAPS, 
    POST_TIMEOUT, 
    SOURCE_HEADERS, 
    URL_REPLACEMENT_KEY, 
    SOURCE_URL, 
    JIRA_CANCELLATION_HEADERS, 
    DATA_TRANSLATIONS, 
    WRITE_EMPTY_DATA, 
    LOGGING_LEVEL, 
    LOG_FOLDER, 
    LOG_FILE_PREFIX, 
    LOG_FILE_SUFFIX, 
    WRITE_LOGS_TO_FILE, 
    MAX_SAVED_LOGS
)

def get_link_data(source_url: str, source_headers: dict, logger: logging.Logger) -> any:
    """
    Attempt to get data from a URL via a GET request.

    [source_url]: The source URL to attempt to retrieve data from.
    [source_headers]: Any relevant headers needed to connect to the source API.
    
    Returns the retireved data if successful, otherwise returns None.
    """
    try:
        data = requests.get(url = source_url, headers = source_headers, timeout = TIMEOUT)
        data.raise_for_status()

        logger.debug(f"Get request from {source_url} connected successfully.")
        
        return data
    
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection timeout connecting to {source_url}: {e}")
        logger.error(f"Timeout is currently set to {TIMEOUT} seconds. The request may need more time to connect, or the request may not have been able to connect at all.")

        return None

def get_source_data(source_path: str, data: set, path_desc: str, logger: logging.Logger) -> any: 
    """
    Resolve some path path.to.value and retrieve the data from that location. See DATA_MAPS in config.py for path syntax.

    [source_path]: The path to follow to retrieve some value, with the key being the last element of the path.
    [data]: The "source" JSON at the top of [source_path]. The function will search through [data] to find the desired value.
    [path_desc]: What is the purpose of the data being retrieved. Used for debug logging.
    
    Returns whatever data was found at the end of the path, if any.
    """
    logger.debug(f"Resolving path [{source_path}] for {path_desc}.")
    path = f"{source_path}".split(".")

    if (path[0].startswith("@")):
        replacement_resolved = {}

        for key in URL_REPLACEMENT_KEY:
            replacement_resolved.update({key: get_source_data(URL_REPLACEMENT_KEY[key], data, f"url replacement key [{key}]", logger)})

        resolved_url = f"{SOURCE_URL}{(path[0].removeprefix('@')).format(**replacement_resolved)}"
        logger.debug(f"URL resolved to {resolved_url}")

        new_data = get_link_data(resolved_url, SOURCE_HEADERS, logger)
        new_data.raise_for_status()

        data = new_data.json()
        path.pop(0)

    def walk(current, index):
        if index == len(path):
            return current

        part = path[index]

        if part.startswith("*"):
            if not isinstance(current, list):
                return ""

            index_val = part[1:]

            if index_val:
                data_index = int(index_val)

                if (data_index >= len(current)):
                    return ""

                return walk(current[data_index], index + 1)

            results = []
            for item in current:
                if current:
                    results.append(walk(item, index + 1))

            return results if results else ""
        
        if isinstance(current, dict) and part in current:
            return walk(current[part], index + 1)

        return ""

    result = walk(data, 0)

    if isinstance(result, list):
        return "" if not all(result) else result

    return result

def cancel_import(cancel_url: str, execution_id: str, logger: logging.Logger) -> bool:
    """
    Attempts to cancel the current import using it's cancel URL.

    [cancel_url]: The cancel url of the import currently being submitted.
    [execution_id]: The execution ID of the ongoing import, for logging.

    Returns true if the cancel was successful, false otherwise.
    """
    logger.info(f"Cancelling import [{execution_id}]...")

    del_request = requests.delete(url = cancel_url, headers = JIRA_CANCELLATION_HEADERS)
    del_request.raise_for_status()

    if (del_request.ok):
        logger.info(f"Import [{execution_id}] was successfully cancelled.")
        return True
        
    logger.error(f"Cancellation of import [{execution_id}] failed: Response {del_request.status_code}")
    logger.error(f"This import may no longer exist, or the cancellation may no longer be possible. If the status still reads processing, you may need to wait for Jira to resolve the broken import.")
    return False

def post_data(url: str, data: set, logger: logging.Logger) -> bool:
    """
    Submit some [data] to [url], usually the CMDB 'start' URL. Method first attempts to post it, then if successful, submits it.
    It will then periodically check the status of the submit, and exit early if it takes too long.

    [url]: URL to post/submit data to.
    [data]: JSON data to attempt to import.

    Returns true if the import was successful or skipped with no errors, false otherwise.
    """
    status_check_counter = 0

    logger.info(f"Posting data to {url}.")
    import_result = requests.post(url = url, headers = JIRA_HEADERS)
    import_result.raise_for_status()

    if (import_result.ok):
        import_result = import_result.json()

        import_submit = import_result.get("links").get("submitResults")
        import_status = import_result.get("links").get("getExecutionStatus")
        import_cancel = import_result.get("links").get("cancel")

        if(not data):
            logger.warning(f"Data packet was empty, skipping this import.")
            return True

        send = requests.post(url = import_submit, headers = JIRA_HEADERS, json = data)

        if (send.ok):
            id = get_link_data(import_status, JIRA_HEADERS, logger)
            id = id.json().get("executionId")
            logger.info(f"Starting import {id}...")

            while status_check_counter < POST_TIMEOUT:
                status_check_counter += 1

                status = get_link_data(import_status, JIRA_HEADERS, logger)
                status = status.json()

                status_code = status.get("status")

                if (status_code == "DONE"):
                    logger.info(f"Data import {id} was successful.")
                    return True

            logger.error(f"Data import {id} took too long, aborting. Would you like to attempt to cancel it?")

            cancel = get_user_yn("Cancel current import?")

            if (not cancel):
                logger.info(f"Import [{id}] will not be cancelled, and will attempt to finish if it can.")
            else:
                cancel_import(import_cancel, id)
                logger.info(f"Current Jira status: {status.get('status')}")

        logger.error(f"Data import failed to connect, aborting: Response {send.status_code}")

    else:
        logger.error(f"Failed to connect to {url}, aborting: Response {import_result.status_code}")

    return False

def build_data(data: set, logger: logging.Logger) -> any:
    """
    Build a data packet using [data], structured in the way the CMDB import expects. Uses the same automatic naming methods
    for selectors and keys as mapping_builder.py.

    [data]: JSON data to be formatted.

    Returns the formatted data if the packet is not empty, otherwise returns false.
    """
    is_packet_empty = True

    unique_id = uuid.uuid4()
    import_packet = {
        "data": {

        },
        "clientGeneratedId": f"{unique_id}",
        "completed": True
    }

    logger.info(f"Building data packet {unique_id}...")

    for loc in DATA_MAPS:
        selector = loc.get("objectTypePath").split(".")
        selector = f"{selector[-1].lower()}Mapping"

        import_data = ""
        keys = loc.get('sourceKey')
        attribute_name = loc.get('attributeName')

        if (isinstance(keys, list)):
            import_data_list = []
            for key in keys:
                import_data_from_key = get_source_data(key, data, f'attribute [{attribute_name}]', logger)
                formatted_data = ", ".join(import_data_from_key) if isinstance(import_data_from_key, list) else import_data_from_key
                import_data_list.append(formatted_data)

            import_data = "".join(import_data_list)

        else:
            import_data = get_source_data(keys, data, f"attribute [{loc.get('attributeName')}]", logger)

        if (not import_data and loc.get("isUniqueIdentifier")):
            logger.error(f"Attribute [{attribute_name}] is marked as a unique identifier, but is empty. This may cause issues.")

        if (import_data or WRITE_EMPTY_DATA):
            if WRITE_EMPTY_DATA and not import_data:
                logger.warning(f"Data for [{attribute_name}] in data packet {unique_id} is empty. WRITE_EMPTY_DATA in config is set to True, so any existing data will be deleted.")

            if (attribute_name in DATA_TRANSLATIONS and f"{import_data}" in DATA_TRANSLATIONS.get(attribute_name)):
                import_data = DATA_TRANSLATIONS.get(attribute_name).get(f"{import_data}")

            is_packet_empty = False

            if selector in import_packet.get("data"):
                import_packet.get("data").get(selector)[0][attribute_name.lower()] = import_data

            else:
                import_packet.get("data").update({
                    selector: [
                            {
                                attribute_name.lower(): import_data
                            }
                        ]
                    }
                )
        else:
            logger.warning(f"Data for [{loc.get('attributeName')}] in data packet {unique_id} is empty, skipping.")

    return import_packet if not is_packet_empty else False

def get_user_yn(question: str) -> bool:
    """Gets user response to a yes/no [question] in terminal."""
    response = input(f"{question} [y/n]:").lower()
    while (not (response == 'y' or response == 'n')):
        response = input(f"Invalid input. {question} [y/n]:").lower()

    return True if response == 'y' else False

# Class to create a logger with uniform formatting across files.
class ImportLogger():

    def __init__(self, logger_name: str, base_log_file_name: str):
        """
        Init ImportLogger

        [logger_name]: The name of the logger to show up in log lines.
        [base_log_file_name]: The base name to apply to the logging file, in addition to the prefix/suffix defined in config.
        """
        self.base_log_file_name = base_log_file_name
        self.logger_name = logger_name

        self.logger = logging.getLogger(self.logger_name)
        self.logger.setLevel(LOGGING_LEVEL)

        handler = logging.StreamHandler()
        handler.setLevel(LOGGING_LEVEL)
        handler.setFormatter(self.Formatter())

        self.logger.addHandler(handler)

        if WRITE_LOGS_TO_FILE:
            self.build_log_file_handler()

    def get_logger(self) -> logging.Logger:
        """Return a logging.Logger instance."""
        return self.logger

    def clean_old_logs(self, folder_path: str):
        """Remove the oldest logs in the log folder, if number of logs is over [MAX_SAVED_LOGS]."""
        current_logs = list(filter(os.path.isfile, glob.glob(f"{folder_path}/*{self.base_log_file_name}*.log")))
        current_logs.sort(key = lambda file: os.path.getmtime(file), reverse = True)

        for f in current_logs[MAX_SAVED_LOGS:]:
            os.unlink(f)

    def build_log_file_handler(self):
        """Build a handler to create log files."""
        log_folder = Path(__file__).parent.resolve() / LOG_FOLDER
        log_folder.mkdir(exist_ok = True)

        file_handler = logging.FileHandler(
            f"{log_folder}/{LOG_FILE_PREFIX}{'' if not LOG_FILE_PREFIX else '-'}{self.base_log_file_name}{'' if not LOG_FILE_SUFFIX else '-'}{LOG_FILE_SUFFIX}.log",
            mode = "w"
        )
        file_handler.setLevel(LOGGING_LEVEL)
        file_handler.setFormatter(logging.Formatter("%(asctime)s[%(name)s][%(levelname)s]: %(message)s"))

        self.clean_old_logs(log_folder)

        self.logger.addHandler(file_handler)

    # Formatter for colors in log lines.
    class Formatter(logging.Formatter):
        grey = "\x1b[38;20m"
        yellow = "\x1b[33m"
        red = "\x1b[31m"
        reset = "\x1b[0m"
        format = "%(asctime)s[%(name)s][%(levelname)s]: %(message)s"

        FORMATS = {
            logging.DEBUG: grey + format + reset,
            logging.INFO: grey + format + reset,
            logging.WARNING: yellow + format + reset,
            logging.ERROR: red + format + reset,
            logging.CRITICAL: red + format + reset
        }

        def format(self, record):
            log_format = self.FORMATS.get(record.levelno)
            formatter = logging.Formatter(log_format)
            return formatter.format(record)