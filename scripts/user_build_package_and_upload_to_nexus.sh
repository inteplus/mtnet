#!/bin/bash

git commit --author "Winnow ML <ml_bitbucket@winnowsolutions.com>" -am "(bug-fix commit)"
git pull
git push

if git rev-parse --git-dir > /dev/null 2>&1; then
    GIT_REPO_PATH=`git rev-parse --show-toplevel`
    CURR_PATH=$(pwd)
    echo "===== Building the Python package residing at ${GIT_REPO_PATH} ====="
    cd ${GIT_REPO_PATH}
    uv build  # previously: ./setup.py bdist_wheel
    echo "===== Installing the Python package ====="
    WHEEL_FILE=`ls -t1 dist | head -n 1`
    PACKAGE_NAME=`echo "${WHEEL_FILE}" | cut -d'-' -f1`
    echo "Package name: ${PACKAGE_NAME}"
    echo "Wheel to install: ${WHEEL_FILE}"
    uv pip uninstall ${PACKAGE_NAME}
    user_pipi.py -U dist/${WHEEL_FILE}
    echo "===== Uploading Python package to Winnow's Nexus server ====="
    user_twineu.sh dist/${WHEEL_FILE}
    cd ${CURR_PATH}
else
    echo "This is not a git repo. No installation has been performed."
fi
