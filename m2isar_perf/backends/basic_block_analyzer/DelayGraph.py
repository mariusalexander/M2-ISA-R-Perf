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

import sympy as sym
from collections import deque
from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant, SchedulingFunction, Node, StaticEdge

class DelayGraph:
    """Delay Graph"""

    def __init__(self):
        self.variable_names = {}
        
    def transform(self, block_model:SchedulingModel):
        print("-- BACKENDS: DELAY_GRAPH --")
        
        # iterate over each variant
        for block_variant in block_model.getAllVariants():
            print(f"> Generating delay graph for '{block_variant.name}'")
            self.__generateDelayGraphForEachFunction(block_variant)

    def __generateDelayGraphForEachFunction(self, block_variant:Variant):
        block_functions = block_variant.getAllSchedulingFunctions()
        for block_function in block_functions:
            self.__generateDelayGraphForFunction(block_variant, block_function)

    def __generateDelayGraphForFunction(self, block_variant:Variant, block_function:SchedulingFunction):
        nodes   = {}
        outputs = {}
        visited = []
        # find all root nodes
        queue     = deque([n for n in block_function.getAllNodes() if len(n.getAllInNodes()) == 0])

        while queue:
            source_node = queue.popleft()
            assert source_node not in visited
            visited.append(source_node)

            args = []
            # append in edges to function
            for edge in source_node.getAllInEdges():
                var_name = self.__variable_name(edge)
                args.append(sym.Symbol(var_name) + source_node.delay)
            # append in node to function
            for in_node in source_node.getAllInNodes():
                args.append(nodes[in_node.name] + source_node.delay)

            function = sym.Max(*args)
            print(f" > {source_node.name.lower(): <15}: {self.__function_to_str(function, indent=19)}")

            # set output
            for edge in source_node.getAllOutEdges():
                var_name = f"out_{self.__variable_name(edge)}"
                outputs[var_name] = function

            # store function of current node
            nodes[source_node.name] = function
            
            # iterate over children if all dependencies have been met
            for next_node_i in source_node.getAllOutNodes():
                if all((predecessor in reversed(visited)) for predecessor in next_node_i.getAllInNodes()):
                    queue.append(next_node_i)

        # make sure all nodes are processed
        assert all([ n in visited for n in block_function.getAllNodes() ])
        
        print()
        print(f" > outputs:")
        for output in outputs:
            print(f"  > {output.replace("out_", ""): <15} = {self.__function_to_str(outputs[output], indent=21)}")

    def __variable_name(self, edge):
        if edge.isDynamic():
            var_name = edge.name
        elif edge.depth == 1:
            var_name = edge.timingVariable.name
        else:
            var_name = f"{edge.timingVariable.name}[{edge.depth}]"
        return self.__simplify_variable_name(var_name)

    def __simplify_variable_name(self, var_name:str):
        new_name =  var_name.lower() \
            .replace("(xa)", "") \
            .replace("(xb)", "") \
            .replace("(xd)", "") \
            .replace("_stage", "") \
            .replace("_substage", "_sub")
        assert new_name not in self.variable_names, f"generated duplicate variable name! ('{new_name}' from '{var_name}')"
        self.variable_names[var_name] = new_name
        return new_name

    def __function_to_str(self, function, indent=0):
        text = f'{function}'
        lines = []
        while len(text) > 120:
            idx = text.index(" ", 120)
            lines += [text[:idx]]
            text   = text[idx:]
        lines += [text]
        return f"\n{" " * indent}".join(lines)