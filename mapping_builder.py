import json
import requests
import re

from config import JIRA_URL, JIRA_HEADERS, DATA_MAPS, IMPORT_NAME
from util import get_link_data, get_source_data, ImportLogger

LOGGER = ImportLogger(f"mapping", re.sub(r'\s+', '-', f"{IMPORT_NAME.lower()}-mapping")).get_logger()

jira_schema = ""
jira_mapping = ""

def get_schema() -> set:
    """Returns the schema pulled from CMDB using the API token. Used when creating mappings."""
    LOGGER.info("Importing current Jira schema...")

    schema_data = get_link_data(jira_schema, JIRA_HEADERS, LOGGER)
    schema_data.raise_for_status()

    if (schema_data.ok):
        schema_json = schema_data.json()
        del schema_json["schema"]["iconSchema"]

        LOGGER.info("Jira schema successfully imported.")
        return schema_json

    else:
        LOGGER.error(f"Schema Retrieval Failed: {schema_data.status_code}")
        return {}

def build_mapping(schema: set) -> set:
    """Takes in a schema as JSON from CMDB, then builds a mapping for each point defined in [DATA_MAPS]."""
    mapping = {
        "mapping": {
            "objectTypeMappings": []
        }
    }
    object_type_mappings = mapping.get("mapping").get("objectTypeMappings")

    def find_type(items: dict, index: int, path: list) -> set:
        """Recursively search for the object type at [path]."""
        for item in items:
            if not isinstance(item, dict):
                return None
            
            if item.get("name") != path[index]:
                continue

            if index == len(path) - 1:
                return item

            result = find_type(
                item.get("children", []),
                index + 1,
                path
            )

            if result is not None:
                return result

        return None

    def exists_in(source: list, source_key: str, search_val: str) -> any:
        """Check if a [search_val] matches any values of [source_key] in [source]"""
        instance = None
        if (source and isinstance(source, list)):
            instance = next (
                (
                    type
                    for type in source
                    if type.get(source_key) == search_val
                ),
                None
            )
        return instance

    def add_data_mapping(path: str, attribute_name: str, is_unique: str) -> None:
        """
        Add a mapping for some attribute [attribute_name] in object type at [path].
        If the object type does NOT exist, then create it and add the attribute to it.
        If the object type DOES exist, check to see if the attribute already exists.
        If the attribute does NOT exist inside that attribute type, then add it.
        """
        resolved_path = re.split(r'(?<!\\)/', f"{path}")

        type_mapping = None
        for entry in get_source_data("schema/objectSchema/objectTypes", schema, "entries in object types", LOGGER):
            result = find_type([entry], 0, resolved_path)
        
            if result is not None:
                type_mapping = result
                break
            
        if type_mapping is None:
            LOGGER.warning(f"Object Type at path [{path}] could not be found in the schema, and will not be mapped. Any attributes using this path will not be mapped.")
            return

        attribute = exists_in(type_mapping.get("attributes"), "name", attribute_name)
        if attribute is None:
            LOGGER.warning(f"Attribute [{attribute_name}] could not be found in object type [{path}], and will not be mapped.")
            return

        obj_type = exists_in(object_type_mappings, "objectTypeExternalId", type_mapping.get("externalId"))

        if obj_type is None:
            object_type_mappings.append(
                {
                    "objectTypeExternalId": type_mapping.get("externalId"),
                    "objectTypeName": type_mapping.get("name"),
                    "selector": f"{type_mapping.get('name').lower()}Mapping",
                    "description": f"Mapping for {path} in CMDB schema.",
                    "attributesMapping": [
                        {
                            "attributeExternalId": attribute.get("externalId"),
                            "attributeName": attribute.get("name"),
                            "attributeLocators": [
                                attribute.get("name").lower()
                            ],
                            "externalIdPart": is_unique
                        }
                    ]
                }
            )

        else:
            existing_attribute = exists_in(
                obj_type.get("attributesMapping"), 
                "attributeExternalId", 
                attribute.get("externalId")
            )

            if (existing_attribute is None):
                obj_type.get("attributesMapping").append(
                    {
                        "attributeExternalId": attribute.get("externalId"),
                        "attributeName": attribute.get("name"),
                        "attributeLocators": [
                            attribute.get("name").lower()
                        ],
                        "externalIdPart": is_unique
                    }
                )

        if is_unique:
            LOGGER.warning(f"Attribute [{attribute_name}] is a unique identifier for objects in the object type [{path}]. If an object with the value of this attribute does not exist, a new object will be created.")
        
        LOGGER.info(f"Added attribute [{attribute_name}] to object type [{path}] in mapping.")

    # For each entry in data maps, attempt to create its mapping.
    for loc in DATA_MAPS:
        path = loc.get("objectTypePath")

        add_data_mapping(
            path, 
            loc.get("attributeName"), 
            loc.get("isUniqueIdentifier")
        )

    return mapping

def init() -> bool:
    """Initializes the core connections to CMDB. Returns whether it was successful or not."""
    jira_links = get_link_data(JIRA_URL, JIRA_HEADERS, LOGGER)

    if (not jira_links.ok):
        LOGGER.error(f"Jira connection failed: Response {jira_links.status_code}")
        return False

    global jira_schema, jira_mapping

    # If Jira connection was successful, set up its links
    jira_json = jira_links.json()

    jira_mapping = jira_json["links"].get("mapping")
    jira_schema = jira_json["links"].get("start")
    jira_schema = jira_schema.removesuffix("/executions")
    jira_schema = f"{jira_schema}/schema-and-mapping"

    LOGGER.info(f"Jira connection successful: Response {jira_links.status_code}")

    return True

def main():
    if (init()):
        mapping = get_schema()
        mapping.update(build_mapping(mapping))

        with open ("mapping.json", "w") as f:
            json.dump(mapping, f, indent = 4)

        LOGGER.info("Starting mapping patch...")
        patch = requests.patch(url = jira_mapping, headers = JIRA_HEADERS, json = mapping)

        if (patch.ok):
            LOGGER.info(f"Mapping update successful: Response {patch.status_code}")

        else:
            LOGGER.error(f"Mapping update was not successful: Response {patch.status_code}")
            LOGGER.error(patch.text)

    else:
        LOGGER.error("Initialization failed, aborting.")

if __name__ == "__main__":
    main()