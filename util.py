import requests
import uuid

from config import TIMEOUT, LOGGER, JIRA_HEADERS, DATA_MAPS, POST_TIMEOUT, SOURCE_HEADERS, URL_REPLACEMENT_KEY, SOURCE_URL, JIRA_CANCELLATION_HEADERS, DATA_TRANSLATIONS, WRITE_EMPTY_DATA

# Get whatever data from [source_url]
def get_link_data(source_url, source_headers):
    data = requests.get(url = source_url, headers = source_headers, timeout = TIMEOUT)
    data.raise_for_status()
    return data

# Get data at some path "path.to.stuff" from JSON data, where that path is of some arbitrary depth. Returns the value
# of the final part of the path, which can be either an array of values, if the final destination is a list, or a single
# value.
def get_source_data(source_path, data, path_desc):
    LOGGER.debug(f"Resolving path [{source_path}] for {path_desc}.")
    path = f"{source_path}".split(".")

    if (path[0].startswith("@")):
        replacement_resolved = {}

        for key in URL_REPLACEMENT_KEY:
            replacement_resolved.update({key: get_source_data(URL_REPLACEMENT_KEY[key], data, f"url replacement key [{key}]")})

        resolved_url = f"{SOURCE_URL}{(path[0].removeprefix('@')).format(**replacement_resolved)}"
        LOGGER.debug(f"URL resolved to {resolved_url}")

        new_data = get_link_data(resolved_url, SOURCE_HEADERS)
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

def cancel_import(cancel_url, execution_id):
    LOGGER.info(f"Cancelling import [{execution_id}]...")

    del_request = requests.delete(url = cancel_url, headers = JIRA_CANCELLATION_HEADERS)
    del_request.raise_for_status()

    if (del_request.ok):
        LOGGER.info(f"Import [{execution_id}] was successfully cancelled.")
        return True
        
    LOGGER.error(f"Cancellation of import [{execution_id}] failed: Response {del_request.status_code}")
    LOGGER.error(f"This import may no longer exist, or the cancellation may no longer be possible. If the status still reads processing, you may need to wait for Jira to resolve the broken import.")
    return False

# Post data to be sent, then submit it.
def post_data(url, data):
    status_check_counter = 0

    LOGGER.info(f"Posting data to {url}.")
    import_result = requests.post(url = url, headers = JIRA_HEADERS)
    import_result.raise_for_status()

    if (import_result.ok):
        import_result = import_result.json()

        import_submit = import_result.get("links").get("submitResults")
        import_status = import_result.get("links").get("getExecutionStatus")
        import_cancel = import_result.get("links").get("cancel")

        if(not data):
            LOGGER.warning(f"Data packet was empty, skipping this import.")
            return True

        send = requests.post(url = import_submit, headers = JIRA_HEADERS, json = data)

        if (send.ok):
            id = get_link_data(import_status, JIRA_HEADERS)
            id = id.json().get("executionId")
            LOGGER.info(f"Starting import {id}...")

            while status_check_counter < POST_TIMEOUT:
                status_check_counter += 1

                status = get_link_data(import_status, JIRA_HEADERS)
                status = status.json()

                status_code = status.get("status")

                if (status_code == "DONE"):
                    LOGGER.info(f"Data import {id} was successful.")
                    return True

            LOGGER.error(f"Data import {id} took too long, aborting. Would you like to attempt to cancel it?")

            cancel = get_user_yn("Cancel current import?")

            if (cancel == 'n'):
                LOGGER.info(f"Import [{id}] will not be cancelled, and will attempt to finish if it can.")
            else:
                cancel_import(import_cancel, id)
                LOGGER.info(f"Current Jira status: {status.get('status')}")

        LOGGER.error(f"Data import failed to connect, aborting: Response {send.status_code}")

    else:
        LOGGER.error(f"Failed to connect to {url}, aborting: Response {import_result.status_code}")

    return False

# Create a piece of data. Takes in a value formatted as in SOURCE_LOCATION.
def build_data(data):
    is_packet_empty = True

    unique_id = uuid.uuid4()
    import_packet = {
        "data": {

        },
        "clientGeneratedId": f"{unique_id}",
        "completed": True
    }

    LOGGER.info(f"Building data packet {unique_id}...")

    for loc in DATA_MAPS:
        selector = loc.get("objectTypePath").split(".")
        selector = f"{selector[-1].lower()}Mapping"

        import_data = ""
        keys = loc.get('sourceKey')
        attribute_name = loc.get('attributeName')

        if (isinstance(keys, list)):
            import_data_list = []
            for key in keys:
                import_data_from_key = get_source_data(key, data, f'attribute [{attribute_name}]')
                formatted_data = ", ".join(import_data_from_key) if isinstance(import_data_from_key, list) else import_data_from_key
                import_data_list.append(formatted_data)

            import_data = "".join(import_data_list)

        else:
            import_data = get_source_data(keys, data, f"attribute [{loc.get('attributeName')}]")

        if (not import_data and loc.get("isUniqueIdentifier")):
            LOGGER.error(f"Attribute [{attribute_name}] is marked as a unique identifier, but is empty. This may cause issues.")

        if (import_data or WRITE_EMPTY_DATA):
            if WRITE_EMPTY_DATA and not import_data:
                LOGGER.warning(f"Data for [{attribute_name}] in data packet {unique_id} is empty. WRITE_EMPTY_DATA in config is set to True, so any existing data will be deleted.")

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
            LOGGER.warning(f"Data for [{loc.get('attributeName')}] in data packet {unique_id} is empty, skipping.")

    return import_packet if not is_packet_empty else False

def get_user_yn(question):
    response = input(f"{question} [y/n]:").lower()
    while (not (response == 'y' or response == 'n')):
        response = input(f"Invalid input. {question} [y/n]:").lower()

    return response