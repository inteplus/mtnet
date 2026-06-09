#/!bin/bash
wml_nexus.py uv publish --allow-insecure-host "localhost" --publish-url https://localhost:5443/repository/minhtri-pypi-dev-hosted/ --username minhtri --password Winnow2019python $@
