#
# Copyright 2025 Chair of EDA, Technical University of Munich
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

# TODO: remove me, for debugging purpose only
from objprint import op

import re
import pathlib
import errno

from backends.estimator_generator.EstimatorGenerator import EstimatorGenerator

from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant, SchedulingFunction, Node, StaticEdge
from meta_models.block_scheduling_model.BlockSchedulingTransformer import BasicBlockDescription

class BasicBlockTestGenerator:

    def __init__(self):
        pass

    def execute(self, sched_model:SchedulingModel, block_model:SchedulingModel, basic_blocks:List[BasicBlockDescription], out_dir):
        
        print()
        print("-- BACKEND: BASIC_BLOCK_TEST_GENERATOR --")

        idx = 0
        for variant_i in block_model.getAllVariants():
            sched_variant_i = sched_model.variants[idx]
            idx += 1

            variant_out_dir  = out_dir / variant_i.name / "code" / "perf_model" / "src"
            try:
                pathlib.Path(variant_out_dir).mkdir(parents=True)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise
            
            EstimatorGenerator().generateSchedulingFunctions(variant_i, variant_out_dir / "..", "Extension")
            
            outFile = variant_out_dir / f"{variant_i.name}_SchedulingFunctionExtension.cpp"
            
            with outFile.open('r') as f:
                code = f.read()
                # link to exisiting scheduling function set
                code = re.sub(f"SchedulingFunctionSet\* {variant_i.name}_SchedulingFunctionSet = (.+)\;",
                              "",
                              code)
                # replace getters and setters to Xd, Xa, Xb with registers by number
                code = re.sub(r"\.get\w+?(\d+)\s\(\w+\)\(\)",
                            lambda m: f".get({m.group(1)})",
                            code)
                code = re.sub(r"\.set\w+?(\d+)\s\(\w+\)\(",
                            lambda m: f".set({m.group(1)}, ",
                            code)
            with outFile.open('w') as f:
                f.write(code)

            self.__generateMain(sched_variant_i, variant_i, basic_blocks, out_dir / variant_i.name / "code" / "main.cpp")
            

    def __generateMain(self, sched_variant, block_variant, basic_blocks, out_file):
        template_dir = pathlib.Path(__file__).parents[0] / "templates"
        with (template_dir / "main.cpp").open('r') as f:
            content = f.read()
        with (template_dir / "basic_block.cpp").open('r') as f:
            bb_test = f.read()

        # generate debug statements for multielement timing variables
        timing_variables = sched_variant.getAllMultiElementTimingVariables()
        for timing_variable in timing_variables:
            text  = f'\tstd::cout << "\\n-> {timing_variable.name}: ";\n'
            text += f'\tfor (int i = 0; i < model.{timing_variable.name}.NUM_ELEMENTS; i++) \n\t{{\n'
            text += f'\t\tstd::cout << (i == model.{timing_variable.name}.ptr ? ">":"") << model.{timing_variable.name}.fifo[i] << ", ";\n\t}}\n'
            text += "$$multi_timing_variables$$"
            content = content.replace("$$multi_timing_variables$$", text)
        content = content.replace("$$multi_timing_variables$$", "")

        # generate channel for the basic block
        for block_desc in basic_blocks:
            code = bb_test
            code = code.replace("$$start_address$$", hex(block_desc.starting_address))
            code = code.replace("$$instruction_count$$", str(len(block_desc.instructions)))

            instr_channel = ""
            for instr in block_desc.instructions:
                instr_channel += f"\t\tchannel.typeId[idx] = {sched_variant.getSchedulingFunction(instr.name).identifier}; // {instr.name}\n"
                instr_channel += f"\t\tchannel.pc[idx]     = pc + (4 * idx);\n"
                if instr.rd is not None:
                    instr_channel += f"\t\tchannel.rd[idx]     = {instr.rd};\n"
                if instr.rs1 is not None:
                    instr_channel += f"\t\tchannel.rs1[idx]    = {instr.rs1};\n"
                if instr.rs2 is not None:
                    instr_channel += f"\t\tchannel.rs2[idx]    = {instr.rs2};\n"
                instr_channel += f"\t\tidx++;\n"

            block_channel  = ""
            block_channel += f"\t\tchannel.typeId[idx] = {block_variant.getSchedulingFunction(block_desc.name).identifier};\n"
            block_channel += f"\t\tchannel.pc[idx]     = pc + (4 * idx);\n"

            code = code.replace("$$instr_begin$$", f'std::cout << "{'#'*5} {block_desc.name} {'#'*5}\\n";')
            code = code.replace("$$instr_end$$"  , f'std::cout << "{'#'*(12+len(block_desc.name))}\\n";')
            code = code.replace("$$instr_channel_setup$$", instr_channel)
            code = code.replace("$$block_desc$$", block_desc.name)
            code = code.replace("$$block_channel_setup$$", block_channel)
            content = content.replace("$$basic_blocks$$", f"{code}\n$$basic_blocks$$")
        content = content.replace("$$basic_blocks$$", "")

        # insert variant name
        content = content.replace("$$variant_name$$", block_variant.name)

        # trim tabs
        content = content.replace("\t", " " * 4)

        with out_file.open('w') as f:
            f.write(content)