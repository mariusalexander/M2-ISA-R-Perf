# 
# Copyright 2023 Chair of EDA, Technical University of Munich
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#       http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import pathlib
import time

def resolveOutDir(outDir_, file_, offset_=0):
    if outDir_ is None:
        return pathlib.Path(file_).resolve().parents[offset_] / "out"
    else:
        return pathlib.Path(outDir_).resolve()

# logs time taken for a code block
class Profile:
    def __init__(self, text: str):
        self.text  = text

    def __enter__(self):
        self.start = time.perf_counter_ns()

    def __exit__(self, *args):
        self.end  = time.perf_counter_ns()
        print(f"{self.text} took {(self.end - self.start) / 1_000_000}ms!")