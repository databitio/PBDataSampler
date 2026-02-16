#!/bin/bash
export PATH="/c/Users/8J4927897/AppData/Local/Microsoft/WinGet/Links:/c/Users/8J4927897/AppData/Local/Packages/PythonSoftwareFoundation.Python.3.10_qbz5n2kfra8p0/LocalCache/local-packages/Python310/Scripts:$PATH"
cd "C:/Users/8J4927897/Repos/PBRepos/PBDataSampler"
rm -rf output/frames/* output/tmp/* output/run_manifest.json 2>/dev/null
python -m ppa_frame_sampler.cli --seed 42 "$@"
