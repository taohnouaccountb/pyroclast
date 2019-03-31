#!/bin/bash
# invoke this from the project root

sphinx-apidoc -o docs -f -e pyroclast/classification pyroclast/classification/selfboosting
sphinx-build -b dirhtml docs/ docs_build/
