#/!bin/bash
pipi_url="https://nexus.winnow.tech/repository/${USER}-pypi-dev-hosted/"
uv publish --publish-url $pipi_url --username minhtri --password Winnow2019python $@
