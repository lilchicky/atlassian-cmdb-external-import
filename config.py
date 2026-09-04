import os
import logging
import datetime

from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------- PATH FORMATTING ---------------------------------------------
# | Many of the settings in this file specify locations of values using a custom path definition. Whenever
# | the config refers to "path", this is the expected format. The path ontology is defined below:
# |
# | Paths are defined as each step through a JSON file required to get to the value(s) you want to retrieve.
# | Each step in the paths are seperated with '/'.
# |     For example: in the following JSON:
# |         {
# |             "values": [
# |                 {
# |                     "key": "value1"
# |                 },
# |                 {
# |                     "key": "value2"
# |                 }
# |             ]
# |         }
# |     the path "values/*0/key" will return the value of "key" (value1) in the first element in "values".
# |
# | These paths support a few custom bits of syntax:
# | - *: Using '*' after another element in the path will retrieve all values from the preceding element.
# |     You can immediately follow '*' with an index to retrieve a specific element from that list. This
# |     can be seen in the above example - values/*0/... will retrieve the values inside of the first element
# |     of "values" (values[0]).
# | - @: You can use '@' to denote that the value of that key will be a URL. That URL will automatically be
# |     appended to the end of [SOURCE_API_URL], and will pull JSON data from that URL to then continue the
# |     path. For example - key.@url_value.list will get some URL extension, like /api/... from "url_value",
# |     found inside "key", then apply that extension to [SOURCE_API_URL], retrieve the JSON data from that
# |     URL, and finally retrieve and return "list" from the new JSON data.
# | - ..: You can use '..' (two periods) at the start of a word to indicate a string literal. This means that
# |     the path is no longer a path, and will set the attribute to the literal string value of what you entered. 
# |     Having this anywhere in your path will essentially completely disregard any results from the rest of the path.
# | - \: Paths support the use of '\' to escape any of the above prefixes. For example, if you have a key
# |     "@data.id", specifying "\@data.id" in your path will simply return the value of that key, instead of
# |     attempting to resolve a URL. You can also escape '/' in cases where the key may contain that character
# |     to prevent it being parsed as a new path entry.
# -----------------------------------------------------------------------------------------------------------

# --------------------------------------------- CMDB IMPORT MAPPING -----------------------------------------
# | These CMDB imports rely on accurate mapping, and imports may fail if the mapping isn't correct, or is
# | outdated. If you make any changes to either [DATA_MAPS] or attributes via the CMDB interface, it is
# | reccomended to run "mapping_builder.py". This will automatically update the mapping in CMDB based on
# | the content of [DATA_MAPS] and the new imported schema.
# |
# | If you attempt an import and are given the "MISSING_MAPPING" error, this also indicates you need to run
# | "mapping_builder.py".
# -----------------------------------------------------------------------------------------------------------

# Name of the import ran using this config. Used in logging.
IMPORT_NAME = "DOME Import"

# Jira API settings
JIRA_TOKEN = os.getenv("JIRA_TOKEN")
JIRA_URL = os.getenv("JIRA_API")
JIRA_HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {JIRA_TOKEN}"
}
JIRA_CANCELLATION_HEADERS = {
    "Authorization": f"Bearer {JIRA_TOKEN}"
}

# Import source API settings
SOURCE_TOKEN = os.getenv("DOME_TOKEN")
SOURCE_API_URL = os.getenv("DOME_API")
SOURCE_HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Basic {SOURCE_TOKEN}"
}

# This are the settings for where the main list of entries in your source are located. It is expected to be a list
# of entries, where each of those entries contain the attributes found in [DATA_MAPS]. This config also supports
# pageinated data, if the "next page" is provided as a URL to a new page that also contains [listKey].
#
# [source]: This is a path to the JSON entry that contains both the list key and the path to whatever the page link is. If
#       [source] is empty, then the source will simply be [SOURCE_API_URL].
# [listKey]: This is the key for the list of entries, found at [source]. Each of these entries should contain the values
#       found in [DATA_MAPS]. This value is not expected to be a path, but is instead expected to be found inside [source].
# [pageKey]: This is the path to the key that contains the next "page" of entries, usually a URL extension of some sort.
#       The path provided is expected to START at [source]. This is not required. Each "page" is expected to contain [listKey]
#       at that URL to obtain the entries from it.
# [maxPages]: This is the maximum number of pages that can be "flipped" through when gathering source data. Pages are flipped
#       through recursively, so if the dataset may be incredibly large, this is probably good to set. Set to 0 to disable and
#       always flip through all available pages. If [pageKey] is empty, then [maxPages] does nothing.
SOURCE_DATA_ENTRY_CONFIG = {
    "source": "DeviceService/@@odata.id/@Devices@odata.navigationLink",
    "listKey": "value",
    "pageKey": "\@odata.nextLink",
    "maxPages": 0
}

# Universal timeout wait for get requests, in seconds.
TIMEOUT = 40

# When attempting to post data to CMDB, this is the maximum number of times to ping the current status of the import before
# aborting it. If it is aborted, it will attempt to cancel the current import. Some imports may take longer depending on the
# connection to Jira or the size of the data packet, in which case [POST_TIMEOUT] may need to be increased.
POST_TIMEOUT = 500

# What percent intervals to log the progress out of [POST_TIMEOUT]. Set to 0 to disable.
PROGRESS_WARN_PERCENT = 20

# These are all the mappings for where to get the values from the source, and what attributes in CMDB to map them to.
#
# [objectTypePath]: The path to the source object type in the schema JSON. Uses "name" attribute of object types.
# [attributeName]: The exact attribute name (NOT "display name") of the attribute in CMDB you wish to map
#       the value found at [sourceKey] to.
# [sourceKey]: The path to whatever value you wish to retrieve from the source API, to be mapped to [attributeName].
#       This path is expected to start from [listKey] defined above, not [SOURCE_API_URL].
# [isUniqueIdentifier]: Whether or not this attribute is a unique identifier. Unique identifiers are what are used to
#       differentiate between objects inside the specified object type. This should be something unique to each object
#       (or entry in [listKey]), and should ideally be unchanging. If an object with matching values for ALL unique 
#       identifiers does not exist, then A NEW OBJECT WILL BE CREATED.

# --------------------------------------------- IMPORTANT NOTICES ---------------------------------------------
# | If you make any changes here, you need to rerun mapping_builder.py, so the mappings reflect the new data maps.
# | If you do not rerun mapping_builder.py, your new additions here will not be imported into CMDB. You can check mapping.json
# | to see the current import mapping. You can also check the "Import" tab in schema settings on CMDB to view what
# | external values are mapped to what object type attributes. (as mentioned at the start of this file.)
# --------------------------------------------------------------------------------------------------------------
DATA_MAPS = [
    {
        "objectTypePath": "Devices/Servers",
        "attributeName": "Identifier",
        "sourceKey": "Identifier",
        "isUniqueIdentifier": True
    },
    {
        "objectTypePath": "Devices/Servers",
        "attributeName": "Network Address",
        "sourceKey": "DeviceManagement/*/NetworkAddress",
        "isUniqueIdentifier": False
    },
    {
        "objectTypePath": "Devices/Servers",
        "attributeName": "Name",
        "sourceKey": "DeviceName",
        "isUniqueIdentifier": False
    },
    {
        "objectTypePath": "Devices/Servers",
        "attributeName": "Power",
        "sourceKey": "PowerState",
        "isUniqueIdentifier": False
    },
    {
        "objectTypePath": "Devices/Servers",
        "attributeName": "Health",
        "sourceKey": "Status",
        "isUniqueIdentifier": False
    },
    {
        "objectTypePath": "Devices/Servers",
        "attributeName": "Model",
        "sourceKey": "Model",
        "isUniqueIdentifier": False
    },
    {
        "objectTypePath": "Devices/Servers",
        "attributeName": "rack_link_testing",
        "sourceKey": [
            "@InventoryDetails@odata.navigationLink/value/*18/InventoryInfo/*/Aisle",
            "@InventoryDetails@odata.navigationLink/value/*18/InventoryInfo/*/Rack"
        ],
        "isUniqueIdentifier": False
    },
    {
        "objectTypePath": "Devices/Servers",
        "attributeName": "OS Name",
        "sourceKey": "@InventoryDetails@odata.navigationLink/value/*6/InventoryInfo/*/OsName",
        "isUniqueIdentifier": False
    },
    {
        "objectTypePath": "Devices/Servers",
        "attributeName": "OS Version",
        "sourceKey": "@InventoryDetails@odata.navigationLink/value/*6/InventoryInfo/*/OsVersion",
        "isUniqueIdentifier": False
    },
    {
        "objectTypePath": "Devices/Servers",
        "attributeName": "OS Hostname",
        "sourceKey": "@InventoryDetails@odata.navigationLink/value/*6/InventoryInfo/*/Hostname",
        "isUniqueIdentifier": False
    },
    {
        "objectTypePath": "Devices/Servers",
        "attributeName": "Slot",
        "sourceKey": "@InventoryDetails@odata.navigationLink/value/*18/InventoryInfo/*/Rackslot",
        "isUniqueIdentifier": False
    },
    {
        "objectTypePath": "Devices/Servers",
        "attributeName": "import_source",
        "sourceKey": "..DOME",
        "isUniqueIdentifier": False
    },

    {
        "objectTypePath": "Locations/Racks",
        "attributeName": "Name",
        "sourceKey": [
            "@InventoryDetails@odata.navigationLink/value/*18/InventoryInfo/*/Aisle",
            "@InventoryDetails@odata.navigationLink/value/*18/InventoryInfo/*/Rack"
        ],
        "isUniqueIdentifier": True
    }
]

# This is a list of "translations" for values retrieved from source, to change what the display value
# for the attribute in CMDB is.
#
# Format as:
# [attributeName]: { ([attributeName] must match the exact attribute name (NOT display name) in CMDB.)
#   [exact source value]: [desired display value]
# }
DATA_TRANSLATIONS = {
    "Health": {
        "1000": "Normal (1000)",
        "2000": "Unknown (2000)",
        "3000": "Warning (3000)",
        "4000": "Critical (4000)"
    },
    "Power": {
        "17": "Online (17)",
        "18": "Offline (18)",
        "1": "Unknown (1)"
    }
}

# Whether or not to write empty data from the source to CMDB. Empty data will simply delete any existing values 
# already in CMDB for each corresponding attribute listed in [DATA_MAPS].
WRITE_EMPTY_DATA = False

# Logging level to display in the console and log files.
# Can be DEBUG, INFO, WARNING, ERROR, or CRITICAL.
LOGGING_LEVEL = logging.INFO

# Whether or not log files should be created.
WRITE_LOGS_TO_FILE = True

# Folder logs will be stored in, with this folder being placed at the same file path as the script being run.
LOG_FOLDER = "logs"

# Prefix/suffix to be appended to the base name (set using a formatted version of [IMPORT_NAME]) of log files.
# If neither prefix nor suffix are some changing value, such as the current date/time, then previous logs (with
# the same name) will be overwritten.
LOG_FILE_PREFIX = f"{datetime.datetime.now():%Y-%m-%d_%H%M%S}"
LOG_FILE_SUFFIX = ""

# Maximum number of saved logs per each unique base file name. If this number is reached, the oldest log with the
# matching base file name will be deleted.
MAX_SAVED_LOGS = 5