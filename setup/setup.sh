#!/bin/bash

# This script sets up the Python virtual environment for the QGIS Tree Detector plugin.

# Get the directory where the script is located
SETUP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# *** FIX: Define config dir in a standard user location ***
CONFIG_DIR="$HOME/.tree_detector_plugin"
VENV_DIR="$CONFIG_DIR/venv"
CONFIG_FILE="$CONFIG_DIR/config.txt"

echo "Setting up Python virtual environment at: $VENV_DIR"
mkdir -p "$CONFIG_DIR"

# Check for Python 3
if ! command -v python3 &> /dev/null
then
    echo "Error: python3 is not installed. Please install Python 3 and try again."
    exit 1
fi

# Create virtual environment
python3 -m venv "$VENV_DIR"

# Check if venv was created successfully
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "Error: Failed to create the virtual environment."
    exit 1
fi

# Activate the environment and install packages
echo "Activating environment and installing required packages..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r "$SETUP_DIR/requirements.txt"

# Check if installation was successful
if [ $? -eq 0 ]; then
    # Write the absolute path of the python executable to the config file
    VENV_PYTHON_PATH="$VENV_DIR/bin/python"
    echo "Writing python path to config: $CONFIG_FILE"
    echo "$VENV_PYTHON_PATH" > "$CONFIG_FILE"

    echo ""
    echo "--------------------------------------------------"
    echo "Setup complete!"
    echo "The processing environment is ready."
    echo "You can now install the 'tree_detector_tools' folder into QGIS."
    echo "--------------------------------------------------"
else
    echo ""
    echo "--------------------------------------------------"
    echo "Error: Package installation failed."
    echo "Please check the error messages above."
    echo "--------------------------------------------------"
fi

deactivate
```