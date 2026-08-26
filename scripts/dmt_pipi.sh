#/!bin/bash
if [ $(id -u) -ne 0 ]; then
  echo "WARNING: As of 2025-04-20, it is not safe to install wml packages locally."
  pip3 install --extra-index https://nexus.winnow.tech/repository/minhtri-pypi-dev/simple/ --upgrade $@
else
  uv pip install -p /usr/bin/python3 --system --break-system-packages --prerelease allow --index https://nexus.winnow.tech/repository/minhtri-pypi-dev/simple/ --index-strategy unsafe-best-match --link-mode=copy $@
fi
