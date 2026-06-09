#/!bin/bash
if [ $(id -u) -ne 0 ]; then
  echo "WARNING: As of 2025-04-28, it is not safe to use pipi.sh to install packages locally."
  pip3 install $@
else
  uv pip install -p /usr/bin/python3 --system --break-system-packages --prerelease allow --index-strategy unsafe-best-match --link-mode=copy $@
fi
