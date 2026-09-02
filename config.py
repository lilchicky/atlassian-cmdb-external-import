import os
import logging
import datetime

from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------- PATH FORMATTING ---------------------------------------------
# | Many of the settings in this file specify locations of values using a custom path definition. The path
# | ontology is defined below:
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
# | - \: Paths support the use of '\' to escape any of the above prefixes. For example, if you have a key
# |     "@data.id", specifying "\@data.id" in your path will simply return the value of that key, instead of
# |     attempting to resolve a URL. You can also escape '/' in cases where the key may contain that character
# |     to prevent it being parsed as a new path entry.
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

SOURCE_DATA_ENTRY_CONFIG = {
    "source": "DeviceService/@@odata.id/@Devices@odata.navigationLink",
    "listKey": "value",
    "pageKey": "\@odata.nextLink",
    "maxPages": 0
}

# Universal timeout wait for get requests, in seconds.
TIMEOUT = 40

# How many times to check the status of the currently ongoing import before aborting. Note that, if the timeout is reached, the import may
# be broken, and will need to be cancelled, or it may just take longer than expected and will finish on its own. Note that this number 
# represents an iteration, not a time, so the length to finish the check loop may fluctuate depending on how long it takes to fetch
# the status.
POST_TIMEOUT = 500

# What percent intervals, out of [POST_TIMEOUT], to log the current progress of the above timeout. Set to 0 to disable.
PROGRESS_WARN_PERCENT = 20

# A list of mappings for data you want to be imported into CMDB, formatted as such:
#
# "objectTypePath": The path to the object type the attribute in Jira being updated is. Each step in the path should be seperated
#   with a period ('.').
# "attributeName": This is the name of the attribute to be updated in Jira. This must match what is in Jira exactly!
# "sourceKey": This is the path to the value in the source API you wish to grab and map to "attributeName". This path will start at
#   whatever list is specified in [SOURCE_LIST], which itself is found at [SOURCE_API_URL].
#   - Entries should be seperated with '.'
#   - To retrieve all elements of a list, then get values from those elements, use *. -> TABLE_NAME.*.value
#   - To specify a deeper URL from [SOURCE_API_URL], use @[extended url], where [extended url] is an EXTENSION to be added to the end of
#       [SOURCE_API_URL]. URLs defined here support formatting using {[PATH]}, defined in [URL_REPLACEMENT_KEY] below.
#       -> @({device_id})/InventoryDetails.value.* will grab the JSON data from https://...SOURCE_API_URL...(device_id)/InventoryDetails,
#           then from that JSON data will run the rest of the path as normal.
#
#   - "sourceKey" can be an array of key paths. If it is, each key value from the array will be merged together in one string.
# "isUniqueIdentifier": This determines if an attribute is a unique identifier for an object in the specified object type. Objects that match
#   ALL identifiers will simply update their values. However, if an import has attributes marked as identifiers with values that do
#   not match an existing object, a new object will be created.
#   - WARNING: Changing which attributes are and are not unique identifiers may create new, potentially duplicate, objects.

# --------------------------------------------- IMPORTANT NOTICES ---------------------------------------------
# |     /!\ 
# |     If you make any changes here, you need to rerun mapping_builder.py, so the mappings reflect the new data maps.
# |     If you do not rerun mapping_builder.py, your new additions here will not be imported into Jira. You can check mapping.json
# |     to check the current import mapping, as well as checking the "Import" tab in your schema in Jira.
# |     /!\
# --------------------------------------------------------------------------------------------------------------
DATA_MAPS = [
    {
        "objectTypePath": "Devices/Servers",
        "attributeName": "ID",
        "sourceKey": "Id",
        "isUniqueIdentifier": False
    },
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
        "attributeName": "Rack (Testing)",
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
        "objectTypePath": "Org/Import Test Owners",
        "attributeName": "Name",
        "sourceKey": "Id",
        "isUniqueIdentifier": True
    }
]

# A list of translations for different attributes pulled from the source API. 
# [attributeName]: { -> attributeName should be the exact name of the attribute specified in both CMDB and [DATA_MAPS].
#   "[source key value]": "[desired display value]" -> the key represents the exact value retrieved from the source API, and
# }                                                the value represents display value to be sent to CMDB.
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

# When false, data pulled from the source will drop any empty data, so as to not overwrite existing data in CMDB.
# This can help preserve any manually entered data in cases where the source does not have any.
WRITE_EMPTY_DATA = False

# Logging level to print in the console and in log files.
# Can be debug, info, warning, error, or critical.
LOGGING_LEVEL = logging.INFO

# Whether or not log files should be written.
WRITE_LOGS_TO_FILE = True

# Folder logs will be stored in, with this folder being placed at the same level as the file being run.
LOG_FOLDER = "logs"

# Prefix/suffix to be appended to the base name of log files. Recommended to be something like date/time.
# If none of the prefix, suffix, or base are ever unique, then new logs will overwrite/append to old logs,
# instead of creating new ones.
LOG_FILE_PREFIX = f"{datetime.datetime.now():%Y-%m-%d_%H%M%S}"
LOG_FILE_SUFFIX = ""

# Max number of saved logs. If logs go over this number, the oldest one will be deleted.
MAX_SAVED_LOGS = 5