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
import copy
from typing import List, Dict, Optional
from collections import deque
from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant, SchedulingFunction, Node, StaticEdge

class SymbolicDelay:

    def __init__(self, name:str, delay:int=0):
        self.name  = name
        self.delay = delay

    def __str__(self):
        return f"{self.delay} + {self.name}"

    def __repr__(self):
        return self.__str__()

    def merge(self, delay:int) -> 'SymbolicDelay':
        return SymbolicDelay(self.name, self.delay + delay)

    @staticmethod
    def Expand(*sym_vars:'SymbolicDelay', aliases:Dict[str,'SymbolicDelay']={}):
        """Expands all alias variables in `sym_vars`, by the term in `aliases` and minimizes the term."""
        expanded = [a.merge(v.delay) for v in sym_vars if v.name in aliases for a in aliases[v.name]] + \
                   [v for v in sym_vars if v.name not in aliases]
        assert not any([v in aliases for v in expanded]), "Failed to expand all aliases!"
        return SymbolicDelay.Max(*expanded)

    @staticmethod
    def DistanceToAlias(sym_var_a:List['SymbolicDelay'], sym_var_b:List['SymbolicDelay'], exact_match=False) -> Optional[int]:
        if exact_match and len(sym_var_a) != len(sym_var_b):
            return None

        diff = None
        for var in sym_var_a:
            other_var = list(filter(lambda v: v.name == var.name, sym_var_b))
            if len(other_var) == 0:
                #print("ERROR:", f"{var.name} is not in {sym_var_b}!")
                #print("A:", sym_var_a)
                #print("B:", sym_var_b)
                return None
            assert len(other_var) == 1
            [other_var] = other_var
            current_diff = other_var.delay - var.delay
            if diff is not None and diff != current_diff:
                #print("ERROR:", f"{var.name}: delay diff {current_diff} vs expected {diff} -> Mismatch!")
                #op("A:", sym_var_a)
                #op("B:", sym_var_b)
                return None
            diff = current_diff
        return diff

    @staticmethod
    def Max(*sym_vars:'SymbolicDelay', aliases:Dict[str,'SymbolicDelay']={}):
        # no need to maximize
        if len(sym_vars) <= 1:
            return list(sym_vars)

        simplified = []
        var_names = set([v.name for v in sym_vars])

        # sym variables containaliasess aliases that must be expanded
        matched_aliases = [v for v in var_names if v in aliases]
        if any(matched_aliases):
            expanded = SymbolicDelay.Expand(*sym_vars, aliases=aliases)

            success = False
            for alias_name in matched_aliases:
                alias = aliases[alias_name]

                distance = SymbolicDelay.DistanceToAlias(alias, expanded)
                if distance is None:
                    continue
                success = True

                var_names   = [v.name for v in alias]
                simplified  = list(filter(lambda v: v.name not in var_names, expanded))
                alias_value = max([v.delay for v in sym_vars if v.name == alias_name])
                simplified.append(SymbolicDelay(alias_name, max(distance, alias_value)))
                break
            if not success:
                print(f"ERROR: failed to merge {matched_aliases}!")
                return expanded
                # raise RuntimeError(f"ERROR: failed to merge {matched_aliases} into {sym_vars}!")

            return list(reversed(sorted(simplified, key=lambda x: x.delay)))

        # core concept to minimize terms:
        #  -> find variable with max static delay and discard variables with equal or less delay
        for var_name in var_names:
            max_value = max([var.delay for var in sym_vars if var.name == var_name])
            simplified.append(SymbolicDelay(var_name, max_value))

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
        aliases = {}
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
                var_name = self.__simplify_variable_name(source_node.name)
                sym_var = SymbolicDelay(var_name, source_node.delay)
                sym_vars.append(sym_var)

            function = SymbolicDelay.Max(*sym_vars, aliases=aliases)

            print(f"   > {source_node.name.lower(): <15}: {self.__function_to_str(function, indent=22)}")

            # set output
            alias_name = None
            for edge in source_node.getAllOutEdges():
                var_name = "o_" + self.__variable_name(edge)
                outputs[var_name] = function
                alias_name = var_name

            # store function of current node
            nodes[source_node.name] = function

            # create alias if function is a max node (multiple input edges)
            if alias_name and len(function) > 1:
                # unroll function for alias
                alias = SymbolicDelay.Expand(*function, aliases=aliases)
                success = False
                # check if term is already implemented by other alias
                for other_alias_name in aliases:
                    other_alias = aliases[other_alias_name]
                    # terms of different length cannot be compatible
                    if len(other_alias) < len(alias):
                        continue
                    distance = SymbolicDelay.DistanceToAlias(other_alias, alias, exact_match=True)
                    # not a multiple
                    if distance is None:
                        continue
                    # alias is positive multiple
                    if distance >= 0:
                        # link to new alias
                        new_function = [SymbolicDelay(other_alias_name, distance)]
                        outputs[alias_name] = new_function
                        # update output of this node
                        nodes[source_node.name] = new_function
                        success = True
                        break
                    # alias is negative multiple -> must update history
                    if distance < 0:
                        print(f"WARN: '{other_alias_name}' is covered by '{alias_name}' (distance: {distance})!")
                        # update old alias
                        outputs[other_alias_name] = [SymbolicDelay(alias_name, -distance)]
                        # update all references to old node
                        for node in nodes:
                            for var in nodes[node]:
                                if var.name == other_alias_name:
                                    var.name   = alias_name
                                    var.delay += -distance
                        break
                # save new alias
                if not success:
                    aliases[alias_name] = alias
                    # update output of this node to alias
                    nodes[source_node.name] = [SymbolicDelay(alias_name)]

            # iterate over children if all dependencies have been met
            for next_node_i in source_node.getAllOutNodes():
                if all((predecessor in reversed(visited)) for predecessor in next_node_i.getAllInNodes()):
                    queue.append(next_node_i)

        # make sure all nodes are processed
        assert all([ n in visited for n in block_function.getAllNodes() ])

        print(f"   > outputs:")
        for output in outputs:
            print(f"    > {output: <13} = {self.__function_to_str(outputs[output], indent=22)}")

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
            .replace("_substage", "_sub") \
            .replace("model", "") \
            .replace(" ", "")
        assert new_name not in self._variable_names, f"generated duplicate variable name! ('{new_name}' from '{var_name}')"
        self._variable_names[var_name] = new_name
        return new_name

    def __function_to_str(self, function, indent=0, word_wrap_at=100):
        indent += 4
        text = '(' + str(function)[1:-1] + ')'
        lines = []
        while len(text) > word_wrap_at:
            try:
                idx = text.index(",", word_wrap_at)
                idx += 1
            except ValueError:
                try:
                    idx = text.index(" ", word_wrap_at)
                except ValueError:
                    break
            lines += [text[:idx+1]]
            text   = text[idx+1:]
        lines += [text]
        return f"max{f"\n{" " * indent}".join(lines)}"