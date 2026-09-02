import json
import requests
import re

from config import JIRA_URL, JIRA_HEADERS, DATA_MAPS, IMPORT_NAME
from util import get_link_data, get_source_data, ImportLogger

LOGGER = ImportLogger(f"{IMPORT_NAME} - mapping", re.sub(r'\s+', '-', f"{IMPORT_NAME.lower()}-mapping")).get_logger()

jira_schema = ""
jira_mapping = ""

# This returns the schema for the database the token is from, to be used when creating the mappings.
def get_schema():
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

def build_mapping(schema):
    mapping = {
        "mapping": {
            "objectTypeMappings": []
        }
    }

    # Somewhat hardcoded recursive function for nested object types. Automatically searches 'children' for the next object type.
    def find_type(items, index, path):
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

    for loc in DATA_MAPS:
        path = re.split(r'(?<!\\)/', f"{loc.get('objectTypePath')}")
        type_mapping = None

        for entry in get_source_data("schema/objectSchema/objectTypes", schema, "entries in object types", LOGGER):
            result = find_type([entry], 0, path)

            if result is not None:
                type_mapping = result
                break

        if type_mapping is None:
            LOGGER.warning(f"Object Type at path [{loc.get('objectTypePath')}] could not be found in the schema, and will not be mapped. Any attributes using this path will not be mapped.")
            continue

        attribute = next(
            (
                attr 
                for attr in type_mapping.get("attributes")
                if attr.get("name") == loc.get("attributeName")
            ),
            None
        )

        if attribute is None:
            LOGGER.warning(f"Attribute [{loc.get('attributeName')}] could not be found in the schema, and will not be mapped.")
            continue

        LOGGER.info(f"Adding attribute [{loc.get('attributeName')}] to object type [{loc.get('objectTypePath')}] in mapping.")
        object_type_mappings = mapping.get("mapping").get("objectTypeMappings")

        obj_type = None

        if (object_type_mappings != []):
            obj_type = next (
                (
                    type
                    for type in object_type_mappings
                    if type.get("objectTypeExternalId") == type_mapping.get("externalId")
                ),
                None
            )

        if obj_type is None:
            object_type_mappings.append(
                {
                    "objectTypeExternalId": type_mapping.get("externalId"),
                    "objectTypeName": type_mapping.get("name"),
                    "selector": f"{type_mapping.get('name').lower()}Mapping",
                    "description": f"Mapping for {loc.get('attributeName')} in {type_mapping.get('name')}",
                    "attributesMapping": [
                        {
                            "attributeExternalId": attribute.get("externalId"),
                            "attributeName": attribute.get("name"),
                            "attributeLocators": [
                                attribute.get("name").lower()
                            ],
                            "externalIdPart": loc.get("isUniqueIdentifier")
                        }
                    ]
                }
            )

        else:
            existing_attribute = next(
                (
                    attr
                    for attr in obj_type.get("attributesMapping")
                    if attr.get("attributeExternalId") == attribute.get("externalId")
                ),
                None
            )

            if (existing_attribute is None):
                obj_type.get("attributesMapping").append(
                    {
                        "attributeExternalId": attribute.get("externalId"),
                        "attributeName": attribute.get("name"),
                        "attributeLocators": [
                            attribute.get("name").lower()
                        ],
                        "externalIdPart": loc.get("isUniqueIdentifier")
                    }
                )

        if loc.get("isUniqueIdentifier"):
            LOGGER.warning(f"Attribute [{loc.get('attributeName')}] is a unique identifier for objects in the object type [{loc.get('objectTypePath')}]. If an object with the value of this attribute does not exist, a new object will be created.")

    return mapping

def init():
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