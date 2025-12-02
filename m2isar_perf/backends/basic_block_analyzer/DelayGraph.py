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
from typing import List, Dict, Optional, TypeAlias
from collections import deque
from meta_models.scheduling_model.SchedulingModel import SchedulingModel, Variant, SchedulingFunction, Node, Edge

MaxTerm : TypeAlias = List['SymbolicDelay']

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
    def Expand(*variables:'SymbolicDelay', aliases:Dict[str,MaxTerm]={}) -> MaxTerm:
        """
        Expands all alias variables by the corresponding term. 
        Returns a minimized term.
        """
        expanded = [a.merge(v.delay) for v in variables if v.name in aliases for a in aliases[v.name]] + \
                   [v for v in variables if v.name not in aliases]
        assert all([v.name not in aliases for v in expanded]), "Failed to expand all aliases!"
        return SymbolicDelay.Max(*expanded)

    @staticmethod
    def Distance(term_a:MaxTerm, term_b:MaxTerm) -> Optional[int]:
        """
        Yields the amount of times `term_a` occures into `term_b`
        """
        if len(term_a) > len(term_b):
            return None

        diff = None
        for var in term_a:
            other_var = list(filter(lambda v: v.name == var.name, term_b))
            # variable not present in other term 
            if len(other_var) == 0:
                return None
            assert len(other_var) == 1, f"Duplicate variable '{var.name}'!"
            # calculate difference
            [other_var]  = other_var
            current_diff = other_var.delay - var.delay
            # difference in delay is not linear
            if diff is not None and diff != current_diff:
                return None
            diff = current_diff
        return diff

    @staticmethod
    def Max(*variables:'SymbolicDelay', aliases:Dict[str,MaxTerm]={}) -> MaxTerm:
        """
        Minimizes the list of variables. Each variable is listed exactly once.
        Alias variables are resolved such that the best fitting alias variable is used which yielding the smallest term. 
        """
        # no need to resolve term
        if len(variables) <= 1:
            return list(variables)

        simplified = []
        var_names  = set([v.name for v in variables])

        # variables contains aliases that must be expanded
        matched_aliases = [v for v in var_names if v in aliases]
        if any(matched_aliases):
            return SymbolicDelay.__resolve_aliases(*variables, aliases=aliases, matched=matched_aliases)

        # for each variable: find entry with max static delay and discard entries with equal or less delay
        for var_name in var_names:
            max_value = max([var.delay for var in variables if var.name == var_name])
            simplified.append(SymbolicDelay(var_name, max_value))

        return SymbolicDelay.__sort(simplified)

    @staticmethod
    def __sort(term:MaxTerm) -> MaxTerm:
        """
        Sorts the max term by its delay (descending). 
        For variables with same delay, alphabetical order is used. 
        """
        # sort by delay and then by name
        return list(sorted(term, key=lambda v: (-v.delay, v.name)))

    @staticmethod
    def __resolve_aliases(*variables:'SymbolicDelay', aliases:Dict[str,MaxTerm]={}, matched:List[str]=[]):
        """
        Helper function that resolves aliases in a term by
         1) unrolling all alias variables
         2) finding an alias variable in the existing term that yields in the smallest term
         3) if none was found, all aliases are searched to find the alias variable resulting in the smallest term
        """
        expanded_term = SymbolicDelay.Expand(*variables, aliases=aliases)

        # find best matching alias
        covering_alias = SymbolicDelay.__find_best_alias(expanded_term, aliases=aliases, matched=matched)

        if covering_alias is not None:
            return SymbolicDelay.__repack_term(expanded_term=expanded_term, alias_variable=covering_alias, aliases=aliases)
            
        print(f"WARN: failed to merge '{", ".join(matched)}'!")
        # check all aliases for a better match
        covering_alias  = SymbolicDelay.__find_best_alias(expanded_term, aliases=aliases, matched=aliases)

        if covering_alias is not None:
            print(f"INFO: alias '{covering_alias.name}' covers unmatched term! (distance: {covering_alias.delay})")
            return SymbolicDelay.__repack_term(expanded_term=expanded_term, alias_variable=covering_alias, aliases=aliases)
            
        print(f"WARN: failed to cover unmatched term!")
        return expanded_term

    @staticmethod
    def __find_best_alias(expanded_term:MaxTerm, aliases:Dict[str,MaxTerm]={}, matched:List[str]=[]) -> Optional['SymbolicDelay']:
        """
        Helper function that attempts to find an alias variable in an existing term (the term must be unrolled),
        such that it yields the smallest term.
        """
        last_name     = None
        last_distance = None
        last_len      = 0
        for name in matched:
            term     = aliases[name]
            distance = SymbolicDelay.Distance(term, expanded_term)
            if distance is None:
                continue
            if last_name is not None:
                curr_len = len(term) 
                if curr_len < last_len:
                    continue
                # keep last alias if its scores a lower distance
                if curr_len == last_len and distance > last_distance:
                    continue
                print(f"INFO: alias '{name}' deemed more optimal than '{last_name}'!")
            last_name     = name
            last_distance = distance
            last_len      = len(term)

        return SymbolicDelay(last_name, last_distance) if last_distance is not None else None

    @staticmethod
    def __repack_term(expanded_term:MaxTerm, alias_variable:'SymbolicDelay', aliases:Dict[str,MaxTerm]={}) -> MaxTerm:
        """
        Helper function that repacks an expanded term with the given alias variable.
        The resulting term does not contain duplicates.
        """
        alias_term = aliases[alias_variable.name]
        var_names  = [v.name for v in alias_term]
        repacked   = list(filter(lambda v: v.name not in var_names, expanded_term))
        repacked.append(alias_variable)
        return SymbolicDelay.__sort(repacked)


class DelayGraph:
    """Delay Graph"""

    def __init__(self):
        # helper variable to verify that no variable is duplicated
        self._variable_names = {}
        # whether to unroll all delay functions
        self.unroll_delays = False

    def transform(self, block_model:SchedulingModel, unroll_delays=False):
        """
        Transforms a (block) scheduling model into a delay graph. 
        For each scheduling function a dict of its outputs and the respective delay functions (max term) is returned.
        Setting `unroll_delays` to `True` will yield a delay graph with a depth of one, i.e. no max terms are shared. 
        """
        print("-- BACKENDS: DELAY_GRAPH --")
        self.unroll_delays = unroll_delays
        variants = {}
        # iterate over each variant
        for block_variant in block_model.getAllVariants():
            print(f" > Generating delay graph for '{block_variant.name}'")
            variants[block_variant.name] = self.__generateDelayGraphForEachFunction(block_variant)
            return variants

    def __generateDelayGraphForEachFunction(self, block_variant:Variant):
        block_functions = block_variant.getAllSchedulingFunctions()
        basic_blocks    = {}
        for block_function in block_functions:
            print(f"  > Generating delay graph for '{block_function.name}'")
            start = time.perf_counter_ns()
            basic_blocks[block_function.name] = self.__generateDelayGraphForFunction(block_variant, block_function)
            end   = time.perf_counter_ns()
            print(f"  > took {(end - start) / 1_000_000}ms!")
        return basic_blocks

    def __generateDelayGraphForFunction(self, block_variant:Variant, block_function:SchedulingFunction):
        # max term for each node indexed by its name
        nodes   = {}
        # max term for each output indexed by its name
        outputs = {}
        # variables that are an alias for a max term
        aliases = {}
        
        # find all root nodes
        queue   = deque([n for n in block_function.getAllNodes() if len(n.getAllInNodes()) == 0])
        while queue:
            node = queue.popleft()
            assert node.name not in nodes

            # create max term, discarding redundant variables
            term = self.__get_inputs(node, nodes)
            function = SymbolicDelay.Max(*term, aliases=aliases)

            # store function of current node
            nodes[node.name] = function
            DelayGraph.print_function(node.name, function, indent=3)

            # set outputs if any
            output_name = self.__set_output(node, outputs, function)

            # create alias if function is a max node (multiple input edges)
            if not self.unroll_delays:
                if output_name is not None and len(function) > 1:
                    self.__update_aliases(node.name, nodes, output_name, outputs, aliases)

            # iterate over children if all dependencies have been met
            for next_node_i in node.getAllOutNodes():
                if all((predecessor.name in nodes) for predecessor in next_node_i.getAllInNodes()):
                    queue.append(next_node_i)

        # make sure all nodes have been processed
        assert all([ n.name in nodes for n in block_function.getAllNodes() ])

        print(f"   > outputs:")
        for output in outputs:
            DelayGraph.print_function(output, outputs[output], indent=4)

        return outputs

    def __get_inputs(self, node:Node, nodes:Dict[str, MaxTerm]):
        """
        Accumulates all input variables for the given node. 
        Returns a non-simplified term.
        """
        sym_vars = []
        # append in edges to function
        for in_edge in node.getAllInEdges():
            var_name = self.__variable_name(in_edge)
            sym_var = SymbolicDelay(var_name, node.delay)
            sym_vars.append(sym_var)
        # append in node to function
        for in_node in node.getAllInNodes():
            for sym_var in nodes[in_node.name]:
                sym_vars.append(sym_var.merge(node.delay))
        # append variable delay of resource model
        if node.resourceModel:
            var_name = self.__simplify_variable_name(node.name)
            sym_var = SymbolicDelay(var_name, node.delay)
            sym_vars.append(sym_var)
        return sym_vars

    def __set_output(self, node:Node, outputs:Dict[str, MaxTerm], function:MaxTerm):
        """
        Sets the node's function to all outputs of this node. 
        Yields the name of the last output that was set (if any)
        """
        alias_name = None
        for edge in node.getAllOutEdges():
            var_name = self.__variable_name(edge, prefix="o_")
            outputs[var_name] = function
            alias_name = var_name
        return alias_name

    def __update_aliases(self, 
                         node_name:str,
                         nodes:Dict[str, MaxTerm], 
                         output_name:str,
                         outputs:Dict[str, MaxTerm], 
                         aliases:Dict[str, MaxTerm]):
        """
        Creates an alias for the function of the current node, if no other alias covers this node. 
        Otherwise, all references are updated.
        """
        # unroll function for alias
        alias = SymbolicDelay.Expand(*nodes[node_name], aliases=aliases)
        # check if alias is covered by other alias
        for other_output in aliases:
            other_alias = aliases[other_output]
            # terms of different length cannot be compatible
            if len(other_alias) != len(alias):
                continue
            distance = SymbolicDelay.Distance(other_alias, alias)
            if distance is None: # not a multiple
                continue
            if distance >= 0:
                # link to other alias
                function = [SymbolicDelay(other_output, distance)]
                outputs[output_name] = function
                # update output of this node
                nodes[node_name]     = function
                return
            # other alias is multiple of this alias
            print(f"WARN: alias '{output_name}' is covered by '{other_output}' (distance: {distance})!")
            # update old alias
            outputs[other_output] = [SymbolicDelay(output_name, -distance)]
            del aliases[other_output]
            # update all references to old alias
            for n in nodes:
                for var in nodes[n]:
                    if var.name == other_output:
                        print(f"WARN: -> updated '{n}'!")
                        var.name   = output_name
                        var.delay += -distance
            break
        # save new alias
        aliases[output_name] = alias
        # update output of this node to alias
        nodes[node_name]     = [SymbolicDelay(output_name)]
            
    def __variable_name(self, edge:Edge, prefix:str=""):
        """
        Generates a unique but simplified variable for the given edge.
        """
        var_name = prefix
        if edge.isDynamic():
            var_name += edge.name
        elif edge.timingVariable.getNumElements() == 1:
            var_name += edge.timingVariable.name
        else:
            var_name += f"{edge.timingVariable.name}[{edge.depth}]"
        return self.__simplify_variable_name(var_name)

    def __simplify_variable_name(self, var_name:str):
        """
        Simplifies the variable name but gurantees that the variable is unique.
        """
        new_name =  var_name.lower() \
            .replace(" (xa)", "") \
            .replace(" (xb)", "") \
            .replace(" (xd)", "") \
            .replace(" (cb_out)", "_cb_out") \
            .replace(" (cb_in)", "_cb_in") \
            .replace("_stage", "") \
            .replace("_substage", "_sub") \
            .replace("model", "")
        assert new_name not in self._variable_names or self._variable_names[new_name] == var_name, \
               f"generated duplicate variable name! ('{new_name}' from '{var_name}' clashes with '{self._variable_names[new_name]}')"
        self._variable_names[new_name] = var_name
        return new_name

    @staticmethod
    def function_to_str(function:MaxTerm, indent=0, word_wrap_at=150):
        """
        Generates a nicely readable function.
        """
        text = str(function)[1:-1] # remove brackets
        lines = []
        while len(text) > word_wrap_at:
            try:
                idx  = text.index(", ", word_wrap_at)
                idx += 2
            except ValueError:
                break
            lines += [text[:idx]]
            text   = text[idx:]
        lines += [text]
        return f"\n{" " * (indent)}".join(lines)

    @staticmethod
    def print_function(name:str, function:MaxTerm, indent=0):
        """
        Prints the node and its function in a standardized manner. Used for stdout
        """
        function_str = DelayGraph.function_to_str(function, indent=20 + 9)
        print(f"{" " * indent}> {name.ljust(20 - indent)} = max({function_str})")