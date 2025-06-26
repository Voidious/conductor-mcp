#!/bin/bash
# Activate the virtual environment and run main.py

# Change to the script's directory (project root)
cd "$(dirname "$0")"

# Determine the correct virtual environment activation script
if [ -f ".venv/bin/activate" ]; then
    # macOS/Linux
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    # Windows (Git Bash, WSL, or Cygwin)
    source .venv/Scripts/activate
else
    echo "Could not find a virtual environment activation script."
    echo "Please ensure you have created a virtual environment in .venv."
    exit 1
fi

# Run the main Python script
python main.py "$@"
