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

import time
from collections import deque
from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant, SchedulingFunction, Node, StaticEdge

class SymbolicDelay:

    def __init__(self, name:str, delay:int=0):
        self.name  = name
        self.delay = delay

    def __str__(self):
        s = ""
        #if self.delay > 0:
        s += f"{self.delay} + "
        s += self.name
        return s

    def __repr__(self):
        return self.__str__()
        
    def merge(self, delay:int) -> 'SymbolicDelay':
        return SymbolicDelay(self.name, self.delay + delay)

    @staticmethod
    def Max(*vars_):
        simplified = []
        names = set([arg.name for arg in vars_])
        for var_name in names:
            max_val = max([var.delay for var in vars_ if var.name == var_name])
            simplified.append(SymbolicDelay(var_name, max_val))
            
        return list(reversed(sorted(simplified, key=lambda x: x.delay)))

class DelayGraph:
    """Delay Graph"""

    def __init__(self):
        self._variable_names = {}
        
    def transform(self, block_model:SchedulingModel):
        print("-- BACKENDS: DELAY_GRAPH --")
        
        variants = {}
        # iterate over each variant
        for block_variant in block_model.getAllVariants():
            print(f" > Generating delay graph for '{block_variant.name}'")
            variants[block_variant.name] = self.__generateDelayGraphForEachFunction(block_variant)
            return variants

    def __generateDelayGraphForEachFunction(self, block_variant:Variant):
        block_functions = block_variant.getAllSchedulingFunctions()
        basic_blocks = {}
        for block_function in block_functions:
            print(f"  > Generating delay graph for '{block_function.name}'")
            start = time.perf_counter_ns()
            basic_blocks[block_function.name] = self.__generateDelayGraphForFunction(block_variant, block_function)
            end   = time.perf_counter_ns()
            print(f"  > took {(end - start) / 1_000_000}ms!")
        return basic_blocks

    def __generateDelayGraphForFunction(self, block_variant:Variant, block_function:SchedulingFunction):
        nodes   = {}
        outputs = {}
        visited = []
        # find all root nodes
        queue   = deque([n for n in block_function.getAllNodes() if len(n.getAllInNodes()) == 0])

        while queue:
            source_node = queue.popleft()
            assert source_node not in visited
            visited.append(source_node)

            sym_vars = []
            # append in edges to function
            for edge in source_node.getAllInEdges():
                var_name = self.__variable_name(edge)
                sym_var = SymbolicDelay(var_name, source_node.delay)
                sym_vars.append(sym_var)
            # append in node to function
            for in_node in source_node.getAllInNodes():
                for sym_var in nodes[in_node.name]:
                    sym_vars.append(sym_var.merge(source_node.delay))
            
            if source_node.resourceModel:
                sym_var = SymbolicDelay(source_node.resourceModel.name.lower(), source_node.delay)
                sym_vars.append(sym_var)

            function = SymbolicDelay.Max(*sym_vars)
            print(f"   > {source_node.name.lower(): <15}: {self.__function_to_str(function, indent=21)}")

            # set output
            for edge in source_node.getAllOutEdges():
                var_name = self.__variable_name(edge)
                outputs[var_name] = function

            # store function of current node
            nodes[source_node.name] = function
            
            # iterate over children if all dependencies have been met
            for next_node_i in source_node.getAllOutNodes():
                if all((predecessor in reversed(visited)) for predecessor in next_node_i.getAllInNodes()):
                    queue.append(next_node_i)

        # make sure all nodes are processed
        assert all([ n in visited for n in block_function.getAllNodes() ])
        
        print(f"   > outputs:")
        for output in outputs:
            print(f"    > {output: <13} = {self.__function_to_str(outputs[output], indent=21)}")
        return outputs

    def __variable_name(self, edge):
        if edge.isDynamic():
            var_name = edge.name
        elif edge.timingVariable.getNumElements() == 1:
            var_name = edge.timingVariable.name
        else:
            var_name = f"{edge.timingVariable.name}[{edge.depth}]"
        return self.__simplify_variable_name(var_name)

    def __simplify_variable_name(self, var_name:str):
        new_name =  var_name.lower() \
            .replace("(xa)", "") \
            .replace("(xb)", "") \
            .replace("(xd)", "") \
            .replace("(cb_out)", "") \
            .replace("(cb_in)", "") \
            .replace("_stage", "") \
            .replace("_substage", "_sub")
        assert new_name not in self._variable_names, f"generated duplicate variable name! ('{new_name}' from '{var_name}')"
        self._variable_names[var_name] = new_name
        return new_name

    def __function_to_str(self, function, indent=0, word_wrap_at=100):
        indent += 4
        text = f'{function}'
        lines = []
        while len(text) > word_wrap_at:
            try:
                idx = text.index(",", word_wrap_at)
            except ValueError:
                try:
                    idx = text.index(" ", word_wrap_at)
                except ValueError:
                    break
            lines += [text[:idx]]
            text   = text[idx:]
        lines += [text]
        return f"max{f"\n{" " * indent}".join(lines)}"