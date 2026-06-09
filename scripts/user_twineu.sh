#/!bin/bash
pipi_url="https://localhost:5443/repository/${USER}-pypi-dev-hosted/"
wml_nexus.py uv publish --allow-insecure-host "localhost" --publish-url $pipi_url --username minhtri --password Winnow2019python $@
