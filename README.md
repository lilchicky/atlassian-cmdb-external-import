## External Import for Atlassian CMDB API

This is a somewhat basic script to import some data from some source into Atlassian CMDB using REST API.

All parameters that could need to be changed can be found in **config.py**. After setting config, running **mapping_builder.py** will automatically create the schema and mapping for
the provided data maps in config based on the schema imported from your CMDB API key. It will also then create **mapping.json** so you can see what the current mapping is, as well as
attempt to post that mapping to CMDB. Make sure you run mapping_builder any time you make any changes to data maps in config, or to your schema via the CMDB dashboard!!

To actually run an import, simply run **main.py**. This will retrieve data specified in config from whatever your source API is, format it, then attempt to import it into CMDB.
