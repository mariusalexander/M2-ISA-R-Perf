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

from backends.basic_block_analyzer.DelayGraph import DelayGraphModel, DelayGraphVariant, DelayGraph, SymbolicVariable
from meta_models.structural_model.StructuralModel import StructuralModel, Variant

class DelayAnalyzer:

    def __init__(self):
        pass

    def assume_perfect_pipeline(self, structural_model:StructuralModel, delay_graph_model:DelayGraphModel):
        print("-- BACKENDS: DELAY_GRAPH_ANALYZER --")
        for structural_variant in structural_model.getAllVariants():
            print(f" > Analyzing delay graph for '{structural_variant.name}'")
            delay_graph_variant = delay_graph_model.variants[structural_variant.name]

            for function_name in delay_graph_variant.scheduling_functions:
                print(f"  > Analyzing delay graph of '{function_name}'")

                delay_graph = delay_graph_variant.scheduling_functions[function_name]

                pipeline = structural_variant.getPipeline()

                mappings = { f"r{reg}":SymbolicVariable("zero") for reg in range(1, 32) }
                mappings["pc"] = SymbolicVariable("if")
                
                stages = pipeline.getFirstStages()
                while stages:
                    next_stages = []
                    for stage in stages:
                        timing_variable = stage.name
                        assert stage.capacity == 1
                        variable_name = delay_graph.input_to_variable_name(timing_variable)
                        if variable_name is None:
                            continue
                        #print(f"STAGE: {timing_variable} -> {variable_name}")
                        
                        next_stages += pipeline.getNextStages(stage)
                        for next_stage in pipeline.getNextStages(stage):
                            assert next_stage.capacity == 1
                            #    for fifo_idx in range(0, next_stage.capacity):
                            #        next_timing_variable = f"{next_stage.name}[{fifo_idx + 1}]"
                            #        next_variable = delay_graph.input_to_variable_name(next_timing_variable)
                            #        #print(f"NEXT: {next_variable} = 0")
                            #else:
                            next_timing_variable = next_stage.name
                            next_variable_name   = delay_graph.input_to_variable_name(next_timing_variable)
                            if next_variable_name is None:
                                continue
                            #print(f"NEXT: {next_variable_name} = 1 + {variable_name}")
                            mappings[next_variable_name] = SymbolicVariable(variable_name, 1)
                            if next_stage not in next_stages:
                                next_stages.append(next_stage)
                    stages = next_stages

                #op(mappings)

                for output_name in delay_graph.outputs():
                    output = delay_graph.get_output(output_name)
                    output = output.expanded(delay_graph.intermediates())
                    before = output
                    for i in range(0, len(mappings)):
                        for mapping in mappings:
                            #print("replacing", mapping, "with", mappings[mapping])

                            output = output.replaced(mapping, mappings[mapping])
                    output = output.resolved("zero")
                    print(f"    > Resolved '{output_name}': {before}\t => \t{output}")

